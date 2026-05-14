"""
v0.1 scoring — asymmetric, adjacency-aware, safety-weighted, track-aware.

See METHODOLOGY.md §3 for the human-readable spec. The function in this
module is the *single source of truth* for how a submission becomes a
score. Any change here is a methodology change and must be versioned
(scoring_version field on the leaderboard).

Scoring summary (v0.1):

    Per-case outcome -> points
    --------------------------
    correct                                +1.00
    adjacent_safe   (over-following by 1)  +0.50
    adjacent_unsafe (under-following by 1) -0.25
    wrong_safe      (over-following ≥2)     0.00
    wrong_unsafe    (under-following ≥2)   -0.50
    cross_track     (track-type error)     -0.50  (same as wrong_unsafe)
    malformed                               0.00

Composite = 100 * mean(per-case points).

CRITICAL: Adjacency is computed WITHIN A TRACK. Solid-track bins
(NO_ROUTINE_FOLLOWUP → OPTIONAL_CT_12MO → CT_6_12MO_THEN_18_24MO_IF_STABLE
→ CT_3_6MO_THEN_18_24MO → CONSIDER_PET_OR_BIOPSY) and sub-solid-track
bins (NO_ROUTINE_FOLLOWUP → SUBSOLID_WORKUP → CONSIDER_PET_OR_BIOPSY)
are scored independently. A cross-track recommendation (e.g.,
SUBSOLID_WORKUP on a solid-nodule case, or OPTIONAL_CT_12MO on a
sub-solid case) scores cross_track, which is treated as wrong_unsafe —
the agent picked the wrong *kind* of follow-up, not the wrong interval.

The MULTIPLE_NODULE_DOMINANT bin is special-cased: when the ground
truth is MULTIPLE_NODULE_DOMINANT, the agent must also predict
MULTIPLE_NODULE_DOMINANT for an exact-match (+1.00); additionally, the
agent's ``dominant_nodule_recommendation`` is scored on the
appropriate intra-track axis and contributes up to 0.25 of partial
credit. Details in :func:`score_case` docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from radgym.schemas import (
    SOLID_ONLY,
    SOLID_TRACK_ORDER,
    SUBSOLID_ONLY,
    SUBSOLID_TRACK_ORDER,
    AgentResponse,
    GroundTruth,
    Recommendation,
)


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


Outcome = Literal[
    "correct",
    "adjacent_safe",
    "adjacent_unsafe",
    "wrong_safe",
    "wrong_unsafe",
    "cross_track",
    "malformed",
    "multiple_correct_full",
    "multiple_correct_partial",
    "multiple_wrong",
]

# Points table — the single source of truth.
POINTS: dict[Outcome, float] = {
    "correct": 1.00,
    "adjacent_safe": 0.50,
    "adjacent_unsafe": -0.25,
    "wrong_safe": 0.00,
    "wrong_unsafe": -0.50,
    "cross_track": -0.50,  # treated same as wrong_unsafe: wrong kind of follow-up
    "malformed": 0.00,
    # Multiple-nodule outcomes:
    "multiple_correct_full": 1.00,
    "multiple_correct_partial": 0.25,  # base partial; actual value scaled in _score_multiple
    "multiple_wrong": 0.00,
}


# ---------------------------------------------------------------------------
# Track identification
# ---------------------------------------------------------------------------


def _track_of(rec: Recommendation) -> Literal["solid", "subsolid", "shared", "multiple"]:
    """Which adjacency track a recommendation belongs to.

    'shared' means the bin appears on both tracks (the floor and ceiling).
    'multiple' is the MULTIPLE_NODULE_DOMINANT special case.
    """
    if rec == Recommendation.MULTIPLE_NODULE_DOMINANT:
        return "multiple"
    if rec in SOLID_ONLY:
        return "solid"
    if rec in SUBSOLID_ONLY:
        return "subsolid"
    return "shared"  # NO_ROUTINE_FOLLOWUP, CONSIDER_PET_OR_BIOPSY


def _is_cross_track(predicted: Recommendation, truth: Recommendation) -> bool:
    """True if predicted and truth are on incompatible tracks.

    Cross-track means: predicted is solid-only AND truth is sub-solid-only,
    or vice versa. Shared bins never trigger cross-track (they're valid on
    both tracks).
    """
    p_track = _track_of(predicted)
    t_track = _track_of(truth)
    if p_track == "solid" and t_track == "subsolid":
        return True
    if p_track == "subsolid" and t_track == "solid":
        return True
    return False


# ---------------------------------------------------------------------------
# Intra-track adjacency
# ---------------------------------------------------------------------------


def _track_for_pair(
    predicted: Recommendation, truth: Recommendation
) -> tuple[Recommendation, ...] | None:
    """Pick the appropriate track ordering for an (predicted, truth) pair.

    Returns the track tuple that contains both recommendations, or None
    if no single track contains both (which means it's a cross-track
    error — caller should have detected that first).
    """
    if predicted in SOLID_TRACK_ORDER and truth in SOLID_TRACK_ORDER:
        return SOLID_TRACK_ORDER
    if predicted in SUBSOLID_TRACK_ORDER and truth in SUBSOLID_TRACK_ORDER:
        return SUBSOLID_TRACK_ORDER
    return None


def _classify_against_truth(
    predicted: Recommendation, truth: Recommendation
) -> Outcome:
    """Classify a prediction against truth.

    Handles cross-track explicitly. Within a track, computes signed delta:
    positive = predicted is more aggressive (over-following, safe direction)
    negative = predicted is less aggressive (under-following, unsafe direction)

    Both inputs must NOT be MULTIPLE_NODULE_DOMINANT — the caller routes
    that to :func:`_score_multiple`.
    """
    if predicted == truth:
        return "correct"

    if _is_cross_track(predicted, truth):
        return "cross_track"

    track = _track_for_pair(predicted, truth)
    if track is None:
        # Both 'shared' bins (NO_ROUTINE_FOLLOWUP vs CONSIDER_PET_OR_BIOPSY)
        # — score on the solid track since it covers both.
        track = SOLID_TRACK_ORDER

    p_idx = track.index(predicted)
    t_idx = track.index(truth)
    delta = p_idx - t_idx  # positive = predicted more aggressive (safe direction)

    if delta == 1:
        return "adjacent_safe"
    if delta == -1:
        return "adjacent_unsafe"
    if delta > 1:
        return "wrong_safe"
    return "wrong_unsafe"


# ---------------------------------------------------------------------------
# Multiple-nodule scoring
# ---------------------------------------------------------------------------


def _score_multiple(
    response: AgentResponse, truth: GroundTruth
) -> tuple[Outcome, float]:
    """Score a case whose ground truth is MULTIPLE_NODULE_DOMINANT.

    Three sub-cases:
      1. Agent picked MULTIPLE_NODULE_DOMINANT AND dominant sub-bin
         matches truth's dominant sub-bin → multiple_correct_full (1.00).
      2. Agent picked MULTIPLE_NODULE_DOMINANT but dominant sub-bin
         differs → partial credit scaled by adjacency of the sub-bin
         miss, using the same track-aware classifier.
      3. Agent did NOT pick MULTIPLE_NODULE_DOMINANT → score against
         the dominant sub-bin at half weight (the agent missed
         multiplicity recognition).
    """
    if response.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT:
        if response.dominant_nodule_recommendation == truth.dominant_nodule_recommendation:
            return "multiple_correct_full", POINTS["multiple_correct_full"]
        sub_outcome = _classify_against_truth(
            response.dominant_nodule_recommendation,  # type: ignore[arg-type]
            truth.dominant_nodule_recommendation,  # type: ignore[arg-type]
        )
        partial_table: dict[Outcome, float] = {
            "correct": 1.00,
            "adjacent_safe": 0.25,
            "adjacent_unsafe": -0.10,
            "wrong_safe": 0.00,
            "wrong_unsafe": -0.25,
            "cross_track": -0.25,
        }
        return "multiple_correct_partial", partial_table.get(sub_outcome, 0.0)

    # Agent didn't recognize multiplicity. Score against the dominant
    # sub-bin on the appropriate track; half weight as a recognition penalty.
    sub_outcome = _classify_against_truth(
        response.recommendation,
        truth.dominant_nodule_recommendation,  # type: ignore[arg-type]
    )
    half_points_table: dict[Outcome, float] = {
        "correct": 0.50,
        "adjacent_safe": 0.25,
        "adjacent_unsafe": -0.15,
        "wrong_safe": 0.00,
        "wrong_unsafe": -0.30,
        "cross_track": -0.30,
    }
    return "multiple_wrong", half_points_table.get(sub_outcome, 0.0)


# ---------------------------------------------------------------------------
# Public scoring API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseScore:
    """The score of a single case."""

    case_id: str
    outcome: Outcome
    points: float


def score_case(response: AgentResponse, truth: GroundTruth) -> CaseScore:
    """Score one agent response against ground truth.

    Returns
    -------
    CaseScore
        outcome + points. Does not raise on bin disagreement — produces
        an outcome label. Raises only on case_id mismatch (a caller bug).
    """
    if response.case_id != truth.case_id:
        raise ValueError(
            f"case_id mismatch: response={response.case_id} truth={truth.case_id}"
        )

    # Ground-truth MULTIPLE_NODULE_DOMINANT → special path.
    if truth.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT:
        outcome, points = _score_multiple(response, truth)
        return CaseScore(case_id=truth.case_id, outcome=outcome, points=points)

    # Agent hallucinated MULTIPLE_NODULE_DOMINANT on a single-nodule case.
    # Score using dominant_nodule_recommendation against the actual truth;
    # half credit reflects the recognition error.
    if response.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT:
        if response.dominant_nodule_recommendation is not None:
            outcome = _classify_against_truth(
                response.dominant_nodule_recommendation, truth.recommendation
            )
        else:
            outcome = "wrong_safe"
        return CaseScore(
            case_id=truth.case_id,
            outcome=outcome,
            points=POINTS[outcome] * 0.5,
        )

    outcome = _classify_against_truth(response.recommendation, truth.recommendation)
    return CaseScore(case_id=truth.case_id, outcome=outcome, points=POINTS[outcome])


@dataclass(frozen=True)
class SubmissionScore:
    """Aggregated scores over a full submission.

    NOTE: For v0.1, the public leaderboard returns ONLY aggregate scores
    to submitters — the ``per_case`` field is for internal use (oracle
    validation, baseline diagnostics) and is not exposed via the
    submission API. This prevents iterative label-probing attacks
    against the hidden test set. See METHODOLOGY §4.2.
    """

    composite: float  # 100 × mean(points)
    exact_accuracy: float  # fraction of `correct` or `multiple_correct_full`
    under_following_rate: float  # adjacent_unsafe + wrong_unsafe + cross_track
    over_following_rate: float  # adjacent_safe + wrong_safe
    cross_track_rate: float  # subset of under_following_rate, surfaced separately
    malformed_rate: float
    n_cases: int
    per_case: list[CaseScore]
    rankable: bool  # False if malformed_rate > 0.10


def aggregate(
    case_scores: list[CaseScore], n_total: int | None = None
) -> SubmissionScore:
    """Aggregate per-case scores into a submission-level summary.

    If ``n_total`` is provided and exceeds ``len(case_scores)``, missing
    cases are treated as malformed (no response received).
    """
    n_total = n_total if n_total is not None else len(case_scores)
    if n_total == 0:
        raise ValueError("Cannot aggregate over zero cases.")

    if len(case_scores) < n_total:
        missing = n_total - len(case_scores)
        case_scores = list(case_scores) + [
            CaseScore(case_id=f"<missing-{i}>", outcome="malformed", points=0.0)
            for i in range(missing)
        ]

    total_points = sum(c.points for c in case_scores)
    composite = 100.0 * total_points / n_total

    def frac(predicate) -> float:
        return sum(1 for c in case_scores if predicate(c)) / n_total

    exact_accuracy = frac(
        lambda c: c.outcome in ("correct", "multiple_correct_full")
    )
    under_following_rate = frac(
        lambda c: c.outcome in ("adjacent_unsafe", "wrong_unsafe", "cross_track")
    )
    over_following_rate = frac(
        lambda c: c.outcome in ("adjacent_safe", "wrong_safe")
    )
    cross_track_rate = frac(lambda c: c.outcome == "cross_track")
    malformed_rate = frac(lambda c: c.outcome == "malformed")

    return SubmissionScore(
        composite=composite,
        exact_accuracy=exact_accuracy,
        under_following_rate=under_following_rate,
        over_following_rate=over_following_rate,
        cross_track_rate=cross_track_rate,
        malformed_rate=malformed_rate,
        n_cases=n_total,
        per_case=case_scores,
        rankable=malformed_rate <= 0.10,
    )


def public_leaderboard_view(score: SubmissionScore) -> dict[str, float | int | bool]:
    """Return the aggregate-only view returned to external submitters.

    v0.1 deliberately omits per-case outcomes to prevent label-probing
    attacks (see external review item #13). Maintainer-only diagnostics
    use the full SubmissionScore.
    """
    return {
        "composite": round(score.composite, 2),
        "exact_accuracy": round(score.exact_accuracy, 4),
        "under_following_rate": round(score.under_following_rate, 4),
        "over_following_rate": round(score.over_following_rate, 4),
        "cross_track_rate": round(score.cross_track_rate, 4),
        "malformed_rate": round(score.malformed_rate, 4),
        "n_cases": score.n_cases,
        "rankable": score.rankable,
    }
