# RadGym v0.1 — Launch Posts

**Status:** Draft, awaiting maintainer redline + κ data + HF Space URL substitution. Numbers below reflect the **final 12-baseline test split** (150 cases, all baselines complete).

Three audiences, three posts, one consistent voice. Read all three before sending any — they cross-reference.

---

## 1. X / Twitter thread

For posting from [@hiKareeem] or wherever the project lives socially. Designed to be screenshot-friendly; each tweet stands alone.

> **(1/12)** RadGym v0.1 is live.
>
> Open agentic benchmark for radiology workflow reasoning. v0.1 track: Fleischner Society 2017 pulmonary nodule follow-up.
>
> 150 hidden test cases. 12 baselines seeded. The headline: every frontier model misses ≥13 composite points vs a 20-line rules engine. Best frontier model is gpt-5.5 at 86.67/100.
>
> 🔗 leaderboard: [HF Space URL]
> 🔗 repo: github.com/hiKareeem/radgym

> **(2/12)** Why this exists:
>
> Radiology AI benchmarks today are saturated with single-image classification (CheXbench, ReXrank, etc.). None of them test the cognitive work radiologists actually do at a workstation — applying clinical guidelines, comparing priors, recommending follow-up.
>
> RadGym is workflow-agentic, not image-classification.

> **(3/12)** v0.1 is deliberately the smallest tractable thing:
>
> - Text in, structured recommendation out (no DICOM yet)
> - One algorithm: Fleischner 2017 Table 1A/1B
> - 50 public dev cases + 150 hidden test cases
> - Asymmetric scoring: under-following penalized harder than over-following
>
> Imaging tracks come in v1.0. Lung-RADS, Fleischner incidental-findings white papers in v0.3.

> **(4/12)** Final leaderboard, test split, 12 baselines on 150 cases:
>
> 🥇 oracle_rules_engine     100.00  $0       (the floor)
> 🥈 gpt-5.5                  86.67  $0.011/case
> 🥉 gemini-3.1-pro-preview   83.33  $0.006/case
> ▫️ gemini-2.5-pro           73.47  $0.010
> ▫️ deepseek-v4-pro          67.87  free (OpenRouter)
> ▫️ claude-sonnet-4-6        67.00  $0.0045
> ▫️ claude-opus-4-7          62.87  $0.0080  ← still loses to Sonnet
> ▫️ gpt-4o                   58.57  $0.0022
> ▫️ claude-sonnet-4          53.73  $0.0034
> ▫️ llama-3.3-70b            48.10  free
> ▫️ llama-4-maverick         37.87  free     ← regression
> ✗  gpt-3.5-turbo            -0.83  $0.0004  (24.7% malformed → not rankable)

> **(5/12)** Across all 9 dev baselines × 50 cases (450 model-cases), **multi-nodule recognition was the single largest error class — 81/450 errors, ~18%**.
>
> Multiple-nodule cases use a separate row of Fleischner Table 1A/1B than single-nodule cases. Models that reason "deeply" about the dominant nodule often miss the case-shape rule and apply single-nodule logic. The error compounds at the top of the leaderboard, not the bottom.

> **(6/12)** Three findings worth digging into:
>
> First — Claude Opus 4.7 underperforms Claude Sonnet 4.6 by 16 composite points on dev, 4 on test. *Within the same provider's lineup.* Smaller, more instruction-tuned siblings beat the reasoning-heavy flagships on structured guideline application.

> **(7/12)** Second — Llama 4 Maverick scores 37.87 on test. Llama 3.3-70b scored 48.10. **The Llama-4 training regressed by 10 composite points** on this specific class of structured medical reasoning.
>
> Open weights haven't caught up to closed frontier on clinical guideline tasks. Worth a separate writeup.

> **(8/12)** Third — gpt-5.5-pro costs 13× gpt-5.5 ($8.15 vs $0.63 for dev) for +2 composite points.
>
> Cost column is on the leaderboard for exactly this reason. The "premium tier" of frontier models isn't always worth it on structured-output tasks.
>
> Total spent seeding 12 baselines on dev+test: ~$18. Real but trivial.

> **(9/12)** The scoring is the interesting part.
>
> Adjacency tracks: solid track (5 bins) and sub-solid track (3 bins). Cross-track recommendations score -0.50 (same as under-following by ≥2). Picking the wrong *kind* of follow-up is a different error than picking the wrong interval.
>
> Multiple-nodule cases get their own decision table.

> **(10/12)** Submissions open today.
>
> Submit: model_identifier (LiteLLM-speak: openai/, anthropic/, gemini/, openrouter/) + system_prompt + user_prompt_template. Bring your own API key or use the free per-user quota.
>
> Dev split has full per-case feedback. Test split returns aggregates only (prevents label probing).

> **(11/12)** What I learned wiring up 12 baselines that I wish someone had told me:
>
> - Reasoning models burn 2000–50000 hidden tokens per case
> - gpt-5.5 + opus-4.7 reject temperature=0
> - opus-4.7 + sonnet-4-6 reject top_p (or paired with temp)
> - OpenRouter doesn't host MedGemma
> - Free-tier Gemini caps at 50 req/day
>
> Full quirks list in docs/SUBMISSION.md.

> **(12/12)** v0.1 is a small narrow benchmark on purpose. Each future version widens the scope:
>
> - v0.2: rationale grading (RadFact), majority-of-3 sampling, sub-solid bin split, MedGemma re-enabled
> - v0.3: Lung-RADS, ACR incidental-findings white papers
> - v1.0: imaging tracks (DICOM in, structured report out)
>
> Why I built this: 3 years radiology residency before I left for AI. Eval-design heritage from SpireBench. Submissions welcome. Tear it apart.
>
> 🔗 leaderboard: [HF Space URL]
> 🔗 repo: github.com/hiKareeem/radgym
> 🔗 submitter docs: github.com/hiKareeem/radgym/blob/main/docs/SUBMISSION.md

**Notes for posting:**
- Schedule for a US-morning / EU-afternoon window (~9-11am ET) for max ML-Twitter overlap.
- Tweet (5) and (6) are the most retweetable individually — they each work as a standalone "huh, that's counterintuitive" hook.
- Don't quote-tweet provider accounts (no "@OpenAI"). Lets the findings speak on their own; avoids defensive responses.
- Pin tweet (1) for a week.

---

## 2. Hacker News — Show HN

```
Show HN: RadGym – an agentic benchmark for radiology workflow reasoning
https://huggingface.co/spaces/hiKareeem/radgym [or wherever it lands]
```

**Body** (HN doesn't allow markdown but this preserves the structure):

> RadGym is an open benchmark that scores LLM agents on radiology workflow reasoning — specifically, applying Fleischner Society 2017 guidelines for incidental pulmonary nodule follow-up — rather than the single-image classification that dominates existing radiology-AI benchmarks (CheXbench, ReXrank, etc.).
>
> The v0.1 track is deliberately narrow: structured text in, structured recommendation out, 200 maintainer-curated cases (50 public dev + 150 hidden test), asymmetric scoring where under-following a Fleischner-flagged nodule costs more than over-following it. Across 12 seeded baselines on the 150-case test split, frontier models cluster 53–87 composite on a 100-point scale held by a 20-line rules engine.
>
> Four findings I didn't expect when I started:
>
> 1. Across 9 dev baselines × 50 cases (450 model-cases), multi-nodule recognition was the single largest error class — 81/450, ~18% of all errors. Fleischner Table 1A/1B has a separate row for multiple-nodule cases; models that reason "deeply" about the dominant nodule often miss the case-shape rule and apply single-nodule logic. The error is concentrated at the top of the leaderboard, not the bottom.
>
> 2. Claude Opus 4.7 scores 4–16 composite points lower than Claude Sonnet 4.6 — within Anthropic's own lineup, depending on split. Smaller, more instruction-tuned siblings beat the reasoning-heavy flagships on structured guideline application.
>
> 3. Llama 4 Maverick scores 37.87 composite on test. Llama 3.3-70b scored 48.10. The Llama-4 training regressed by 10 composite points on this specific class of structured medical reasoning. Open weights haven't caught up to closed frontier on clinical guideline tasks.
>
> 4. The "pro" tier of frontier models is a poor price/performance trade on structured-output tasks. gpt-5.5-pro costs 13× gpt-5.5 for +2 composite points.
>
> The benchmark also functions as a stress test of the new generation of reasoning models. Each one has its own hidden-thinking-token budget that has to be reasoned about explicitly: DeepSeek V4 Pro burns ~2500 reasoning tokens per case, gpt-5.5-pro burns ~50000. The submitter docs (`docs/SUBMISSION.md`) include a per-model token budget table because every external submitter will hit this.
>
> I'm a radiologist by training (3 years residency) who left for AI infrastructure work. I wanted to scratch the gap between "ML researchers who don't know what radiologists do" and "physicians who can't ship infra." This is the smallest tractable version of that gap.
>
> Code: github.com/hiKareeem/radgym
> Leaderboard: [HF Space URL]
> Submitter docs: github.com/hiKareeem/radgym/blob/main/docs/SUBMISSION.md
> Methodology: github.com/hiKareeem/radgym/blob/main/docs/METHODOLOGY.md
>
> v0.2 will add rationale grading (RadFact-style), majority-of-3 sampling for reasoning models, and split the sub-solid bin. v0.3 adds Lung-RADS. v1.0 adds imaging tracks. Submissions open today.
>
> Bugs and methodology critiques welcome. Tear it apart.

**Notes for posting:**
- Submit during HN sweet spot: 8-9am ET weekday for best Show HN visibility window.
- Don't engage with surface-level "is this medical advice???" comments — point them at the RUO disclaimer in the README, move on.
- DO engage with: methodology questions, "why this bin and not that one," scoring critiques, "what about [other guideline]". These build the project's credibility.
- Likely first-week pushback: "100 score by a rules engine means the benchmark is gameable / unmoored." Response: that's the *floor*. If your model can't beat 20 lines of Python applying the published algorithm, your model isn't applying the algorithm — which is itself useful information. The interesting score range is 50-90.

---

## 3. r/LocalLLaMA post

Title: **Open benchmark: agentic radiology reasoning. Llama 4 Maverick regressed 10 points vs Llama 3.3-70b. DeepSeek V4 Pro (free on OpenRouter) beats Claude Opus 4.7.**

Body:

> Built an open benchmark for LLM agents applying Fleischner Society 2017 guidelines to pulmonary nodule cases. Structured input, structured output, 200 maintainer-curated cases (I'm an ex-radiologist), asymmetric scoring that penalizes under-following more than over-following.
>
> The open-weight tier had two surprises:
>
> **Test-split composite scores (150 cases, 12 baselines):**
> - oracle_rules_engine: 100.00 (the floor — 20 lines of Python applying Fleischner literally)
> - gpt-5.5: 86.67
> - gemini-3.1-pro-preview: 83.33
> - gemini-2.5-pro: 73.47
> - **deepseek-v4-pro: 67.87 (free on OpenRouter)** ← best non-Western open frontier
> - claude-sonnet-4-6: 67.00
> - claude-opus-4-7: 62.87
> - gpt-4o: 58.57
> - claude-sonnet-4: 53.73
> - **llama-3.3-70b: 48.10 (free)** ← still our strongest Llama-family result
> - **llama-4-maverick: 37.87 (free)** ← 10-point regression vs 3.3
> - gpt-3.5-turbo: -0.83 (not rankable, 24.7% malformed)
>
> Two headlines for this audience:
>
> 1. **DeepSeek V4 Pro at $0/case beats Claude Opus 4.7 ($0.0080/case) by 5 composite points** and beats Claude Sonnet 4.6 by a hair. This is the open-weight story I didn't expect — closed-frontier price/performance is genuinely competitive against free OpenRouter access for structured medical reasoning tasks.
>
> 2. **Llama 4 Maverick (37.87) regressed 10 points vs Llama 3.3-70b (48.10)** on the same benchmark. Both run at temperature=0 with identical prompts. Llama-4's 26% under-following rate (the clinically dangerous error class) is higher than Llama 3.3's 22%. Something in the Llama-4 training regressed on structured medical reasoning.
>
> Reasoning-model gotchas I documented for submitters (full table in `docs/SUBMISSION.md`):
> - DeepSeek V4 Pro: ~2500 hidden reasoning tokens/case even with `reasoning_effort=low`. Default 2048 max_tokens truncates 16% of responses.
> - gpt-5.5-pro: ~50000 reasoning tokens/case
> - Gemini 2.5 Pro with `reasoning_effort=low`: ~800 reasoning tokens/case
> - Anthropic Opus 4.7 and OpenAI gpt-5.5 family reject temperature=0; must run at temp=1
>
> All baselines use LiteLLM + OpenRouter for open-weight models. Repo includes a baseline runner you can point at any LiteLLM-compatible model.
>
> Submissions open. The dev split (50 cases, full per-case ground truth in the repo) is the right way to debug your prompt before submitting to the hidden test split. If anyone has a Qwen, Magistral, or fine-tuned medical model they want benchmarked, that's exactly the v0.1 use case.
>
> [HF Space URL]
> github.com/hiKareeem/radgym

**Notes for posting:**
- r/LocalLLaMA cares about open weights. The Llama 4 regression IS the post — don't bury it.
- Expect questions: "is this just one task / overfit benchmark?" → yes, deliberately narrow. v0.1 is one algorithm; v0.2-v0.3 widen. Cite the roadmap.
- Expect: "what's the open-source baseline beat this with prompt engineering?" → invite them to submit. Free per-user quota.

---

## Posting order and timing

**Day 1 (launch day):**
1. Push final HF Space URL into all three drafts.
2. Post HN Show HN at 8-9am ET (highest Show HN visibility).
3. Post X thread at 9-10am ET (cross-promote — first reply to tweet 1 links the HN post).

**Day 2-7:**
- Respond to methodology questions in both forums.
- Don't post follow-up content; let the original threads breathe.
- Continue grinding r/LocalLLaMA karma quietly via genuine participation on adjacent threads. ~50-100 karma typically clears the spam filter.

**Day 8-14:**
- Once you have submitter karma, post the r/LocalLLaMA thread. Now reframable as "two weeks in: X submissions, here's the leaderboard" if there's traction; or as the original DeepSeek+Llama-regression scoop if not.
- One follow-up X tweet with: "X submissions so far, top-3 leaderboard movers" — only if there are actually submissions to talk about. Don't fake activity.

**Why r/LocalLLaMA isn't day-1:** fresh accounts auto-filter to mod-queue on r/LocalLLaMA. The Llama-4-regression + DeepSeek-beats-Opus story is durable; it'll still be true on day 8. Splitting launch into two moments (HN+X day 1, r/LocalLLaMA week 2) is better than one big-bang post that gets stuck pending mod approval.

---

## Cuts I considered and rejected

- **Skipping the "I was a radiologist" framing**: would have made the posts more discoverable to ML audiences but less credible to the medical-AI audience. The credibility matters more for a benchmark's longevity than the discovery does for launch day.
- **Adding a "Mistral Magistral" or "Qwen3-Max" baseline before launch**: scope creep. v0.1.1 can add them once we have submitter feedback on what's missing.
- **Leading with the cost story**: would have read as cynical. The cost column exists because it's diagnostic, not because we're trying to embarrass any provider. Made it tweet (7) instead of tweet (1).
- **A separate "why benchmarks matter" thesis post**: cut. The posts above are about the artifact; meta-essays come later if at all.
