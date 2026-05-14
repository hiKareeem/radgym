# RadGym — Methodology (v0.1)

**Document status:** v0.1 design draft, awaiting maintainer redline.
**Last updated:** 2026-05-14
**Companion doc:** `CONCEPT.md` (the *why*); this doc is the *how*.

---

## 1. Track definition: Fleischner 2017 follow-up

### 1.1 Source

MacMahon H, et al. "Guidelines for Management of Incidental Pulmonary Nodules Detected on CT Images: From the Fleischner Society 2017." *Radiology* 2017;284(1):228-243. doi:10.1148/radiol.2017161659

Scope: incidental pulmonary nodules detected on CT in patients ≥35 years old, **excluding** lung cancer screening (Lung-RADS, future track), patients with known primary cancer, and immunocompromised patients.

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
    "known_primary_cancer": boolean,     // if true, case is excluded — present for parser sanity
    "immunocompromised": boolean         // if true, case is excluded
  },
  "context": "string"                    // free-text framing for the agent
}
```

### 1.3 Output schema (per case)

```jsonc
{
  "case_id": "RGYM-v01-XXXX",
  "recommendation": "<one of the bin IDs from CONCEPT §4.3>",
  "rationale": "string"                   // collected; not scored in v0.1
}
```

Strict JSON, validated by Pydantic on receipt. Malformed outputs score 0 for that case with a `malformed_output` flag.

### 1.4 Recommendation bins (canonical list)

See `CONCEPT.md` §4.3. The full mapping from case features to bin will be encoded in `scoring/fleischner_oracle.py`. This oracle:

- Is the deterministic Fleischner 2017 algorithm in code.
- Is the answer key for scoring.
- Is also a reference baseline ("rules engine" — submitted publicly to the leaderboard).
- **Is reviewed by the maintainer (radiology background) for clinical correctness before any case is scored.**

## 2. Case construction

### 2.1 Sources

200 cases for v0.1, sourced from:

| Source | Approx. count | Use type |
|---|---|---|
| Fleischner 2017 paper worked examples (Table 1 + body) | ~20 | Direct application of the published examples |
| Radiopaedia public cases tagged "pulmonary nodule" | ~60 | Adapted from public case writeups (CC BY-NC-SA — attribution per case) |
| OpenI (NLM Open-i) excerpts mentioning pulmonary nodules | ~30 | Pulled from public NLM data |
| Radiology Assistant public articles on nodule workup | ~20 | Paraphrased illustrative cases |
| Synthetic cases (maintainer-authored) | ~70 | Edge cases, bin boundaries, risk-factor combinations |

Every case has a `source` field in its JSON metadata. Public-source cases reference the original (URL or DOI); synthetic cases note `source: synthetic_maintainer_authored`.

### 2.2 Curation procedure

The maintainer (radiology background, 3 years clinical experience) personally constructs or reviews every case. For each case:

1. **Construct or extract** the clinical narrative.
2. **Encode** the structured fields per §1.2.
3. **Determine the ground-truth recommendation** by applying Fleischner 2017 directly.
4. **Record any ambiguity** in a `notes` field — cases with genuine ambiguity (e.g., size exactly at a threshold, mixed risk factors) are flagged for either inclusion (as deliberate edge cases) or exclusion.
5. **Cross-check** against `scoring/fleischner_oracle.py` — the rules engine must produce the same recommendation as the maintainer's ground truth. Disagreements are resolved before the case enters the test set.

### 2.3 Public vs hidden split

- **Public dev split (50 cases)**: published in `cases/v0.1/dev/`. Used by submitters to debug their prompts. Includes ground-truth labels.
- **Hidden test split (150 cases)**: never published. Lives in a private Git submodule or a HuggingFace private dataset. Submissions are scored against this split.

Both splits draw from the same source mix and the same distribution of bin labels.

### 2.4 Contamination resistance

LLM training data inevitably includes Fleischner 2017 and likely includes Radiopaedia case writeups. RadGym addresses this:

1. **Paraphrasing**: All extracted cases are paraphrased by the maintainer; verbatim language from the source guideline or case database is avoided in the `presentation` and `context` fields.
2. **Structural variation**: The clinical narrative is rewritten so that surface n-grams differ from the source. The *clinical content* is preserved; the *prose* is not.
3. **Synthetic edge cases**: ~35% of the test set is fully synthetic, parameterized along the Fleischner decision tree to ensure coverage of bin boundaries.
4. **No verbatim Fleischner clauses** appear in any case. The agent must apply the algorithm; it cannot pattern-match memorized text.
5. **Hidden test set** is never published, period. Submission outputs are returned to the submitter; the test cases themselves are not.

This is not contamination-proof — no benchmark can be against a model that *has* seen Fleischner 2017 — but it makes "memorize verbatim" less useful than "apply the algorithm."

### 2.5 Case distribution

Target distribution for v0.1 (subject to maintainer revision):

| Bin | Target % | Rationale |
|---|---|---|
| `no_routine_followup` | 15% | Common but trivial — small floor |
| `optional_ct_12mo` | 15% | Tests low-/high-risk distinction at <6 mm |
| `ct_6_12mo_then_18_24mo_if_stable` | 15% | Mid-range, common bin |
| `ct_3_6mo_then_18_24mo` | 20% | Most algorithm branches converge here |
| `consider_pet_or_biopsy` | 15% | Tests recognition of higher-risk findings |
| `ct_3_6mo_subsolid` | 15% | Tests sub-solid handling |
| `multiple_nodule_dominant` | 5% | Tests dominant-nodule rule (small for v0.1) |

Roughly uniform across the main bins, with deliberate over-sampling of bin boundaries (e.g., nodules at exactly 6 mm and 8 mm) within each bin.

## 3. Scoring

### 3.1 Scoring function (v0.1)

For each case, the agent's recommendation is compared to ground truth. Let:

- `correct` = recommended bin equals ground-truth bin
- `adjacent_safe` = recommended bin is one step toward *more aggressive* follow-up than ground truth (over-following)
- `adjacent_unsafe` = recommended bin is one step toward *less aggressive* follow-up than ground truth (under-following)
- `wrong` = any other mismatch (≥2 bins off, in either direction)
- `malformed` = output failed schema validation

Per-case score:

| Outcome | Points |
|---|---|
| `correct` | 1.00 |
| `adjacent_safe` | 0.50 |
| `adjacent_unsafe` | -0.25 |
| `wrong` (off by ≥2, over-following) | 0.00 |
| `wrong` (off by ≥2, under-following) | -0.50 |
| `malformed` | 0.00 |

**Composite score for a submission** = `100 × (sum of per-case scores) / N`, where N is the test set size (150 for v0.1 hidden). The composite is bounded to [-50, 100] but typical good agents will fall in [40, 90].

### 3.2 Why asymmetric

Under-following a Fleischner-flagged nodule means missing a potentially malignant lesion — the clinically dangerous failure mode. Over-following means extra imaging cost and patient anxiety — a real harm but a recoverable one. The score reflects this asymmetry, matching the maintainer's clinical instinct.

### 3.3 Bin ordering for adjacency

Adjacency is computed on this ordered sequence (least → most aggressive follow-up):

1. `no_routine_followup`
2. `optional_ct_12mo`
3. `ct_6_12mo_then_18_24mo_if_stable`
4. `ct_3_6mo_then_18_24mo`
5. `ct_3_6mo_subsolid`
6. `consider_pet_or_biopsy`

`multiple_nodule_dominant` is treated specially: a recommendation of `multiple_nodule_dominant` on a multiple-nodule case is scored against the dominant-nodule sub-recommendation (an additional field the agent must produce on those cases).

### 3.4 Reported metrics

The leaderboard reports for each submission:

- **`composite`** — the headline number (the asymmetric score, primary ranking).
- **`exact_accuracy`** — % of cases with `correct` outcome (familiar baseline metric).
- **`under_following_rate`** — % of cases scored as `adjacent_unsafe` or `wrong_unsafe`. **The "safety" metric.** Lower is better.
- **`over_following_rate`** — % scored as `adjacent_safe` or `wrong_safe`.
- **`malformed_rate`** — % of malformed outputs (a robustness metric).
- **`per_bin_accuracy`** — confusion matrix collapsed to per-bin accuracy.

A submission is **not** rankable if `malformed_rate > 10%` — the agent failed to follow the output schema reliably enough to be evaluated.

### 3.5 Statistical reporting

With N=150, bootstrap 95% CIs are computed for the composite and shown next to point estimates. Submissions whose CI overlaps the rules-engine baseline are flagged as "not distinguishable from oracle" — useful information, not a penalty.

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
4. Submitter receives a per-case breakdown (which cases were `correct`, `unsafe`, `malformed`, etc.) but **not** the cases themselves.
5. Rate limit: 1 submission per submitter per 24 hours per model identifier, to prevent thrash.

### 4.3 Submitter-provided API keys

For closed-source models (OpenAI, Anthropic, Google), submitters can paste their API key into the HF Space's per-session secret field. The key is used only for that submission's evaluation and is not persisted. For open-weight models on HuggingFace, RadGym uses HuggingFace Inference Endpoints (no key required from submitter; rate-limited).

### 4.4 What counts as a "different" submission

A submission is considered different from another if **any** of `model_identifier`, `system_prompt`, `user_prompt_template`, or `decoding.temperature` differ. This lets the leaderboard show prompt-engineering wins as distinct entries.

## 5. Reference baselines

The maintainer runs these on the hidden test set before public launch:

| Baseline | Notes |
|---|---|
| **Rules engine** | 20-line Python applying Fleischner 2017 literally. Should score near 100. The oracle's correctness is the floor of the benchmark. |
| **GPT-4o** (`gpt-4o-2024-11-20`) | Default modern API reference. |
| **Claude Sonnet 4** (`claude-sonnet-4-20250514`) | The other default. |
| **Gemini 2.5 Pro** | Long-context reference. |
| **Llama-3.3-70B-Instruct** | Open generalist reference. |
| **MedGemma-27B-it** | Open medical SLM reference. |
| **GPT-3.5-turbo** | Deliberate floor so the leaderboard has visible spread. |

All baselines use the same default system prompt (a clinically-neutral framing) and same temperature=0 settings. A second pass of each baseline with a "chain-of-thought" prompt is also published as a separate entry, demonstrating that prompt engineering moves the score (the explicit lesson for the indie-hacker audience).

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
