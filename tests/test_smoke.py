"""Smoke tests — make sure schemas, oracle, and scoring agree on the sample case."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from radgym.oracle import apply_fleischner_2017, derive_risk
from radgym.schemas import AgentResponse, CaseRecord, Recommendation
from radgym.scoring import aggregate, score_case


CASES_DIR = Path(__file__).resolve().parents[1] / "cases" / "v0.1" / "dev"


def _load_records() -> list[CaseRecord]:
    records = []
    for path in sorted(CASES_DIR.glob("RGYM-v01-*.json")):
        records.append(CaseRecord.model_validate_json(path.read_text()))
    return records


def test_dev_cases_load() -> None:
    """All dev cases parse against the schema."""
    records = _load_records()
    assert records, "expected at least one dev case"


def test_oracle_matches_ground_truth_on_dev_cases() -> None:
    """Oracle must agree with maintainer-curated ground truth for every dev case.

    This is the curation safety check: if the oracle disagrees with a
    maintainer-written label, that case is either mis-labeled or the
    oracle is wrong. Either way it must not enter the test set.
    """
    records = _load_records()
    disagreements = []
    for rec in records:
        result = apply_fleischner_2017(rec.case)
        if result.recommendation != rec.ground_truth.recommendation:
            disagreements.append(
                (rec.case.case_id, result.recommendation, rec.ground_truth.recommendation)
            )
    assert not disagreements, f"oracle/ground-truth disagreements: {disagreements}"


def test_risk_derivation_table() -> None:
    """A table of risk-derivation expectations."""
    from radgym.schemas import Patient

    def patient(**kwargs) -> Patient:
        defaults = dict(
            age=60,
            smoking_history="never",
            pack_years=None,
            asbestos_exposure=False,
            family_history_lung_ca=False,
            emphysema=False,
            pulmonary_fibrosis=False,
            known_primary_cancer=False,
            immunocompromised=False,
        )
        defaults.update(kwargs)
        return Patient(**defaults)

    assert derive_risk(patient()) == "low"
    assert derive_risk(patient(smoking_history="never", asbestos_exposure=True)) == "high"
    assert derive_risk(patient(smoking_history="former")) == "high"
    assert derive_risk(patient(smoking_history="current")) == "high"
    assert derive_risk(patient(family_history_lung_ca=True)) == "high"
    assert derive_risk(patient(emphysema=True)) == "high"
    assert derive_risk(patient(pulmonary_fibrosis=True)) == "high"


@pytest.mark.parametrize(
    "size_mm,smoking,expected",
    [
        # <6 mm, low risk: NO_ROUTINE_FOLLOWUP
        (5, "never", Recommendation.NO_ROUTINE_FOLLOWUP),
        # <6 mm, high risk: OPTIONAL_CT_12MO
        (5, "former", Recommendation.OPTIONAL_CT_12MO),
        # 6-8 mm, low risk: CT_6_12MO_THEN_18_24MO_IF_STABLE
        (7, "never", Recommendation.CT_6_12MO_THEN_18_24MO_IF_STABLE),
        # 6-8 mm, high risk: CT_3_6MO_THEN_18_24MO
        (7, "current", Recommendation.CT_3_6MO_THEN_18_24MO),
        # >8 mm, low risk: CT_3_6MO_THEN_18_24MO
        (10, "never", Recommendation.CT_3_6MO_THEN_18_24MO),
        # >8 mm, high risk: CONSIDER_PET_OR_BIOPSY
        (10, "current", Recommendation.CONSIDER_PET_OR_BIOPSY),
    ],
)
def test_solid_nodule_table(size_mm: float, smoking: str, expected: Recommendation) -> None:
    """Spot-check the solid-nodule decision table."""
    from radgym.schemas import Case, Nodule, Patient

    case = Case(
        case_id="RGYM-v01-9999",
        presentation="Test case (table-driven).",
        nodule=Nodule(
            type="solid",
            size_mm=size_mm,
            multiplicity="single",
            morphology="smooth",
            location="upper_lobe",
        ),
        patient=Patient(
            age=60,
            smoking_history=smoking,
            pack_years=20 if smoking != "never" else None,
        ),
        context="",
    )
    result = apply_fleischner_2017(case)
    assert result.recommendation == expected


def test_scoring_round_trip_correct() -> None:
    """Agent that nails the ground truth scores +1.00 per case."""
    records = _load_records()
    scores = []
    for rec in records:
        resp = AgentResponse(
            case_id=rec.case.case_id,
            recommendation=rec.ground_truth.recommendation,
            rationale="oracle baseline",
            dominant_nodule_recommendation=rec.ground_truth.dominant_nodule_recommendation,
        )
        scores.append(score_case(resp, rec.ground_truth))
    assert all(s.points == 1.00 for s in scores)
    agg = aggregate(scores)
    assert agg.composite == 100.0
    assert agg.exact_accuracy == 1.0
    assert agg.under_following_rate == 0.0
    assert agg.malformed_rate == 0.0
    assert agg.rankable


def test_scoring_under_following_penalized_more_than_over() -> None:
    """Asymmetric scoring: under-following is worse than over-following.

    Use within-track bins so the test reflects intra-track adjacency, not
    cross-track. CT_6_12MO → CT_3_6MO is one step more aggressive on the
    solid track (safe); CT_3_6MO → CT_6_12MO is one step less aggressive
    (unsafe).
    """
    from radgym.schemas import GroundTruth

    truth = GroundTruth(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.CT_3_6MO_THEN_18_24MO,
        source="synthetic_maintainer_authored",
    )
    safe_response = AgentResponse(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.CONSIDER_PET_OR_BIOPSY,  # one step more aggressive on solid track
        rationale="over-following by one bin",
    )
    unsafe_response = AgentResponse(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.CT_6_12MO_THEN_18_24MO_IF_STABLE,  # one step less aggressive
        rationale="under-following by one bin",
    )
    safe_score = score_case(safe_response, truth)
    unsafe_score = score_case(unsafe_response, truth)
    assert safe_score.outcome == "adjacent_safe"
    assert unsafe_score.outcome == "adjacent_unsafe"
    assert safe_score.points > unsafe_score.points
    assert unsafe_score.points < 0


def test_cross_track_recommendation_scores_wrong_unsafe() -> None:
    """SUBSOLID_WORKUP on a solid-nodule case is a track-type error.

    External review item #1: this used to score adjacent_safe under
    the old single-axis ordering, which is wrong. It must score
    cross_track (-0.50, same magnitude as wrong_unsafe).
    """
    from radgym.schemas import GroundTruth

    truth = GroundTruth(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.CT_3_6MO_THEN_18_24MO,  # solid track
        source="synthetic_maintainer_authored",
    )
    wrong_track_response = AgentResponse(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.SUBSOLID_WORKUP,  # subsolid track
        rationale="wrong follow-up type",
    )
    score = score_case(wrong_track_response, truth)
    assert score.outcome == "cross_track"
    assert score.points == -0.50


def test_cross_track_reverse_direction() -> None:
    """Solid-track bin on a subsolid case is also cross-track."""
    from radgym.schemas import GroundTruth

    truth = GroundTruth(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.SUBSOLID_WORKUP,  # subsolid track
        source="synthetic_maintainer_authored",
    )
    wrong_track_response = AgentResponse(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.OPTIONAL_CT_12MO,  # solid track
        rationale="wrong follow-up type",
    )
    score = score_case(wrong_track_response, truth)
    assert score.outcome == "cross_track"


def test_shared_bins_not_cross_track() -> None:
    """NO_ROUTINE_FOLLOWUP and CONSIDER_PET_OR_BIOPSY appear on both tracks.

    A recommendation of NO_ROUTINE_FOLLOWUP when truth is SUBSOLID_WORKUP
    is under-following on the subsolid track — NOT cross-track.
    """
    from radgym.schemas import GroundTruth

    truth = GroundTruth(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.SUBSOLID_WORKUP,
        source="synthetic_maintainer_authored",
    )
    shared_floor_response = AgentResponse(
        case_id="RGYM-v01-0001",
        recommendation=Recommendation.NO_ROUTINE_FOLLOWUP,
        rationale="under-following on subsolid track",
    )
    score = score_case(shared_floor_response, truth)
    assert score.outcome == "adjacent_unsafe"
    assert score.points == -0.25


def test_public_leaderboard_view_omits_per_case() -> None:
    """External review item #13: external submitters get aggregates only.

    The public view must not contain per-case outcomes (label-leak vector).
    """
    from radgym.scoring import CaseScore, aggregate, public_leaderboard_view

    scores = [CaseScore(f"RGYM-v01-{i:04d}", "correct", 1.0) for i in range(10)]
    agg = aggregate(scores)
    view = public_leaderboard_view(agg)
    assert "per_case" not in view
    assert "composite" in view
    assert "cross_track_rate" in view  # exposed as a separate aggregate metric


def test_malformed_rate_gate() -> None:
    """A submission with malformed_rate > 10% is not rankable."""
    from radgym.scoring import CaseScore

    scores = [CaseScore(f"RGYM-v01-{i:04d}", "correct", 1.0) for i in range(80)]
    scores += [
        CaseScore(f"RGYM-v01-{i:04d}", "malformed", 0.0) for i in range(80, 100)
    ]
    agg = aggregate(scores)
    assert agg.malformed_rate == 0.20
    assert not agg.rankable
