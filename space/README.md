# RadGym v0.1 leaderboard

This directory is the HuggingFace Spaces app for the RadGym leaderboard.

## Local preview

```bash
cd space
pip install -r requirements.txt
python app.py
```

Then open the printed URL (typically `http://127.0.0.1:7860`).

## Data refresh

The app reads pre-baked summaries from `data/{dev,test}_leaderboard.json`.
To regenerate after a new baseline run:

```bash
python scripts/build_leaderboard.py
```

This reads `results/{dev,test}/*.jsonl` (one row per case per baseline) and
emits one summary JSON per split into `space/data/`. **The raw JSONLs are
never bundled with the Space** — only the per-baseline aggregates — so the
hidden test split's per-case outcomes cannot leak through the public app
(METHODOLOGY §4.2).

## Deployment

```bash
huggingface-cli upload <user/radgym> space/ --repo-type space
```

The `data/` directory must be committed; the Space's `app.py` reads from it
at request time.
