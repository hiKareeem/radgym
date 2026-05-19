"""
Maintainer-side: validate and (optionally) run a submission from a GH Issue.

Workflow:

  1. External submitter files a GH Issue using .github/ISSUE_TEMPLATE/submission.yml
  2. You fetch the issue body (gh CLI or copy-paste).
  3. Run this script against the body — it:
     - parses the GitHub form output back into a structured submission
     - validates it (schema, prompt size, JSON parse, model identifier shape)
     - dry-runs cost preview against test split (150 cases)
     - if you pass --run, executes the baseline and writes results/test/<name>.jsonl
     - if you pass --rebuild, rebuilds the leaderboard JSONs

Usage:

    # Validate only (no API calls)
    gh issue view 12 --json body --jq '.body' > /tmp/submission.md
    python scripts/process_submission.py --issue-body /tmp/submission.md

    # Validate + cost preview
    python scripts/process_submission.py --issue-body /tmp/submission.md --dry-run

    # Validate + run + rebuild leaderboard
    python scripts/process_submission.py --issue-body /tmp/submission.md --run --rebuild

The script is the single source of truth for what 'processing a submission'
means. v0.2 will turn this into an HF-Space-triggered automated pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Limits (mirror docs/SUBMISSION.md §6)
MAX_SYSTEM_PROMPT_CHARS = 16_000
MAX_USER_PROMPT_CHARS = 4_000
MAX_PROJECTED_COST_USD = 25.0  # auto-reject above this; can raise per submitter


VALID_RECOMMENDATIONS = {
    "no_routine_followup",
    "optional_ct_12mo",
    "ct_6_12mo_then_18_24mo_if_stable",
    "ct_3_6mo_then_18_24mo",
    "subsolid_workup",
    "consider_pet_or_biopsy",
    "multiple_nodule_dominant",
}


@dataclass
class Submission:
    submission_name: str
    submitter: str
    model_identifier: str
    model_provider: str
    system_prompt: str
    user_prompt_template: str
    temperature: float
    max_tokens: int
    top_p: float | None
    extra_params: dict
    api_key_arrangement: str
    show_cost: bool
    notes: str


# ---------------------------------------------------------------------------
# Parse GitHub Issue body
# ---------------------------------------------------------------------------


def parse_issue_body(body: str) -> dict[str, str]:
    """GitHub form issues emit a markdown body with H3 section headers.

    Format:
        ### Section label

        Field value goes here

        ### Next section

        ...

    Returns dict keyed by **lowercase** section label substring (sufficient
    to match against the known labels in submission.yml).
    """
    sections: dict[str, str] = {}
    parts = re.split(r"^### ", body, flags=re.MULTILINE)
    for part in parts[1:]:  # skip prelude before first ###
        if "\n" not in part:
            continue
        header, rest = part.split("\n", 1)
        label = header.strip().lower()
        value = rest.strip()
        # GH renders blank fields as "_No response_"
        if value in ("_No response_", "*No response*", ""):
            value = ""
        sections[label] = value
    return sections


def _required(sections: dict[str, str], key_substring: str) -> str:
    for label, value in sections.items():
        if key_substring.lower() in label:
            if not value:
                raise ValueError(f"required field empty: {label!r}")
            return value
    raise ValueError(f"required section missing: needed substring {key_substring!r}")


def _optional(sections: dict[str, str], key_substring: str, default: str = "") -> str:
    for label, value in sections.items():
        if key_substring.lower() in label:
            return value or default
    return default


def build_submission(sections: dict[str, str]) -> Submission:
    sys_prompt = _required(sections, "system prompt")
    user_tmpl = _required(sections, "user prompt template")
    extra_raw = _optional(sections, "extra provider params")
    top_p_raw = _optional(sections, "top_p")

    extra_params: dict = {}
    if extra_raw:
        try:
            extra_params = json.loads(extra_raw)
            if not isinstance(extra_params, dict):
                raise ValueError("extra_params must be a JSON object")
        except json.JSONDecodeError as e:
            raise ValueError(f"extra_params is not valid JSON: {e}")

    top_p: float | None = None
    if top_p_raw and top_p_raw.lower() not in ("leave blank for default", "default", "none"):
        try:
            top_p = float(top_p_raw)
        except ValueError:
            raise ValueError(f"top_p must be a float, got {top_p_raw!r}")

    return Submission(
        submission_name=_required(sections, "submission name"),
        submitter=_required(sections, "submitter"),
        model_identifier=_required(sections, "model identifier"),
        model_provider=_required(sections, "model provider").strip().lower(),
        system_prompt=sys_prompt,
        user_prompt_template=user_tmpl,
        temperature=float(_required(sections, "decoding temperature")),
        max_tokens=int(_required(sections, "max_tokens")),
        top_p=top_p,
        extra_params=extra_params,
        api_key_arrangement=_required(sections, "api key arrangement"),
        show_cost=_required(sections, "show cost").lower().startswith("yes"),
        notes=_optional(sections, "notes"),
    )


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


def validate(sub: Submission) -> list[str]:
    """Return a list of errors. Empty list = clean."""
    errors: list[str] = []

    # Prompt size limits
    if len(sub.system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
        errors.append(
            f"system_prompt is {len(sub.system_prompt)} chars; max is {MAX_SYSTEM_PROMPT_CHARS}"
        )
    if len(sub.user_prompt_template) > MAX_USER_PROMPT_CHARS:
        errors.append(
            f"user_prompt_template is {len(sub.user_prompt_template)} chars; "
            f"max is {MAX_USER_PROMPT_CHARS}"
        )

    # User template must contain {case_json}
    if "{case_json}" not in sub.user_prompt_template:
        errors.append("user_prompt_template must contain the literal `{case_json}` placeholder")

    # Model identifier shape (LiteLLM expects provider/model)
    if "/" not in sub.model_identifier:
        errors.append(
            f"model_identifier {sub.model_identifier!r} doesn't look like a LiteLLM identifier "
            "(expected `provider/model`, e.g. `openai/gpt-4o-2024-11-20`)"
        )

    # Sanity checks on decoding params
    if not (0.0 <= sub.temperature <= 2.0):
        errors.append(f"temperature {sub.temperature} out of range [0.0, 2.0]")
    if sub.max_tokens < 256 or sub.max_tokens > 32768:
        errors.append(
            f"max_tokens {sub.max_tokens} should be in [256, 32768]. "
            "Reasoning models need ≥4096; non-reasoning ~2048 suffices."
        )
    if sub.top_p is not None and not (0.0 < sub.top_p <= 1.0):
        errors.append(f"top_p {sub.top_p} out of range (0.0, 1.0]")

    # Submission name shouldn't collide with seeded baselines
    seeded_names = _seeded_baseline_names()
    if sub.submission_name in seeded_names:
        errors.append(
            f"submission_name {sub.submission_name!r} collides with a seeded baseline. "
            "Pick a unique name (e.g. add your handle + a version suffix)."
        )

    return errors


def _seeded_baseline_names() -> set[str]:
    """Names of baselines that ship pre-seeded; submitters can't reuse these."""
    from radgym.baselines.presets import ALL_BASELINES

    names = {cfg.name for cfg in ALL_BASELINES.values()}
    names.add("oracle_rules_engine")
    return names


# ---------------------------------------------------------------------------
# Cost preview
# ---------------------------------------------------------------------------


def _build_config(sub: Submission):
    """Build a BaselineConfig from the parsed submission."""
    from radgym.baselines.runner import BaselineConfig

    return BaselineConfig(
        name=sub.submission_name,
        model_identifier=sub.model_identifier,
        system_prompt=sub.system_prompt,
        user_prompt_template=sub.user_prompt_template,
        temperature=sub.temperature,
        max_tokens=sub.max_tokens,
        top_p=sub.top_p if sub.top_p is not None else 1.0,
        api_key_env=_provider_to_env(sub.model_provider),
        notes=sub.notes,
        extra_params=sub.extra_params,
    )


def _provider_to_env(provider: str) -> str | None:
    """Map a provider slug to its standard API key env var name."""
    return {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "huggingface": "HUGGINGFACE_API_KEY",
        "custom": None,
    }.get(provider)


def cost_preview(sub: Submission, n_cases: int = 150) -> float:
    """Rough projected cost in USD for `n_cases` runs."""
    rough_per_1m_in = {"openai": 5.0, "anthropic": 3.0, "google": 1.25, "openrouter": 1.0}
    rough_per_1m_out = {"openai": 15.0, "anthropic": 15.0, "google": 5.0, "openrouter": 2.0}

    provider = sub.model_provider.lower()
    avg_in = 500 + len(sub.system_prompt) // 4 + len(sub.user_prompt_template) // 4
    avg_out = min(sub.max_tokens // 4, 800)  # visible output usually small fraction of budget

    in_rate = rough_per_1m_in.get(provider, 5.0)
    out_rate = rough_per_1m_out.get(provider, 15.0)
    in_cost = n_cases * avg_in / 1_000_000 * in_rate
    out_cost = n_cases * avg_out / 1_000_000 * out_rate
    return in_cost + out_cost


# ---------------------------------------------------------------------------
# Run the baseline
# ---------------------------------------------------------------------------


def run_submission(sub: Submission, output_dir: Path) -> None:
    """Actually execute the submission against the test split."""
    from radgym.baselines.runner import run_baseline
    from radgym.schemas import CaseRecord

    cfg = _build_config(sub)
    cases_dir = REPO_ROOT / "cases" / "v0.1" / "test"
    records = [
        CaseRecord.model_validate_json(p.read_text())
        for p in sorted(cases_dir.glob("RGYM-v01-*.json"))
    ]
    if not records:
        raise RuntimeError(f"no cases in {cases_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_jsonl = output_dir / f"{sub.submission_name}.jsonl"
    summary = run_baseline(cfg, records, output_jsonl=output_jsonl, verbose=True)
    print("\n" + summary.pretty())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-body",
        required=True,
        help="Path to a file containing the GH issue body markdown (e.g. from `gh issue view <N> --json body --jq .body`).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show cost preview; do not call any model.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the baseline against the test split.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="After running, rebuild the leaderboard JSONs via scripts/build_leaderboard.py.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "results" / "test"),
        help="Where to write the JSONL when --run is set.",
    )
    args = parser.parse_args()

    body = Path(args.issue_body).read_text()
    sections = parse_issue_body(body)
    if not sections:
        print("ERROR: no section headers found — is this a GH form issue body?", file=sys.stderr)
        return 1

    try:
        sub = build_submission(sections)
    except ValueError as e:
        print(f"PARSE ERROR: {e}", file=sys.stderr)
        return 2

    print(f"=== Submission: {sub.submission_name} ===")
    print(f"  submitter:     {sub.submitter}")
    print(f"  model:         {sub.model_identifier} ({sub.model_provider})")
    print(f"  temperature:   {sub.temperature}")
    print(f"  max_tokens:    {sub.max_tokens}")
    print(f"  top_p:         {sub.top_p if sub.top_p is not None else '(default, omitted)'}")
    print(f"  extra_params:  {sub.extra_params or '(none)'}")
    print(f"  api_key:       {sub.api_key_arrangement}")
    print(f"  show_cost:     {sub.show_cost}")
    print(f"  system_prompt: {len(sub.system_prompt)} chars")
    print(f"  user_template: {len(sub.user_prompt_template)} chars")

    errors = validate(sub)
    if errors:
        print(f"\nVALIDATION FAILED ({len(errors)} errors):")
        for e in errors:
            print(f"  ✗ {e}")
        return 3
    print("\nVALIDATION PASSED ✓")

    projected = cost_preview(sub, n_cases=150)
    print(f"\nProjected test-split cost (150 cases): ~${projected:.4f}")
    if projected > MAX_PROJECTED_COST_USD:
        print(
            f"  ✗ exceeds cost cap (${MAX_PROJECTED_COST_USD}). "
            f"Submission requires explicit maintainer approval."
        )

    if args.dry_run:
        return 0

    if not args.run:
        print("\n(use --run to execute against the test split)")
        return 0

    if projected > MAX_PROJECTED_COST_USD:
        print("\nREFUSED: projected cost exceeds cap. Re-run with --run after raising the cap.", file=sys.stderr)
        return 4

    print("\nRunning baseline against test split...")
    run_submission(sub, Path(args.output_dir))

    if args.rebuild:
        import subprocess
        print("\nRebuilding leaderboard JSONs...")
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "build_leaderboard.py")],
            check=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
