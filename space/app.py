"""
RadGym v0.1 leaderboard — HuggingFace Spaces (Gradio) app.

Reads pre-baked JSON summaries from data/{dev,test}_leaderboard.json (built
by scripts/build_leaderboard.py) and renders them as ranked tables with
two tabs per split: Snapshot baselines and Current-frontier baselines.

No raw test-case data is bundled with this app — only aggregate metrics
per baseline. Per METHODOLOGY §4.2, per-case outcomes for the hidden test
split are never returned to external submitters.

To run locally:
    cd space && pip install -r requirements.txt && python app.py

To deploy:
    huggingface-cli upload <user/radgym> . --repo-type space
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import gradio as gr  # type: ignore[import-not-found]
import pandas as pd  # type: ignore[import-not-found]


DATA_DIR = Path(__file__).resolve().parent / "data"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_split(split: str) -> dict | None:
    path = DATA_DIR / f"{split}_leaderboard.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _format_baselines_df(baselines: list[dict]) -> pd.DataFrame:
    """Convert baseline summaries into the displayed dataframe."""
    if not baselines:
        return pd.DataFrame(
            columns=["Rank", "Baseline", "Composite", "Exact", "Unsafe", "Cross-track", "Malformed", "Rankable", "Cost / case", "Total cost", "Model"]
        )

    rows = []
    rank = 1
    for b in baselines:
        rankable = b["rankable"]
        rank_display = str(rank) if rankable else "—"
        if rankable:
            rank += 1
        rows.append(
            {
                "Rank": rank_display,
                "Baseline": b["name"],
                "Composite": f"{b['composite']:.2f}",
                "Exact": f"{b['exact_accuracy']*100:.1f}%",
                "Unsafe": f"{b['under_following_rate']*100:.1f}%",
                "Cross-track": f"{b['cross_track_rate']*100:.1f}%",
                "Malformed": f"{b['malformed_rate']*100:.1f}%",
                "Rankable": "✓" if rankable else "✗",
                "Cost / case": f"${b['cost_per_case_usd']:.5f}" if b["cost_per_case_usd"] else "—",
                "Total cost": f"${b['total_cost_usd']:.4f}" if b["total_cost_usd"] else "—",
                "Model": b["model_identifier"] or "rules engine",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


INTRO_MD = """
# RadGym v0.1 — Fleischner 2017 pulmonary nodule follow-up

**An open agentic benchmark for radiology workflow reasoning.**

RadGym evaluates LLM agents on the kinds of decisions radiologists make at a
workstation — applying clinical guidelines, reasoning over priors, recommending
follow-up — not single-image classification. The **v0.1 track** is the Fleischner
Society 2017 algorithm for incidental pulmonary nodule follow-up: structured
text input, structured recommendation output, asymmetric safety-weighted scoring.

> ⚕️ **Research use only.** Not a medical device. Not for clinical decision-making.
> Submissions and baselines apply published guidelines to synthetic cases —
> they do not direct patient care.

**Two splits:**

- **Dev split (50 cases)** — public, full ground-truth labels included.
  Submitters use this to debug prompts.
- **Test split (150 cases)** — hidden. Submissions are scored against this
  split and only aggregate metrics are returned (METHODOLOGY §4.2 — closes
  the iterative label-probe attack).

**Two baseline tiers** (METHODOLOGY §5):

- **Snapshot** — date-pinned model IDs frozen at the v0.1 launch. Reproducibility
  anchors. Paper-citable.
- **Current frontier** — non-pinned aliases tracking each provider's current
  flagship. Refreshed when a new flagship ships; previous frontier rolls into
  Snapshot with its resolved date stamp.

**Composite scoring is asymmetric** (METHODOLOGY §3.1): under-following a
Fleischner-flagged nodule costs more than over-following it. The
*Unsafe* column above is the safety metric — **lower is better.** Submissions
with `Malformed` > 5% are not rankable.

[GitHub: hiKareeem/radgym](https://github.com/hiKareeem/radgym) ·
[Submitter docs](https://github.com/hiKareeem/radgym/blob/main/docs/SUBMISSION.md) ·
Maintainer: [@hiKareeem](https://github.com/hiKareeem) (radiology background; eval-design history with SpireBench)
"""


SCORING_HELP_MD = """
## How scoring works (short version)

For each case, the agent picks a recommendation bin. Outcomes:

| Outcome | Points | Meaning |
|---|---|---|
| `correct` | +1.00 | Exact match |
| `adjacent_safe` | +0.50 | Off by one bin, more aggressive than truth |
| `wrong_safe` | 0.00 | Off by ≥2 bins, more aggressive |
| `malformed` | 0.00 | Output didn't parse; agent failed loudly |
| `adjacent_unsafe` | -0.25 | Off by one bin, less aggressive than truth |
| `wrong_unsafe` | -0.50 | Off by ≥2 bins, less aggressive |
| `cross_track` | -0.50 | Picked the wrong follow-up *type* (solid vs sub-solid) |

`Composite = 100 × mean(points per case)`. Bounded `[-50, 100]`.

For multiple-nodule cases (~25% of the test set), scoring has a separate
decision table — see METHODOLOGY §3.4.

## Why the cost column

This is launch transparency, not part of the ranking. We seeded the
leaderboard with concrete API costs so prospective submitters can see what
their model class actually spends per Fleischner case. Two patterns visible
on launch day:

- **Reasoning models are expensive but accurate.** gpt-5.5-pro tops the
  leaderboard at ~$0.16/case — 30-75× more than gpt-4o, for ~30 composite
  points of gain.
- **Open weights compete on safety.** Some open-weight baselines have
  unsafe rates competitive with or better than paid frontier models at a
  fraction of the cost.

External submitters can opt in to cost display on their submission;
default is hidden.

## Submitting

Submission docs live at `docs/SUBMISSION.md` in the repo. Short version:
you give us a model identifier + system prompt + user prompt template
(+ optionally your own API key), we run it against the hidden test set,
you get back aggregate metrics. Per-case feedback is dev-split-only.
"""


def render_split_tab(split: str) -> tuple:
    """Build the UI for one split (dev or test)."""
    data = load_split(split)
    if data is None:
        gr.Markdown(f"_No leaderboard data found for **{split}** split. "
                    f"Run `scripts/build_leaderboard.py` to generate it._")
        return None, None, None

    n_cases = data["n_cases"]
    n_snap = data["n_baselines_snapshot"]
    n_front = data["n_baselines_current_frontier"]
    tag = data["current_frontier_registry_tag"]
    ts = datetime.fromisoformat(data["generated_at"]).strftime("%Y-%m-%d %H:%M UTC")

    header = gr.Markdown(
        f"**Split:** `{split}` ({n_cases} cases) · "
        f"**Snapshot baselines:** {n_snap} · "
        f"**Current frontier baselines:** {n_front} (`{tag}`) · "
        f"**Generated:** {ts}"
    )

    snap_df = _format_baselines_df(data["snapshot_baselines"])
    front_df = _format_baselines_df(data["current_frontier_baselines"])

    with gr.Tabs():
        with gr.Tab("Snapshot baselines (date-pinned, frozen)"):
            gr.Markdown(
                "_Reproducibility tier. Date-pinned model IDs. These scores "
                "never change. Cite these for paper-tracking._"
            )
            snap_table = gr.Dataframe(
                value=snap_df,
                interactive=False,
                wrap=True,
                row_count=(len(snap_df), "fixed"),
            )
        with gr.Tab(f"Current frontier ({tag})"):
            gr.Markdown(
                f"_Non-pinned aliases tracking each provider's current flagship. "
                f"Refreshed when a new flagship ships; previous frontier rolls into "
                f"Snapshot with its resolved date stamp. Current tag: `{tag}`._"
            )
            front_table = gr.Dataframe(
                value=front_df,
                interactive=False,
                wrap=True,
                row_count=(len(front_df), "fixed"),
            )

    return header, snap_table, front_table


def build_app() -> gr.Blocks:
    with gr.Blocks(
        title="RadGym v0.1 leaderboard",
    ) as demo:
        gr.Markdown(INTRO_MD)

        with gr.Tabs():
            with gr.Tab("Test split (hidden, scored)"):
                gr.Markdown(
                    "_The launch leaderboard. 150 hidden cases, aggregate "
                    "metrics only — per-case outcomes never returned (METHODOLOGY §4.2)._"
                )
                render_split_tab("test")
            with gr.Tab("Dev split (public, debug-only)"):
                gr.Markdown(
                    "_50 public cases with full ground-truth labels in the repo. "
                    "Submitters use this split to debug prompts before scoring on test._"
                )
                render_split_tab("dev")
            with gr.Tab("How scoring works"):
                gr.Markdown(SCORING_HELP_MD)

    return demo


if __name__ == "__main__":
    demo = build_app()
    demo.launch(theme=gr.themes.Soft())
