"""
CLI: run one or more baseline configurations against the v0.1 case set.

Usage examples:

    # Dry-run: count cases, estimate tokens, no API calls
    python scripts/run_baseline.py --baseline oracle --dry-run

    # Run the oracle baseline (free, no API key needed)
    python scripts/run_baseline.py --baseline oracle

    # Run gpt-4o (requires OPENAI_API_KEY)
    python scripts/run_baseline.py --baseline gpt-4o

    # Run all baselines that have credentials available
    python scripts/run_baseline.py --baseline all --skip-missing-keys

    # Only run a small case sample (debugging)
    python scripts/run_baseline.py --baseline gpt-4o --limit 5

Output:
    Per-case results are appended to results/<baseline_name>.jsonl as a
    resumable log. A summary is printed to stdout after each baseline
    finishes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from radgym.baselines import oracle_baseline  # noqa: E402
from radgym.baselines.presets import (  # noqa: E402
    ALL_BASELINE_NAMES,
    ALL_BASELINES,
    PRESET_BASELINES,
)
from radgym.baselines.runner import (  # noqa: E402
    BaselineConfig,
    RunSummary,
    run_baseline,
    run_oracle_baseline,
)
from radgym.schemas import CaseRecord  # noqa: E402


DEFAULT_CASES_DIR = REPO_ROOT / "cases" / "v0.1" / "dev"
DEFAULT_RESULTS_DIR = REPO_ROOT / "results"


def _load_case_records(cases_dir: Path) -> list[CaseRecord]:
    """Load every CaseRecord from a directory, sorted by case_id."""
    records = []
    for path in sorted(cases_dir.glob("RGYM-v01-*.json")):
        try:
            records.append(CaseRecord.model_validate_json(path.read_text()))
        except Exception as e:
            print(f"  WARN: failed to load {path.name}: {e}", file=sys.stderr)
    return records


def _check_api_key(cfg: BaselineConfig) -> bool:
    if cfg.api_key_env is None:
        return True
    return bool(os.environ.get(cfg.api_key_env))


def _estimate_cost(n_cases: int, cfg: BaselineConfig) -> str:
    """Cheap rough-cut cost estimate. Real cost comes from LiteLLM."""
    # Heuristic: ~500 input + ~200 output tokens per case, modal prices.
    # Just for the dry-run preview; production numbers come from the runner.
    rough_per_1m_in = {"openai": 5.0, "anthropic": 3.0, "google": 1.25, "openrouter": 1.0}
    rough_per_1m_out = {"openai": 15.0, "anthropic": 15.0, "google": 5.0, "openrouter": 2.0}
    provider = cfg.model_identifier.split("/")[0] if "/" in cfg.model_identifier else "openai"
    in_cost = n_cases * 500 / 1_000_000 * rough_per_1m_in.get(provider, 5.0)
    out_cost = n_cases * 200 / 1_000_000 * rough_per_1m_out.get(provider, 15.0)
    return f"~${(in_cost + out_cost):.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        action="append",
        choices=ALL_BASELINE_NAMES + ["all"],
        required=True,
        help="Baseline name (repeatable). Use 'all' to run every preset.",
    )
    parser.add_argument(
        "--cases-dir",
        default=str(DEFAULT_CASES_DIR),
        help=f"Directory of CaseRecord JSON files (default: {DEFAULT_CASES_DIR}).",
    )
    parser.add_argument(
        "--results-dir",
        default=str(DEFAULT_RESULTS_DIR),
        help=f"Output directory for per-baseline JSONL logs (default: {DEFAULT_RESULTS_DIR}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N cases (for debugging).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show case count and rough cost estimate; do not call any model.",
    )
    parser.add_argument(
        "--skip-missing-keys",
        action="store_true",
        help="Skip baselines whose API key env var is unset (instead of failing).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-case progress output.",
    )
    args = parser.parse_args()

    # Expand 'all' to every preset + oracle
    selected: list[str] = []
    for b in args.baseline:
        if b == "all":
            selected.extend(ALL_BASELINE_NAMES)
        else:
            selected.append(b)
    # de-dupe, preserve order
    seen: set[str] = set()
    selected = [b for b in selected if not (b in seen or seen.add(b))]

    cases_dir = Path(args.cases_dir)
    if not cases_dir.exists():
        print(f"ERROR: cases dir not found: {cases_dir}", file=sys.stderr)
        return 1

    records = _load_case_records(cases_dir)
    if args.limit:
        records = records[: args.limit]
    if not records:
        print(f"ERROR: no cases found in {cases_dir}", file=sys.stderr)
        return 1

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loaded {len(records)} cases from {cases_dir}")
    print(f"Results dir: {results_dir}")
    print(f"Baselines:   {', '.join(selected)}\n")

    if args.dry_run:
        print("--- DRY RUN ---")
        for name in selected:
            if name == "oracle":
                print(f"  {oracle_baseline.BASELINE_NAME:35s}  $0.0000 (no LLM)")
                continue
            cfg = ALL_BASELINES[name]
            est = _estimate_cost(len(records), cfg)
            key_ok = "✓" if _check_api_key(cfg) else f"✗ (missing {cfg.api_key_env})"
            print(f"  {cfg.name:40s}  est {est:>10s}  key {key_ok}")
        return 0

    summaries: list[RunSummary] = []
    for name in selected:
        print(f"\n=== {name} ===")
        try:
            if name == "oracle":
                jsonl = results_dir / f"{oracle_baseline.BASELINE_NAME}.jsonl"
                summary = run_oracle_baseline(
                    records, output_jsonl=jsonl, verbose=not args.quiet
                )
            else:
                cfg = ALL_BASELINES[name]
                if not _check_api_key(cfg):
                    msg = (
                        f"  baseline {cfg.name}: env var {cfg.api_key_env} not set"
                    )
                    if args.skip_missing_keys:
                        print(msg + "  → SKIPPING")
                        continue
                    print("ERROR: " + msg, file=sys.stderr)
                    return 1
                jsonl = results_dir / f"{cfg.name}.jsonl"
                summary = run_baseline(
                    cfg, records, output_jsonl=jsonl, verbose=not args.quiet
                )
            summaries.append(summary)
            print()
            print(summary.pretty())
        except KeyboardInterrupt:
            print(f"\n  interrupted; partial results in {results_dir}")
            return 130

    # Final leaderboard preview
    if summaries:
        print("\n\n=== Leaderboard preview ===")
        rankable = [s for s in summaries if s.composite is not None]
        rankable.sort(key=lambda s: s.composite or -100, reverse=True)
        print(
            f"\n  {'baseline':45s}  {'composite':>10s}  "
            f"{'exact':>8s}  {'unsafe':>8s}  {'malformed':>10s}  "
            f"{'rankable':>9s}  {'cost':>9s}"
        )
        for s in rankable:
            assert s.composite is not None  # for type narrowing
            print(
                f"  {s.baseline_name:45s}  {s.composite:10.2f}  "
                f"{(s.exact_accuracy or 0)*100:7.1f}%  "
                f"{(s.under_following_rate or 0)*100:7.1f}%  "
                f"{(s.malformed_rate or 0)*100:9.1f}%  "
                f"{str(s.rankable):>9s}  "
                f"${s.total_cost_usd:>7.4f}"
            )

    # Dump a JSON summary for downstream consumption (e.g. the HF Space)
    summary_path = results_dir / "_summary.json"
    summary_path.write_text(
        json.dumps([s.__dict__ for s in summaries], indent=2, default=str)
    )
    print(f"\nSummary written to {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
