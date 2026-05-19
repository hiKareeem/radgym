"""
Contamination check: detect verbatim copying from Fleischner 2017 in cases.

Runs in CI on every PR. Loads the paper fingerprint (a set of SHA-256
hashes of every 7-gram in the Fleischner 2017 paper, built once locally
by scripts/build_paper_fingerprint.py — committed to the repo as
data/fleischner_paper_fingerprint.json) and checks every curated case's
`presentation` + `context` text against it.

Detection model:
  - Normalize case text the same way the paper was normalized.
  - Compute case 7-grams, hash each.
  - For each case, find the longest CONTIGUOUS run of 7-grams whose
    hashes appear in the paper.
  - That run length × tokens/n-gram ≈ length of the longest verbatim
    copy. (Run length 1 = 7 words copied; run length 4 = 10 words
    copied since they overlap.)
  - Fail if any case's longest run exceeds --max-run.

Why contiguous run length is the right metric:
  - Common clinical phrases ('CT at 6-12 months') produce isolated
    matches, never long runs.
  - Verbatim paragraph copying produces a long monotone run.
  - This is robust to the false-positive concern external reviewer #10
    raised about a flat n-gram-count threshold.

Boilerplate allowlist: none in v0.1. Common phrases produce isolated
hits which don't trigger the run-length threshold. If false positives
emerge after launch we'll add per-phrase exemptions here.

Usage:
    python scripts/check_contamination.py            # check all cases
    python scripts/check_contamination.py --verbose  # show match snippets
    python scripts/check_contamination.py --max-run 6  # tighter threshold
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINGERPRINT = REPO_ROOT / "data" / "fleischner_paper_fingerprint.json"
DEFAULT_CASES_DIRS = [
    REPO_ROOT / "cases" / "v0.1" / "dev",
    REPO_ROOT / "cases" / "v0.1" / "test",
]
DEFAULT_MAX_RUN = 4  # 4 consecutive 7-grams ≈ 10-word verbatim copy


def normalize(text: str) -> list[str]:
    """MUST match build_paper_fingerprint.py::normalize exactly."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def hash_ngram_tuple(ngram: tuple[str, ...]) -> str:
    payload = " ".join(ngram).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def longest_contiguous_run(
    case_tokens: list[str], paper_hashes: set[str], ngram_size: int
) -> tuple[int, int, int]:
    """Return (max_run_length, start_index, end_index_exclusive).

    A 'run' is a contiguous stretch of n-grams whose hashes all appear in
    the paper. The hit positions give us the slice of original case
    tokens that was verbatim-copied (length = run + ngram_size - 1).
    """
    if len(case_tokens) < ngram_size:
        return 0, 0, 0
    hits = [
        hash_ngram_tuple(tuple(case_tokens[i : i + ngram_size])) in paper_hashes
        for i in range(len(case_tokens) - ngram_size + 1)
    ]
    max_run = 0
    max_start = 0
    cur_run = 0
    cur_start = 0
    for i, is_hit in enumerate(hits):
        if is_hit:
            if cur_run == 0:
                cur_start = i
            cur_run += 1
            if cur_run > max_run:
                max_run = cur_run
                max_start = cur_start
        else:
            cur_run = 0
    # Slice the verbatim-copied stretch out of the case tokens
    if max_run == 0:
        return 0, 0, 0
    verbatim_end = max_start + max_run + ngram_size - 1
    return max_run, max_start, verbatim_end


def collect_case_text(record: dict) -> str:
    """presentation + context are the maintainer-authored prose fields."""
    case = record.get("case", {})
    parts = [case.get("presentation") or "", case.get("context") or ""]
    return " ".join(parts)


def check_cases(
    cases_dirs: list[Path],
    paper_hashes: set[str],
    ngram_size: int,
    max_run: int,
    verbose: bool,
) -> int:
    """Returns number of cases that exceeded the run-length threshold."""
    failures: list[tuple[str, int, list[str]]] = []
    longest_clean: tuple[int, str] = (0, "")
    n_total = 0

    for cases_dir in cases_dirs:
        if not cases_dir.exists():
            print(f"  (skip: {cases_dir} does not exist)", file=sys.stderr)
            continue
        for path in sorted(cases_dir.glob("RGYM-v01-*.json")):
            n_total += 1
            rec = json.loads(path.read_text())
            text = collect_case_text(rec)
            tokens = normalize(text)
            run, start, end = longest_contiguous_run(tokens, paper_hashes, ngram_size)
            verbatim = tokens[start:end]
            if run > max_run:
                failures.append((path.stem, run, verbatim))
            elif run > longest_clean[0]:
                snippet = " ".join(verbatim) if verbatim else "(none)"
                longest_clean = (run, f"{path.stem}: {snippet}")
            if verbose and run > 0:
                snippet = " ".join(verbatim)
                marker = "FAIL" if run > max_run else "ok"
                print(f"  [{marker}] {path.stem}: run={run} ({len(verbatim)} tokens) {snippet!r}")

    print(f"\nChecked {n_total} cases.")
    print(f"Threshold: contiguous run of >{max_run} matching {ngram_size}-grams (~{max_run+ngram_size-1}+ tokens verbatim).")

    if longest_clean[0]:
        print(f"Worst clean case: run={longest_clean[0]} — {longest_clean[1]}")
    else:
        print("Worst clean case: no matches in any case.")

    if failures:
        print(f"\n❌ {len(failures)} case(s) exceeded the contamination threshold:\n")
        for case_id, run, verbatim in failures:
            snippet = " ".join(verbatim)
            verbatim_len = len(verbatim)
            print(f"  {case_id}:  run={run} ({verbatim_len} tokens verbatim)")
            print(f"    snippet: {snippet!r}")
        print(
            "\nMaintainer action: paraphrase the flagged cases so no verbatim\n"
            "stretch from the Fleischner 2017 paper exceeds the threshold."
        )
        return len(failures)

    print("\n✅ No cases exceed the contamination threshold.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fingerprint",
        default=str(DEFAULT_FINGERPRINT),
        help=f"Paper fingerprint JSON (default: {DEFAULT_FINGERPRINT}).",
    )
    parser.add_argument(
        "--cases-dir",
        action="append",
        default=None,
        help="Cases directory to scan (repeatable). Default: dev + test.",
    )
    parser.add_argument(
        "--max-run",
        type=int,
        default=DEFAULT_MAX_RUN,
        help=(
            f"Max allowed contiguous matching n-gram run (default: {DEFAULT_MAX_RUN}). "
            "Higher = more permissive. ~4 matches a ~10-token verbatim stretch."
        ),
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    fp_path = Path(args.fingerprint)
    if not fp_path.exists():
        print(
            f"ERROR: fingerprint file not found: {fp_path}\n"
            "  Run scripts/build_paper_fingerprint.py first (maintainer-only step).",
            file=sys.stderr,
        )
        return 2

    fp = json.loads(fp_path.read_text())
    paper_hashes = set(fp["hashes"])
    ngram_size = fp["ngram_size"]
    print(
        f"Loaded fingerprint: {len(paper_hashes):,} unique {ngram_size}-gram hashes "
        f"from '{fp.get('source_description', 'unknown source')[:60]}...'"
    )

    cases_dirs = [Path(d) for d in args.cases_dir] if args.cases_dir else DEFAULT_CASES_DIRS

    n_failures = check_cases(
        cases_dirs=cases_dirs,
        paper_hashes=paper_hashes,
        ngram_size=ngram_size,
        max_run=args.max_run,
        verbose=args.verbose,
    )
    return 0 if n_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
