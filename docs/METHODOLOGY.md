# RadGym — Methodology (v0.1)

**Document status:** v0.1 design draft, awaiting maintainer redline.
**Last updated:** 2026-05-15
**Companion doc:** `CONCEPT.md` (the *why*); this doc is the *how*.

> **Where the canonical definitions live.** This document is the human-readable spec. The authoritative implementation is in code:
>
> - **Schemas (input, output, ground truth):** `radgym/schemas.py` — `Case`, `Nodule`, `Patient`, `AgentResponse`, `GroundTruth`, `CaseRecord`. All Pydantic v2 strict; validators enforce the conditional-required rules described here (e.g., `dominant_nodule_recommendation` iff `recommendation == multiple_nodule_dominant`; `additional_nodules` non-empty iff `multiplicity == multiple`).
> - **Oracle / rules engine:** `radgym/oracle.py` — Fleischner 2017 Table 1A/1B as executable code. Verified cell-by-cell by `tests/test_fleischner_table1.py` (19/19 launch gate).
> - **Scoring:** `radgym/scoring.py` — adjacency tracks, asymmetric outcomes, multiple-nodule decision table, aggregation.
>
> When this document and the code disagree, the code is authoritative. External reviewers should read both. A pointer to each code location appears at the head of the relevant section below.

---

## 1. Track definition: Fleischner 2017 follow-up

### 1.1 Source

MacMahon H, et al. "Guidelines for Management of Incidental Pulmonary Nodules Detected on CT Images: From the Fleischner Society 2017." *Radiology* 2017;284(1):228-243. doi:10.1148/radiol.2017161659

Scope: incidental pulmonary nodules detected on CT in patients ≥35 years old, **excluding**:

- Lung cancer screening (Lung-RADS, future track)
- Patients with known primary cancer
- Immunocompromised patients
- **Nodules with classic benign features** — fat density of hamartoma, popcorn calcification, diffuse/central/laminated benign-pattern calcification, perifissural triangular morphology classic for intrapulmonary lymph node. Fleischner 2017 explicitly says these "do not require routine follow-up per these guidelines" because the diagnostic question is answered by morphology, not the algorithm. Cases with these features are out-of-scope for v0.1 because they bypass the algorithm entirely. A future track (v0.2+) may add a `benign_features_no_followup` bin that captures the *recognition* of benign features as a distinct reasoning task — until then, the v0.1 test set contains only cases where Fleischner 2017's size+density+risk algorithm is the active decision path.

### 1.2 Input schema (per case)

Strict JSON. Fields are exhaustively listed; submitters can rely on the schema being stable through v0.1.

```jsonc
{
  "case_id": "RGYM-v01-XXXX",           // stable identifier, zero-padded 4-digit
  "presentation": "string",              // 1-3 sentence clinical context
  "nodule": {
    "type": "solid" | "sub_solid_ground_glass" | "sub_solid_part_solid",
    "size_mm": number,                   // long-axis, integer or 1-decimal
    "multiplicity": "single" | "multiple",
    "morphology": "smooth" | "lobulated" | "spiculated" | "unspecified",
    "location": "upper_lobe" | "middle_lobe" | "lower_lobe" | "lingula" | "unspecified",
    "additional_nodules": [              // present only if multiplicity = multiple
      { "type": "...", "size_mm": ..., "morphology": "..." }
    ]
  },
  "patient": {
    "age": integer,
    "smoking_history": "never" | "former" | "current" | "unknown",
    "pack_years": number | null,
    "asbestos_exposure": boolean,
    "family_history_lung_ca": boolean,
    "emphysema": boolean,
    "pulmonary_fibrosis": boolean,
    "known_primary_cancer": boolean,     // if true, case is excluded from v0.1 — see below
    "immunocompromised": boolean         // if true, case is excluded from v0.1 — see below
  },
  "context": "string"                    // free-text framing for the agent
}
```

The `known_primary_cancer` and `immunocompromised` flags are kept in the schema even though Fleischner 2017 excludes these patients. Reasons: (a) parser sanity — a mis-curated out-of-scope case is rejected loudly at `Case` construction time rather than silently scored; (b) forward-compat — v0.3+ may add an `out_of_scope_per_fleischner` bin where the agent must *recognize* exclusion as a reasoning task. v0.1's test set filters these out at curation; they never reach the agent.

**Risk-factor encoding rationale**: v0.1 exposes individual risk-factor fields rather than a pre-computed `risk_category` binary because part of what we're measuring is whether the agent correctly *derives* high vs low risk from the case. The exact rule encoded in `radgym/oracle.py::derive_risk()` is: smoker (current or former) OR asbestos OR family history of lung CA OR emphysema OR pulmonary fibrosis → high; otherwise → low.

**Age is deliberately excluded from the v0.1 heuristic risk derivation.** Fleischner 2017 lists "older age" as a high-risk contributor but specifies no numeric threshold; the published recommendation is to "consider all relevant risk factors" without a formula. Hard-coding any age threshold (≥60? ≥65? ≥70?) into the heuristic would be a maintainer choice that the paper does not authorize. v0.1 keeps the heuristic conservative — it captures the unambiguous risk modifiers and leaves age judgment to the maintainer-assigned risk override (`GroundTruth.maintainer_assigned_risk`). Agents are still free to consider age in their reasoning; the heuristic is only a sanity-check baseline, not the source of ground-truth risk classification (see §2.2 and §2.4).

**Heuristic vs ground-truth risk separation.** Because Fleischner does not provide a mechanical risk formula, ground-truth risk is the maintainer's clinical synthesis, stored in `GroundTruth.maintainer_assigned_risk`. The oracle accepts a `risk_override` parameter and uses the maintainer's assignment when computing the Table 1 lookup; `derive_risk()` is invoked only as a fallback diagnostic.

### 1.3 Output schema (per case)

```jsonc
{
  "case_id": "RGYM-v01-XXXX",
  "recommendation": "<one of the bin IDs from CONCEPT §4.3>",
  "dominant_nodule_recommendation": "<bin ID, REQUIRED iff recommendation == 'multiple_nodule_dominant', else null/omitted>",
  "rationale": "string"                   // collected; not scored in v0.1
}
```

Strict JSON, validated by Pydantic on receipt. Malformed outputs score 0 for that case with a `malformed_output` flag.

The conditional-required rule for `dominant_nodule_recommendation` is enforced by `radgym/schemas.py::AgentResponse._multiple_requires_dominant()` — `dominant_nodule_recommendation` MUST be present when `recommendation == "multiple_nodule_dominant"` and MUST be null/omitted otherwise. A response violating this rule is `malformed`. The canonical Pydantic models live in `radgym/schemas.py` (`AgentResponse`, `Case`, `GroundTruth`, `Nodule`, `Patient`); when this doc and the code disagree, the code is authoritative.

### 1.4 Recommendation bins (canonical list)

See `CONCEPT.md` §4.3. The full mapping from case features to bin is encoded in `radgym/oracle.py`. This oracle:

- Is the deterministic Fleischner 2017 algorithm in code.
- Is the answer key for scoring.
- Is also a reference baseline ("rules engine" — submitted publicly to the leaderboard via a thin wrapper in `radgym/baselines/oracle_baseline.py`, which converts `OracleResult` into a valid `AgentResponse` JSON for leaderboard submission).
- **Is verified against the verbatim Fleischner 2017 Table 1 by `tests/test_fleischner_table1.py` (19/19 cells round-trip — the launch gate).**
- **Is reviewed by the maintainer (radiology background) for clinical correctness before any case is scored.**

## 2. Case construction

### 2.1 Sources

200 cases for v0.1, sourced from:

| Source | Approx. count | Use type |
|---|---|---|
| Fleischner 2017 paper worked examples (Table 1 + body) | ~20 | Direct application of the published examples; also encoded in `tests/test_fleischner_paper_examples.py` as the launch gate |
| OpenI (NLM Open-i) excerpts mentioning pulmonary nodules | ~30 | Pulled from public NLM data |
| Radiology Assistant public articles on nodule workup | ~20 | Paraphrased illustrative cases |
| Synthetic cases (maintainer-authored) | ~130 | Edge cases, bin boundaries, risk-factor combinations |

**Radiopaedia is deliberately excluded as a source.** Their content is CC BY-NC-SA, and the NC clause creates an unresolvable question about whether a commercial vendor benchmarking their model against RadGym constitutes commercial use of derivative data. v0.1 sidesteps this entirely by sourcing only from (a) factual algorithm-output content (Fleischner paper examples — facts about an algorithm's output are not copyrightable), (b) public-domain NLM data (OpenI), (c) maintainer-authored synthetic cases. Radiology Assistant cases are paraphrased to the maintainer's own clinical voice, and only the *structural pattern* of a case is borrowed, not the prose.

Every case has a `source` field in its JSON metadata. Public-source cases reference the original (URL or DOI); synthetic cases note `source: synthetic_maintainer_authored`.

### 2.2 Curation procedure

The maintainer (Kareem Albaba, MD — 3-year radiology residency, chest as confident subspecialty) personally constructs or reviews every case. For each case:

1. **Construct or extract** the clinical narrative.
2. **Encode** the structured fields per §1.2.
3. **Determine the ground-truth recommendation** by applying Fleischner 2017 directly. **The maintainer commits to a label *before* seeing the oracle's prediction** — the case authoring tool deliberately exposes the maintainer's answer first, oracle second, to avoid anchoring on the algorithm.
4. **Record any ambiguity** in a `notes` field — cases with genuine ambiguity (e.g., size exactly at a threshold, mixed risk factors) are flagged for either inclusion (as deliberate edge cases) or exclusion.
5. **Cross-check** against `radgym/oracle.py` — disagreements between the maintainer's label and the oracle are resolved before the case enters the test set. Three possible resolutions:
    - Maintainer's reading of Fleischner was wrong → label updated to oracle.
    - Oracle has a bug → fix oracle, re-run all existing cases.
    - Case is genuinely outside Fleischner's algorithmic scope (e.g., benign features, prior comparison) → exclude.

### 2.3 Inter-rater reliability

External review identified single-maintainer labeling as the largest credibility gap. **Pre-launch plan**: once ~50 cases are curated, recruit ≥1 external radiologist (target: chest-interested resident or fellow, secondary plan: paid attending moonlighter) to blind-label a random 30-case sample. Report Cohen's κ in METHODOLOGY before tagging v0.1.0. Disagreements are reviewed by both raters and resolved by reference to the Fleischner 2017 paper; if neither rater can reconcile, the case is excluded from the test set.

### 2.4 Oracle vs ground truth — separation of concerns

External review item #6 noted a circularity risk where the oracle simultaneously labels cases, scores submissions, and serves as a baseline. Mitigations in v0.1:

- **Maintainer-first labeling**: the case authoring tool prompts the maintainer for the recommendation before showing the oracle's prediction. Labels are the maintainer's, not the oracle's.
- **Independent paper-example gate**: `tests/test_fleischner_paper_examples.py` round-trips ~12 worked examples from MacMahon 2017 against the oracle. The oracle must produce the paper's stated answer 100% of the time before v0.1 ships. This is an external validation of the oracle independent of the maintainer's own labels.
- **Inter-rater κ**: see §2.3.
- **v0.2 stretch goal**: an independently-reimplemented baseline rules engine (separate from `radgym/oracle.py`) that scores against the same hidden test set. Disagreement between the two implementations of the algorithm would surface ambiguity in the algorithm itself.

### 2.5 Public vs hidden split

- **Public dev split (50 cases)**: published in `cases/v0.1/dev/`. Used by submitters to debug their prompts. Includes ground-truth labels.
- **Hidden test split (150 cases)**: never published. Lives in a private Git submodule or a HuggingFace private dataset. Submissions are scored against this split, and **only aggregate metrics are returned to submitters** (see §4.2).

Both splits draw from the same source mix and the same distribution of bin labels.

### 2.6 Contamination resistance

LLM training data inevitably includes Fleischner 2017 and likely includes Radiology Assistant case writeups. RadGym addresses this:

1. **Paraphrasing**: All extracted cases are paraphrased by the maintainer; verbatim language from the source guideline or case database is avoided in the `presentation` and `context` fields.
2. **Structural variation**: The clinical narrative is rewritten so that surface n-grams differ from the source. The *clinical content* is preserved; the *prose* is not.
3. **N-gram overlap as a CI gate (refined per external review #10)**: the contamination check is implemented in `scripts/check_contamination.py` and runs in GitHub Actions on every PR (`.github/workflows/ci.yml`). The pipeline:
    - `scripts/build_paper_fingerprint.py` extracts the Fleischner 2017 paper text from the PDF, normalizes to lowercase + stripped punctuation, computes overlapping 7-grams, and writes the **SHA-256-hashed** n-gram set to `data/fleischner_paper_fingerprint.json`. (Hashes only — the paper text never enters the repo.) 12,005 unique 7-gram hashes from the actual paper.
    - `scripts/check_contamination.py` computes the same 7-grams over every case's `presentation` + `context` text, finds the longest *contiguous run* of n-grams whose hashes appear in the paper, and fails CI if any case exceeds a 4-run threshold (~10+ tokens verbatim).
    - **Why contiguous run length, not raw match count**: common clinical phrases like "CT at 6-12 months" produce isolated matches but never long runs. Verbatim paragraph copying produces a long monotone run. This addresses the false-positive concern: a flat n-gram-count threshold would have flagged unavoidable common phrasing. Empirically on v0.1's 200 cases the worst case has 0 matching n-grams.
    - CI runs the check on the public dev split (the test split is gitignored). The maintainer runs the check locally on the full 200 before tagging a release.
4. **Synthetic edge cases**: ~65% of the test set is fully synthetic, parameterized along the Fleischner decision tree to ensure coverage of bin boundaries.
5. **No verbatim Fleischner clauses** appear in any case. The agent must apply the algorithm; it cannot pattern-match memorized text.
6. **Hidden test set** is never published, period. Submission outputs are returned to the submitter as aggregate metrics; the test cases themselves and per-case outcomes are not.

This is not contamination-proof — no benchmark can be against a model that *has* seen Fleischner 2017 — but it makes "memorize verbatim" less useful than "apply the algorithm."

### 2.7 Case distribution

Target distribution for v0.1 (subject to maintainer revision):

| Top-level `recommendation`         | Target N | Target % | Rationale                                                  |
| ---------------------------------- | -------- | -------- | ---------------------------------------------------------- |
| `no_routine_followup`              | 30       | 15%      | Common but trivial — small floor                           |
| `optional_ct_12mo`                 | 30       | 15%      | Tests low-/high-risk distinction at <6 mm                  |
| `ct_6_12mo_then_18_24mo_if_stable` | 30       | 15%      | Mid-range, common bin                                      |
| `subsolid_workup`                  | 30       | 15%      | Tests sub-solid handling (covers GGN q2y/5y and part-solid annual/5y; v0.2 will split) |
| `consider_pet_or_biopsy`           | 30       | 15%      | Tests recognition of higher-risk findings                  |
| `multiple_nodule_dominant`         | 50       | 25%      | All multiple-nodule cases; sub-bin distribution below      |
| **Total**                          | **200**  | **100%** |                                                            |

**Note on `ct_3_6mo_then_18_24mo`:** This bin is unreachable as a top-level single-nodule recommendation per Fleischner 2017. Table 1A produces it only in multiple-row cells (multiple solid 6-8mm low, multiple solid 6-8mm high, multiple solid >8mm low, multiple solid >8mm high — 4 of 6 multiple-solid cells route here). Table 1B and the body text contain no single-nodule path producing this recommendation. The bin therefore lives exclusively as a `dominant_nodule_recommendation` value under `multiple_nodule_dominant`. This is intentional — it reflects how Fleischner's algorithm actually behaves, not a curation gap. Distribution targets within `multiple_nodule_dominant`:

| Sub-bin (`dominant_nodule_recommendation`) | Target N | Rationale                                                                                                                                                                                              |
| ------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `ct_3_6mo_then_18_24mo`                    | 30       | Where most multiple-nodule branches converge (4 of 6 Table 1A multiple-solid cells)                                                                                                                    |
| `subsolid_workup`                          | 10       | Multiple-subsolid cases (both Table 1B multiple cells route here)                                                                                                                                      |
| `no_routine_followup`                      | 3        | Multiple solid <6mm low-risk (one Table 1A cell)                                                                                                                                                       |
| `optional_ct_12mo`                         | 3        | Multiple solid <6mm high-risk (one Table 1A cell)                                                                                                                                                      |
| `consider_pet_or_biopsy`                   | 4        | NOT produced by the oracle for any v0.1 case; reachable only when an agent recognizes a clinically-worrisome dominant nodule (e.g., large part-solid with concerning features — the v0.2 PET-routing case per §3.3) |
| **Sub-bin total**                          | **50**   |                                                                                                                                                                                                        |

This distribution is **uniform-ish across top-level bins for benchmark resolution, not weighted by clinical prevalence.** Real-world incidental nodules are overwhelmingly <6mm — a prevalence-weighted benchmark would be ~70% `no_routine_followup` cases, which would (a) inflate exact_accuracy scores trivially, (b) provide little discrimination between agents on the harder bins, (c) hide failures on rare-but-critical cases. A `clinical_prevalence_weighted` secondary score may be added in v0.2 for those who want it; v0.1's headline composite is uniform-bin. `multiple_nodule_dominant` is the one bin allocated more than 15% — this reflects that it absorbs the entire Fleischner Table 1A multiple-row branch space, which alone produces 6 algorithmically distinct sub-bin × risk combinations. Scoring (§3.4) exercises top-level and sub-bin separately, so sub-bin coverage genuinely matters for benchmark sensitivity.

Within each bin we deliberately over-sample bin boundaries (nodules at exactly 6 mm and 8 mm) to discriminate agents that approximate Fleischner from agents that truly apply it.

## 3. Scoring

### 3.1 Scoring function (v0.1)

For each case, the agent's recommendation is compared to ground truth on the *appropriate adjacency track* (see §3.3). Let:

- `correct` = recommended bin equals ground-truth bin
- `adjacent_safe` = recommended bin is one step toward *more aggressive* follow-up than ground truth, on the same track (over-following by one)
- `adjacent_unsafe` = recommended bin is one step toward *less aggressive* follow-up than ground truth, on the same track (under-following by one)
- `wrong_safe` = ≥2 bins over-following, same track
- `wrong_unsafe` = ≥2 bins under-following, same track
- `cross_track` = recommended bin is on the wrong track (e.g., `subsolid_workup` on a solid-nodule case, or `optional_ct_12mo` on a sub-solid case). Scored as `wrong_unsafe`-equivalent because the agent picked the wrong *kind* of follow-up.
- `malformed` = output failed schema validation

Per-case score:

| Outcome | Points |
|---|---|
| `correct` | 1.00 |
| `adjacent_safe` | 0.50 |
| `adjacent_unsafe` | -0.25 |
| `wrong_safe` (off by ≥2, over-following) | 0.00 |
| `wrong_unsafe` (off by ≥2, under-following) | -0.50 |
| `cross_track` (wrong follow-up type) | -0.50 |
| `malformed` | 0.00 |

**Composite score for a submission** = `100 × (sum of per-case scores) / N`. The composite is bounded to `[-50, 100]`. Typical good agents fall in `[40, 90]`.

### 3.2 Why asymmetric

Under-following a Fleischner-flagged nodule means missing a potentially malignant lesion — the clinically dangerous failure mode. Over-following means extra imaging cost and patient anxiety — a real harm but a recoverable one. The score reflects this asymmetry, matching the maintainer's clinical instinct.

Why is `malformed` scored 0.00 (above `wrong_unsafe`) rather than penalized harder? Maintainer judgment call: a malformed output is *engagement failure* — the agent refused or broke. A `wrong_unsafe` output is *engaged dangerously* — the agent confidently recommended undertreatment. We prefer agents that fail loudly (malformed) to agents that fail silently into harm (`wrong_unsafe`), so malformed sits above unsafe in the scoring.

### 3.3 Adjacency tracks

**Solid track** (least → most aggressive follow-up):

1. `no_routine_followup`
2. `optional_ct_12mo`
3. `ct_6_12mo_then_18_24mo_if_stable`
4. `ct_3_6mo_then_18_24mo`
5. `consider_pet_or_biopsy`

**Sub-solid track** (least → most aggressive):

1. `no_routine_followup`
2. `subsolid_workup`
3. `consider_pet_or_biopsy`

`no_routine_followup` and `consider_pet_or_biopsy` are *shared* — they are the floor and ceiling of both tracks. A recommendation of `no_routine_followup` when truth is `subsolid_workup` scores `adjacent_unsafe` on the sub-solid track (under-following by one), NOT cross-track.

**v0.1 simplification**: the oracle never *outputs* `consider_pet_or_biopsy` for subsolid cases in v0.1 because the part-solid "solid component ≥6mm with concerning features → PET/biopsy" rule from Table 1B requires solid-component size, which v0.1's schema does not collect (deferred to v0.2). However, the bin is still reachable by *agents*: an agent that correctly identifies a part-solid nodule with worrisome features in the case prose is free to recommend `consider_pet_or_biopsy`, and would score `adjacent_safe` (over-following by one) against a v0.1 ground-truth `subsolid_workup`. This is a known scoring asymmetry: agents can be more clinically nuanced than the oracle and still score well, just not perfectly. v0.2 will fix this by adding solid-component size to the schema.

`multiple_nodule_dominant` is special-cased and not on any track (see §3.4).

External review flagged that an earlier draft put `subsolid_workup` at position 5 of a single linear axis, which produced the wrong outcome class for cross-track recommendations. The fix (this section) is encoded canonically in `radgym/scoring.py::_classify_against_truth()`.

### 3.4 Multiple-nodule scoring (complete decision table)

Multiple-nodule scoring is intricate because two orthogonal things must match: (a) the agent recognized the case as multiple (`recommendation == multiple_nodule_dominant`), and (b) the agent's `dominant_nodule_recommendation` matches what Table 1A/1B's multiple-row prescribes. Below is the complete `(ground_truth_recommendation, agent_recommendation, dominant_subbin_outcome) → points` table, in lockstep with `radgym/scoring.py::_score_multiple()` and `score_case()`. The code is authoritative.

#### Case A: ground truth is `multiple_nodule_dominant`

| Agent picks `multiple_nodule_dominant`? | Sub-bin outcome (agent's `dominant_nodule_recommendation` vs truth's) | Points | Outcome label |
|---|---|---|---|
| Yes | `correct` (sub-bin matches) | **+1.00** | `multiple_correct_full` |
| Yes | `adjacent_safe` | +0.25 | `multiple_correct_partial` |
| Yes | `adjacent_unsafe` | -0.10 | `multiple_correct_partial` |
| Yes | `wrong_safe` | 0.00 | `multiple_correct_partial` |
| Yes | `wrong_unsafe` | -0.25 | `multiple_correct_partial` |
| Yes | `cross_track` | -0.25 | `multiple_correct_partial` |
| **No** (agent missed multiplicity, picked a single-nodule bin) | `correct` (single-bin matches the multiple-rule sub-bin) | +0.50 | `multiple_wrong` |
| **No** | `adjacent_safe` | +0.25 | `multiple_wrong` |
| **No** | `adjacent_unsafe` | -0.15 | `multiple_wrong` |
| **No** | `wrong_safe` | 0.00 | `multiple_wrong` |
| **No** | `wrong_unsafe` | -0.30 | `multiple_wrong` |
| **No** | `cross_track` | -0.30 | `multiple_wrong` |

The "Yes" rows are roughly 0.5× the single-nodule scoring magnitudes (max ±0.25 vs ±0.50) because correctness on multiples requires two things; getting one right deserves partial but not full credit. The "No" rows are roughly half of single-nodule magnitudes again, reflecting that the agent missed multiplicity recognition entirely. Both are deliberately less harsh than the single-nodule scale at the unsafe extreme to avoid double-counting the recognition penalty.

#### Case B: ground truth is a single-nodule bin, but agent hallucinated `multiple_nodule_dominant`

The agent's `dominant_nodule_recommendation` is compared to the ground-truth bin using the same `_classify_against_truth` outcomes. The resulting outcome's standard `POINTS` value is multiplied by 0.5 (half credit, reflecting the recognition error).

| Sub-bin outcome (agent's `dominant_nodule_recommendation` vs truth) | Half-weight points |
|---|---|
| `correct` | +0.50 |
| `adjacent_safe` | +0.25 |
| `adjacent_unsafe` | -0.125 |
| `wrong_safe` | 0.00 |
| `wrong_unsafe` | -0.25 |
| `cross_track` | -0.25 |

If the agent picked `multiple_nodule_dominant` but failed to provide `dominant_nodule_recommendation`, the response is `malformed` (the schema validator rejects it). In the unlikely event the validator is bypassed, the fallback outcome is `wrong_safe * 0.5 = 0.00`.

#### Case C: ground truth is a single-nodule bin, agent also single-nodule

Standard adjacency-track scoring per §3.1 — no multiple-nodule rules involved.

The full table is implemented as two `dict[Outcome, float]` lookup tables in `radgym/scoring.py` (`partial_table` and `half_points_table`) and is the source of truth. Any future scoring change MUST update both this section and those tables together, and bump the `scoring_version` field on the leaderboard.

### 3.5 Reported metrics

The leaderboard reports for each submission:

- **`composite`** — the headline number (the asymmetric score, primary ranking).
- **`exact_accuracy`** — % of cases with `correct` or `multiple_correct_full` outcome (familiar baseline metric).
- **`under_following_rate`** — % of cases scored as `adjacent_unsafe`, `wrong_unsafe`, or `cross_track`. **The "safety" metric.** Lower is better.
- **`over_following_rate`** — % scored as `adjacent_safe` or `wrong_safe`.
- **`cross_track_rate`** — % scored as `cross_track`. Surfaces a specific failure mode (agent picked the wrong follow-up type).
- **`malformed_rate`** — % of malformed outputs (a robustness metric).

A submission is **not** rankable if `malformed_rate > 5%` — the agent failed to follow the output schema reliably enough to be evaluated. (External review #4 flagged the original 10% threshold as wide enough to incentivize strategic refusal: an agent could output malformed JSON on its hardest 10% of cases — which would otherwise score `wrong_unsafe` (-0.50) — and gain ~5 composite points over an honest agent. 5% closes that gaming margin while preserving the "humility is okay on genuinely difficult cases" incentive that motivates the `malformed=0.00` value in the first place.)

Per-bin confusion matrices are computed internally but are **not** returned to external submitters in v0.1 (see §4.2 for the label-leak rationale). Aggregate per-bin accuracy may be returned in v0.2 once submission rate-limiting is in place.

### 3.6 Statistical reporting

With N=150, bootstrap 95% CIs are computed for the composite and shown next to point estimates. Submissions whose CI overlaps the rules-engine baseline are flagged as "not distinguishable from oracle" — useful information, not a penalty.

**Determinism caveat**: `temperature=0` is not reproducible across providers (OpenAI fingerprint drift, Anthropic small-numerical variation, batched HF endpoints). v0.1 commitments:

- Each submission records the provider's `system_fingerprint` (OpenAI) or equivalent (where available) at run time.
- Submissions from closed APIs pin the exact model identifier including date (e.g., `gpt-4o-2024-11-20`, not `gpt-4o`).
- A submission is re-run if and only if the maintainer suspects scoring infrastructure error (not for routine variance). Re-runs are visible in the submissions log with both runs' scores.
- Two runs of the same submission may produce composite scores differing within the bootstrap CI; the leaderboard ranks on the most recent run. We do *not* claim deterministic reproducibility for closed APIs in v0.1.
- v0.2 will add majority-of-3 sampling for closed-API submissions, which converts the variance from a ranking risk into a scoring noise floor.

## 4. Submission

### 4.1 v0.1 submission format

A submission is a JSON file with:

```jsonc
{
  "submission_name": "string",            // human-readable, e.g. "claude-4-fleischner-coT-v1"
  "submitter": "string",                  // github handle, email, or org
  "model_identifier": "string",           // e.g. "gpt-4o-2024-11-20", "claude-sonnet-4-20250514", "medgemma-27b-it@hf"
  "model_provider": "openai" | "anthropic" | "google" | "huggingface" | "openrouter" | "custom",
  "system_prompt": "string",              // full system prompt — counts toward "is this submission unique"
  "user_prompt_template": "string",       // Jinja2 template; receives the case JSON as `case`
  "decoding": {
    "temperature": number,                // typically 0 for deterministic scoring
    "top_p": number,
    "max_tokens": integer
  },
  "submitter_provided_api_key": boolean,  // if true, submitter pastes key into the HF Space form
  "notes": "string"                       // optional, public, shown on leaderboard
}
```

### 4.2 Submission flow (v0.1)

1. Submitter fills the form on the HF Space (or PRs a JSON file to `submissions/`).
2. The leaderboard runs the model on the hidden test set: for each case, fills the user-prompt template, calls the model, parses the JSON output.
3. Scores are computed and posted to the leaderboard.
4. **Submitter receives only aggregate metrics** (composite, exact_accuracy, under/over_following_rate, cross_track_rate, malformed_rate). Per-case outcomes are NOT returned. **Why**: external review identified that per-case feedback combined with unbounded prompt variants enables iterative label probing — a submitter could binary-search the hidden test set's labels across many submissions. v0.1 closes this leak by returning aggregates only. v0.2 will reintroduce per-case feedback once submission rate-limiting and per-submitter caps are in place (see §4.3).
5. The dev split (50 cases) ships with ground-truth labels, so submitters can debug prompts against full per-case feedback without touching the hidden set.

### 4.3 Anti-abuse controls

External review flagged several submission-abuse vectors. v0.1 controls:

- **Rate limit**: 1 submission per submitter per 24 hours per model identifier. Submitter is identified by GitHub handle (verified via HF Spaces OAuth where possible) — not a perfect anti-sybil, but raises the cost.
- **Monthly cap**: maximum 30 submissions per GitHub identity per calendar month across all model identifiers. Combined with aggregate-only feedback, this caps the information a single actor can extract from the hidden set.
- **Cost cap**: each submission is capped at a maximum total inference cost (token budget × case count) computed at submission time. Submissions exceeding the cap are rejected before running.
- **Prompt size limit**: `system_prompt` ≤ 16k chars, `user_prompt_template` ≤ 4k chars. Prevents prompt-flood attacks against maintainer API quotas.
- **No streaming / no tool calls** in v0.1. Single request/response per case.
- **Submitter-provided API key required for closed-source providers** when monthly cap is exceeded. Maintainer-funded API budget covers initial baselines + a per-user free quota; beyond that, submitters bring their own key.

### 4.4 What counts as a "different" submission

A submission is considered different from another if **any** of `model_identifier`, `system_prompt`, `user_prompt_template`, or `decoding.temperature` differ. This lets the leaderboard show prompt-engineering wins as distinct entries. The 30/month cap prevents this from becoming a spam vector.

### 4.5 Submitter-provided API keys

For closed-source models (OpenAI, Anthropic, Google), submitters can paste their API key into the HF Space's per-session secret field. The key is used only for that submission's evaluation and is not persisted. For open-weight models on HuggingFace, RadGym uses HuggingFace Inference Endpoints (no key required from submitter; rate-limited).

### 4.6 Cost model

Maintainer-paid costs at launch:
- 7 baselines × 200 cases × ~500 output tokens × current per-1M-token prices ≈ $5-15 one-time.
- Per-user free quota: 1 free submission per GitHub identity per month using maintainer-funded API budget; beyond that, BYO key.

Total maintainer cost projected at <$50/month at the expected v0.1 submission rate. If submission volume exceeds projections, the free quota is reduced before any other change.

## 5. Reference baselines

> **Canonical implementation:** `radgym/baselines/presets.py` — `PRESET_BASELINES` (snapshot) and `CURRENT_FRONTIER_BASELINES` (refresh-on-flagship), unified at `ALL_BASELINES`. The launch leaderboard runs both tiers and displays them as separate tabs.

The maintainer runs these baselines on the hidden test set before public launch. They serve two distinct purposes, captured by a two-tier system:

### 5.1 Snapshot baselines (frozen at launch)

**Purpose**: reproducibility anchors. Date-pinned model IDs where available. Once a submission has scored against these, the scores never change. Paper-citable.

| Baseline | Model identifier | Notes |
|---|---|---|
| **Rules engine** | `radgym.baselines.oracle_baseline` | Encodes Fleischner 2017 Table 1A/1B literally. Should score near 100. The benchmark floor. |
| **GPT-4o** | `openai/gpt-4o-2024-11-20` | OpenAI Nov-2024 frontier reference. |
| **Claude Sonnet 4** | `anthropic/claude-sonnet-4-20250514` | Anthropic May-2025 reference. |
| **Gemini 2.5 Pro** | `gemini/gemini-2.5-pro` | Google reasoning model. `reasoning_effort=low` to cap hidden thinking budget. |
| **Llama-3.3-70B-Instruct** | `openrouter/meta-llama/llama-3.3-70b-instruct` | Open generalist reference. |
| **GPT-3.5-turbo** | `openai/gpt-3.5-turbo` | Deliberate floor — ensures the leaderboard has visible spread. |

MedGemma-27B was originally planned as a sixth open-weight baseline but is deferred to v0.2 because OpenRouter does not host it; v0.2 will set up a local Ollama or vLLM endpoint to enable it.

### 5.2 Current frontier baselines (refresh-on-flagship)

**Purpose**: "what is SOTA today" view. Non-date-pinned aliases that follow whatever the provider currently calls their flagship. Refreshed when a new flagship ships: the previous current-frontier rolls into §5.1 with a resolved date stamp, the new flagship takes its place. The current registry tag is `CURRENT_FRONTIER_REGISTRY_TAG` in `presets.py`.

| Baseline | Model identifier | Notes |
|---|---|---|
| **GPT-5.5** | `openai/gpt-5.5` | OpenAI current frontier as of 2026-05-18. |
| **GPT-5.5 Pro** | `openai/gpt-5.5-pro` | OpenAI pro tier. |
| **Claude Opus 4.7** | `anthropic/claude-opus-4-7` | Anthropic current frontier (Opus tier). |
| **Claude Sonnet 4.6** | `anthropic/claude-sonnet-4-6` | Anthropic current frontier (Sonnet tier). |
| **Gemini 3.1 Pro preview** | `gemini/gemini-3.1-pro-preview` | Google current frontier (preview). Reasoning model — same `reasoning_effort=low` cap as Gemini 2.5 Pro. |
| **DeepSeek V4 Pro** | `openrouter/deepseek/deepseek-v4-pro` | DeepSeek current frontier (open-weight reasoning), via OpenRouter. The strongest non-Western frontier reference. |
| **Llama 4 Maverick** | `openrouter/meta-llama/llama-4-maverick` | Meta current frontier (open-weight), via OpenRouter. Successor to the Llama 3.3 snapshot baseline. |

### 5.3 Settings and disclosure

All baselines use the same default system prompt (clinically-neutral framing). Decoding parameters differ by provider mandate:

| Tier | Baselines | Temperature | Notes |
|---|---|---|---|
| Snapshot (§5.1) | gpt-4o, claude-sonnet-4, gemini-2.5-pro, llama-3.3-70b, gpt-3.5-turbo | **0.0** | Standard low-variance setting. |
| Current frontier (§5.2) | gpt-5.5, gpt-5.5-pro, claude-opus-4-7 | **1.0 (provider-mandated)** | Reasoning models reject `temperature=0` with `BadRequestError` / "temperature is deprecated for this model". The provider's stance is that internal reasoning replaces the temperature knob for determinism. |
| Current frontier (§5.2) | claude-sonnet-4-6 | **0.0** | Still accepts temperature=0 — kept consistent with snapshot tier. |

**Honest framing on cross-tier comparison.** A direct composite comparison between a temp=0 snapshot baseline and a temp=1 current-frontier baseline includes whatever within-run variance the temp=1 model has. METHODOLOGY §3.6 already acknowledged that "temperature=0 isn't actually deterministic across providers" — the temp=1 case is the same problem at a higher amplitude. v0.1 surfaces the actual per-baseline temperature on the leaderboard and reports composite ± bootstrap CI. Submissions that want to claim a particular provider/temperature combination is "deterministic enough" are welcome to do so on their submission card.

Reasoning-model baselines (Gemini 2.5, GPT-5.5, Claude Opus 4.7) also receive `reasoning_effort=low` or equivalent provider-specific knobs (via `BaselineConfig.extra_params`) to keep visible-output budgets adequate for the JSON response. Without this cap, ~20% of Gemini cases truncated their visible output to "" with the entire `max_tokens=2048` budget consumed by hidden reasoning.

**Cost transparency**: the launch leaderboard shows the per-case cost for every seeded baseline (provider × token usage × current API price). External submissions can opt in to cost display; default is hidden. The cost column is *not* part of the ranking — it's diagnostic information for submitters comparing price/performance tradeoffs.

A second pass of each baseline with a "chain-of-thought" prompt is also published as a separate entry, demonstrating that prompt engineering moves the score (the explicit lesson for the indie-hacker audience).

## 6. Infrastructure

| Component | Tech | Why |
|---|---|---|
| Leaderboard host | HuggingFace Spaces (Gradio) | Free, model-leaderboard precedent (Open LLM Leaderboard, ReXrank), no infra to maintain |
| Submission storage | HF Datasets (private) for test set + public for submissions log | Same |
| Scoring | Python 3.11 + Pydantic v2 for schema | Standard |
| Baseline inference | LiteLLM unified client | One client for OpenAI/Anthropic/Google/HF/local |
| CI | GitHub Actions | Lint, test, validate case schemas, validate oracle on dev split |
| Version pinning | Submissions record the model identifier + date; HF Space pins LiteLLM, Pydantic versions per release tag | Reproducibility |

Total code target: ≤1000 LOC excluding case data.

## 7. Open methodology questions (TODO)

These are flagged in CONCEPT.md §8 and need maintainer redline before code:

1. Final canonical list of recommendation bins (§1.4 / CONCEPT §4.3).
2. Risk-factor encoding granularity — keep all individual fields, or collapse to a derived `risk_category`?
3. Multiple-nodule cases in v0.1 (5%) or defer to v0.2?
4. Sub-solid distinction (ground-glass vs part-solid) in v0.1, or treat as one type?
5. Whether to publish the rules engine *before* the leaderboard launches (transparency) or *after* (so submitters can't trivially replicate it).
6. Bootstrap CI methodology — paired or unpaired comparisons against the oracle?
7. Should the dev split include the same distribution as test, or be biased toward edge cases (more useful for debugging prompts)?

## 8. Limitations & honest caveats

- **Single track**: v0.1 evaluates one narrow guideline. High score on RadGym v0.1 ≠ "this agent is a good radiologist." It means "this agent applies Fleischner 2017 to text descriptions correctly." Future tracks broaden the claim.
- **Text-only**: Real radiology workflows require images. v0.1 deliberately sidesteps this; the imaging tracks come in v1.0+.
- **English-only**: All cases are in English. Multilingual evaluation is out of scope.
- **Single-turn**: No multi-turn agent loops in v0.1. The agent receives a case, produces a recommendation. Multi-turn comes in v0.4+.
- **Contamination**: As noted in §2.4, full contamination resistance is impossible. Paraphrasing + hidden test set + synthetic cases mitigate but do not eliminate this.
- **No clinical validation**: The benchmark measures algorithm application, not real-world clinical utility. A different (and longer, harder, more expensive) study would be needed for that.

These caveats are stated up front because the rad-AI research audience will look for them; better to own them than be caught.

---

**Maintainer:** Kareem Albaba, MD ([@hiKareeem](https://github.com/hiKareeem)) — 3-year radiology residency, now in AI infrastructure. RadGym is research-use-only; not a medical device.
