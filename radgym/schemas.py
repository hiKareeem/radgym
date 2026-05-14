"""
RadGym v0.1 schemas — Fleischner 2017 pulmonary nodule follow-up track.

Strict Pydantic v2 schemas for case input, agent output, and ground-truth labels.
The schemas are the contract between case curators, the oracle, baseline agents,
and external submissions. Any change to these schemas is a breaking change.

See docs/METHODOLOGY.md §1.2-§1.3 for the human-readable spec.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Recommendation bins — the canonical v0.1 ordered list.
#
# Order matters: it defines "adjacency" for scoring. Index 0 is least
# aggressive follow-up; higher indices are more aggressive. See
# scoring/score.py for how adjacency is consumed.
#
# v0.2 will split BIN_SUBSOLID_WORKUP into separate GGN (q2y to 5y) and
# part-solid (annual to 5y) bins. For v0.1 they share a bin and the
# specific interval is expected in the agent's rationale field.
# ---------------------------------------------------------------------------


class Recommendation(str, Enum):
    """Canonical v0.1 Fleischner follow-up recommendation bins.

    Ordering (declaration order = adjacency order, least → most aggressive):
        1. NO_ROUTINE_FOLLOWUP
        2. OPTIONAL_CT_12MO
        3. CT_6_12MO_THEN_18_24MO_IF_STABLE
        4. CT_3_6MO_THEN_18_24MO
        5. SUBSOLID_WORKUP        (GGN ≥6mm OR part-solid ≥6mm — see module docstring)
        6. CONSIDER_PET_OR_BIOPSY
        7. MULTIPLE_NODULE_DOMINANT
    """

    NO_ROUTINE_FOLLOWUP = "no_routine_followup"
    OPTIONAL_CT_12MO = "optional_ct_12mo"
    CT_6_12MO_THEN_18_24MO_IF_STABLE = "ct_6_12mo_then_18_24mo_if_stable"
    CT_3_6MO_THEN_18_24MO = "ct_3_6mo_then_18_24mo"
    SUBSOLID_WORKUP = "subsolid_workup"
    CONSIDER_PET_OR_BIOPSY = "consider_pet_or_biopsy"
    MULTIPLE_NODULE_DOMINANT = "multiple_nodule_dominant"


# ---------------------------------------------------------------------------
# Adjacency tracks for scoring
#
# Critical fix from external review: SUBSOLID_WORKUP is NOT on the same
# 1-D severity axis as the solid-track bins. Sub-solid follow-up exists
# on a parallel track. A single linear ordering would make
# "recommend SUBSOLID_WORKUP on a solid 8mm case" look like a 1-bin miss
# (adjacent_safe, +0.50) when it's actually a track-type error and
# should score wrong_unsafe (-0.50).
#
# Two intra-track axes are defined here. Cross-track recommendations
# are scored as wrong_unsafe by scoring._classify_against_truth().
# NO_ROUTINE_FOLLOWUP and CONSIDER_PET_OR_BIOPSY appear on both
# tracks — they are the shared floor and ceiling.
# ---------------------------------------------------------------------------

SOLID_TRACK_ORDER: tuple[Recommendation, ...] = (
    Recommendation.NO_ROUTINE_FOLLOWUP,
    Recommendation.OPTIONAL_CT_12MO,
    Recommendation.CT_6_12MO_THEN_18_24MO_IF_STABLE,
    Recommendation.CT_3_6MO_THEN_18_24MO,
    Recommendation.CONSIDER_PET_OR_BIOPSY,
)

SUBSOLID_TRACK_ORDER: tuple[Recommendation, ...] = (
    Recommendation.NO_ROUTINE_FOLLOWUP,
    Recommendation.SUBSOLID_WORKUP,
    Recommendation.CONSIDER_PET_OR_BIOPSY,
)

# Bins that only appear on the solid track.
SOLID_ONLY: frozenset[Recommendation] = frozenset(
    {
        Recommendation.OPTIONAL_CT_12MO,
        Recommendation.CT_6_12MO_THEN_18_24MO_IF_STABLE,
        Recommendation.CT_3_6MO_THEN_18_24MO,
    }
)

# Bins that only appear on the sub-solid track.
SUBSOLID_ONLY: frozenset[Recommendation] = frozenset(
    {Recommendation.SUBSOLID_WORKUP}
)

# Backwards-compat alias — DEPRECATED, do not use in new code.
# Kept so anyone consuming the old import gets a runtime error pointing
# at the new track-aware API instead of a silently-wrong adjacency calc.
RECOMMENDATION_ORDER = SOLID_TRACK_ORDER + (Recommendation.SUBSOLID_WORKUP,)
# MULTIPLE_NODULE_DOMINANT is special-cased and not on any linear axis.


# ---------------------------------------------------------------------------
# Input schema (the case)
# ---------------------------------------------------------------------------


NoduleType = Literal["solid", "sub_solid_ground_glass", "sub_solid_part_solid"]
Multiplicity = Literal["single", "multiple"]
Morphology = Literal["smooth", "lobulated", "spiculated", "unspecified"]
Location = Literal[
    "upper_lobe", "middle_lobe", "lower_lobe", "lingula", "unspecified"
]
SmokingHistory = Literal["never", "former", "current", "unknown"]


class AdditionalNodule(BaseModel):
    """A non-dominant nodule in a multiple-nodule case."""

    model_config = ConfigDict(extra="forbid")

    type: NoduleType
    size_mm: float = Field(gt=0, le=50)
    morphology: Morphology = "unspecified"
    location: Location = "unspecified"


class Nodule(BaseModel):
    """The dominant (or only) nodule. Long-axis size in mm."""

    model_config = ConfigDict(extra="forbid")

    type: NoduleType
    size_mm: float = Field(gt=0, le=50, description="Long-axis diameter in mm.")
    multiplicity: Multiplicity
    morphology: Morphology = "unspecified"
    location: Location = "unspecified"
    additional_nodules: list[AdditionalNodule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _multiplicity_consistency(self) -> "Nodule":
        if self.multiplicity == "single" and self.additional_nodules:
            raise ValueError(
                "additional_nodules must be empty when multiplicity='single'"
            )
        if self.multiplicity == "multiple" and not self.additional_nodules:
            raise ValueError(
                "additional_nodules must list ≥1 entry when multiplicity='multiple'"
            )
        return self


class Patient(BaseModel):
    """Patient risk-factor encoding. v0.1 exposes individual factors so the
    agent must derive low/high risk — see METHODOLOGY §1.2 / open question 2.
    """

    model_config = ConfigDict(extra="forbid")

    age: int = Field(ge=35, le=120, description="Fleischner 2017 applies to ≥35y.")
    smoking_history: SmokingHistory
    pack_years: float | None = Field(default=None, ge=0, le=200)
    asbestos_exposure: bool = False
    family_history_lung_ca: bool = False
    emphysema: bool = False
    pulmonary_fibrosis: bool = False
    # The following two, if True, mean Fleischner 2017 does NOT apply.
    # Cases with either flag True are excluded from the v0.1 test set;
    # the fields exist so parsers detect mis-included cases loudly.
    known_primary_cancer: bool = False
    immunocompromised: bool = False


class Case(BaseModel):
    """One v0.1 RadGym case. The full input given to a submitted agent."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^RGYM-v01-\d{4}$")
    presentation: str = Field(min_length=10, max_length=2000)
    nodule: Nodule
    patient: Patient
    context: str = Field(min_length=0, max_length=2000)

    @model_validator(mode="after")
    def _exclude_out_of_scope(self) -> "Case":
        if self.patient.known_primary_cancer:
            raise ValueError(
                f"{self.case_id}: known_primary_cancer=True is out of Fleischner 2017 scope"
            )
        if self.patient.immunocompromised:
            raise ValueError(
                f"{self.case_id}: immunocompromised=True is out of Fleischner 2017 scope"
            )
        return self


# ---------------------------------------------------------------------------
# Output schema (the agent's answer)
# ---------------------------------------------------------------------------


class AgentResponse(BaseModel):
    """The structured output an agent must produce per case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^RGYM-v01-\d{4}$")
    recommendation: Recommendation
    rationale: str = Field(
        min_length=0,
        max_length=4000,
        description=(
            "Free-text reasoning. Collected in v0.1 but not scored — will be "
            "RadFact-graded in v0.2. Agents are encouraged to include the "
            "specific follow-up interval here, especially for SUBSOLID_WORKUP "
            "where GGN vs part-solid intervals differ."
        ),
    )
    # For MULTIPLE_NODULE_DOMINANT cases, the agent must also specify the
    # bin that the dominant nodule alone would receive. Required only when
    # recommendation == MULTIPLE_NODULE_DOMINANT.
    dominant_nodule_recommendation: Recommendation | None = None

    @model_validator(mode="after")
    def _multiple_requires_dominant(self) -> "AgentResponse":
        if (
            self.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT
            and self.dominant_nodule_recommendation is None
        ):
            raise ValueError(
                "dominant_nodule_recommendation is required when "
                "recommendation=MULTIPLE_NODULE_DOMINANT"
            )
        if (
            self.recommendation != Recommendation.MULTIPLE_NODULE_DOMINANT
            and self.dominant_nodule_recommendation is not None
        ):
            raise ValueError(
                "dominant_nodule_recommendation must be null unless "
                "recommendation=MULTIPLE_NODULE_DOMINANT"
            )
        return self


# ---------------------------------------------------------------------------
# Ground-truth label schema (kept alongside cases; never sent to agents)
# ---------------------------------------------------------------------------


class GroundTruth(BaseModel):
    """The maintainer-reviewed correct answer for a case."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^RGYM-v01-\d{4}$")
    recommendation: Recommendation
    dominant_nodule_recommendation: Recommendation | None = None
    source: str = Field(
        description=(
            "Origin of the case: 'fleischner_2017_example', 'radiopaedia:<url>', "
            "'openi:<id>', 'radiology_assistant:<url>', or "
            "'synthetic_maintainer_authored'."
        )
    )
    notes: str = Field(
        default="",
        max_length=2000,
        description="Maintainer notes: ambiguity flags, edge-case rationale, etc.",
    )

    @model_validator(mode="after")
    def _dominant_consistency(self) -> "GroundTruth":
        if (
            self.recommendation == Recommendation.MULTIPLE_NODULE_DOMINANT
            and self.dominant_nodule_recommendation is None
        ):
            raise ValueError(
                "dominant_nodule_recommendation is required when "
                "recommendation=MULTIPLE_NODULE_DOMINANT"
            )
        return self


class CaseRecord(BaseModel):
    """A case + its ground truth. The on-disk format in cases/v0.1/."""

    model_config = ConfigDict(extra="forbid")

    case: Case
    ground_truth: GroundTruth

    @model_validator(mode="after")
    def _ids_match(self) -> "CaseRecord":
        if self.case.case_id != self.ground_truth.case_id:
            raise ValueError(
                f"case_id mismatch: case={self.case.case_id} "
                f"ground_truth={self.ground_truth.case_id}"
            )
        return self
