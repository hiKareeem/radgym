# RadGym build log

Build-in-public progress notes. Newest entries at top.

## 2026-05-14 — Repo init

- Decided on project after BMAD-style brainstorm: agentic experiment, shareable, monetizable potential.
- Considered TradeBench (clear gap, high) and GameAgentBench (SpireBench continuation) — chose RadGym because maintainer's radiology background is unusually rare leverage in the medical-AI-benchmark space.
- v0.1 track locked: **Fleischner 2017 pulmonary nodule follow-up reasoning**, text-only, 200 cases (50 public dev + 150 hidden test), asymmetric scoring (under-following penalized).
- v0.1 submission mechanism: prompt + model identifier (Docker in v0.2).
- v0.1 audience: indie AI hackers / agent builders.
- Baselines: rules engine + GPT-4o + Claude Sonnet 4 + Gemini 2.5 Pro + Llama-3.3-70B + MedGemma-27B + GPT-3.5-turbo.
- Repo: `github.com/hiKareeem/radgym`, public from commit #1.
- 3-week target to public leaderboard launch.

Next: maintainer redlines CONCEPT.md + METHODOLOGY.md; case curation begins in parallel.
