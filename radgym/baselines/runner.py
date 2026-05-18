"""
LLM baseline runner for RadGym v0.1.

Executes a (model_identifier, system_prompt, user_prompt_template,
decoding_params) baseline against a set of cases, parses each response
into an AgentResponse, scores against ground truth (when available), and
writes per-case results to a JSONL log. Resumable: if interrupted, a
subsequent run skips cases already in the log.

Robustness:

  - Per-case retry with exponential backoff (3 attempts) via tenacity.
    Final failure → AgentResponse-equivalent "malformed" marker.
  - JSON extraction tries strict-parse → fenced-block → first-balanced-
    braces → looser repair, with the strategy used recorded.
  - `system_fingerprint` captured per case (where provider supplies one)
    per METHODOLOGY §3.6.
  - Per-case latency and token usage recorded.

The runner is intentionally simple to read end-to-end. It is also the
single source of truth for what "running a baseline" means — the HF
Space leaderboard will call into this same engine.

Usage (programmatic):

    from radgym.baselines.runner import BaselineConfig, run_baseline
    cfg = BaselineConfig(...)
    summary = run_baseline(cfg, case_records, output_jsonl="results.jsonl")

CLI: see scripts/run_baseline.py.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import ValidationError

from radgym.schemas import AgentResponse, CaseRecord, Recommendation
from radgym.scoring import CaseScore, aggregate, score_case


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


DEFAULT_SYSTEM_PROMPT = """\
You are a radiology decision-support assistant applying Fleischner Society \
2017 guidelines for incidental pulmonary nodule follow-up. You will be given \
a structured JSON case description. Apply the algorithm faithfully and respond \
with a single valid JSON object matching exactly this schema (no markdown \
fences, no surrounding prose):

{
  "case_id": "<echo the case_id verbatim>",
  "recommendation": "<one of: no_routine_followup, optional_ct_12mo, \
ct_6_12mo_then_18_24mo_if_stable, ct_3_6mo_then_18_24mo, subsolid_workup, \
consider_pet_or_biopsy, multiple_nodule_dominant>",
  "dominant_nodule_recommendation": "<bin ID, REQUIRED only if recommendation \
is multiple_nodule_dominant, otherwise omit or null>",
  "rationale": "<brief clinical reasoning, 1-3 sentences>"
}

Use the patient's risk factors (smoking, age, family history, asbestos, \
emphysema, fibrosis) to synthesize a Fleischner 'low risk' vs 'high risk' \
category. Multiple nodules use Table 1A/1B's multiple-row rules, not the \
dominant nodule's single-nodule rule.

Output JSON only.\
"""

DEFAULT_USER_PROMPT_TEMPLATE = "Case:\n{case_json}\n"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineConfig:
    """One baseline configuration."""

    name: str                                  # human-readable, e.g. "claude-sonnet-4-default"
    model_identifier: str                      # LiteLLM model string, e.g. "openai/gpt-4o-2024-11-20"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    user_prompt_template: str = DEFAULT_USER_PROMPT_TEMPLATE
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 800
    api_key_env: str | None = None             # env var name; None = LiteLLM default lookup
    notes: str = ""
    # Provider-specific extras passed straight through to litellm.completion().
    # Examples:
    #   {"thinking": {"type": "enabled", "budget_tokens": 1024}}  # Anthropic extended thinking
    #   {"reasoning_effort": "low"}                                # Gemini 2.5 reasoning budget
    # Default factory because frozen dataclass + mutable default is forbidden.
    extra_params: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, str]:
        return {
            "submission_name": self.name,
            "submitter": "radgym-maintainer",
            "model_identifier": self.model_identifier,
            "model_provider": _provider_of(self.model_identifier),
            "system_prompt": self.system_prompt,
            "user_prompt_template": self.user_prompt_template,
            "decoding_temperature": str(self.temperature),
            "decoding_top_p": str(self.top_p),
            "decoding_max_tokens": str(self.max_tokens),
            "submitter_provided_api_key": "false",
            "notes": self.notes,
        }


def _provider_of(model_id: str) -> str:
    """Best-effort provider identification from a LiteLLM model string."""
    if "/" in model_id:
        return model_id.split("/", 1)[0]
    if model_id.startswith(("gpt-", "o1-", "o3-")):
        return "openai"
    if model_id.startswith("claude-"):
        return "anthropic"
    if model_id.startswith("gemini-"):
        return "google"
    return "unknown"


# ---------------------------------------------------------------------------
# Per-case result record (one line of the JSONL log)
# ---------------------------------------------------------------------------


@dataclass
class CaseRunResult:
    """What we record for a single case after running the baseline.

    Stored as one JSON line in the run's output log. The log is
    append-only and resumable: on restart we skip case_ids that already
    have a CaseRunResult line.
    """

    case_id: str
    baseline_name: str
    # Either a parsed AgentResponse (dict) or None if malformed.
    response: dict[str, Any] | None
    parse_strategy: Literal["strict", "fenced", "balanced", "repaired", "failed"]
    raw_text: str                              # the model's raw output (truncated)
    score_outcome: str | None = None           # filled when ground truth available
    score_points: float | None = None
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    system_fingerprint: str | None = None      # METHODOLOGY §3.6
    error: str | None = None                   # only set on hard failure
    timestamp: float = field(default_factory=time.time)

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# JSON extraction (the agent reliability layer)
# ---------------------------------------------------------------------------


_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```",
    re.DOTALL,
)


def _try_parse(text: str) -> tuple[dict[str, Any] | None, str]:
    """Attempt to extract a JSON object from `text`.

    Returns (parsed_dict_or_None, strategy_name). Strategies in order:

        strict   — text is itself valid JSON
        fenced   — JSON wrapped in ```json ... ``` markdown
        balanced — first balanced {...} substring is valid JSON
        repaired — strip trailing commas; retry
        failed   — none of the above worked
    """
    text = text.strip()

    # 1. strict
    try:
        return json.loads(text), "strict"
    except json.JSONDecodeError:
        pass

    # 2. fenced markdown
    m = _FENCED_JSON_RE.search(text)
    if m:
        try:
            return json.loads(m.group(1)), "fenced"
        except json.JSONDecodeError:
            pass

    # 3. first balanced {...} block
    extracted = _extract_first_balanced_braces(text)
    if extracted is not None:
        try:
            return json.loads(extracted), "balanced"
        except json.JSONDecodeError:
            # 4. repair trailing commas and re-parse
            repaired = re.sub(r",(\s*[}\]])", r"\1", extracted)
            try:
                return json.loads(repaired), "repaired"
            except json.JSONDecodeError:
                pass

    return None, "failed"


def _extract_first_balanced_braces(text: str) -> str | None:
    """Return the first balanced {...} substring, or None if not found.

    Naive: walks the string counting brace depth. Does not understand
    strings (so a `{` inside a quoted string would mess it up), but
    agent JSON outputs in practice are flat enough that this works.
    """
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# ---------------------------------------------------------------------------
# Validation: parsed JSON → AgentResponse
# ---------------------------------------------------------------------------


def _validate_response(
    parsed: dict[str, Any] | None, case_id: str
) -> tuple[AgentResponse | None, str | None]:
    """Validate a parsed JSON dict against the AgentResponse schema.

    Returns (agent_response_or_None, error_message_or_None). Coerces
    obvious problems (string-typed recommendation values that match the
    enum, missing `dominant_nodule_recommendation` set to None when not
    needed) before validation.
    """
    if parsed is None:
        return None, "no JSON extracted from model output"

    # Coerce missing case_id to the expected one (some models forget to echo)
    parsed.setdefault("case_id", case_id)

    # Coerce rationale presence (schema requires the field; allow empty string)
    parsed.setdefault("rationale", "")

    # Some models emit dominant_nodule_recommendation as the literal string "null"
    if parsed.get("dominant_nodule_recommendation") in ("null", "None", ""):
        parsed["dominant_nodule_recommendation"] = None

    try:
        return AgentResponse(**parsed), None
    except ValidationError as e:
        return None, f"schema validation failed: {e.errors()[:3]}"
    except Exception as e:  # pragma: no cover - defensive
        return None, f"unexpected validation error: {e!r}"


# ---------------------------------------------------------------------------
# LLM call (delegates to LiteLLM)
# ---------------------------------------------------------------------------


def _call_llm(
    cfg: BaselineConfig, case_json: str, *, max_retries: int = 3
) -> dict[str, Any]:
    """Call the model via LiteLLM with retries.

    Returns a dict with: text, input_tokens, output_tokens, cost_usd,
    latency_ms, system_fingerprint. Raises on permanent failure (caller
    catches and records as malformed).
    """
    # Local import so module-level import works without litellm installed.
    import litellm  # type: ignore[import-not-found]
    from tenacity import (  # type: ignore[import-not-found]
        retry,
        stop_after_attempt,
        wait_exponential,
    )

    # Drop unsupported params silently rather than 400-ing out. Providers
    # increasingly reject specific params per-model (gpt-5.5-pro: top_p
    # not supported; gpt-5.5 / opus-4-7: temperature != 1; others
    # likely to follow). With drop_params=True, LiteLLM logs the drop
    # and proceeds with the remaining supported params. This is the
    # robust way to keep the runner working as providers tighten APIs.
    litellm.drop_params = True

    @retry(
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    def _one_call() -> Any:
        # Build kwargs explicitly so we can omit defaults that some
        # providers reject as deprecated/conflicting. As of 2026-05:
        #   - Anthropic Opus 4.7 rejects top_p outright.
        #   - Anthropic Sonnet 4.6 rejects (temperature AND top_p) together.
        #   - OpenAI gpt-5.5-pro rejects top_p.
        # litellm.drop_params=True does NOT catch these because LiteLLM's
        # allow-list is conservative. The robust play is to only forward
        # top_p when it's a non-default value (i.e. someone actually wants
        # nucleus sampling). Same conservatism for temperature on the
        # reasoning models (handled per-baseline in presets.py).
        call_kwargs: dict[str, Any] = {
            "model": cfg.model_identifier,
            "messages": [
                {"role": "system", "content": cfg.system_prompt},
                {
                    "role": "user",
                    "content": cfg.user_prompt_template.format(case_json=case_json),
                },
            ],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens,
            **cfg.extra_params,
        }
        # Only send top_p if the caller deliberately set something other
        # than the no-op default of 1.0.
        if cfg.top_p != 1.0:
            call_kwargs["top_p"] = cfg.top_p
        return litellm.completion(**call_kwargs)

    t0 = time.perf_counter()
    response = _one_call()
    latency_ms = int((time.perf_counter() - t0) * 1000)

    text = response.choices[0].message.content or ""

    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
    output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0

    # Cost via LiteLLM's helper (uses its model_cost map)
    try:
        cost_usd = float(litellm.completion_cost(completion_response=response) or 0.0)
    except Exception:
        cost_usd = 0.0

    return {
        "text": text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "system_fingerprint": getattr(response, "system_fingerprint", None),
    }


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


@dataclass
class RunSummary:
    """Result of running a baseline over a case set."""

    baseline_name: str
    n_cases: int
    n_succeeded: int
    n_malformed: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    composite: float | None              # None if no ground truth was available
    exact_accuracy: float | None
    under_following_rate: float | None
    over_following_rate: float | None
    cross_track_rate: float | None
    malformed_rate: float | None
    rankable: bool | None

    def pretty(self) -> str:  # pragma: no cover - presentational
        lines = [
            f"Baseline: {self.baseline_name}",
            f"  cases: {self.n_succeeded}/{self.n_cases} parsed "
            f"({self.n_malformed} malformed)",
            f"  cost:  ${self.total_cost_usd:.4f}  "
            f"({self.total_input_tokens} in / {self.total_output_tokens} out)",
        ]
        if self.composite is not None:
            lines.extend(
                [
                    f"  composite:           {self.composite:6.2f}",
                    f"  exact_accuracy:      {self.exact_accuracy:.3f}",
                    f"  under_following:     {self.under_following_rate:.3f}",
                    f"  over_following:      {self.over_following_rate:.3f}",
                    f"  cross_track:         {self.cross_track_rate:.3f}",
                    f"  malformed_rate:      {self.malformed_rate:.3f}",
                    f"  rankable:            {self.rankable}",
                ]
            )
        return "\n".join(lines)


def _load_completed_case_ids(jsonl_path: Path) -> set[str]:
    """Return the set of case_ids already present in the JSONL log."""
    if not jsonl_path.exists():
        return set()
    completed: set[str] = set()
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            completed.add(obj["case_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return completed


def run_baseline(
    cfg: BaselineConfig,
    records: Iterable[CaseRecord],
    *,
    output_jsonl: str | Path,
    score_with_truth: bool = True,
    verbose: bool = True,
) -> RunSummary:
    """Run a baseline over a set of CaseRecords.

    Parameters
    ----------
    cfg
        BaselineConfig describing the model and prompt.
    records
        Iterable of CaseRecord (case + ground truth). Order is preserved.
    output_jsonl
        Path to the per-case JSONL log. Created if missing; resumed if
        existing case_ids overlap with the input records.
    score_with_truth
        If True (default), each parsed response is scored against ground
        truth. If False, only the response is recorded (use when running
        against unlabeled cases).
    verbose
        Print per-case progress to stdout.

    Returns
    -------
    RunSummary
        Aggregate cost, token counts, and (if scored) composite metrics.
    """
    records_list = list(records)
    output_path = Path(output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed_ids = _load_completed_case_ids(output_path)
    to_run = [r for r in records_list if r.case.case_id not in completed_ids]

    if verbose:
        skipped = len(records_list) - len(to_run)
        print(
            f"[{cfg.name}] {len(records_list)} cases total; "
            f"{skipped} already in log, {len(to_run)} to run."
        )

    # Streaming JSONL append; flush after each case so a crash leaves a valid log.
    fh = output_path.open("a")
    case_scores: list[CaseScore] = []

    try:
        for i, rec in enumerate(to_run, start=1):
            case_id = rec.case.case_id
            case_json = rec.case.model_dump_json(indent=2)

            try:
                raw = _call_llm(cfg, case_json)
                text = raw["text"]
                parsed, strategy = _try_parse(text)
                agent_resp, err = _validate_response(parsed, case_id)

                result = CaseRunResult(
                    case_id=case_id,
                    baseline_name=cfg.name,
                    response=agent_resp.model_dump() if agent_resp else None,
                    parse_strategy=strategy if agent_resp else "failed",
                    raw_text=text[:2000],
                    latency_ms=raw["latency_ms"],
                    input_tokens=raw["input_tokens"],
                    output_tokens=raw["output_tokens"],
                    cost_usd=raw["cost_usd"],
                    system_fingerprint=raw["system_fingerprint"],
                    error=err,
                )

                if score_with_truth and agent_resp is not None:
                    cs = score_case(agent_resp, rec.ground_truth)
                    result.score_outcome = cs.outcome
                    result.score_points = cs.points
                    case_scores.append(cs)
                elif score_with_truth:
                    case_scores.append(
                        CaseScore(case_id=case_id, outcome="malformed", points=0.0)
                    )
                    result.score_outcome = "malformed"
                    result.score_points = 0.0

            except Exception as e:  # any hard failure → malformed for this case
                result = CaseRunResult(
                    case_id=case_id,
                    baseline_name=cfg.name,
                    response=None,
                    parse_strategy="failed",
                    raw_text="",
                    error=f"{type(e).__name__}: {e}",
                )
                if score_with_truth:
                    case_scores.append(
                        CaseScore(case_id=case_id, outcome="malformed", points=0.0)
                    )
                    result.score_outcome = "malformed"
                    result.score_points = 0.0

            fh.write(result.to_jsonl() + "\n")
            fh.flush()

            if verbose:
                tag = (
                    f"{result.score_outcome:18s} {result.score_points:+.2f}"
                    if result.score_outcome is not None
                    else "(unscored)"
                )
                print(
                    f"  [{i:3d}/{len(to_run)}] {case_id}  "
                    f"{tag}  "
                    f"parse={result.parse_strategy}  "
                    f"${result.cost_usd:.4f}"
                )
    finally:
        fh.close()

    # Re-load all scores from the JSONL (covers both fresh and resumed runs)
    all_scores = _rehydrate_scores(output_path) if score_with_truth else []
    totals = _summarize_log(output_path, cfg.name)

    if score_with_truth and all_scores:
        agg = aggregate(all_scores, n_total=len(records_list))
        composite: float | None = agg.composite
        exact = agg.exact_accuracy
        under = agg.under_following_rate
        over = agg.over_following_rate
        cross = agg.cross_track_rate
        malformed = agg.malformed_rate
        rankable: bool | None = agg.rankable
    else:
        composite = exact = under = over = cross = malformed = None
        rankable = None

    return RunSummary(
        baseline_name=cfg.name,
        n_cases=len(records_list),
        n_succeeded=totals["n_succeeded"],
        n_malformed=totals["n_malformed"],
        total_cost_usd=totals["total_cost_usd"],
        total_input_tokens=totals["total_input_tokens"],
        total_output_tokens=totals["total_output_tokens"],
        composite=composite,
        exact_accuracy=exact,
        under_following_rate=under,
        over_following_rate=over,
        cross_track_rate=cross,
        malformed_rate=malformed,
        rankable=rankable,
    )


def _rehydrate_scores(jsonl_path: Path) -> list[CaseScore]:
    """Re-read scores from a JSONL log for aggregation."""
    scores: list[CaseScore] = []
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("score_outcome") is not None:
            scores.append(
                CaseScore(
                    case_id=obj["case_id"],
                    outcome=obj["score_outcome"],
                    points=float(obj["score_points"]),
                )
            )
    return scores


def _summarize_log(jsonl_path: Path, baseline_name: str) -> dict[str, Any]:
    """Sum cost/tokens and count succeeded/malformed from a JSONL log."""
    n_succ = 0
    n_mal = 0
    cost = 0.0
    in_tok = 0
    out_tok = 0
    for line in jsonl_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("baseline_name") != baseline_name:
            continue
        if obj.get("response") is not None:
            n_succ += 1
        else:
            n_mal += 1
        cost += float(obj.get("cost_usd", 0) or 0)
        in_tok += int(obj.get("input_tokens", 0) or 0)
        out_tok += int(obj.get("output_tokens", 0) or 0)
    return {
        "n_succeeded": n_succ,
        "n_malformed": n_mal,
        "total_cost_usd": cost,
        "total_input_tokens": in_tok,
        "total_output_tokens": out_tok,
    }


# ---------------------------------------------------------------------------
# Oracle baseline integration
# ---------------------------------------------------------------------------


def run_oracle_baseline(
    records: Iterable[CaseRecord],
    *,
    output_jsonl: str | Path,
    verbose: bool = True,
) -> RunSummary:
    """Run the deterministic oracle baseline (no LLM call).

    Wraps oracle_baseline.predict_unblinded so the rules engine ships as
    a first-class leaderboard entry. See oracle_baseline.py for the
    blind-vs-truth distinction.
    """
    from radgym.baselines import oracle_baseline

    records_list = list(records)
    output_path = Path(output_jsonl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed_ids = _load_completed_case_ids(output_path)
    to_run = [r for r in records_list if r.case.case_id not in completed_ids]

    if verbose:
        print(
            f"[{oracle_baseline.BASELINE_NAME}] {len(records_list)} cases "
            f"({len(to_run)} to run, {len(records_list) - len(to_run)} cached)."
        )

    fh = output_path.open("a")
    try:
        for i, rec in enumerate(to_run, start=1):
            agent_resp = oracle_baseline.predict_unblinded(rec.case)
            cs = score_case(agent_resp, rec.ground_truth)
            result = CaseRunResult(
                case_id=rec.case.case_id,
                baseline_name=oracle_baseline.BASELINE_NAME,
                response=agent_resp.model_dump(),
                parse_strategy="strict",
                raw_text="",
                score_outcome=cs.outcome,
                score_points=cs.points,
            )
            fh.write(result.to_jsonl() + "\n")
            fh.flush()
            if verbose:
                print(
                    f"  [{i:3d}/{len(to_run)}] {rec.case.case_id}  "
                    f"{cs.outcome:18s} {cs.points:+.2f}"
                )
    finally:
        fh.close()

    all_scores = _rehydrate_scores(output_path)
    agg = aggregate(all_scores, n_total=len(records_list))
    totals = _summarize_log(output_path, oracle_baseline.BASELINE_NAME)
    return RunSummary(
        baseline_name=oracle_baseline.BASELINE_NAME,
        n_cases=len(records_list),
        n_succeeded=totals["n_succeeded"],
        n_malformed=totals["n_malformed"],
        total_cost_usd=0.0,
        total_input_tokens=0,
        total_output_tokens=0,
        composite=agg.composite,
        exact_accuracy=agg.exact_accuracy,
        under_following_rate=agg.under_following_rate,
        over_following_rate=agg.over_following_rate,
        cross_track_rate=agg.cross_track_rate,
        malformed_rate=agg.malformed_rate,
        rankable=agg.rankable,
    )


__all__ = [
    "BaselineConfig",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_USER_PROMPT_TEMPLATE",
    "CaseRunResult",
    "RunSummary",
    "run_baseline",
    "run_oracle_baseline",
]
