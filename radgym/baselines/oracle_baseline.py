"""
Oracle rules-engine baseline.

This is one of v0.1's seven reference baselines and the one the
leaderboard floor sits on. It does NOT call an LLM — it applies
`radgym.oracle.apply_fleischner_2017` directly to each case and wraps
the deterministic result in a valid `AgentResponse`.

External review item #9: the oracle produces an `OracleResult` dataclass,
but the leaderboard expects a JSON-serializable `AgentResponse`. This
module is the thin adapter that converts one to the other so the
rules engine ships as a first-class entry.

Properties:

  - Free to run (no API calls, no token cost).
  - Strictly deterministic — same input always produces same output.
  - Score should be ~100 on a clean test set (any deviation is a
    methodology bug, not a baseline weakness).
  - Uses the case's `maintainer_assigned_risk` from GroundTruth via
    `risk_override` when running for scoring — see `score_with_risk_override`.
    For "blind" scoring without ground truth (e.g. dev-set exploration
    without labels), call `predict_unblinded` which derives risk from
    the heuristic in :func:`radgym.oracle.derive_risk`.

The oracle baseline is "unfair" in the sense that it has access to the
exact algorithm. That's intentional — it establishes the ceiling against
which actual learned/prompted agents are compared.
"""

from __future__ import annotations

from radgym.oracle import apply_fleischner_2017
from radgym.schemas import AgentResponse, Case, GroundTruth, Recommendation


BASELINE_NAME = "oracle_rules_engine"
BASELINE_DESCRIPTION = (
    "Deterministic Fleischner 2017 Table 1A/1B rules engine. "
    "Reference floor for the leaderboard; expected to score ~100 on a "
    "correctly-curated test set."
)


def predict_unblinded(case: Case) -> AgentResponse:
    """Run the oracle WITHOUT access to ground-truth risk.

    Uses :func:`radgym.oracle.derive_risk` (the conservative heuristic)
    for the risk classification. This is what the oracle baseline
    actually produces on the leaderboard — it does NOT get to peek at
    `GroundTruth.maintainer_assigned_risk`. The leaderboard score will
    reflect the heuristic's clinical incompleteness (e.g., age not used).

    This is the honest oracle baseline: it knows the algorithm but
    has to derive risk from individual factors like an agent would.
    """
    result = apply_fleischner_2017(case)
    return _to_agent_response(case, result)


def predict_blinded_to_truth(case: Case, truth: GroundTruth) -> AgentResponse:
    """Run the oracle WITH the maintainer's risk override.

    DO NOT use this for leaderboard scoring — it's for methodology
    diagnostics only. The leaderboard's oracle baseline runs
    :func:`predict_unblinded`.

    This variant exists so the curation/audit tooling can compute "what
    the oracle would say if it had the maintainer's risk synthesis" — a
    useful debugging artifact when investigating oracle/ground-truth
    disagreements during curation. It is NOT shipped as a leaderboard
    entry; the name reflects that it's blinded TO the truth (i.e. it's
    *consulting* the truth, the opposite of blind).
    """
    result = apply_fleischner_2017(
        case, risk_override=truth.maintainer_assigned_risk
    )
    return _to_agent_response(case, result)


def _to_agent_response(case: Case, result) -> AgentResponse:  # type: ignore[no-untyped-def]
    """Convert an OracleResult to a valid AgentResponse.

    For single-nodule cases the oracle's `recommendation` is the bin
    directly; `dominant_nodule_recommendation` is None.

    For multiple-nodule cases the oracle returns
    `recommendation=MULTIPLE_NODULE_DOMINANT` with the actual Table 1
    multiple-row bin in `dominant_nodule_recommendation` — which is
    exactly the shape `AgentResponse` requires (see schemas.py and
    METHODOLOGY §3.4).
    """
    return AgentResponse(
        case_id=case.case_id,
        recommendation=result.recommendation,
        dominant_nodule_recommendation=result.dominant_nodule_recommendation,
        rationale=result.reasoning,
    )


def metadata() -> dict[str, str]:
    """Baseline metadata for the leaderboard."""
    return {
        "submission_name": BASELINE_NAME,
        "submitter": "radgym-maintainer",
        "model_identifier": "radgym-oracle-fleischner-2017",
        "model_provider": "custom",
        "system_prompt": "(no LLM — deterministic rules engine)",
        "user_prompt_template": "(no LLM — deterministic rules engine)",
        "decoding_temperature": "0.0",
        "decoding_top_p": "1.0",
        "decoding_max_tokens": "0",
        "submitter_provided_api_key": "false",
        "notes": BASELINE_DESCRIPTION,
    }


__all__ = [
    "BASELINE_NAME",
    "BASELINE_DESCRIPTION",
    "predict_unblinded",
    "predict_blinded_to_truth",
    "metadata",
]
