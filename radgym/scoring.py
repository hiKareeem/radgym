"""
v0.1 scoring — asymmetric, adjacency-aware, safety-weighted.

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
    malformed                               0.00

Composite = 100 * mean(per-case points).

The MULTIPLE_NODULE_DOMINANT bin is special-cased: when the ground
truth is MULTIPLE_NODULE_DOMINANT, the agent must also predict
MULTIPLE_NODULE_DOMINANT for an exact-match (+1.00); additionally, the
agent's ``dominant_nodule_recommendation`` is scored on the linear
adjacency axis and contributes 0.25 of partial credit at most. Details
in :func:`score_case` docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from radgym.schemas import AgentResponse, GroundTruth, RECOMMENDATION_ORDER, Recommendation


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


Outcome = Literal[
    "correct",
    "adjacent_safe",
    "adjacent_unsafe",
    "wrong_safe",
    "wrong_unsafe",
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
    "malformed": 0.00,
    # Multiple-nodule outcomes:
    # full credit when bin AND dominant sub-bin both correct
    "multiple_correct_full": 1.00,
    # partial credit when MULTIPLE_NODULE_DOMINANT picked but dominant
    # sub-bin off; magnitude of partial determined dynamically — see
    # _score_multiple()
    "multiple_correct_partial": 0.25,
    "multiple_wrong": 0.00,
}


# ---------------------------------------------------------------------------
# Scoring primitives
# ---------------------------------------------------------------------------


def _adjacency_index(rec: Recommendation) -> int | None:
    """Return position of `rec` on the linear adjacency axis, or None
    if `rec` is off-axis (MULTIPLE_NODULE_DOMINANT)."""
    try:
        return RECOMMENDATION_ORDER.index(rec)
    except ValueError:
        return None


def _classify_linear(
    predicted: Recommendation, truth: Recommendation
) -> Outcome:
    """Classify a prediction against truth on the linear bin axis.

    Both predicted and truth must be on the axis (not
    MULTIPLE_NODULE_DOMINANT). 'safe' direction means MORE aggressive
    follow-up than truth (over-following). 'unsafe' direction means
    LESS aggressive (under-following) — the clinically dangerous error.
    """
    p = _adjacency_index(predicted)
    t = _adjacency_index(truth)
    assert p is not None and t is not None, (
        "_classify_linear requires on-axis recommendations"
    )
    delta = p - t  # positive = predicted is more aggressive (safe direction)
    if delta == 0:
        return "correct"
    if delta == 1:
        return "adjacent_safe"
    if delta == -1:
        return "adjacent_unsafe"
    if delta > 1:
        return "wrong_safe"
    return "wrong_unsafe"


def _score_multiple(
    response: AgentResponse, truth: GroundTruth
) -> tuple[Outcome, float]:
    """Score a case whose ground truth is MULTIPLE_NODULE_DOMINANT.

    Three sub-cases:
      1. Agent picked MULTIPLE_NODULE_DOMINANT AND dominant sub-bin
         matches truth's dominant sub-bin → multiple_correct_full (1.00).
      2. Agent picked MULTIPLE_NODULE_DOMINANT but dominant sub-bin
         differs → partial credit scaled by adjacency of the sub-bin
         miss (multiple_correct_partial). Magnitude:
           - sub-bin off by 1 in safe direction: 0.25
           - sub-bin off by 1 in unsafe direction: -0.10
           - sub-bin off by ≥2: 0.00 if safe, -0.25 if unsafe.
      3. Agent did NOT pick MULTIPLE_NODULE_DOMINANT → fall back to
         linear scoring against the dominant sub-bin (treating the
         agent's recommendation as if it were the agent's best guess
         at the dominant). This catches agents that didn't recognize
         multiplicity but still produced a reasonable bin.
    """
    if response.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT:
        # Both should have dominant_nodule_recommendation set; schemas enforce this.
        if response.dominant_nodule_recommendation == truth.dominant_nodule_recommendation:
            return "multiple_correct_full", POINTS["multiple_correct_full"]
        # Sub-bin mismatch — scale partial credit by adjacency.
        sub_outcome = _classify_linear(
            response.dominant_nodule_recommendation,  # type: ignore[arg-type]
            truth.dominant_nodule_recommendation,  # type: ignore[arg-type]
        )
        partial_table = {
            "correct": 1.00,  # unreachable given the equality check above
            "adjacent_safe": 0.25,
            "adjacent_unsafe": -0.10,
            "wrong_safe": 0.00,
            "wrong_unsafe": -0.25,
        }
        return "multiple_correct_partial", partial_table[sub_outcome]

    # Agent didn't recognize multiplicity. Score against dominant sub-bin
    # on the linear axis; this is strictly worse than recognizing it.
    sub_outcome = _classify_linear(
        response.recommendation,
        truth.dominant_nodule_recommendation,  # type: ignore[arg-type]
    )
    # Map linear outcomes to "multiple_wrong" + scaled points (half
    # weight, since the agent missed the multiplicity recognition).
    half_points_table = {
        "correct": 0.50,
        "adjacent_safe": 0.25,
        "adjacent_unsafe": -0.15,
        "wrong_safe": 0.00,
        "wrong_unsafe": -0.30,
    }
    return "multiple_wrong", half_points_table[sub_outcome]


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

    # Linear axis path.
    # If the agent picked MULTIPLE_NODULE_DOMINANT but truth is single-nodule,
    # treat as "wrong" — they hallucinated multiplicity. Score against truth
    # using the agent's dominant_nodule_recommendation if available (their
    # best guess at the actual answer), otherwise just call it wrong_safe (no
    # safety harm but methodologically wrong).
    if response.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT:
        if response.dominant_nodule_recommendation is not None:
            outcome = _classify_linear(
                response.dominant_nodule_recommendation, truth.recommendation
            )
        else:
            outcome = "wrong_safe"
        return CaseScore(
            case_id=truth.case_id,
            outcome=outcome,
            points=POINTS[outcome] * 0.5,  # half credit for the recognition error
        )

    outcome = _classify_linear(response.recommendation, truth.recommendation)
    return CaseScore(case_id=truth.case_id, outcome=outcome, points=POINTS[outcome])


@dataclass(frozen=True)
class SubmissionScore:
    """Aggregated scores over a full submission."""

    composite: float  # 100 × mean(points)
    exact_accuracy: float  # fraction of `correct` or `multiple_correct_full`
    under_following_rate: float  # adjacent_unsafe + wrong_unsafe
    over_following_rate: float  # adjacent_safe + wrong_safe
    malformed_rate: float
    n_cases: int
    per_case: list[CaseScore]
    rankable: bool  # False if malformed_rate > 0.10

    def __post_init__(self) -> None:  # pragma: no cover - dataclass guard
        pass


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

    # Pad with malformed for any missing case.
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
        lambda c: c.outcome in ("adjacent_unsafe", "wrong_unsafe")
    )
    over_following_rate = frac(
        lambda c: c.outcome in ("adjacent_safe", "wrong_safe")
    )
    malformed_rate = frac(lambda c: c.outcome == "malformed")

    return SubmissionScore(
        composite=composite,
        exact_accuracy=exact_accuracy,
        under_following_rate=under_following_rate,
        over_following_rate=over_following_rate,
        malformed_rate=malformed_rate,
        n_cases=n_total,
        per_case=case_scores,
        rankable=malformed_rate <= 0.10,
    )
