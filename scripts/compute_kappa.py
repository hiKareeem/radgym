"""
Compute Cohen's κ between maintainer ground truth and reviewer labels.

Run AFTER the reviewer returns their filled CSV. Uses the maintainer_key.csv
(gitignored, kept on disk locally) and the reviewer's filled CSV
(typically `reviewer_filled.csv` — save their reply under that name).

Reports:
  - Overall Cohen's κ (top-level recommendation) — primary metric
  - Per-bin agreement rates
  - Concordance on the multiple-vs-single recognition (the hard case)
  - List of disagreements with side-by-side labels (for redline)

Usage:
    python scripts/compute_kappa.py \\
        --reviewer kappa_review/v0.1/reviewer_filled.csv

If the reviewer sends back a different filename or format, fix the path.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEY = REPO_ROOT / "kappa_review" / "v0.1" / "maintainer_key.csv"
DEFAULT_REVIEWER = REPO_ROOT / "kappa_review" / "v0.1" / "reviewer_filled.csv"


def load_labels(path: Path, key_col: str) -> dict[str, str]:
    """Map case_id → recommendation."""
    out: dict[str, str] = {}
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["case_id"].strip()
            label = (row.get(key_col) or "").strip()
            if not label:
                continue
            out[cid] = label
    return out


def cohens_kappa(labels_a: list[str], labels_b: list[str]) -> tuple[float, dict]:
    """Compute Cohen's κ. Returns (κ, breakdown dict).

    Standard formula: κ = (p_o - p_e) / (1 - p_e)
    where p_o = observed agreement and p_e = expected agreement by chance.
    """
    assert len(labels_a) == len(labels_b)
    n = len(labels_a)
    if n == 0:
        return 0.0, {"n": 0}

    p_o = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n

    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    all_labels = set(counts_a) | set(counts_b)
    p_e = sum(
        (counts_a[lbl] / n) * (counts_b[lbl] / n) for lbl in all_labels
    )

    if p_e == 1.0:
        kappa = 1.0  # both raters used a single label uniformly
    else:
        kappa = (p_o - p_e) / (1.0 - p_e)

    return kappa, {
        "n": n,
        "observed_agreement": p_o,
        "expected_agreement": p_e,
        "agreements": sum(1 for a, b in zip(labels_a, labels_b) if a == b),
    }


def interpret_kappa(k: float) -> str:
    """Landis & Koch 1977 cutoffs (the radiology-paper default)."""
    if k < 0:
        return "worse than chance"
    if k < 0.20:
        return "slight (0.00-0.20)"
    if k < 0.40:
        return "fair (0.21-0.40)"
    if k < 0.60:
        return "moderate (0.41-0.60)"
    if k < 0.80:
        return "substantial (0.61-0.80)"
    return "almost perfect (0.81-1.00)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", default=str(DEFAULT_KEY))
    parser.add_argument(
        "--reviewer",
        default=str(DEFAULT_REVIEWER),
        help="Reviewer's filled CSV (`reviewer_recommendation` column required).",
    )
    args = parser.parse_args()

    key_path = Path(args.key)
    rev_path = Path(args.reviewer)
    if not key_path.exists():
        print(f"ERROR: key not found: {key_path}", file=sys.stderr)
        return 1
    if not rev_path.exists():
        print(f"ERROR: reviewer file not found: {rev_path}", file=sys.stderr)
        return 1

    maint = load_labels(key_path, "maintainer_recommendation")
    rev = load_labels(rev_path, "reviewer_recommendation")

    common = sorted(set(maint) & set(rev))
    if not common:
        print("ERROR: no case_ids in common between key and reviewer", file=sys.stderr)
        return 1

    only_key = set(maint) - set(rev)
    only_rev = set(rev) - set(maint)
    if only_key:
        print(f"WARN: in key but reviewer didn't label: {sorted(only_key)}")
    if only_rev:
        print(f"WARN: in reviewer but not in key: {sorted(only_rev)}")

    a = [maint[c] for c in common]
    b = [rev[c] for c in common]
    kappa, info = cohens_kappa(a, b)

    print(f"\nCohen's κ on {info['n']} cases: {kappa:.3f}  ({interpret_kappa(kappa)})")
    print(f"  Observed agreement:  {info['observed_agreement']:.3f}")
    print(f"  Expected agreement:  {info['expected_agreement']:.3f}")
    print(f"  Agreements:          {info['agreements']}/{info['n']}")

    # Per-bin agreement (how often each maintainer-bin gets the same label)
    print("\nPer-bin agreement (rows = maintainer bin, columns = reviewer bin):")
    bins = sorted(set(a) | set(b))
    print(f"  {'bin':40s}  {'n':>3s}  {'matches':>8s}  {'rate':>6s}")
    for bn in bins:
        idx = [i for i, x in enumerate(a) if x == bn]
        if not idx:
            continue
        matches = sum(1 for i in idx if b[i] == bn)
        print(f"  {bn:40s}  {len(idx):>3d}  {matches:>8d}  {matches/len(idx)*100:5.1f}%")

    # Multiple-vs-single recognition agreement (the hard test)
    multi = "multiple_nodule_dominant"
    maint_multi = [c for c in common if maint[c] == multi]
    rev_multi = [c for c in common if rev[c] == multi]
    agree_multi = sum(1 for c in maint_multi if rev[c] == multi)
    print(f"\nMulti-nodule recognition:")
    print(f"  Maintainer said multiple: {len(maint_multi)}")
    print(f"  Reviewer said multiple:   {len(rev_multi)}")
    print(f"  Both agreed it's multiple: {agree_multi}")

    # Disagreements
    disagreements = [(c, maint[c], rev[c]) for c in common if maint[c] != rev[c]]
    if disagreements:
        print(f"\nDisagreements ({len(disagreements)}):")
        for cid, m, r in disagreements:
            print(f"  {cid}  maintainer={m:35s}  reviewer={r}")
    else:
        print("\n(no disagreements — perfect agreement)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
