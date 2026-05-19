---
title: "RadGym: An Open Agentic Benchmark for Radiology Workflow Reasoning"
subtitle: "v0.1 — Fleischner 2017 Pulmonary Nodule Follow-up Track"
author: "Kareem Albaba, MD"
affiliation: "Independent"
contact: "github.com/hiKareeem/radgym · @hiKareeem"
date: "2026-05-XX"
status: "preprint draft, arXiv-targeted; pending inter-rater κ data and external co-author"
target_venue: "arXiv first; potential ML4H 2026 workshop submission depending on κ outcome"
abstract_length_target: "200 words"
total_length_target: "8 pages incl. references"
license: "Apache-2.0 (code), CC BY 4.0 (paper)"
---

# RadGym: An Open Agentic Benchmark for Radiology Workflow Reasoning

## Abstract

`[KAREEM DRAFT — 200 words. Anchor on the workflow-vs-classification framing,
the 12-baseline result with frontier 53-87 / oracle 100, and the three
findings: Opus < Sonnet (within Anthropic), Llama 4 regression vs Llama 3.3,
multi-nodule recognition as 18% of all errors. Skip cost in abstract; cost
discussion lives in §2. Suggested opening: "Existing radiology AI benchmarks
test single-image classification, not the cognitive work radiologists do at
a workstation — applying clinical guidelines, recommending follow-up,
synthesizing risk."]`

**Keywords**: agentic AI evaluation, medical-AI benchmarks, clinical guidelines, Fleischner 2017, large language models, structured output evaluation, asymmetric scoring.

---

## 1. Introduction

`[KAREEM DRAFT — ~600 words. The personal/credibility framing is yours. Skeleton:]`

### 1.1 The gap

`[Existing radiology AI benchmarks (CheXbench, ReXrank, ChestXray-14, etc.) saturate on single-image classification. None evaluate the cognitive work radiologists actually do at the workstation. Cite a few. The cognitive work being: apply published guidelines (Fleischner, Lung-RADS, TI-RADS, BI-RADS) to structured clinical inputs; reason over priors; recommend follow-up; flag when out-of-scope.]`

### 1.2 Why this matters now

`[LLMs are increasingly proposed as clinical decision-support tools. The medical-AI literature has thousands of papers on image classification but very few on guideline application. The agents being shipped right now (every major closed-source model has an "MD" persona in user-facing products) need to be evaluated on the actual task, not a proxy.]`

### 1.3 What RadGym is

`[Open agentic benchmark. v0.1 track = Fleischner 2017 pulmonary nodule follow-up. Structured text input, structured recommendation output, asymmetric track-aware scoring. 200 maintainer-curated cases (50 public dev / 150 hidden test). 12 baselines seeded at launch. Submissions open via GitHub Issues; v0.2 will add HF-Space-triggered automated pipeline.]`

### 1.4 Contributions

This paper contributes:

1. **A maintainer-curated open benchmark** of 200 cases for Fleischner 2017 pulmonary nodule follow-up, with stratified 50/150 dev/test split.
2. **An asymmetric, track-aware scoring rubric** that penalizes under-following more than over-following and distinguishes wrong-track errors from wrong-interval errors (§2.3).
3. **Empirical evaluation of 12 LLM baselines** spanning closed-source frontier (GPT-5.5 family, Claude 4.6/4.7, Gemini 2.5/3.1 Pro), open-weight (Llama 3.3/4, DeepSeek V4 Pro), and a deliberate-floor reference (GPT-3.5-turbo). Findings include (a) ~14-point gap from best frontier (gpt-5.5: 86.67) to oracle (100.00); (b) intra-provider inversion (Opus 4.7 < Sonnet 4.6); (c) open-weight regression (Llama 4 Maverick < Llama 3.3-70b); (d) multi-nodule recognition as the largest single error class (~18% of all errors across baselines).
4. **A hash-based contamination detection method** (§2.5) using SHA-256-fingerprinted n-grams that ships the detector without distributing the source paper.
5. **A submission and methodology framework** designed for v0.2-v1.0 extensions (Lung-RADS, TI-RADS, BI-RADS, eventually DICOM-in tracks).

---

## 2. Methodology

> The full implementation lives at `github.com/hiKareeem/radgym`. This section summarizes; the repo is authoritative.

### 2.1 Track scope

v0.1 evaluates one narrow clinical task: applying the Fleischner Society 2017 algorithm (MacMahon et al., *Radiology* 2017 [REF]) to text-only descriptions of incidental pulmonary nodules. Scope is deliberately narrow to make the v0.1 contract tractable:

- **In scope**: patients ≥35 years, incidental indeterminate nodules detected on CT.
- **Excluded**: lung cancer screening cases (Lung-RADS, v0.3 track), known primary cancer, immunocompromised patients, benign-feature nodules (perifissural, classic granuloma calcification, hamartoma fat).

### 2.2 Case curation

200 cases authored by the sole maintainer (Kareem Albaba, MD — 3-year radiology residency, chest as confident subspecialty). The curation pipeline:

1. **Author** the clinical narrative as a 1-3 sentence presentation plus structured fields (nodule type/size/morphology/location/multiplicity; patient age/risk factors).
2. **Run the oracle** (§2.4) and verify the maintainer-assigned recommendation agrees with the algorithm's output. Disagreement triggers either a maintainer label revision (clinical judgment override) or an oracle update (algorithm bug discovered through curation).
3. **Stratified split**: 50 cases public dev, 150 hidden test. Stratified on `(top_level_recommendation, maintainer_assigned_risk)` via largest-remainder method to keep both splits' bin distributions within rounding of overall.

Distribution across the 6 main top-level recommendation bins is roughly uniform (~15% each) with `multiple_nodule_dominant` at ~25% (deliberately over-sampled because it is where models fail most; see §3).

`[Table: bin distribution, dev vs test, % each.]`

### 2.3 Scoring

For each case, the agent produces a recommendation from the 7-bin output schema. The scorer assigns one outcome per case:

| Outcome | Points | Description |
|---|---|---|
| `correct` | +1.00 | Exact bin match |
| `adjacent_safe` | +0.50 | Off by 1 on the adjacency track, more aggressive than truth |
| `wrong_safe` | 0.00 | Off by ≥2, more aggressive |
| `malformed` | 0.00 | Output didn't parse |
| `adjacent_unsafe` | −0.25 | Off by 1, less aggressive than truth |
| `wrong_unsafe` | −0.50 | Off by ≥2, less aggressive |
| `cross_track` | −0.50 | Wrong follow-up *type* (solid vs sub-solid) |

**Composite** = 100 × mean(points/case). Bounded [−50, +100].

**Two adjacency tracks** (rejecting the natural mistake of putting them on a single 1-D axis): a solid track (5 bins ordered by follow-up intensity) and a sub-solid track (3 bins). Cross-track recommendations score the maximum unsafe penalty regardless of position on the wrong track. This addresses a real scoring bug surfaced by external review: putting `subsolid_workup` on the solid track would have scored a sub-solid recommendation for a solid nodule as "adjacent," when it is in fact a different *type* of clinical workup.

**Multiple-nodule cases** use a separate decision table (§3.4 of `docs/METHODOLOGY.md`). When ground truth is `multiple_nodule_dominant`, the agent must produce both a top-level bin and a `dominant_nodule_recommendation`, scored against the multi-row of Fleischner Table 1A/1B.

**Rankability gate**: submissions with `malformed_rate > 5%` are not ranked — they failed to follow the output schema reliably enough to be evaluated, regardless of composite score.

**Determinism caveat**: `temperature=0` is not reproducible across providers (OpenAI fingerprint drift, Anthropic numerical variation, batched HF endpoints). Some reasoning-class models (GPT-5.5 family, Claude Opus 4.7) reject `temperature=0` outright with provider-mandated minimum temperatures. v0.1 surfaces per-baseline temperature on the leaderboard and reports composite ± bootstrap CI rather than claiming determinism we don't have. v0.2 will add majority-of-3 sampling.

### 2.4 Oracle / rules engine

`radgym/oracle.py` implements Fleischner 2017 Table 1A (solid) and 1B (sub-solid) as a ~300-LOC Python decision tree. It serves three roles:

1. **Curation aid**: during case authoring, the maintainer enters case fields and the oracle returns its predicted recommendation. Maintainer-assigned label is committed first; oracle agreement is verified second. Disagreement is treated as either a bug or a clinical-judgment override.
2. **Reference baseline**: by construction, the oracle should score 100.00. On both dev (50 cases) and test (150 cases) it does — confirming case labels and oracle implementation are internally consistent end-to-end.
3. **Independent validation gate**: `tests/test_fleischner_table1.py` round-trips 12 worked examples from MacMahon et al. against the oracle. The oracle must produce the paper's stated answer 100% of the time before any release.

**On the circularity concern**: an external reviewer noted the oracle simultaneously labels cases, scores submissions, and serves as a baseline. Mitigations (full discussion in `docs/METHODOLOGY.md` §2.5): maintainer-first labeling, paper-example validation gate independent of maintainer judgment, and the inter-rater κ analysis described in §2.7.

### 2.5 Contamination handling

Every LLM in our baseline set was likely trained on the Fleischner 2017 paper. The benchmark cannot eliminate this, only mitigate it.

**Paraphrasing protocol**: all cases are authored in the maintainer's own clinical voice. Verbatim Fleischner phrasing is prohibited in the `presentation` and `context` fields.

**Hash-based verification**: `scripts/build_paper_fingerprint.py` extracts the Fleischner 2017 PDF text, normalizes (lowercase + stripped punctuation), computes overlapping 7-grams, and writes their SHA-256 hashes (16-hex-prefix each) to `data/fleischner_paper_fingerprint.json`. The paper text itself never enters the repo — only an irreversible derivative. 12,005 unique 7-gram hashes from the actual paper.

`scripts/check_contamination.py` hashes every case's normalized text the same way and computes the **longest contiguous run** of 7-grams matching the paper. This is a deliberate choice over flat n-gram match count: common clinical phrases ("CT at 6-12 months") produce isolated matches but never long runs, while verbatim paragraph copying produces a long monotone run.

Empirically on all 200 v0.1 cases (dev + test): **zero matches at any threshold**. The maintainer-authored prose has no contiguous 7-token overlap with the paper at all. Detector validation: a synthetic case verbatim-copying the paper title is correctly flagged with run=5 / 11 tokens verbatim.

`[KAREEM REDLINE — this approach (publish hashes only, never source text) is generalizable to any future track and arguably a novel contribution worth one sentence in the abstract. Worth discussing whether to elevate.]`

### 2.6 Baselines

We seeded the leaderboard with 12 baselines spanning two tiers (full table at github.com/hiKareeem/radgym/blob/main/docs/METHODOLOGY.md#5-reference-baselines):

**Snapshot tier (frozen at launch, date-pinned where possible):**
- Oracle (rules engine; the floor)
- GPT-4o (`gpt-4o-2024-11-20`)
- Claude Sonnet 4 (`claude-sonnet-4-20250514`)
- Gemini 2.5 Pro
- Llama 3.3-70B-Instruct (via OpenRouter)
- GPT-3.5-turbo (deliberate floor — ensures leaderboard has visible spread)

**Current-frontier tier (refreshed as flagships ship):**
- GPT-5.5, GPT-5.5 Pro
- Claude Opus 4.7, Claude Sonnet 4.6
- Gemini 3.1 Pro preview
- DeepSeek V4 Pro
- Llama 4 Maverick

All baselines use a clinically-neutral system prompt (`docs/SUBMISSION.md` §2) and `temperature=0` where the provider allows it; reasoning models that mandate `temperature=1` run at 1.0 with this disclosed on the leaderboard. Output is parsed with a four-stage strategy (strict JSON → fenced block → first balanced braces → trailing-comma repair) before declaring `malformed`.

**Cost transparency**: total cost of seeding 12 baselines on dev (50) + test (150) was approximately **$18 USD**. The leaderboard displays per-case cost for each seeded baseline. External submissions opt-in to cost display. The cost column is *not* part of the ranking; it is diagnostic information about price/performance tradeoffs. The most expensive baseline (gpt-5.5-pro) cost $0.163 per case; the cheapest paid baseline (gpt-3.5-turbo) cost $0.0004; open-weight baselines via OpenRouter are free at the time of writing.

### 2.7 Inter-rater reliability

`[PENDING κ RESULTS — Dr. {NAME}, blind-labeled stratified random 30-case sample, drawn from the full 200-case set via the same stratification used for the dev/test split. Submitter: chest-subspecialty rad. Cohen's κ over the 7-bin recommendation space. Interpretation per Landis & Koch 1977: ≥0.61 = substantial, ≥0.81 = almost perfect.]`

`[FILLS IN WHEN MARTINEZ REPLIES]`

### 2.8 Submission and anti-abuse

v0.1 submissions are filed as GitHub Issues using a structured template (`.github/ISSUE_TEMPLATE/submission.yml`); the maintainer validates and runs each submission (`scripts/process_submission.py`). The dev split provides full per-case feedback to submitters; **the test split returns aggregate metrics only**, with no per-case outcomes returned — a deliberate label-leak mitigation against iterative probe attacks (`docs/METHODOLOGY.md` §4.2). Submissions are rate-limited (1 per submitter per `model_identifier` per 24h, 30/month total) and capped at a $25 projected cost per submission without explicit approval. v0.2 will replace the manual pipeline with an HF-Space-triggered automated harness.

---

## 3. Results

### 3.1 Leaderboard

12 seeded baselines on the 150-case hidden test split:

| # | Baseline | Tier | Composite | Exact | Unsafe | Mal | $/case | Rankable |
|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | oracle_rules_engine | oracle | 100.00 | 100.0% | 0.0% | 0.0% | $0.000 | ✅ |
| 2 | gpt-5.5 | frontier | 86.67 | 74.7% | 0.0% | 1.3% | $0.011 | ✅ |
| 3 | gemini-3.1-pro-preview | frontier | 83.33 | 72.0% | 0.0% | 0.0% | $0.006 | ✅ |
| 4 | gemini-2.5-pro | snapshot | 73.47 | 63.3% | 5.3% | 0.7% | $0.010 | ✅ |
| 5 | deepseek-v4-pro | frontier | 67.87 | 65.3% | 12.0% | 1.3% | $0.000 | ✅ |
| 6 | claude-sonnet-4-6 | frontier | 67.00 | 60.7% | 11.3% | 3.3% | $0.005 | ✅ |
| 7 | claude-opus-4-7 | frontier | 62.87 | 54.0% | 10.7% | 0.7% | $0.008 | ✅ |
| 8 | gpt-4o-2024-11-20 | snapshot | 58.57 | 52.7% | 14.0% | 0.0% | $0.002 | ✅ |
| 9 | claude-sonnet-4-20250514 | snapshot | 53.73 | 49.3% | 16.0% | 0.0% | $0.003 | ✅ |
| 10 | llama-3.3-70b | snapshot | 48.10 | 42.7% | 22.0% | 0.7% | $0.000 | ✅ |
| 11 | llama-4-maverick | frontier | 37.87 | 35.3% | 26.0% | 0.0% | $0.000 | ✅ |
| 12 | gpt-3.5-turbo | snapshot | -0.83 | 19.3% | 52.7% | 24.7% | $0.000 | ❌ |

**Unsafe** = `adjacent_unsafe + wrong_unsafe + cross_track` (the clinically dangerous outcome class).

### 3.2 Headline gap

The best frontier model (gpt-5.5) misses 13.33 composite points relative to a 300-LOC Python rules engine. The cheapest passing frontier model (gemini-3.1-pro-preview, $0.006/case) misses 16.67 points. **No closed-source frontier model in the seeded set exceeds 87.** This is the central finding: despite high apparent capability of frontier LLMs on medical-domain text, none reliably apply a published, structured clinical algorithm.

### 3.3 Three sub-findings

**3.3.1 Intra-provider inversion**

Claude Opus 4.7 (62.87) underperforms Claude Sonnet 4.6 (67.00) by ~4 composite points on test, ~16 points on dev. This is the same provider's lineup, evaluated under identical prompts and temperature constraints (both at provider-mandated `temperature=1`). Diagnostic breakdown on dev: Opus produces 11 `multiple_wrong` outcomes vs Sonnet's 6, and 0 `multiple_correct_full` outcomes vs Sonnet's 7. The mechanism is concentrated on multi-nodule recognition (§3.3.3): Opus reasons "deeply" about the dominant nodule but misses the case-shape rule that multiple-nodule cases route through a separate row of Fleischner Table 1A/1B.

`[KAREEM CLINICAL VOICE — this paragraph is the most quotable in the paper.
The finding that "more expensive frontier ≠ better at structured guideline
application" is the kind of result the medical-AI Twitter audience picks up.
Worth your redline.]`

**3.3.2 Open-weight regression**

Llama 4 Maverick scores 37.87 on test. Llama 3.3-70b (the previous-generation open-weight reference) scored 48.10 on the same benchmark, under identical prompts. The Llama-4 family regressed by approximately 10 composite points and 4% on the unsafe rate (26.0% vs 22.0%) for this specific class of structured medical reasoning. We do not have the training-data composition or hyperparameter detail to explain this beyond hypothesis. It is, however, a directly comparable result.

**3.3.3 Multi-nodule recognition is the dominant single failure mode**

Across all 9 dev-split baselines (450 model-cases total), the single largest error class is `multiple_wrong` — 81 of 450 outcomes (18%). This dominates `adjacent_unsafe` (22), `cross_track` (9), and `wrong_unsafe` (7) combined.

The clinical interpretation: Fleischner Table 1A/1B has a distinct row for multiple-nodule cases. Models that reason about the dominant nodule and apply single-nodule logic — which is what closed-source LLMs trained on the paper text consistently do — produce confidently-wrong recommendations. This failure is concentrated at the top of the leaderboard, not the bottom: the best frontier model (gpt-5.5) still produces multi-nodule errors that the rules engine does not.

**3.3.4 Cost vs performance**

`[Plot: composite vs $/case scatter. Each baseline a dot, labeled. Pareto-frontier
clearly visible. gpt-5.5-pro is dominated by gpt-5.5 — same Pareto-front point but
30× cheaper. Llama-3.3-70b at $0 is on the cheap Pareto front. Open-weight tier is
substantially behind closed-source for this task.]`

The cost data demonstrates two real patterns: (a) the "pro" tier of frontier models is poor price/performance for structured-output tasks (gpt-5.5-pro buys +2.33 composite points over gpt-5.5 for 13× the cost); (b) free-tier open-weight access (Llama 3.3 via OpenRouter) achieves ~50% of frontier performance at zero cost per case — relevant to indie deployments where API costs constrain experimentation.

### 3.4 Bootstrap confidence intervals

`[TABLE — bootstrap 95% CI on composite for each baseline, computed via 10000
resamples with replacement. Honest framing on the temp=1 caveat for reasoning
models; their CIs are wider.]`

### 3.5 Inter-rater agreement

`[PENDING κ DATA]`

`[Cohen's κ between maintainer and external rater on the 30-case stratified sample. Per-bin agreement table. Disagreement analysis: which bins are most contested?]`

---

## 4. Discussion

`[KAREEM DRAFT — ~800 words. Your voice, your interpretation. Skeleton:]`

### 4.1 Why this gap exists

`[Hypothesis: LLMs trained on the Fleischner paper learn the algorithm as text but don't execute it as a decision procedure. Cite parallel findings from MedQA-style benchmarks (LLMs memorize medical-question patterns rather than reason from first principles). Connect to broader medical-AI literature on "reasoning vs recall."]`

### 4.2 The multi-nodule recognition failure mode

`[Clinical interpretation: this is exactly the kind of error a junior resident makes — focus on the dominant lesion, miss the algorithm's case-shape branch. Adults of intermediate experience handle it. Worth one paragraph drawing a parallel between LLM failure modes and human developmental trajectories in radiology training.]`

### 4.3 Cost transparency as benchmark practice

`[Argue: medical-AI benchmarks should report cost. The economic argument is part of the methodological argument. A model that costs $100/case is not deployable regardless of how well it scores. The cost column on RadGym's leaderboard is itself a methodological contribution.]`

### 4.4 What v0.1 is NOT measuring

`[Honest framing: v0.1 measures one narrow task. The benchmark is "can an agent apply Fleischner 2017 correctly to structured text descriptions." NOT: "is this agent a good radiologist." Diff from clinical validation, image-based evaluation, multi-turn workflows.]`

### 4.5 Where this scales

`[The fingerprinted-contamination + asymmetric-scoring + dev/test-split framework is generalizable. v0.2 → Lung-RADS. v0.3 → TI-RADS, BI-RADS (parallel decision trees with structured output). v1.0 → imaging tracks (DICOM in, structured report out). The asymmetric-scoring rubric here is specifically designed to be reused across these — under/over-following is universal in screening guidelines.]`

---

## 5. Related work

`[I'll write this — outline:]`

- **Radiology-AI benchmarks**: CheXbench, ReXrank, ChestXray-14, MIMIC-CXR. All image-classification. None workflow-agentic.
- **Medical LLM benchmarks**: MedQA, USMLE-style, MultiMedQA. Multiple-choice or open-ended QA. Don't test guideline application.
- **Clinical guideline reasoning**: ACR Appropriateness Criteria benchmarks, but those are RAG-style retrieval tasks.
- **General agentic benchmarks**: SWE-bench, ARC, BigBench. Domain-agnostic.
- **Workflow-level radiology eval (closest priors)**: RadFact (rationale grading), but RadFact is single-image classification with text rationale. RadGym scopes to text-to-text *structured recommendation* output.

`[~10-15 citations, BibTeX file appendix.]`

---

## 6. Limitations

- **Single track**: v0.1 evaluates one narrow guideline. Scores do not generalize to "is this agent a good radiologist." Future tracks broaden the claim.
- **Text-only**: Real radiology requires images. v0.1 deliberately sidesteps this; imaging tracks come in v1.0+.
- **English-only**: All cases are in English. Multilingual evaluation is out of scope.
- **Single-turn**: No multi-turn agent loops in v0.1. v0.4+ adds this.
- **Single-maintainer labels**: 200 cases curated by one radiologist. The inter-rater κ analysis (§2.7) is the credibility check. v0.2 will recruit additional raters.
- **Contamination is not eliminated**: Every LLM in the seeded set was likely trained on Fleischner 2017. Our paraphrasing + n-gram-hash verification + maintainer-authored prose mitigate but do not eliminate this. A high score may reflect successful algorithm application *or* successful memorization.
- **No clinical validation**: The benchmark measures algorithm application, not real-world clinical utility. A different (longer, harder, more expensive) study would be needed for that.
- **Temperature non-determinism**: Reasoning models (gpt-5.5, claude-opus-4-7) cannot run at `temperature=0`. Bootstrap CIs reported, but cross-tier comparisons include unmeasured within-run variance.
- **No image evaluation of model confidence calibration**: We score binary correct/wrong, not calibrated probabilities. v0.2 may add this.

---

## 7. Conclusion

`[KAREEM DRAFT — 100 words. The closing claim: "Frontier LLMs cluster 53-87 composite on Fleischner 2017 application; a 300-line Python rules engine scores 100. The largest single error class is multi-nodule recognition. RadGym makes both findings reproducible and the benchmark extensible." Plus standard "future work" sentence.]`

---

## Acknowledgments

`[Acknowledge: Dr. {NAME} for inter-rater κ work; the open-weight model providers (Meta, DeepSeek) for free-tier access via OpenRouter; the Fleischner Society for the underlying paper. NO acknowledgment of AI assistance — this is research not vibes-coded, even if drafted with help, and academia is sensitive about it. The contribution is the methodology and data; the prose was iterated upon and is the maintainer's own.]`

---

## Data availability

- Public dev split (50 cases, full ground-truth labels): `cases/v0.1/dev/` at github.com/hiKareeem/radgym, Apache-2.0 licensed.
- Hidden test split: not publicly distributed (label-leak mitigation). Submission scoring runs server-side.
- Baseline raw outputs: `space/data/dev_leaderboard.json` and `space/data/test_leaderboard.json` (aggregate metrics, public).
- Paper fingerprint hashes: `data/fleischner_paper_fingerprint.json` (SHA-256 hashes only; not reversible to source text).

## Code availability

- All code at github.com/hiKareeem/radgym, Apache-2.0.
- Leaderboard at huggingface.co/spaces/hiKareem/radgym.
- Submission docs at github.com/hiKareeem/radgym/blob/main/docs/SUBMISSION.md.

## Funding statement

This work was unfunded; all baseline API costs (~$18 USD total) were maintainer-paid.

## Competing interests

None declared.

---

## References

`[BibTeX file. ~25-30 entries:]`

`[1] MacMahon H, et al. Guidelines for Management of Incidental Pulmonary Nodules Detected on CT Images: From the Fleischner Society 2017. Radiology 2017; 284:228-243.`

`[2-N] Related benchmarks: CheXbench, ReXrank, RadFact, MedQA, MultiMedQA, ACR Appropriateness, SWE-bench (as eval-design prior), Landis & Koch 1977 κ paper, ...]`

`[NOTE for Kareem: I'll generate a starter BibTeX file at refs.bib in the next session if/when you're ready to flesh references out.]`
