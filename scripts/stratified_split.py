"""
One-shot stratified split of cases/v0.1/dev/ into a public dev split and
a hidden test split.

Defaults: 50 dev (public) + 150 test (hidden), stratified on
(top_level_recommendation, maintainer_assigned_risk).

The test split lives in cases/v0.1/test/ which is gitignored — it MUST
never be committed. After the split, agents will be scored against
cases/v0.1/test/ on the HF Space.

Usage:
    python scripts/stratified_split.py --dry-run    # show counts only
    python scripts/stratified_split.py              # do the split
    python scripts/stratified_split.py --seed 1337  # different shuffle

This is idempotent given a fixed seed. It refuses to clobber existing
test/ files unless --force is passed.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = REPO_ROOT / "cases" / "v0.1" / "dev"
TEST_DIR = REPO_ROOT / "cases" / "v0.1" / "test"

DEFAULT_DEV_SIZE = 50
DEFAULT_SEED = 20260514  # date we hit 200 cases


def _stratum_key(record: dict) -> tuple[str, str]:
    gt = record["ground_truth"]
    return (gt["recommendation"], gt["maintainer_assigned_risk"])


def _load_all() -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(DEV_DIR.glob("RGYM-v01-*.json")):
        out.append((p, json.loads(p.read_text())))
    return out


def stratified_split(
    records: list[tuple[Path, dict]],
    dev_size: int,
    seed: int,
) -> tuple[list[Path], list[Path]]:
    """Return (dev_keep_paths, test_move_paths).

    Allocates dev/test counts per stratum proportional to stratum size,
    with deterministic remainder allocation. Each stratum's items are
    shuffled with the seed.
    """
    by_stratum: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for path, rec in records:
        by_stratum[_stratum_key(rec)].append(path)

    total = sum(len(v) for v in by_stratum.values())
    target_dev_frac = dev_size / total

    rng = random.Random(seed)
    dev_keep: list[Path] = []
    test_move: list[Path] = []

    # First pass: exact integer allocation per stratum
    fractional_remainders: list[tuple[float, tuple[str, str]]] = []
    for stratum, paths in by_stratum.items():
        rng.shuffle(paths)
        ideal = len(paths) * target_dev_frac
        whole = int(ideal)
        remainder = ideal - whole
        dev_keep.extend(paths[:whole])
        test_move.extend(paths[whole:])
        fractional_remainders.append((remainder, stratum))

    # Second pass: allocate any rounding gap to strata with the largest
    # fractional remainders (largest-remainder method — minimizes bias).
    current_dev = len(dev_keep)
    gap = dev_size - current_dev
    if gap > 0:
        fractional_remainders.sort(reverse=True)
        for _, stratum in fractional_remainders[:gap]:
            # Move one path from test_move back to dev_keep for this stratum
            stratum_paths = by_stratum[stratum]
            ideal_whole = int(len(stratum_paths) * target_dev_frac)
            if ideal_whole < len(stratum_paths):
                promoted = stratum_paths[ideal_whole]
                test_move.remove(promoted)
                dev_keep.append(promoted)
    elif gap < 0:
        # Over-allocated; demote from strata with smallest remainders
        fractional_remainders.sort()
        for _, stratum in fractional_remainders[:-gap]:
            stratum_paths = by_stratum[stratum]
            ideal_whole = int(len(stratum_paths) * target_dev_frac)
            if ideal_whole > 0:
                demoted = stratum_paths[ideal_whole - 1]
                dev_keep.remove(demoted)
                test_move.append(demoted)

    return sorted(dev_keep), sorted(test_move)


def _print_distribution(label: str, paths: list[Path]) -> None:
    bins: Counter[str] = Counter()
    risks: Counter[str] = Counter()
    for p in paths:
        rec = json.loads(p.read_text())
        bins[rec["ground_truth"]["recommendation"]] += 1
        risks[rec["ground_truth"]["maintainer_assigned_risk"]] += 1
    print(f"\n{label} ({len(paths)} cases):")
    for k in sorted(bins, key=lambda x: -bins[x]):
        pct = 100.0 * bins[k] / len(paths)
        print(f"  {k:40s} {bins[k]:3d}  ({pct:5.1f}%)")
    print(f"  risk: low={risks['low']}  high={risks['high']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-size", type=int, default=DEFAULT_DEV_SIZE)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing test/ directory.",
    )
    args = parser.parse_args()

    if not DEV_DIR.exists():
        print(f"ERROR: {DEV_DIR} not found", file=sys.stderr)
        return 1

    records = _load_all()
    if not records:
        print(f"ERROR: no cases in {DEV_DIR}", file=sys.stderr)
        return 1
    if args.dev_size >= len(records):
        print(
            f"ERROR: --dev-size {args.dev_size} >= total cases {len(records)}",
            file=sys.stderr,
        )
        return 1

    dev_keep, test_move = stratified_split(records, args.dev_size, args.seed)

    print(f"Total cases:    {len(records)}")
    print(f"Seed:           {args.seed}")
    print(f"Dev (public):   {len(dev_keep)}")
    print(f"Test (hidden):  {len(test_move)}")

    _print_distribution("DEV split", dev_keep)
    _print_distribution("TEST split", test_move)

    if args.dry_run:
        print("\n(dry-run; no files moved)")
        return 0

    if TEST_DIR.exists() and any(TEST_DIR.iterdir()) and not args.force:
        print(
            f"\nERROR: {TEST_DIR} already exists and is non-empty. "
            f"Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    TEST_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nMoving {len(test_move)} cases to {TEST_DIR} ...")
    for src in test_move:
        dst = TEST_DIR / src.name
        shutil.move(str(src), str(dst))
    print(f"  done. dev kept: {len(dev_keep)}  test moved: {len(test_move)}")

    # Sanity check
    dev_remaining = list(DEV_DIR.glob("RGYM-v01-*.json"))
    test_final = list(TEST_DIR.glob("RGYM-v01-*.json"))
    assert len(dev_remaining) == len(dev_keep), (
        f"sanity: dev has {len(dev_remaining)}, expected {len(dev_keep)}"
    )
    assert len(test_final) == len(test_move), (
        f"sanity: test has {len(test_final)}, expected {len(test_move)}"
    )
    print(f"  verified on disk: dev={len(dev_remaining)}  test={len(test_final)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
