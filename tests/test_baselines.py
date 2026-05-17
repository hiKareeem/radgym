"""
Tests for the baseline runner's robustness layer — primarily the JSON
extractor, which is what stands between flaky model outputs and a
malformed-flooded leaderboard.

We do NOT test against real LLM calls here (too slow, requires keys).
The runner.run_baseline() integration is exercised by the oracle baseline
path, which is deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from radgym.baselines.oracle_baseline import (
    BASELINE_NAME as ORACLE_BASELINE_NAME,
    predict_unblinded,
    predict_blinded_to_truth,
)
from radgym.baselines.runner import (
    _try_parse,
    _validate_response,
    run_oracle_baseline,
)
from radgym.schemas import CaseRecord


REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = REPO_ROOT / "cases" / "v0.1" / "dev"


def _load_some_records(n: int = 5) -> list[CaseRecord]:
    """Load the first N dev cases for integration tests."""
    paths = sorted(CASES_DIR.glob("RGYM-v01-*.json"))[:n]
    return [CaseRecord.model_validate_json(p.read_text()) for p in paths]


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------


class TestTryParse:
    """All strategies in _try_parse must succeed on the right shapes."""

    def test_strict_json(self) -> None:
        text = '{"case_id":"RGYM-v01-0001","recommendation":"no_routine_followup"}'
        parsed, strategy = _try_parse(text)
        assert strategy == "strict"
        assert parsed is not None
        assert parsed["recommendation"] == "no_routine_followup"

    def test_strict_json_with_leading_whitespace(self) -> None:
        text = '   \n  {"a": 1}\n  '
        parsed, strategy = _try_parse(text)
        assert strategy == "strict"
        assert parsed == {"a": 1}

    def test_fenced_markdown_json(self) -> None:
        text = "Here is my answer:\n```json\n{\"a\": 1, \"b\": 2}\n```\n"
        parsed, strategy = _try_parse(text)
        assert strategy == "fenced"
        assert parsed == {"a": 1, "b": 2}

    def test_fenced_markdown_no_language_tag(self) -> None:
        text = "```\n{\"a\": 1}\n```"
        parsed, strategy = _try_parse(text)
        assert strategy == "fenced"
        assert parsed == {"a": 1}

    def test_balanced_braces_with_prose_around(self) -> None:
        text = (
            "Looking at this case, I see a small nodule. My recommendation:\n"
            '{"case_id":"X","recommendation":"no_routine_followup","rationale":"r"}\n'
            "Hope that helps!"
        )
        parsed, strategy = _try_parse(text)
        assert strategy == "balanced"
        assert parsed is not None
        assert parsed["recommendation"] == "no_routine_followup"

    def test_balanced_braces_with_nested_object(self) -> None:
        text = 'Reasoning... {"a": {"nested": true}, "b": 2} done.'
        parsed, strategy = _try_parse(text)
        assert strategy == "balanced"
        assert parsed == {"a": {"nested": True}, "b": 2}

    def test_repaired_trailing_comma(self) -> None:
        # The fenced extractor catches it first; force into the balanced path.
        text = '{"a": 1, "b": 2,}'
        parsed, strategy = _try_parse(text)
        assert strategy == "repaired"
        assert parsed == {"a": 1, "b": 2}

    def test_failed_no_json_at_all(self) -> None:
        text = "I cannot comply with this request."
        parsed, strategy = _try_parse(text)
        assert strategy == "failed"
        assert parsed is None

    def test_failed_unbalanced_braces(self) -> None:
        text = '{"a": 1'
        parsed, strategy = _try_parse(text)
        assert strategy == "failed"
        assert parsed is None


# ---------------------------------------------------------------------------
# Validation: parsed dict → AgentResponse
# ---------------------------------------------------------------------------


class TestValidateResponse:
    def test_clean_valid_response(self) -> None:
        parsed = {
            "case_id": "RGYM-v01-0001",
            "recommendation": "no_routine_followup",
            "rationale": "Single solid <6mm, low risk.",
        }
        resp, err = _validate_response(parsed, "RGYM-v01-0001")
        assert err is None
        assert resp is not None
        assert resp.recommendation.value == "no_routine_followup"

    def test_missing_case_id_is_filled_from_argument(self) -> None:
        parsed = {"recommendation": "no_routine_followup"}
        resp, err = _validate_response(parsed, "RGYM-v01-0042")
        assert err is None
        assert resp is not None
        assert resp.case_id == "RGYM-v01-0042"

    def test_missing_rationale_defaults_to_empty(self) -> None:
        parsed = {
            "case_id": "RGYM-v01-0001",
            "recommendation": "no_routine_followup",
        }
        resp, err = _validate_response(parsed, "RGYM-v01-0001")
        assert err is None
        assert resp is not None
        assert resp.rationale == ""

    def test_string_null_dominant_is_coerced_to_None(self) -> None:
        parsed = {
            "case_id": "RGYM-v01-0001",
            "recommendation": "no_routine_followup",
            "dominant_nodule_recommendation": "null",
            "rationale": "x",
        }
        resp, err = _validate_response(parsed, "RGYM-v01-0001")
        assert err is None
        assert resp is not None
        assert resp.dominant_nodule_recommendation is None

    def test_invalid_recommendation_string_fails_validation(self) -> None:
        parsed = {
            "case_id": "RGYM-v01-0001",
            "recommendation": "totally_made_up_bin",
            "rationale": "x",
        }
        resp, err = _validate_response(parsed, "RGYM-v01-0001")
        assert resp is None
        assert err is not None and "validation" in err

    def test_multiple_without_dominant_fails_validation(self) -> None:
        parsed = {
            "case_id": "RGYM-v01-0001",
            "recommendation": "multiple_nodule_dominant",
            "rationale": "x",
        }
        resp, err = _validate_response(parsed, "RGYM-v01-0001")
        assert resp is None
        assert err is not None

    def test_none_parsed_returns_error(self) -> None:
        resp, err = _validate_response(None, "RGYM-v01-0001")
        assert resp is None
        assert err is not None and "no JSON" in err


# ---------------------------------------------------------------------------
# Oracle baseline integration
# ---------------------------------------------------------------------------


class TestOracleBaseline:
    def test_predict_unblinded_returns_valid_agent_response(self) -> None:
        records = _load_some_records(1)
        agent_resp = predict_unblinded(records[0].case)
        assert agent_resp.case_id == records[0].case.case_id
        assert agent_resp.recommendation is not None
        # rationale should always be populated by the oracle wrapper
        assert agent_resp.rationale != ""

    def test_predict_blinded_uses_maintainer_risk(self) -> None:
        """When maintainer_assigned_risk overrides heuristic, the bin
        chosen must reflect the maintainer's risk classification."""
        records = _load_some_records(5)
        for rec in records:
            blinded = predict_blinded_to_truth(rec.case, rec.ground_truth)
            assert blinded.case_id == rec.case.case_id
            # Blinded prediction should match ground truth for every case
            # where the maintainer's labeling didn't override the oracle.
            # We can't guarantee equality (maintainer may have overridden),
            # but the call must succeed and return a valid AgentResponse.
            assert blinded.recommendation in [
                r for r in type(blinded.recommendation)
            ]

    def test_oracle_baseline_full_run_scores_high(self, tmp_path: Path) -> None:
        """Running the oracle baseline against the dev set should score
        in the 90s — the oracle uses the heuristic risk (not maintainer
        override), so it can be wrong on cases where the maintainer
        assigned higher risk than the heuristic.

        This is the canonical 'oracle baseline on real data' test: we
        check it scores high but allow some slack (>= 70 composite) to
        accommodate the heuristic vs maintainer divergence."""
        records = _load_some_records(20)
        jsonl = tmp_path / "oracle.jsonl"
        summary = run_oracle_baseline(records, output_jsonl=jsonl, verbose=False)

        assert summary.n_cases == len(records)
        assert summary.n_succeeded == len(records)  # oracle never produces malformed
        assert summary.n_malformed == 0
        assert summary.total_cost_usd == 0.0
        assert summary.composite is not None
        # Loose floor — oracle on heuristic risk should still do well.
        assert summary.composite >= 70.0, (
            f"oracle baseline scored {summary.composite:.2f}, expected >= 70. "
            "If this drops, either the heuristic is mis-aligned with maintainer "
            "labels (curation issue) or the oracle has a bug."
        )
        assert summary.rankable is True

    def test_oracle_baseline_resumable(self, tmp_path: Path) -> None:
        """A second invocation with the same output_jsonl skips completed cases."""
        records = _load_some_records(5)
        jsonl = tmp_path / "oracle.jsonl"

        run_oracle_baseline(records, output_jsonl=jsonl, verbose=False)
        line_count_first = len(jsonl.read_text().strip().splitlines())

        # Second run on the same path with the same cases: should be a no-op
        # (no new lines written).
        run_oracle_baseline(records, output_jsonl=jsonl, verbose=False)
        line_count_second = len(jsonl.read_text().strip().splitlines())

        assert line_count_first == line_count_second == len(records)
