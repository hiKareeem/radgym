"""
Build the public leaderboard JSONs that the HF Space consumes.

Reads `results/{dev,test}/*.jsonl` (one row per case per baseline), computes
aggregate metrics per baseline, and writes a single summary JSON per split
to `space/data/`. The HF Space loads only these summary files — never the
raw JSONLs — so the public surface area cannot leak per-case test outcomes
(METHODOLOGY §4.2).

Per-baseline tier assignment is pulled from `radgym/baselines/presets.py`:
  - oracle → "oracle"
  - PRESET_BASELINES → "snapshot"
  - CURRENT_FRONTIER_BASELINES → "current_frontier"

Usage:
    python scripts/build_leaderboard.py            # both splits
    python scripts/build_leaderboard.py --split test
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from radgym.baselines.presets import (  # noqa: E402
    ALL_BASELINES,
    CURRENT_FRONTIER_BASELINES,
    CURRENT_FRONTIER_REGISTRY_TAG,
    PRESET_BASELINES,
)

RESULTS_DIR = REPO_ROOT / "results"
SPACE_DATA_DIR = REPO_ROOT / "space" / "data"


def _baseline_tier(jsonl_stem: str) -> str:
    """Return 'oracle', 'snapshot', or 'current_frontier' for a JSONL stem.

    Matches by config .name field (the field used to name the JSONL file).
    """
    if jsonl_stem == "oracle_rules_engine":
        return "oracle"
    for cfg in PRESET_BASELINES.values():
        if cfg.name == jsonl_stem:
            return "snapshot"
    for cfg in CURRENT_FRONTIER_BASELINES.values():
        if cfg.name == jsonl_stem:
            return "current_frontier"
    return "unknown"


def _baseline_config(jsonl_stem: str):
    """Return the BaselineConfig that produced this jsonl, or None."""
    for cfg in ALL_BASELINES.values():
        if cfg.name == jsonl_stem:
            return cfg
    return None


def summarize_baseline(jsonl_path: Path) -> dict:
    """Compute leaderboard-ready summary for one baseline."""
    lines = [
        json.loads(line)
        for line in jsonl_path.read_text().strip().splitlines()
        if line.strip()
    ]
    n = len(lines)
    if n == 0:
        raise ValueError(f"empty jsonl: {jsonl_path}")

    outcomes = Counter(r.get("score_outcome") for r in lines)
    total_points = sum((r.get("score_points") or 0.0) for r in lines)
    total_cost = sum((r.get("cost_usd") or 0.0) for r in lines)
    total_in = sum((r.get("input_tokens") or 0) for r in lines)
    total_out = sum((r.get("output_tokens") or 0) for r in lines)

    exact = outcomes.get("correct", 0) + outcomes.get("multiple_correct_full", 0)
    unsafe = (
        outcomes.get("adjacent_unsafe", 0)
        + outcomes.get("wrong_unsafe", 0)
        + outcomes.get("cross_track", 0)
    )
    over_following = outcomes.get("adjacent_safe", 0) + outcomes.get("wrong_safe", 0)
    cross_track = outcomes.get("cross_track", 0)
    malformed = outcomes.get("malformed", 0)

    composite = 100.0 * total_points / n
    malformed_rate = malformed / n
    rankable = malformed_rate <= 0.05

    cfg = _baseline_config(jsonl_path.stem)
    tier = _baseline_tier(jsonl_path.stem)

    return {
        "name": jsonl_path.stem,
        "tier": tier,
        "model_identifier": cfg.model_identifier if cfg else None,
        "temperature": cfg.temperature if cfg else None,
        "max_tokens": cfg.max_tokens if cfg else None,
        "extra_params": (cfg.extra_params if cfg else {}) or {},
        "api_key_env": cfg.api_key_env if cfg else None,
        "notes": cfg.notes if cfg else "",
        # Metrics
        "n_cases": n,
        "composite": round(composite, 2),
        "exact_accuracy": round(exact / n, 4),
        "under_following_rate": round(unsafe / n, 4),
        "over_following_rate": round(over_following / n, 4),
        "cross_track_rate": round(cross_track / n, 4),
        "malformed_rate": round(malformed_rate, 4),
        "rankable": rankable,
        # Cost / tokens
        "total_cost_usd": round(total_cost, 4),
        "cost_per_case_usd": round(total_cost / n, 6),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "avg_input_tokens": int(total_in / n),
        "avg_output_tokens": int(total_out / n),
    }


def build_split(split: str) -> dict:
    """Build leaderboard JSON for one split."""
    split_dir = RESULTS_DIR / split
    if not split_dir.exists():
        raise FileNotFoundError(f"results dir not found: {split_dir}")

    summaries = []
    for jsonl in sorted(split_dir.glob("*.jsonl")):
        try:
            summaries.append(summarize_baseline(jsonl))
        except ValueError as e:
            print(f"  WARN: {e}", file=sys.stderr)

    # Sort each tier by composite desc; oracle always first within itself
    summaries.sort(key=lambda s: -s["composite"])

    snapshot = [s for s in summaries if s["tier"] in ("oracle", "snapshot")]
    frontier = [s for s in summaries if s["tier"] == "current_frontier"]

    # n_cases inferred from any non-zero baseline (they should agree)
    n_cases = summaries[0]["n_cases"] if summaries else 0

    return {
        "split": split,
        "n_cases": n_cases,
        "n_baselines_snapshot": len(snapshot),
        "n_baselines_current_frontier": len(frontier),
        "current_frontier_registry_tag": CURRENT_FRONTIER_REGISTRY_TAG,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "snapshot_baselines": snapshot,
        "current_frontier_baselines": frontier,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split",
        choices=["dev", "test", "both"],
        default="both",
        help="Which split(s) to build (default: both).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(SPACE_DATA_DIR),
        help=f"Where to write leaderboard JSONs (default: {SPACE_DATA_DIR}).",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = ["dev", "test"] if args.split == "both" else [args.split]
    for split in splits:
        try:
            data = build_split(split)
        except FileNotFoundError as e:
            print(f"  SKIP {split}: {e}", file=sys.stderr)
            continue
        out_path = out_dir / f"{split}_leaderboard.json"
        out_path.write_text(json.dumps(data, indent=2) + "\n")
        n_snap = data["n_baselines_snapshot"]
        n_front = data["n_baselines_current_frontier"]
        print(
            f"  {split}: {n_snap} snapshot + {n_front} frontier baselines on "
            f"{data['n_cases']} cases → {out_path.relative_to(REPO_ROOT)}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
