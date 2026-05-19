"""
Build the Fleischner 2017 paper fingerprint for contamination checking.

ONE-TIME maintainer-side script. Run locally with the Fleischner PDF
available; commits the resulting fingerprint JSON to the repo. The
fingerprint is a set of SHA-256 hashes of every overlapping n-gram in
the paper, so the paper text itself is NEVER shipped — only an
irreversible derivative used to detect verbatim copying.

Why hashes:
  - Distributing the paper text or n-gram phrases would be a copyright
    issue (the n-grams ARE the work, chunked).
  - Hashes are irreversible: scripts/check_contamination.py can detect
    whether a case's text contains paper n-grams, but can't reconstruct
    the paper from the hash set.

Usage:
    python scripts/build_paper_fingerprint.py \\
        --pdf "/path/to/fleischner-2017.pdf" \\
        --ngram-size 7 \\
        --output data/fleischner_paper_fingerprint.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "data" / "fleischner_paper_fingerprint.json"
DEFAULT_NGRAM = 7


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract all text from a PDF using pymupdf."""
    try:
        import pymupdf  # type: ignore[import-not-found]
    except ImportError:
        print(
            "ERROR: pymupdf not installed. Run: pip install pymupdf",
            file=sys.stderr,
        )
        raise

    doc = pymupdf.open(str(pdf_path))
    chunks = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(chunks)


def normalize(text: str) -> list[str]:
    """Lowercase, strip punctuation, collapse whitespace, return token list.

    This MUST match the normalization in check_contamination.py exactly,
    otherwise we'd compare apples to oranges.
    """
    # Lowercase
    text = text.lower()
    # Replace punctuation with spaces (keep apostrophes inside words: don't)
    text = re.sub(r"[^a-z0-9'\s-]", " ", text)
    # Collapse runs of whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    """Return all overlapping n-grams as tuples."""
    if len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def hash_ngram(ngram: tuple[str, ...]) -> str:
    """SHA-256 of joined n-gram. Hex prefix-12 for compactness in the JSON file."""
    payload = " ".join(ngram).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf",
        required=True,
        help="Path to the Fleischner 2017 PDF (MacMahon et al., Radiology 2017).",
    )
    parser.add_argument(
        "--ngram-size",
        type=int,
        default=DEFAULT_NGRAM,
        help=(
            f"N-gram size (default: {DEFAULT_NGRAM}). 5-grams produce too many "
            "false positives on common clinical phrases; 7+ is the sweet spot."
        ),
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"Where to write the fingerprint JSON (default: {DEFAULT_OUTPUT}).",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    print(f"Extracting text from {pdf_path.name}...")
    text = extract_pdf_text(pdf_path)
    tokens = normalize(text)
    print(f"  {len(text):,} chars → {len(tokens):,} tokens after normalization")

    print(f"Computing {args.ngram_size}-grams...")
    grams = ngrams(tokens, args.ngram_size)
    print(f"  {len(grams):,} overlapping n-grams")

    print("Hashing...")
    hashes = sorted({hash_ngram(g) for g in grams})
    print(f"  {len(hashes):,} unique hashes (dedupe ratio {len(hashes)/max(1,len(grams)):.1%})")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_description": (
            "MacMahon H, et al. 'Guidelines for Management of Incidental "
            "Pulmonary Nodules Detected on CT Images: From the Fleischner "
            "Society 2017.' Radiology 2017; 284:228-243."
        ),
        "ngram_size": args.ngram_size,
        "hash_algorithm": "sha256-hex-prefix-16",
        "n_unique_hashes": len(hashes),
        "hashes": hashes,
    }
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nWrote {output}")
    print(f"  file size: {output.stat().st_size:,} bytes")
    print(
        "\nCommit this file. It contains no paper text — only irreversible\n"
        "SHA-256 hashes used by scripts/check_contamination.py to detect\n"
        "verbatim copying in curated cases."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
