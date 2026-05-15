# RadGym build log

Build-in-public progress notes. Newest entries at top.

## 2026-05-15 — Second external review triaged; doc/code consistency pass

Second external-agent review (different model). Less impressive than the first — caught ~5 real items and 3 misreads (they only saw the 3 design files, not the code, so flagged `dominant_nodule_recommendation`, `GroundTruth`, and `additional_nodules` validation as "missing" when all three exist in `schemas.py`). Real fixes shipped this commit:

- Output-schema doc snippet (METHODOLOGY §1.3) now includes `dominant_nodule_recommendation` with the conditional-required rule explicit. Added a top-of-METHODOLOGY pointer to canonical code locations so future external reviewers know to read code as well as docs.
- §3.4 multiple-nodule scoring rewritten as a complete decision table that mirrors `scoring._score_multiple()` exactly (the prose was ambiguous about scaling factors; the table now resolves it).
- Age-exclusion from `derive_risk()` documented explicitly with rationale (Fleischner specifies no threshold; refusing to hard-code one is a methodology choice, not an oversight).
- Subsolid track `consider_pet_or_biopsy` reachability: documented as a v0.1 simplification (oracle never outputs it; agents can; scoring still works).
- Determinism caveat in §3.6 expanded to a concrete v0.1 commitment list (record `system_fingerprint`, pin date-stamped model IDs, no routine re-runs).
- N-gram contamination check refined: three-signal gate (longest n-gram excluding allowlist + Jaccard + ROUGE-L), all three must fail to reject a case. Original "single longest n-gram" approach had unavoidable false positives on common clinical phrasing.
- Malformed-rate rankable threshold tightened from 10% to 5% per external review #4 (closes the strategic-refusal gaming margin).

Test count: 35 → 37 (2 new boundary tests for the 5% threshold).

## 2026-05-14 — Oracle rewrite against verbatim Fleischner 2017 Table 1

Found the source PDF, extracted Table 1A and 1B verbatim, rewrote the oracle decision tables to match cell-by-cell. Caught 4 oracle bugs introduced by my draft-from-memory implementation (was conflating 2005 and 2017 guidelines on some cells):

- Single solid 6-8mm high-risk: 2017 unified to same bin as low-risk (CT 6-12mo); was wrongly returning CT 3-6mo per 2005.
- Single solid >8mm low-risk: 2017 routes to PET/biopsy consideration; was wrongly returning CT 3-6mo.
- Multiple-solid rules: 2017 has its own table-row; was wrongly routing through single-nodule rules.
- Multiple-subsolid rules: same — own table-row, was routing through single-nodule.

All 19 Table 1 cells now round-trip green through `tests/test_fleischner_table1.py`. Schema gained `maintainer_assigned_risk: low|high` on `GroundTruth` to capture the clinical-synthesis-not-formula nature of risk classification.

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
