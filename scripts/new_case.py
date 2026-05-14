"""
Interactive case authoring tool for RadGym v0.1.

Usage:
    python scripts/new_case.py                      # interactive, auto-assigns next case ID
    python scripts/new_case.py --split test         # write to hidden test/ (default: dev/)
    python scripts/new_case.py --case-id RGYM-v01-0042  # override case ID

The flow:
    1. Prompts for nodule, patient, and free-text fields with sensible defaults.
    2. Validates each field through the Pydantic schemas as you go.
    3. Runs the oracle to predict the recommendation.
    4. Shows the oracle's reasoning trace.
    5. Asks you to confirm or override the ground-truth label.
    6. Asks for source attribution (Fleischner example, Radiopaedia, synthetic, etc.).
    7. Writes the JSON to cases/v0.1/<split>/.
    8. Re-validates the on-disk file by parsing it back through CaseRecord.

The point: every case that lands on disk has been (a) schema-valid, (b) reviewed
by the maintainer against the oracle's algorithmic answer, and (c) annotated with
its source. Disagreements between oracle and maintainer are surfaced loudly so
they can be resolved before the case enters the test set.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, get_args

from pydantic import ValidationError

# Make the repo importable when run as a script from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from radgym.oracle import apply_fleischner_2017  # noqa: E402
from radgym.schemas import (  # noqa: E402
    AdditionalNodule,
    Case,
    CaseRecord,
    GroundTruth,
    Location,
    Morphology,
    Multiplicity,
    Nodule,
    NoduleType,
    Patient,
    Recommendation,
    SmokingHistory,
)


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------


def _c(s: str, code: str) -> str:
    """ANSI color if stdout is a tty, plain otherwise."""
    if not sys.stdout.isatty():
        return s
    return f"\033[{code}m{s}\033[0m"


def bold(s: str) -> str:
    return _c(s, "1")


def cyan(s: str) -> str:
    return _c(s, "36")


def green(s: str) -> str:
    return _c(s, "32")


def yellow(s: str) -> str:
    return _c(s, "33")


def red(s: str) -> str:
    return _c(s, "31")


def dim(s: str) -> str:
    return _c(s, "2")


def banner(text: str) -> None:
    bar = "─" * max(20, len(text) + 4)
    print()
    print(cyan(bar))
    print(cyan(f"  {bold(text)}"))
    print(cyan(bar))


# ---------------------------------------------------------------------------
# Input primitives
# ---------------------------------------------------------------------------


def ask(prompt: str, default: str | None = None, allow_empty: bool = False) -> str:
    """Prompt for free text with an optional default."""
    suffix = f" {dim(f'[{default}]')}" if default else ""
    while True:
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        if not raw and allow_empty:
            return ""
        if raw:
            return raw
        print(red("  (required)"))


def ask_choice(prompt: str, choices: tuple[str, ...], default: str | None = None) -> str:
    """Prompt for one of a fixed set of literals."""
    choices_str = " | ".join(
        bold(c) if c == default else c for c in choices
    )
    while True:
        raw = ask(f"{prompt} ({choices_str})", default=default)
        if raw in choices:
            return raw
        print(red(f"  must be one of: {', '.join(choices)}"))


def ask_int(prompt: str, default: int | None = None, lo: int | None = None, hi: int | None = None) -> int:
    while True:
        raw = ask(prompt, default=str(default) if default is not None else None)
        try:
            v = int(raw)
        except ValueError:
            print(red("  must be an integer"))
            continue
        if lo is not None and v < lo:
            print(red(f"  must be ≥ {lo}"))
            continue
        if hi is not None and v > hi:
            print(red(f"  must be ≤ {hi}"))
            continue
        return v


def ask_float(prompt: str, default: float | None = None, lo: float | None = None, hi: float | None = None) -> float:
    while True:
        raw = ask(prompt, default=str(default) if default is not None else None)
        try:
            v = float(raw)
        except ValueError:
            print(red("  must be a number"))
            continue
        if lo is not None and v < lo:
            print(red(f"  must be ≥ {lo}"))
            continue
        if hi is not None and v > hi:
            print(red(f"  must be ≤ {hi}"))
            continue
        return v


def ask_optional_float(prompt: str, lo: float | None = None, hi: float | None = None) -> float | None:
    raw = ask(prompt + dim(" (blank = None)"), default="", allow_empty=True)
    if not raw:
        return None
    try:
        v = float(raw)
    except ValueError:
        print(red("  must be a number or blank; setting to None"))
        return None
    if lo is not None and v < lo:
        print(red(f"  must be ≥ {lo}; setting to None"))
        return None
    if hi is not None and v > hi:
        print(red(f"  must be ≤ {hi}; setting to None"))
        return None
    return v


def ask_bool(prompt: str, default: bool = False) -> bool:
    default_str = "y" if default else "n"
    while True:
        raw = ask(prompt + dim(" (y/n)"), default=default_str).lower()
        if raw in ("y", "yes", "true", "1"):
            return True
        if raw in ("n", "no", "false", "0"):
            return False
        print(red("  y/n"))


def with_retry(builder: Callable[[], Any], label: str) -> Any:
    """Run a Pydantic-model builder until it validates."""
    while True:
        try:
            return builder()
        except ValidationError as e:
            print(red(f"\n  {label} failed validation:"))
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                print(red(f"    - {loc}: {err['msg']}"))
            print(yellow("  Try again.\n"))


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_nodule_core(prefix: str = "") -> tuple[NoduleType, float, Morphology, Location]:
    """Common nodule fields used by both primary and additional nodules."""
    p = f"{prefix} " if prefix else ""
    nodule_type = ask_choice(
        f"{p}type",
        choices=get_args(NoduleType),
        default="solid",
    )
    size_mm = ask_float(f"{p}long-axis size (mm)", lo=0.1, hi=50.0)
    morphology = ask_choice(
        f"{p}morphology",
        choices=get_args(Morphology),
        default="unspecified",
    )
    location = ask_choice(
        f"{p}location",
        choices=get_args(Location),
        default="unspecified",
    )
    return nodule_type, size_mm, morphology, location  # type: ignore[return-value]


def build_nodule() -> Nodule:
    banner("Nodule")
    nodule_type, size_mm, morphology, location = build_nodule_core()
    multiplicity = ask_choice(
        "multiplicity",
        choices=get_args(Multiplicity),
        default="single",
    )

    additional: list[AdditionalNodule] = []
    if multiplicity == "multiple":
        print(dim("  Add additional nodules (you've already declared the dominant above)."))
        while True:
            print(yellow(f"\n  Additional nodule #{len(additional) + 1}"))
            atype, asize, amorph, aloc = build_nodule_core(prefix="  additional")
            extra = with_retry(
                lambda: AdditionalNodule(
                    type=atype, size_mm=asize, morphology=amorph, location=aloc
                ),
                label="additional nodule",
            )
            additional.append(extra)
            more = ask_bool("  add another?", default=False)
            if not more:
                break

    return with_retry(
        lambda: Nodule(
            type=nodule_type,
            size_mm=size_mm,
            multiplicity=multiplicity,  # type: ignore[arg-type]
            morphology=morphology,
            location=location,
            additional_nodules=additional,
        ),
        label="nodule",
    )


def build_patient() -> Patient:
    banner("Patient")
    age = ask_int("age (≥35)", lo=35, hi=120)
    smoking = ask_choice("smoking history", choices=get_args(SmokingHistory), default="never")
    pack_years: float | None = None
    if smoking in ("former", "current"):
        pack_years = ask_optional_float("  pack-years", lo=0.0, hi=200.0)
    asbestos = ask_bool("asbestos exposure?", default=False)
    fhx = ask_bool("family history of lung cancer?", default=False)
    emph = ask_bool("emphysema?", default=False)
    fibrosis = ask_bool("pulmonary fibrosis?", default=False)

    print(dim("\n  --- Out-of-scope flags (Fleischner 2017 excludes these patients) ---"))
    primary_ca = ask_bool("known primary cancer?", default=False)
    immuno = ask_bool("immunocompromised?", default=False)

    return with_retry(
        lambda: Patient(
            age=age,
            smoking_history=smoking,  # type: ignore[arg-type]
            pack_years=pack_years,
            asbestos_exposure=asbestos,
            family_history_lung_ca=fhx,
            emphysema=emph,
            pulmonary_fibrosis=fibrosis,
            known_primary_cancer=primary_ca,
            immunocompromised=immuno,
        ),
        label="patient",
    )


def build_case(case_id: str) -> Case:
    banner(f"Case {case_id}")
    presentation = ask(
        "presentation (1-3 sentence clinical context that mentions the nodule)"
    )
    nodule = build_nodule()
    patient = build_patient()
    context = ask("context (free-text framing for the agent)", allow_empty=True)

    return with_retry(
        lambda: Case(
            case_id=case_id,
            presentation=presentation,
            nodule=nodule,
            patient=patient,
            context=context,
        ),
        label="case",
    )


# ---------------------------------------------------------------------------
# Oracle review + ground-truth confirmation
# ---------------------------------------------------------------------------


def review_oracle_and_get_ground_truth(case: Case) -> GroundTruth:
    banner("Maintainer risk classification")
    print(dim(
        "  Per Fleischner 2017: 'Consider all relevant risk factors.'"
        "\n  No mechanical formula — your clinical synthesis is the source of truth."
        "\n  Inputs: smoking, age, asbestos, family hx, emphysema, fibrosis,"
        "\n          nodule morphology (spiculated → higher), upper-lobe location."
    ))
    print()
    maintainer_risk = ask_choice(
        "your assigned risk category",
        choices=("low", "high"),
        default="low",
    )

    banner("Oracle review")

    result = apply_fleischner_2017(case)

    print(f"  Oracle's heuristic risk:   {bold(result.risk_category)}")
    print(f"  Your assigned risk:        {bold(green(maintainer_risk))}")
    if result.risk_category != maintainer_risk:
        print(yellow(
            f"  ⚠ Oracle disagrees with you on risk. Oracle uses a conservative\n"
            f"    smoking-OR-comorbidity rule and ignores age/location/morphology.\n"
            f"    Your judgment wins — but flag in notes if this is a deliberate call."
        ))
    print()
    print(f"  Oracle recommendation:     {bold(green(result.recommendation.value))}")
    if result.dominant_nodule_recommendation:
        print(f"  Oracle dominant sub-bin:   {bold(result.dominant_nodule_recommendation.value)}")
    if result.subsolid_intent != "not_applicable":
        print(f"  Sub-solid intent:          {dim(result.subsolid_intent)}")
    print()
    print(f"  Reasoning trace:")
    for line in result.reasoning.split(". "):
        if line.strip():
            print(f"    {dim('•')} {line.strip().rstrip('.')}")

    print()
    accept = ask_bool(
        "Accept the oracle's recommendation as ground truth?",
        default=(result.risk_category == maintainer_risk),
    )
    if accept:
        gt_rec = result.recommendation
        gt_dominant = result.dominant_nodule_recommendation
        notes_default = ""
    else:
        print(yellow(
            "\n  ⚠ You're overriding the oracle. Three possible reasons:"
            "\n    (a) you assigned different risk than the oracle (legitimate — your judgment),"
            "\n    (b) oracle has a bug for this case shape (file an issue), OR"
            "\n    (c) the case has clinical nuance the rules engine can't capture."
            "\n  In case (c), strongly consider excluding from v0.1 instead."
        ))
        bin_choices = tuple(r.value for r in Recommendation)
        gt_rec = Recommendation(ask_choice("  override recommendation", choices=bin_choices))
        if gt_rec == Recommendation.MULTIPLE_NODULE_DOMINANT:
            sub_choices = tuple(r.value for r in Recommendation if r != Recommendation.MULTIPLE_NODULE_DOMINANT)
            gt_dominant = Recommendation(ask_choice("  override dominant sub-bin", choices=sub_choices))
        else:
            gt_dominant = None
        notes_default = f"MAINTAINER OVERRIDE (risk={maintainer_risk}, oracle_risk={result.risk_category}): "

    banner("Source attribution")
    print(dim("  Examples:"))
    print(dim("    fleischner_2017_example"))
    print(dim("    fleischner_2017_table1_row:single_solid_lt6mm_low"))
    print(dim("    openi:CXR123_IM-0456"))
    print(dim("    radiology_assistant:https://radiologyassistant.nl/chest/..."))
    print(dim("    synthetic_maintainer_authored"))
    source = ask("source", default="synthetic_maintainer_authored")
    notes = ask(
        "notes (ambiguity flags, edge-case rationale, etc.; blank ok)",
        default=notes_default,
        allow_empty=True,
    )

    return with_retry(
        lambda: GroundTruth(
            case_id=case.case_id,
            recommendation=gt_rec,
            dominant_nodule_recommendation=gt_dominant,
            maintainer_assigned_risk=maintainer_risk,  # type: ignore[arg-type]
            source=source,
            notes=notes,
        ),
        label="ground_truth",
    )


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------


CASES_BASE = REPO_ROOT / "cases" / "v0.1"


def next_case_id(split: str) -> str:
    """Find the next unused RGYM-v01-XXXX id across BOTH splits.

    IDs are globally unique across dev/ and test/ so a case never gets the
    same ID as another case just because they live in different splits.
    """
    used = set()
    for sub in ("dev", "test"):
        d = CASES_BASE / sub
        if d.exists():
            for p in d.glob("RGYM-v01-*.json"):
                stem = p.stem  # RGYM-v01-0001
                try:
                    used.add(int(stem.split("-")[-1]))
                except ValueError:
                    continue
    n = 1
    while n in used:
        n += 1
    return f"RGYM-v01-{n:04d}"


def write_case_record(record: CaseRecord, split: str) -> Path:
    out_dir = CASES_BASE / split
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{record.case.case_id}.json"
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite existing case: {out_path}")
    out_path.write_text(record.model_dump_json(indent=2) + "\n")
    # Round-trip verify.
    reloaded = CaseRecord.model_validate_json(out_path.read_text())
    assert reloaded.case.case_id == record.case.case_id
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split",
        choices=("dev", "test"),
        default="dev",
        help="Which split to write to (default: dev). The test split is gitignored.",
    )
    parser.add_argument(
        "--case-id",
        default=None,
        help="Override the auto-assigned case ID. Must match RGYM-v01-\\d{4}.",
    )
    parser.add_argument(
        "--repeat",
        action="store_true",
        help="After writing one case, immediately start another.",
    )
    args = parser.parse_args()

    while True:
        case_id = args.case_id or next_case_id(args.split)
        if args.case_id:
            args.case_id = None  # only use the override once

        try:
            case = build_case(case_id)
        except KeyboardInterrupt:
            print(yellow("\n\nAborted by user. No case written."))
            return 130

        gt = review_oracle_and_get_ground_truth(case)

        record = with_retry(
            lambda: CaseRecord(case=case, ground_truth=gt),
            label="case_record",
        )

        out_path = write_case_record(record, args.split)
        print()
        print(green(f"  ✓ wrote {out_path.relative_to(REPO_ROOT)}"))
        print(dim(f"    bin: {gt.recommendation.value}"))
        print(dim(f"    source: {gt.source}"))
        if gt.notes:
            print(dim(f"    notes: {gt.notes}"))

        if not args.repeat:
            break
        print()
        if not ask_bool(yellow("\nAuthor another case?"), default=True):
            break

    print(green("\nDone."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
