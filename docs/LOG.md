# RadGym build log

Build-in-public progress notes. Newest entries at top.

## 2026-05-14 — First curation session, exclusion criteria discovered

- Curated RGYM-v01-0002 successfully (8mm solid, current smoker, 6-8mm high-risk path).
- Hit first ambiguous case: a hamartoma from the Fleischner paper in a 28yo. **Two scope issues caught at curation time**:
  1. Patient age 28 — Fleischner 2017 applies only to ≥35yo (schema's `Field(ge=35)` correctly blocked it).
  2. Hamartoma has classic benign imaging features (fat density / popcorn calcification) — Fleischner 2017 explicitly excludes these from the algorithm because morphology answers the question directly.
- **Lesson**: the curation process surfaces methodology gaps better than upfront design. Documented benign-features exclusion in METHODOLOGY §1.1. Decided against adding a `benign_features` schema field for v0.1 — it would expand scope and require revalidating earlier cases. Captured as v0.2 candidate: a `benign_features_no_followup` bin or pre-algorithm gate.
- The case authoring tool's oracle-override gate caught this correctly: the override warning explicitly asks "could this be a case the rules engine can't capture?" and the answer here is yes — exclude rather than override.

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
