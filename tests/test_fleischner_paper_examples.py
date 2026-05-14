"""
Fleischner 2017 worked-examples release gate.

External review item #9: before v0.1 ships, the oracle must round-trip
through every worked example in MacMahon H et al. 2017 with 100%
accuracy. This file is the gate.

Process:
    1. Maintainer reads the Fleischner 2017 paper (linked in METHODOLOGY §1.1).
    2. For each worked example in the paper (Table 1, figures, body
       discussion), add a CASE entry below with the exact features as
       described in the paper and the recommendation the paper explicitly
       gives.
    3. CI runs this file. Any disagreement between the oracle and the
       paper's stated answer fails the test — and ships nothing.

The maintainer can fill these in incrementally while curating; v0.1 will
not be marked launch-ready until this list has ≥10 examples and all pass.

NOTE: The clinical content here is factual (algorithm output for a
specified input) and not copyrightable. The case `presentation` text
is rewritten to avoid verbatim copying from the paper.
"""

from __future__ import annotations

import pytest

from radgym.oracle import apply_fleischner_2017
from radgym.schemas import Case, Nodule, Patient, Recommendation


# Each entry: (case_id_suffix, Case, expected_recommendation, paper_citation)
# paper_citation: page number or table/figure ref in MacMahon 2017 for the
# maintainer's audit trail. NOT shown to agents.

FLEISCHNER_PAPER_EXAMPLES: list[tuple[str, Case, Recommendation, str]] = [
    # ----- Maintainer: fill these in from the Fleischner 2017 paper as -----
    # ----- you curate. Each entry must come straight from the paper. -----
    # Example skeleton (uncomment and fill):
    # (
    #     "single_solid_lt6mm_low_risk",
    #     Case(
    #         case_id="RGYM-v01-9001",  # 9000-range reserved for paper examples
    #         presentation="(rewritten from paper) ...",
    #         nodule=Nodule(
    #             type="solid",
    #             size_mm=4,
    #             multiplicity="single",
    #             morphology="smooth",
    #             location="upper_lobe",
    #         ),
    #         patient=Patient(
    #             age=55,
    #             smoking_history="never",
    #         ),
    #         context="",
    #     ),
    #     Recommendation.NO_ROUTINE_FOLLOWUP,
    #     "Table 1, row 1: single solid <6mm low risk → no routine F/U",
    # ),
]


@pytest.mark.skipif(
    not FLEISCHNER_PAPER_EXAMPLES,
    reason="Maintainer has not yet added Fleischner paper examples — v0.1 launch gate.",
)
@pytest.mark.parametrize(
    "name,case,expected,citation", FLEISCHNER_PAPER_EXAMPLES, ids=lambda x: x if isinstance(x, str) else ""
)
def test_oracle_matches_paper_example(
    name: str, case: Case, expected: Recommendation, citation: str
) -> None:
    """Oracle must agree with the Fleischner 2017 paper for every worked example."""
    result = apply_fleischner_2017(case)
    assert result.recommendation == expected, (
        f"\n  Paper example '{name}' ({citation})"
        f"\n  Paper says: {expected.value}"
        f"\n  Oracle says: {result.recommendation.value}"
        f"\n  Oracle reasoning: {result.reasoning}"
    )


def test_paper_examples_count_for_launch_gate() -> None:
    """v0.1 launch requires ≥10 Fleischner-paper examples encoded here.

    This test PASSES until launch (so CI is green during development) but
    its message is a reminder. Promoted to a hard failure before tagging v0.1.0.
    """
    n = len(FLEISCHNER_PAPER_EXAMPLES)
    if n < 10:
        pytest.skip(
            f"Launch gate: {n}/10 Fleischner paper examples encoded. "
            "Add more in tests/test_fleischner_paper_examples.py before tagging v0.1.0."
        )
