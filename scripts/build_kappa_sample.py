"""
Build the inter-rater Cohen's κ sample CSV for external radiologist review.

Selects 30 cases from the full 200-case set via stratified random sampling
on (top-level recommendation, maintainer-assigned risk) so that the κ
measurement is over the same distribution as the maintainer-labeled set
overall. Reads from both cases/v0.1/dev and cases/v0.1/test (which
together form the full 200).

Output: kappa_review/v0.1/cases_for_reviewer.csv — one row per case,
columns formatted for a radiologist to fill in their independent
Fleischner recommendation. NO ground-truth labels included in the
sent file (κ is blind labeling).

Also writes kappa_review/v0.1/maintainer_key.csv with the ground truth
for the same 30 case_ids, gitignored, used post-hoc to compute κ.

Usage:
    python scripts/build_kappa_sample.py                   # uses default seed
    python scripts/build_kappa_sample.py --seed 1337       # different shuffle
    python scripts/build_kappa_sample.py --n 50            # bigger sample
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = REPO_ROOT / "cases" / "v0.1" / "dev"
TEST_DIR = REPO_ROOT / "cases" / "v0.1" / "test"
OUT_DIR = REPO_ROOT / "kappa_review" / "v0.1"

DEFAULT_N = 30
DEFAULT_SEED = 20260519  # date we sent the recruitment email


RECOMMENDATION_OPTIONS = [
    "no_routine_followup",
    "optional_ct_12mo",
    "ct_6_12mo_then_18_24mo_if_stable",
    "ct_3_6mo_then_18_24mo",
    "subsolid_workup",
    "consider_pet_or_biopsy",
    "multiple_nodule_dominant",
]


def _stratum_key(record: dict) -> tuple[str, str]:
    gt = record["ground_truth"]
    return (gt["recommendation"], gt["maintainer_assigned_risk"])


def _load_all_cases() -> list[tuple[str, dict]]:
    """Return [(case_id, full_record), ...] for all 200 cases."""
    out = []
    for d in (DEV_DIR, TEST_DIR):
        for path in sorted(d.glob("RGYM-v01-*.json")):
            rec = json.loads(path.read_text())
            out.append((rec["case"]["case_id"], rec))
    return out


def stratified_sample(
    records: list[tuple[str, dict]], n: int, seed: int
) -> list[tuple[str, dict]]:
    """Largest-remainder stratified random sample over (recommendation, risk).

    Mirrors the same approach used in scripts/stratified_split.py — keeps
    the κ sample distributed like the source set within rounding error.
    """
    by_stratum: dict[tuple[str, str], list[tuple[str, dict]]] = defaultdict(list)
    for cid, rec in records:
        by_stratum[_stratum_key(rec)].append((cid, rec))

    total = sum(len(v) for v in by_stratum.values())
    target_frac = n / total

    rng = random.Random(seed)
    selected: list[tuple[str, dict]] = []
    remainders: list[tuple[float, tuple[str, str]]] = []
    for stratum, pool in by_stratum.items():
        rng.shuffle(pool)
        ideal = len(pool) * target_frac
        whole = int(ideal)
        selected.extend(pool[:whole])
        remainders.append((ideal - whole, stratum))

    gap = n - len(selected)
    if gap > 0:
        remainders.sort(reverse=True)
        for _, stratum in remainders[:gap]:
            pool = by_stratum[stratum]
            already = int(len(pool) * target_frac)
            if already < len(pool):
                selected.append(pool[already])

    # Sort the final selection by case_id for reviewer ergonomics
    selected.sort(key=lambda x: x[0])
    return selected


def _format_nodule_for_reviewer(nodule: dict) -> str:
    """Compact human-readable nodule description for the CSV cell."""
    parts = [
        nodule["type"].replace("_", "-"),
        f"{nodule['size_mm']}mm",
    ]
    if nodule.get("morphology") and nodule["morphology"] != "unspecified":
        parts.append(nodule["morphology"])
    if nodule.get("location") and nodule["location"] != "unspecified":
        parts.append(nodule["location"].replace("_", " "))
    return ", ".join(parts)


def _format_additionals(additionals: list[dict] | None) -> str:
    if not additionals:
        return ""
    return "; ".join(_format_nodule_for_reviewer(n) for n in additionals)


def _format_risk_factors(patient: dict) -> str:
    factors = []
    smoking = patient.get("smoking_history", "never")
    if smoking == "current":
        py = patient.get("pack_years")
        factors.append(f"current smoker ({py}py)" if py else "current smoker")
    elif smoking == "former":
        py = patient.get("pack_years")
        factors.append(f"former smoker ({py}py)" if py else "former smoker")
    elif smoking == "never":
        factors.append("never-smoker")
    if patient.get("asbestos_exposure"):
        factors.append("asbestos exposure")
    if patient.get("family_history_lung_ca"):
        factors.append("FHx lung CA")
    if patient.get("emphysema"):
        factors.append("emphysema")
    if patient.get("pulmonary_fibrosis"):
        factors.append("pulmonary fibrosis")
    return ", ".join(factors)


def write_reviewer_csv(
    sample: list[tuple[str, dict]], out_path: Path
) -> None:
    """Write the CSV the reviewer fills in. NO ground-truth labels included."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "case_id",
                "presentation",
                "patient_age",
                "patient_sex",
                "risk_factors",
                "dominant_nodule",
                "additional_nodules",
                "context",
                # Columns the reviewer fills in:
                "reviewer_recommendation",
                "reviewer_dominant_recommendation",
                "reviewer_notes",
            ]
        )
        for cid, rec in sample:
            case = rec["case"]
            patient = case["patient"]
            nodule = case["nodule"]
            w.writerow(
                [
                    cid,
                    case.get("presentation", ""),
                    patient.get("age", ""),
                    patient.get("sex", ""),
                    _format_risk_factors(patient),
                    _format_nodule_for_reviewer(nodule),
                    _format_additionals(nodule.get("additional_nodules")),
                    case.get("context", ""),
                    "",  # reviewer_recommendation
                    "",  # reviewer_dominant_recommendation (multiples only)
                    "",  # reviewer_notes
                ]
            )


def write_key_csv(sample: list[tuple[str, dict]], out_path: Path) -> None:
    """Write the maintainer ground-truth key for post-hoc κ computation."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "case_id",
                "maintainer_recommendation",
                "maintainer_dominant_recommendation",
                "maintainer_assigned_risk",
                "source_split",
            ]
        )
        for cid, rec in sample:
            gt = rec["ground_truth"]
            split = "dev" if (DEV_DIR / f"{cid}.json").exists() else "test"
            w.writerow(
                [
                    cid,
                    gt["recommendation"],
                    gt.get("dominant_nodule_recommendation") or "",
                    gt["maintainer_assigned_risk"],
                    split,
                ]
            )


def write_instructions(out_path: Path, n_cases: int) -> None:
    """Write the cover-page instructions for the reviewer."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"""# RadGym v0.1 — Inter-rater κ review

Thank you for reviewing these cases. Your independent labels will be
compared to my labels to compute Cohen's κ for the methodology section.

## What to do

1. Open `cases_for_reviewer.csv` in Excel, Google Sheets, Numbers, or any
   CSV-aware tool.
2. For each row, read the patient + nodule columns and fill in:
   - **reviewer_recommendation** (required): your Fleischner 2017
     recommendation, picking ONE of these {len(RECOMMENDATION_OPTIONS)} bin IDs:
{chr(10).join(f"     - {opt}" for opt in RECOMMENDATION_OPTIONS)}
   - **reviewer_dominant_recommendation** (required ONLY if your
     `reviewer_recommendation` is `multiple_nodule_dominant`): the bin
     you would apply per Table 1A/1B's "Multiple" row. Same allowed
     values as above, except not `multiple_nodule_dominant` itself.
   - **reviewer_notes** (optional): any case where you want to flag
     ambiguity, methodology concerns, or "this case doesn't fit
     Fleischner 2017 cleanly."
3. Send the filled CSV back. Whatever you find easiest — email
   attachment, shared link, smoke signal.

## Important framing

- Apply **Fleischner 2017** (MacMahon et al., Radiology 2017). Not 2005.
- Cases are scoped to incidental indeterminate nodules in
  patients ≥35 years, no known primary cancer, not immunocompromised.
  Benign-feature nodules (perifissural, classic granuloma calcification,
  hamartoma fat) are excluded from the case set.
- For multiple-nodule cases, apply the "Multiple" row of Table 1A or 1B,
  NOT the single-nodule rule for the dominant nodule.
- Patient risk classification is up to you (synthesize from the
  `risk_factors` column). The benchmark's own oracle uses a conservative
  rule (any of: current/former smoker, asbestos, FHx, emphysema, fibrosis
  → high; otherwise low) but your clinical judgment is what we want.

## Time estimate

~1-2 minutes per case. ~30-60 minutes total for {n_cases} cases.

## Questions

Just reply to my email. Happy to clarify any case or the methodology.

— Kareem
"""
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=DEFAULT_N)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    if not DEV_DIR.exists() or not TEST_DIR.exists():
        print(
            f"ERROR: cases dirs not found ({DEV_DIR}, {TEST_DIR})", file=sys.stderr
        )
        return 1

    records = _load_all_cases()
    if len(records) < args.n:
        print(
            f"ERROR: only {len(records)} cases on disk, can't sample {args.n}",
            file=sys.stderr,
        )
        return 1

    sample = stratified_sample(records, args.n, args.seed)

    # Distribution sanity print
    dist = Counter(_stratum_key(r) for _, r in sample)
    overall = Counter(_stratum_key(r) for _, r in records)
    print(f"Sample of {len(sample)} cases drawn from {len(records)} total")
    print(f"Seed: {args.seed}")
    print(f"\n  {'stratum (rec, risk)':50s}  {'sampled':>8s}  {'overall':>8s}")
    for stratum in sorted(overall, key=lambda s: -overall[s]):
        print(
            f"  {str(stratum):50s}  {dist.get(stratum, 0):8d}  {overall[stratum]:8d}"
        )

    out_dir = Path(args.output_dir)
    reviewer_csv = out_dir / "cases_for_reviewer.csv"
    key_csv = out_dir / "maintainer_key.csv"
    instructions = out_dir / "README.md"

    write_reviewer_csv(sample, reviewer_csv)
    write_key_csv(sample, key_csv)
    write_instructions(instructions, len(sample))

    print(f"\nWrote {reviewer_csv}")
    print(f"Wrote {key_csv}  (DO NOT SEND TO REVIEWER)")
    print(f"Wrote {instructions}")
    print(
        "\nTo bundle for sending: zip the reviewer CSV + README.md ONLY,\n"
        "leaving maintainer_key.csv on disk."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
