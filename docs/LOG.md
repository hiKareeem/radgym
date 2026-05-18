# RadGym build log

Build-in-public progress notes. Newest entries at top.

## 2026-05-17 — Stratified dev/test split (50/150)

200 curated cases split into:

- `cases/v0.1/dev/` — 50 public cases (committed). Submitters can debug prompts against full per-case ground truth here.
- `cases/v0.1/test/` — 150 hidden cases (gitignored, never published). The scored split.

Both halves mirror the overall bin distribution and the ~45/55 low/high risk balance:

- DEV (50):  multiples 13 (26%), subsolid 8, ct_6_12mo 8, optional_ct 7, no_routine 7, consider_pet 7, consider_pet 7
- TEST (150): multiples 37 (24.7%), no_routine 23, optional_ct 23, consider_pet 23, ct_6_12mo 22, subsolid 22

Oracle round-trips 100/100 on both splits — curation is internally consistent end-to-end.

Stratification: `(top_level_recommendation, maintainer_assigned_risk)` strata, largest-remainder method for rounding gap allocation, seeded RNG (`seed=20260514` — date we hit 200) so the split is reproducible. Tool: `scripts/stratified_split.py`.

Next: run the 6 LLM baselines on the test split (gpt-4o, claude-sonnet-4, gemini-2.5-pro, llama-3.3-70b, medgemma-27b-it, gpt-3.5-turbo). API keys ready.

## 2026-05-16 — Baseline runner shipped; oracle scores 100/127

Built `radgym/baselines/` (runner, oracle wrapper, preset configs) + `scripts/run_baseline.py` CLI. Key design decisions:

- **Resumable JSONL log** — per-case append-only, so a crashed run picks up where it left off without re-charging completed cases.
- **Robust JSON extraction** — 4 fallback strategies (strict → fenced markdown → first balanced braces → trailing-comma repair) with the strategy recorded per case. Agents in the wild return JSON in every shape; the strict-only parser would have a 30%+ malformed rate from a frontier model that's actually getting the answer right.
- **`system_fingerprint` capture** per METHODOLOGY §3.6 commitment.
- **Cost preview via dry-run** — `--dry-run` shows projected cost before any API call.
- **Skip-missing-keys** — partial-baseline runs are fine; the leaderboard accepts incremental baseline additions.
- **External review #9 closed** — `oracle_baseline.py` wraps `OracleResult` into a valid `AgentResponse` so the rules engine ships as a first-class leaderboard entry. The wrapper distinguishes `predict_unblinded` (heuristic risk — what the leaderboard runs) from `predict_blinded_to_truth` (uses maintainer's risk — diagnostic only, never shipped).

First oracle-baseline run on the dev set (127 cases):

  composite: 100.00 / exact: 100.0% / malformed: 0.0% / cost: $0.00

Perfect score means every maintainer-curated label matches the algorithm exactly. Curation is internally consistent.

**Curation catch**: case RGYM-v01-0094 had `known_primary_cancer=True` (62yo female with uterine cancer, 8mm nodule on staging CT). Schema validator rejected it correctly — Fleischner 2017 explicitly excludes these patients. Case quarantined to `docs/quarantine/` pending Kareem's call on delete-vs-rewrite. Pattern to watch in remaining curation: any case framed around staging in a known cancer is out of scope; CT 3-month follow-up is driven by the primary's protocol, not Fleischner.

Tests: 35 → 57 (added 22 baseline tests covering JSON-extraction edge cases, schema validation pathways, oracle baseline integration, and resumability).

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
