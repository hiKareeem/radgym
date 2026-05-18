# Submitting to RadGym v0.1

**Status:** v0.1 launch draft. Open issues on `github.com/hiKareeem/radgym` for clarifications.

This document is for people who want their LLM agent ranked on the public leaderboard. It covers what a submission *is*, how to format it, what we run on, what comes back, and the provider quirks that will eat half your debugging time if nobody warns you.

If you just want to read the leaderboard, you don't need this file. If you want to ship an agent and have it appear next to gpt-5.5 and Sonnet 4.6, read on.

---

## TL;DR

You give us:

1. A **model identifier** (anything LiteLLM speaks — OpenAI, Anthropic, Google, OpenRouter, HuggingFace Inference, etc.).
2. A **system prompt** and a **user prompt template** with a `{case_json}` placeholder.
3. Decoding parameters (`temperature`, `max_tokens`, optional `extra_params` for reasoning-effort knobs).
4. Optionally, your **own API key** (closed-source providers, or to bypass the free-quota cap).

We run your agent against the **hidden 150-case test split**, score with the asymmetric track-aware scorer described in [METHODOLOGY §3](METHODOLOGY.md#3-scoring), and post the aggregate to the leaderboard. **Per-case outcomes are never returned.** That's a deliberate label-leak mitigation, not an oversight — see §4.

You debug your prompt against the public **50-case dev split** (`cases/v0.1/dev/` in the repo) where ground-truth labels are visible.

---

## 1. What a submission looks like

A submission is a JSON file matching this schema:

```jsonc
{
  "submission_name": "string",            // human-readable, e.g. "claude-sonnet-4-6-cot-v1"
  "submitter": "string",                  // github handle, email, or org
  "model_identifier": "string",           // LiteLLM model string (see §3)
  "model_provider": "openai" | "anthropic" | "google" | "huggingface" | "openrouter" | "custom",
  "system_prompt": "string",              // counts toward submission uniqueness
  "user_prompt_template": "string",       // Jinja2-ish; we just call .format(case_json=...)
  "decoding": {
    "temperature": number,                // see §5 — your value here may be silently clamped by the provider
    "top_p": number,                      // omit unless you want non-default nucleus sampling
    "max_tokens": integer,                // see §5 for reasoning-model sizing
    "extra_params": {                     // optional, provider-specific
      "reasoning_effort": "low" | "medium" | "high",
      "thinking": { "type": "enabled", "budget_tokens": 1024 }
    }
  },
  "submitter_provided_api_key": boolean,  // true → you paste the key into the HF Space form
  "show_cost_publicly": boolean,          // default false; opt-in to display $/case on the leaderboard
  "notes": "string"                       // optional, public, shown on leaderboard
}
```

A submission counts as **different from another** if any of `model_identifier`, `system_prompt`, `user_prompt_template`, or `decoding.temperature` differ. Prompt-engineering wins appear as distinct leaderboard entries — that's the point.

---

## 2. The schema your agent must satisfy

Your agent receives a structured **case** as JSON (the full schema is `radgym.schemas.Case` — pasted below for convenience) and must produce a structured **response**.

### Input (we give your agent)

```jsonc
{
  "case_id": "RGYM-v01-XXXX",
  "presentation": "1-3 sentence clinical context that mentions the nodule",
  "nodule": {
    "type": "solid" | "sub_solid_ground_glass" | "sub_solid_part_solid",
    "size_mm": 6.0,
    "multiplicity": "single" | "multiple",
    "morphology": "smooth" | "lobulated" | "spiculated" | "unspecified",
    "location": "upper_lobe" | "middle_lobe" | "lower_lobe" | "lingula" | "unspecified",
    "additional_nodules": [...]           // present only when multiplicity = "multiple"
  },
  "patient": {
    "age": 60,
    "smoking_history": "never" | "former" | "current" | "unknown",
    "pack_years": null | number,
    "asbestos_exposure": false,
    "family_history_lung_ca": false,
    "emphysema": false,
    "pulmonary_fibrosis": false,
    "known_primary_cancer": false,        // always false in v0.1 test cases (out of scope)
    "immunocompromised": false            // same
  },
  "context": "free-text framing for the agent (often empty)"
}
```

### Output (your agent must produce)

```jsonc
{
  "case_id": "RGYM-v01-XXXX",             // echo verbatim
  "recommendation": "<one of: no_routine_followup | optional_ct_12mo | ct_6_12mo_then_18_24mo_if_stable | ct_3_6mo_then_18_24mo | subsolid_workup | consider_pet_or_biopsy | multiple_nodule_dominant>",
  "dominant_nodule_recommendation": "<bin ID, REQUIRED iff recommendation = multiple_nodule_dominant, otherwise null/omitted>",
  "rationale": "1-3 sentences of reasoning (collected; not scored in v0.1, will be RadFact-graded in v0.2)"
}
```

**Conditional-required rule on `dominant_nodule_recommendation`** (enforced by Pydantic):

- When `recommendation == "multiple_nodule_dominant"`: field **must** be present and non-null.
- When `recommendation` is anything else: field **must** be null or omitted.

A response that violates this scores `malformed` (zero points, counts against the rankability gate).

### Robust JSON extraction

We try four parse strategies before declaring `malformed`:

1. Strict JSON parse of the whole response.
2. Extract from a fenced markdown block (```` ```json ... ``` ````).
3. First balanced `{...}` substring.
4. Trailing-comma repair pass.

This is *liberal*. If your model emits valid JSON wrapped in any reasonable amount of prose, fences, or trailing whitespace, we'll find it. If your model emits a long monologue followed by `{...}`, we'll find it. If your model emits two JSON objects, we take the first balanced one.

If you have a reasoning-class model: be aware it may emit its hidden thinking BEFORE the visible JSON. That's fine — our extractor handles it. But it eats your `max_tokens` budget; see §5.

---

## 3. Pick a model identifier LiteLLM speaks

We use [LiteLLM](https://docs.litellm.ai/docs/providers) as the unified client. Examples that work:

| Provider | Identifier format | Notes |
|---|---|---|
| OpenAI | `openai/gpt-4o-2024-11-20`, `openai/gpt-5.5` | Date-pin for reproducibility where possible. |
| Anthropic | `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-7` | |
| Google | `gemini/gemini-2.5-pro`, `gemini/gemini-3.1-pro-preview` | Gemini family burns hidden reasoning tokens; see §5. |
| OpenRouter | `openrouter/<provider>/<model>` e.g. `openrouter/meta-llama/llama-4-maverick`, `openrouter/deepseek/deepseek-v4-pro` | Cheapest way to ship open-weight baselines. |
| HuggingFace Inference Endpoints | `huggingface/<model-id>` | For self-hosted or fine-tuned models. |
| Custom / self-hosted | Any LiteLLM-compatible endpoint | OpenAI-compatible APIs work; use `openai/` prefix + `api_base`. |

If LiteLLM speaks it, we accept it. If it doesn't, file an issue and we'll see if it's worth adding.

---

## 4. What feedback you get back

After your submission scores against the hidden test split:

**You receive** (aggregate-only):

- `composite` — your headline score (0-100 typical range, capped at [-50, 100])
- `exact_accuracy` — fraction of cases scored `correct` or `multiple_correct_full`
- `under_following_rate` — fraction scored `adjacent_unsafe` + `wrong_unsafe` + `cross_track`. **The safety metric. Lower is better.**
- `over_following_rate` — fraction scored `adjacent_safe` + `wrong_safe`
- `cross_track_rate` — fraction scored `cross_track` (you picked the wrong follow-up *type*)
- `malformed_rate` — fraction of outputs that didn't parse
- `rankable` — true if `malformed_rate <= 5%`
- `cost_per_case` and `total_cost` — only if you opted in to public cost display

**You do NOT receive**:

- Per-case outcomes (which specific cases were correct, wrong, malformed)
- The case prompts themselves
- The ground-truth labels for the test split

**Why**: per-case feedback + unlimited prompt variants enables iterative binary-search of the hidden test set's labels. This is a real attack vector ([discussed in METHODOLOGY §4.2](METHODOLOGY.md#42-submission-flow-v01)). v0.2 will reintroduce per-case feedback once we have stricter rate-limiting and a non-trivial sybil cost.

If you want full per-case feedback today: run your agent against the **dev split** (50 cases, ground-truth labels in the repo). That's exactly what it's there for.

---

## 5. Provider quirks that will absolutely waste your time

We hit every one of these while wiring up the seed baselines. Skip the foot-shooting:

### 5.1 Reasoning models burn hidden tokens you can't see

GPT-5.5, GPT-5.5 Pro, Claude Opus 4.7, Gemini 2.5/3.1 Pro, DeepSeek V4 Pro, Magistral, o-series — all emit **hidden reasoning tokens** before the visible JSON response. These count against your `max_tokens` budget but never appear in the parsed output.

| Model | Reasoning tokens (per Fleischner case, observed) | Suggested `max_tokens` |
|---|---|---|
| Gemini 2.5 Pro with `reasoning_effort=low` | 700-1000 | 2048 |
| Gemini 3.1 Pro preview | ~250 | 2048 |
| GPT-5.5 | ~150 | 2048 |
| GPT-5.5 Pro | **~50000** | 4096+ (mostly hidden; visible answer is small) |
| Claude Opus 4.7 | ~200 | 2048 |
| Claude Sonnet 4.6 | ~50 | 2048 |
| Llama 4 Maverick | ~30 | 2048 |
| DeepSeek V4 Pro | **~2000-2600** (even with `reasoning_effort=low`) | **4096** |

**Heuristic**: if you're using a reasoning-class model, set `max_tokens` to at least 4× your expected visible JSON size. RadGym responses are short (~150-300 visible tokens) so 2048 works for most. DeepSeek and gpt-5.5-pro need more headroom.

**Symptom of getting this wrong**: high `malformed_rate` with `output_tokens` equal to your `max_tokens` cap on every malformed case. Visible content is empty or truncated mid-JSON.

**Knob**: pass `reasoning_effort: "low"` (or provider-specific equivalent) in `decoding.extra_params`. Caps the hidden budget so the visible answer doesn't starve.

### 5.2 Reasoning models reject `temperature=0`

- **OpenAI**: `gpt-5.5`, `gpt-5.5-pro` reject `temperature != 1` with `BadRequestError: Unsupported value: 'temperature' does not support 0 with this model`.
- **Anthropic**: `claude-opus-4-7` rejects `temperature=0` with `temperature is deprecated for this model`. (Claude Sonnet 4.6 still accepts it.)
- **Workaround**: set `temperature=1.0` for these models. RadGym's leaderboard surfaces the actual per-baseline temperature so cross-tier comparisons are honest about the variance.

This violates pure determinism. METHODOLOGY §3.6 already acknowledged that `temperature=0` was never truly reproducible across providers; the temp=1 reasoning models are the same problem at higher amplitude. Bootstrap CIs are reported alongside composite scores.

### 5.3 `top_p` is restricted on some Anthropic and OpenAI models

- **Opus 4.7**: rejects `top_p` outright. The runner only forwards `top_p` when the caller deliberately set a non-default value (`!= 1.0`).
- **Sonnet 4.6**: rejects `(temperature AND top_p)` together. Pick one.
- **gpt-5.5-pro**: rejects `top_p`.

**Workaround in submissions**: only include `top_p` in `decoding` if you actually want nucleus sampling. If you're running greedy/low-variance, omit it entirely. The runner sets `litellm.drop_params=True` which catches the most common cases, but LiteLLM's allow-list lags real provider changes by months. Don't rely on it.

### 5.4 OpenRouter doesn't host every "open" model

Specifically: **MedGemma-27B-it** is *not* on OpenRouter as of 2026-05, even though it's an open-weight Google model. Symptom: `BadRequestError: <model> is not a valid model ID`. Workaround: stand up a local Ollama or vLLM endpoint, or use HuggingFace Inference Endpoints (paid).

We deferred MedGemma from v0.1 baselines for this reason. v0.2 will revisit.

### 5.5 Free-tier Gemini API quotas are tiny

Gemini 2.5 Pro free tier ≈ 50 requests/day. The leaderboard test split is 150 cases. Plan accordingly: paid Google AI tier, or smaller-quota baseline like Gemini Flash, or bring-your-own-key with billing enabled.

### 5.6 Fish shell universal variables can corrupt long keys in subprocess

If you're on fish: `fish -c 'echo $ANTHROPIC_API_KEY'` and `grep+sed+python` pipelines have edge cases where long keys get mangled. The repo includes `scripts/fish_env.py` which reads `fish_variables` directly with hex-decode — use that instead.

---

## 6. Anti-abuse: the rules you're agreeing to

By submitting, you agree:

- **Rate limit**: 1 submission per submitter per 24h per `model_identifier`.
- **Monthly cap**: 30 submissions per GitHub identity per calendar month across all model identifiers. Combined with aggregate-only feedback, this caps the information any single actor can extract from the hidden set.
- **Cost cap**: each submission is rejected if its projected total inference cost exceeds a fixed ceiling, computed at submission time.
- **Prompt size**: `system_prompt` ≤ 16k chars, `user_prompt_template` ≤ 4k chars. Prevents prompt-flood attacks against our API quotas.
- **No streaming, no tool calls** in v0.1. Single request/response per case.
- **Bring-your-own-key** beyond the free per-user quota.

If you have a legitimate reason to exceed any of these (a research lab benchmarking a fine-tuned model with 1k submissions, an authorized integration partner, etc.), open a GitHub issue. We'd rather raise a limit than have you sybil around it.

---

## 7. How to test your submission before submitting

Three escalating-rigor checks:

### 7.1 Cheapest: 5-case smoke test

Pick 5 dev cases that span bins. Manually run your prompt against your model. Eyeball the JSON. If 5/5 parse cleanly and your bin pick matches the ground truth on 3+ of them, your prompt template is structurally fine.

### 7.2 Full dev: 50 cases (~$0.05-2 depending on model)

Run on the public dev split (`cases/v0.1/dev/`). All 50 cases have ground-truth labels. You'll see per-case outcomes, your composite, and where you're failing. **This is the only way you get per-case feedback**, so squeeze it for everything it's worth.

Use `scripts/run_baseline.py` if you've cloned the repo; otherwise replicate the loop manually. The schema is short and the runner is ~250 LOC.

### 7.3 Full test: 150 cases (your real submission)

Once dev is clean, submit. Test runs are aggregate-only.

If your dev composite is X, expect test composite within ~±5 points of X. Larger gaps usually indicate prompt overfitting to the dev split (which is itself useful information — note it in your submission's `notes` field).

---

## 8. What scores well, empirically

From the seeded baselines on the dev split:

- **Frontier reasoning models (gpt-5.5, gpt-5.5-pro, gemini-3.1-pro)** score 83-89. They pay for it in tokens — gpt-5.5-pro is ~30× the cost of gpt-5.5 for +2 composite points.
- **Mid-tier closed models (claude-sonnet-4-6, gemini-2.5-pro)** score 73-74 at ~$0.005-0.010/case. Best price/performance for closed-source.
- **Open-weight (Llama 4 Maverick)** is currently a disaster on this task (composite 26.40, 34% unsafe rate). The earlier Llama 3.3-70b snapshot scored 48.10. Something regressed in the Llama 4 training. Worth a separate writeup.
- **The rules engine** scores 100 by construction. It is the floor: any submission below the rules engine is, by definition, applying Fleischner worse than 20 lines of Python.

The **clinically interesting failure mode** is `multiple_nodule_dominant` recognition. Multiple-nodule cases use a different row of Table 1A/1B than single-nodule cases; models that "deeply reason" about the dominant nodule often miss the case-level recognition rule and apply single-nodule logic to multiple-nodule cases. This is how Opus 4.7 lost 15 composite points to Sonnet 4.6 within Anthropic's lineup. If your prompt explicitly reminds the model to **check multiplicity first**, you'll likely beat your tier baselines on this axis.

---

## 9. Common rejection reasons

If your submission is rejected before scoring:

| Reason | Fix |
|---|---|
| `model_identifier` not parseable by LiteLLM | Check spelling, check LiteLLM provider list, file issue if it's a new provider. |
| Estimated cost exceeds cap | Use a cheaper model, bring your own key, or open an issue requesting a quota bump with justification. |
| `system_prompt` or `user_prompt_template` exceeds size limit | Trim it. |
| Submission identical to a prior one from the same submitter | Change at least one of `model_identifier`, `system_prompt`, `user_prompt_template`, or `decoding.temperature`. |
| `user_prompt_template` doesn't contain `{case_json}` | Fix the template. |

If your submission scored but is marked **not rankable**:

- `malformed_rate > 5%`: your agent failed to produce valid JSON on more than 5% of cases. Tighten the system prompt's JSON-only directive, raise `max_tokens`, add `reasoning_effort: low` if it's a reasoning model.

---

## 10. v0.1 → v0.2 roadmap (what's coming)

v0.2 will likely add:

- **Per-case feedback restored**, paired with stricter rate-limiting.
- **Majority-of-3 sampling** for reasoning models — converts within-run variance from a ranking risk into a quantified noise floor.
- **RadFact-style rationale grading** — your `rationale` field starts getting scored.
- **Split sub-solid bin** — `SUBSOLID_WORKUP` becomes `GGN_q2y_5y` and `PART_SOLID_annual_5y`. Affects scoring on existing cases.
- **Solid-component-size field** for part-solid nodules, enabling the "concerning features → PET/biopsy" path.
- **MedGemma re-enabled** via local Ollama/vLLM or HF Inference.

If something on this list blocks your use case, the v0.2 timeline is negotiable. Open an issue.

---

## Questions, bugs, contributions

GitHub: [hiKareeem/radgym](https://github.com/hiKareeem/radgym) · Issues are the right channel.

Maintainer: [@hiKareeem](https://github.com/hiKareeem) — radiology background, eval-design heritage from SpireBench. Mostly responsive on weekdays.

This benchmark is **research-use-only**. It is not a medical device. Submissions and scores do not direct patient care.
