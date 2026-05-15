"""
Fleischner 2017 oracle — deterministic rules-engine.

This module is THREE things at once:

  1. The **answer key** for scoring. Ground-truth labels in `cases/v0.1/`
     are reviewed by the maintainer (radiology background) but
     ``apply_fleischner_2017()`` is the algorithmic check that catches
     human curation errors before a case enters the test set.

  2. A **reference baseline** submitted to the public leaderboard as
     "rules-engine". Indie hackers compete *against* this floor.

  3. The **executable spec** of v0.1's bin definitions. If you want to
     know what `CT_3_6MO_THEN_18_24MO` means in concrete decision terms,
     read this file rather than METHODOLOGY.md — the markdown is for
     humans, this is for machines.

Source: MacMahon H et al., "Guidelines for Management of Incidental
Pulmonary Nodules Detected on CT Images: From the Fleischner Society
2017." Radiology 2017;284(1):228-243. doi:10.1148/radiol.2017161659

KNOWN v0.1 SIMPLIFICATION (will be split in v0.2):
    The SUBSOLID_WORKUP bin currently merges:
      - Ground-glass nodule (GGN) ≥6mm:   CT 6-12mo, then q2y to 5y
      - Part-solid nodule ≥6mm:           CT 3-6mo, then annual to 5y
    These differ in interval. v0.1 scoring treats them as one bin and
    expects the specific interval in the agent's rationale field. The
    `intent` returned alongside the bin disambiguates for v0.2 migration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from radgym.schemas import Case, Nodule, Patient, Recommendation


# ---------------------------------------------------------------------------
# Risk derivation
# ---------------------------------------------------------------------------
#
# Fleischner 2017 uses a binary "low risk" vs "high risk" patient
# classification. The guideline defines high risk as: history of smoking
# OR other known risk factors (asbestos exposure, family history of lung
# cancer, emphysema, pulmonary fibrosis, older age in combination with
# above).
#
# This function encodes a conservative reading: any of the listed risk
# factors → high risk. Pure age is NOT used as a sole trigger (Fleischner
# does not specify an age threshold for "high risk" independent of other
# factors). Current or former smokers are high-risk.
#
# The v0.1 cases are curated against this derivation; any disagreement
# between this function and the maintainer's clinical judgment is a
# curation bug to be resolved before the case ships.

RiskCategory = Literal["low", "high"]


def derive_risk(patient: Patient) -> RiskCategory:
    """Return Fleischner risk category from individual patient factors."""
    if patient.smoking_history in ("current", "former"):
        return "high"
    if patient.asbestos_exposure:
        return "high"
    if patient.family_history_lung_ca:
        return "high"
    if patient.emphysema:
        return "high"
    if patient.pulmonary_fibrosis:
        return "high"
    return "low"


# ---------------------------------------------------------------------------
# Sub-solid intent — preserved for v0.2 split
# ---------------------------------------------------------------------------


SubsolidIntent = Literal["ggn_q2y_to_5y", "part_solid_annual_to_5y", "not_applicable"]


@dataclass(frozen=True)
class OracleResult:
    """The oracle's verdict on a case.

    Attributes
    ----------
    recommendation
        The v0.1 bin.
    dominant_nodule_recommendation
        Set only when ``recommendation == MULTIPLE_NODULE_DOMINANT``;
        the bin the dominant nodule alone would receive.
    risk_category
        The derived patient risk (for debugging / case review).
    subsolid_intent
        Disambiguates the v0.1 SUBSOLID_WORKUP merged bin so v0.2 can
        split cleanly. ``"not_applicable"`` for non-subsolid cases.
    reasoning
        Plain-English trace of the rule path taken. Useful for case
        review and for the rules-engine baseline's rationale field.
    """

    recommendation: Recommendation
    dominant_nodule_recommendation: Recommendation | None
    risk_category: RiskCategory
    subsolid_intent: SubsolidIntent
    reasoning: str


# ---------------------------------------------------------------------------
# Single-nodule rules
# ---------------------------------------------------------------------------


def _classify_single_solid(size_mm: float, risk: RiskCategory) -> tuple[Recommendation, str]:
    """Fleischner 2017 Table 1A, single solid nodule rules.

    Verbatim from Table 1A:

    +----------+-----------+------------------------------------------------------+
    | Size     | Risk      | Recommendation                                       |
    +----------+-----------+------------------------------------------------------+
    | <6 mm    | low       | No routine follow-up                                 |
    | <6 mm    | high      | Optional CT at 12 months                             |
    | 6-8 mm   | low       | CT 6-12 mo, then consider CT 18-24 mo                |
    | 6-8 mm   | high      | CT 6-12 mo, then CT 18-24 mo  ← SAME interval as low |
    | >8 mm    | low       | Consider CT 3 mo, PET/CT, or tissue sampling         |
    | >8 mm    | high      | Consider CT 3 mo, PET/CT, or tissue sampling         |
    +----------+-----------+------------------------------------------------------+

    Note: 2005 Fleischner guidelines had distinct intervals for high-risk
    6-8mm (CT at 3-6mo, then 9-12mo and 24mo) — the 2017 update simplified
    this to a single 6-12mo / 18-24mo recommendation for both risk
    categories at 6-8mm. The previous oracle version conflated the
    two guidelines; this is the 2017 reading.
    """
    if size_mm < 6:
        if risk == "low":
            return (
                Recommendation.NO_ROUTINE_FOLLOWUP,
                f"Single solid nodule {size_mm} mm <6mm, low risk → no routine follow-up. (Table 1A)",
            )
        return (
            Recommendation.OPTIONAL_CT_12MO,
            f"Single solid nodule {size_mm} mm <6mm, high risk → optional CT at 12 months. (Table 1A)",
        )
    if size_mm <= 8:
        # Per Fleischner 2017 Table 1A: BOTH low- and high-risk 6-8mm route
        # to CT 6-12mo then 18-24mo. (2005 guideline split them; 2017 unified.)
        return (
            Recommendation.CT_6_12MO_THEN_18_24MO_IF_STABLE,
            f"Single solid nodule {size_mm} mm (6-8mm), {risk} risk → CT 6-12 mo, then 18-24 mo. (Table 1A)",
        )
    # >8 mm — both low and high risk route to PET/biopsy consideration.
    return (
        Recommendation.CONSIDER_PET_OR_BIOPSY,
        f"Single solid nodule {size_mm} mm >8mm, {risk} risk → consider CT 3 mo, PET/CT, or tissue sampling. (Table 1A)",
    )


def _classify_multiple_solid(
    size_mm: float, risk: RiskCategory
) -> tuple[Recommendation, str]:
    """Fleischner 2017 Table 1A, MULTIPLE solid nodule rules.

    Verbatim from Table 1A. Multiple-nodule rules are NOT the same as
    single-nodule rules — the dominant nodule's individual rule does not
    apply. Table 1A specifies its own multiple-row recommendations:

    +----------+-----------+----------------------------------------------+
    | Size     | Risk      | Recommendation                                |
    +----------+-----------+----------------------------------------------+
    | <6 mm    | low       | No routine follow-up                          |
    | <6 mm    | high      | Optional CT at 12 months                      |
    | 6-8 mm   | low       | CT 3-6 mo, then consider CT 18-24 mo          |
    | 6-8 mm   | high      | CT 3-6 mo, then CT 18-24 mo                   |
    | >8 mm    | low       | CT 3-6 mo, then consider CT 18-24 mo          |
    | >8 mm    | high      | CT 3-6 mo, then CT 18-24 mo                   |
    +----------+-----------+----------------------------------------------+

    Note that multiple-nodule cases never route to CONSIDER_PET_OR_BIOPSY
    in Table 1A — even >8mm multiples get the CT 3-6mo workup pathway.
    The Comments column says "Use most suspicious nodule as guide to
    management. Follow-up intervals may vary according to size and risk"
    — so the multiple-rule output is the *case-level* recommendation;
    individual nodule workup decisions remain the radiologist's judgment.
    """
    size_band = "lt6" if size_mm < 6 else ("6_8" if size_mm <= 8 else "gt8")

    if size_band == "lt6":
        if risk == "low":
            return (
                Recommendation.NO_ROUTINE_FOLLOWUP,
                f"Multiple solid nodules, dominant {size_mm} mm <6mm, low risk → no routine follow-up. (Table 1A multiple-row)",
            )
        return (
            Recommendation.OPTIONAL_CT_12MO,
            f"Multiple solid nodules, dominant {size_mm} mm <6mm, high risk → optional CT at 12 months. (Table 1A multiple-row)",
        )
    # 6-8mm OR >8mm, regardless of risk → CT 3-6mo then 18-24mo
    return (
        Recommendation.CT_3_6MO_THEN_18_24MO,
        f"Multiple solid nodules, dominant {size_mm} mm ({size_band}), {risk} risk → CT 3-6 mo, then 18-24 mo. (Table 1A multiple-row)",
    )


def _classify_single_subsolid(
    nodule: Nodule, risk: RiskCategory
) -> tuple[Recommendation, SubsolidIntent, str]:
    """Fleischner 2017 Table 1B, SINGLE subsolid nodule rules.

    Ground-glass nodule (GGN), single:
      - <6 mm  → no routine follow-up
      - ≥6 mm  → CT 6-12 mo, then q2y to 5y               [SUBSOLID_WORKUP / ggn_q2y_to_5y]

    Part-solid nodule, single:
      - <6 mm  → no routine follow-up
      - ≥6 mm  → CT 3-6 mo, then annual to 5y              [SUBSOLID_WORKUP / part_solid_annual_to_5y]
      - solid component ≥6 mm with concerning features → PET/biopsy
        (v0.1 does not collect solid-component size separately; that
         path is reserved for v0.2.)

    Risk category does NOT modify subsolid recommendations in Fleischner
    2017 (subsolid nodules are managed by size + density only).
    """
    size = nodule.size_mm
    if nodule.type == "sub_solid_ground_glass":
        if size < 6:
            return (
                Recommendation.NO_ROUTINE_FOLLOWUP,
                "not_applicable",
                f"Single GGN {size} mm <6 mm → no routine follow-up. (Table 1B)",
            )
        return (
            Recommendation.SUBSOLID_WORKUP,
            "ggn_q2y_to_5y",
            f"Single GGN {size} mm ≥6 mm → CT 6-12 mo, then q2y to 5 years. (Table 1B)",
        )
    # part-solid
    if size < 6:
        return (
            Recommendation.NO_ROUTINE_FOLLOWUP,
            "not_applicable",
            f"Single part-solid nodule {size} mm <6 mm → no routine follow-up. (Table 1B)",
        )
    return (
        Recommendation.SUBSOLID_WORKUP,
        "part_solid_annual_to_5y",
        f"Single part-solid nodule {size} mm ≥6 mm → CT 3-6 mo, then annual to 5 years. (Table 1B)",
    )


def _classify_multiple_subsolid(
    size_mm: float,
) -> tuple[Recommendation, SubsolidIntent, str]:
    """Fleischner 2017 Table 1B, MULTIPLE subsolid nodule rules.

    Table 1B "Multiple" row (does not distinguish GGN from part-solid):

    +----------+----------------------------------------------------------+
    | Size     | Recommendation                                            |
    +----------+----------------------------------------------------------+
    | <6 mm    | CT 3-6 mo. If stable, consider CT at 2 and 4 years.       |
    | ≥6 mm    | CT 3-6 mo. Subsequent management based on most suspicious |
    +----------+----------------------------------------------------------+

    Both rows are MORE aggressive than the single-nodule subsolid rule
    for the same size (single <6mm = no follow-up; multiple <6mm = CT 3-6mo).
    Both map to SUBSOLID_WORKUP in v0.1's bin set — the specific
    interval distinction is captured in the rationale, not the bin.
    Risk category does not modify subsolid follow-up.
    """
    if size_mm < 6:
        return (
            Recommendation.SUBSOLID_WORKUP,
            "ggn_q2y_to_5y",  # closest match for the q2y/4y interval
            f"Multiple subsolid nodules, dominant {size_mm} mm <6 mm → CT 3-6 mo, then CT 2 and 4 yr. (Table 1B multiple-row)",
        )
    return (
        Recommendation.SUBSOLID_WORKUP,
        "ggn_q2y_to_5y",  # most-suspicious-guides — defaulting to longer interval
        f"Multiple subsolid nodules, dominant {size_mm} mm ≥6 mm → CT 3-6 mo, then per most suspicious. (Table 1B multiple-row)",
    )


# ---------------------------------------------------------------------------
# Multiple-nodule rules
# ---------------------------------------------------------------------------
#
# Per Fleischner 2017, for multiple nodules the recommendation is keyed
# to the most suspicious (largest/highest-risk-features) nodule. v0.1
# encodes this as the dedicated MULTIPLE_NODULE_DOMINANT bin and
# additionally reports what the dominant nodule alone would receive.


def _dominant_nodule(nodule: Nodule) -> Nodule:
    """Return the dominant (largest) nodule from a multiple-nodule case.

    Tie-breaking (Fleischner 2017 does not strictly specify, common
    practice): larger size > sub-solid > part-solid > solid for
    suspicion. v0.1 implementation: largest size wins; on tie, the more
    suspicious morphology wins (spiculated > lobulated > smooth >
    unspecified); on further tie, the dominant declared in `nodule`
    field wins.
    """
    if nodule.multiplicity == "single":
        return nodule

    morphology_rank = {
        "spiculated": 3,
        "lobulated": 2,
        "smooth": 1,
        "unspecified": 0,
    }

    candidates = [
        (
            nodule.size_mm,
            morphology_rank[nodule.morphology],
            0,  # the originally-declared dominant gets index 0
            "declared",
            Nodule(
                type=nodule.type,
                size_mm=nodule.size_mm,
                multiplicity="single",
                morphology=nodule.morphology,
                location=nodule.location,
            ),
        )
    ]
    for i, extra in enumerate(nodule.additional_nodules, start=1):
        candidates.append(
            (
                extra.size_mm,
                morphology_rank[extra.morphology],
                i,
                "additional",
                Nodule(
                    type=extra.type,
                    size_mm=extra.size_mm,
                    multiplicity="single",
                    morphology=extra.morphology,
                    location=extra.location,
                ),
            )
        )

    # Sort: largest size first, then most suspicious morphology, then
    # declared-dominant ahead of additionals (stable).
    candidates.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return candidates[0][4]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_fleischner_2017(
    case: Case, *, risk_override: RiskCategory | None = None
) -> OracleResult:
    """Apply the Fleischner 2017 algorithm to a case.

    Returns an OracleResult containing the v0.1 bin, the dominant-nodule
    bin (for multiple-nodule cases), the derived risk category, the
    sub-solid intent (for v0.2 migration), and a plain-English trace.

    Parameters
    ----------
    case
        The case to evaluate.
    risk_override
        If provided, use this risk category instead of the heuristic
        :func:`derive_risk`. Used by the Table 1 launch-gate test and by
        the case authoring tool when the maintainer's clinical judgment
        differs from the heuristic — see schemas.GroundTruth's
        ``maintainer_assigned_risk`` field for the rationale.

    Raises
    ------
    ValueError
        If the case falls outside Fleischner 2017 scope (this should be
        impossible because :class:`radgym.schemas.Case` validates the
        scope flags at construction time).
    """
    nodule = case.nodule
    risk: RiskCategory = risk_override if risk_override is not None else derive_risk(case.patient)

    if nodule.multiplicity == "single":
        if nodule.type == "solid":
            rec, trace = _classify_single_solid(nodule.size_mm, risk)
            return OracleResult(
                recommendation=rec,
                dominant_nodule_recommendation=None,
                risk_category=risk,
                subsolid_intent="not_applicable",
                reasoning=trace,
            )
        rec, intent, trace = _classify_single_subsolid(nodule, risk)
        return OracleResult(
            recommendation=rec,
            dominant_nodule_recommendation=None,
            risk_category=risk,
            subsolid_intent=intent,
            reasoning=trace,
        )

    # Multiple nodules — Fleischner 2017 Table 1A/1B "Multiple" rows.
    # The case-level recommendation comes from the multiple-rules table
    # (NOT from the dominant nodule's single-rules row). We surface this
    # as MULTIPLE_NODULE_DOMINANT at the top level (the case-shape
    # indicator) and put the actual multiple-rule recommendation into
    # the dominant_nodule_recommendation field — which is what v0.1's
    # scoring compares against ground-truth (METHODOLOGY §3.4).
    dominant = _dominant_nodule(nodule)

    case_level_intent: SubsolidIntent
    if dominant.type == "solid":
        case_level_rec, case_level_trace = _classify_multiple_solid(
            dominant.size_mm, risk
        )
        case_level_intent = "not_applicable"
    else:
        case_level_rec, case_level_intent, case_level_trace = (
            _classify_multiple_subsolid(dominant.size_mm)
        )

    trace = (
        f"Multiple nodules ({1 + len(nodule.additional_nodules)} total). "
        f"Dominant: {dominant.type} {dominant.size_mm} mm. "
        f"{case_level_trace}"
    )
    return OracleResult(
        recommendation=Recommendation.MULTIPLE_NODULE_DOMINANT,
        dominant_nodule_recommendation=case_level_rec,
        risk_category=risk,
        subsolid_intent=case_level_intent,
        reasoning=trace,
    )
