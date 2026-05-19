# RadGym

**An open agentic benchmark for radiology workflow reasoning.**

RadGym evaluates LLM agents on the kinds of decisions radiologists make in front of a workstation — applying clinical guidelines, comparing prior studies, recommending follow-up, flagging critical findings — rather than on single-image classification or one-shot report generation.

> ⚕️ **Research use only.** RadGym is a benchmark for evaluating AI systems. It is not a medical device, is not intended for clinical decision-making, and outputs from any agent submitted to RadGym must not be used to direct patient care.

## Status

🚧 **v0.1 in active development** — track design phase. First track: **Fleischner Society 2017 pulmonary nodule follow-up reasoning**. Public leaderboard target: ~3 weeks from repo init.

## Why

The radiology-AI benchmark landscape is rich for *single-image* tasks (CheXbench, ReXrank, MIMIC-CXR report-gen leaderboards) but empty for *workflow-agentic* tasks. No public benchmark currently evaluates:

- Application of structured clinical guidelines (Fleischner, Lung-RADS, BI-RADS, Fleischner incidental-finding white papers)
- Prior-study reasoning (new / improved / stable change detection)
- Tool use (requesting additional views, querying priors, structured-template population)
- Critical-finding triage urgency

This is the gap RadGym fills.

## Tracks

| Version | Track | Modality | Status |
|---|---|---|---|
| v0.1 | Fleischner 2017 pulmonary nodule follow-up | Text → structured answer | In design |
| v0.2 | Rationale-graded Fleischner (RadFact-style) | Text → answer + reasoning | Planned |
| v0.3 | Lung-RADS 2022 screening categorization | Text → category + interval | Planned |
| v0.4 | Prior-aware change detection | Text + prior reports → delta | Planned |
| v1.0 | Multi-image (CXR) with priors | Image + prior + indication → report | Planned |

## Submitting

v0.1 submissions are **prompt + model identifier** — submit a system prompt and a model name (e.g. `gpt-4o-2024-11-20`, `claude-sonnet-4`, `medgemma-27b-it`), and RadGym runs the eval on the hidden test set. Bring-your-own API key supported. **Full submission docs: [`docs/SUBMISSION.md`](docs/SUBMISSION.md)** — covers schema, provider gotchas (temperature/top_p/reasoning-token budget), anti-abuse limits, and a dev-vs-test feedback policy.

v0.2 will add Dockerized agent submissions for fine-tuned and custom-agent entries.

## Repo layout

```
radgym/
├── docs/             # CONCEPT, METHODOLOGY, SUBMISSION
├── cases/v0.1/       # public dev split (50 cases) + reference to hidden test set
├── baselines/        # reference baseline agents (rules engine + 6 LLMs)
├── scoring/          # scoring functions
├── leaderboard/      # Gradio/HF-Spaces leaderboard app
└── .github/          # CI, issue templates
```

## License

- **Code**: Apache 2.0 (see `LICENSE`)
- **Cases / dataset**: CC BY-NC 4.0 — research use only, derived from public sources (radiopaedia, OpenI, Fleischner 2017 worked examples, paraphrased synthetic cases). Source attribution per case in `cases/v0.1/SOURCES.md`.

## Build log

RadGym is being built in public from commit #1. Design discussions in `docs/`, weekly progress notes in `docs/LOG.md`.

## Maintainer

**Kareem Albaba, MD** ([@hiKareeem](https://github.com/hiKareeem)) — 3-year radiology residency, now in AI infrastructure (Hermes, SpireBench).
