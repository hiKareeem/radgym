# RadGym — Concept

**Document status:** v0.1 design draft, awaiting maintainer redline.
**Last updated:** 2026-05-14

---

## 1. One-paragraph pitch

RadGym is an open, agentic benchmark for radiology workflow reasoning. Where existing radiology-AI benchmarks score a model's ability to *generate a report from one image*, RadGym scores an agent's ability to *apply clinical guidelines, reason over priors, and recommend correct downstream actions* — the actual cognitive work radiologists do, broken into tracks that are objectively scorable. The v0.1 track is Fleischner Society 2017 pulmonary nodule follow-up reasoning: pure text in, structured answer out, ~200 cases, asymmetric scoring that penalizes clinically dangerous under-following more heavily than over-following. The leaderboard is hosted on Hugging Face Spaces; submissions in v0.1 are prompt-plus-model-identifier (Docker comes in v0.2); reference baselines include 6 LLMs plus a 20-line rules-engine to make the leaderboard immediately interpretable.

## 2. Problem & gap

### 2.1 What exists

- **Single-image report generation**: CheXagent / CheXbench, MAIRA-2, LLaVA-Rad, RadFM, ReXrank (the de facto public leaderboard for CXR report generation).
- **Single-image classification / detection**: CheXpert, NIH ChestX-ray14, RSNA challenges, VinDr-CXR.
- **General medical QA**: MedQA, MedMCQA, PubMedQA, MultiMedQA.
- **Eval metrics for radiology text**: RadFact, GREEN, FineRadScore, RadGraph-F1.

### 2.2 What does not exist

A public benchmark that evaluates an agent's ability to:

1. **Apply structured clinical guidelines** to a case (Fleischner, Lung-RADS, BI-RADS, ACR incidental-findings white papers).
2. **Reason over prior studies** (new vs improved vs stable; interval change).
3. **Use tools deliberately** (request additional views, query priors, populate structured templates).
4. **Triage by urgency** (flag critical findings — pneumothorax, PE, ICH — with appropriate communication latency).
5. **Make multi-turn workflow decisions** (clarifying questions, hand-offs).

MAIRA-2 (Microsoft, 2024) is the closest published system to "agentic" because it uses prior studies + indication for grounded reporting — but it is not a benchmark, has a non-commercial license, and has no public leaderboard. A handful of "RadAgent"-named papers exist but each defines its own eval and shares no infrastructure.

### 2.3 Why nobody has filled this gap

- Curating cases requires radiology domain expertise.
- Scoring requires either deterministic rule-encoders (medium effort) or radiologist-panel review (high effort, slow).
- Longitudinal/prior-study data requires MIMIC-IV credentialing.
- The audience (medical-AI researchers + indie agent builders) is bifurcated and easy to miss.

RadGym's bet is that by **starting with the simplest tractable track (Fleischner, text-only, deterministic scoring)** and growing complexity track-by-track, the benchmark earns credibility and contributor flow before tackling the harder tracks.

## 3. Audience & user types

RadGym serves three audiences with different intents:

| Audience | Primary action | Cares about | v0.1 priority |
|---|---|---|---|
| **Indie AI hackers / agent-framework builders** | Submit prompts + model identifiers | Easy submission UX, fast iteration, leaderboard clout | **Primary** |
| **Academic medical-AI researchers** | Cite the benchmark, eventually submit Dockerized fine-tuned models | Rigorous methodology, contamination resistance, peer-review viability | Secondary (v0.2+) |
| **Radiologists / residents** | Read the leaderboard, compare agent reasoning to their own | Clinically meaningful cases, transcript viewer, "would I have done better?" framing | Tertiary (v0.3+) |

The v0.1 design optimizes for indie-hacker submission velocity. Academic rigor is preserved (asymmetric scoring, hidden test set, contamination resistance via paraphrasing) but the *ergonomics* are tuned to the indie audience because they generate the first 30 days of submissions and social signal.

## 4. v0.1 scope

### 4.1 Track: Fleischner 2017 pulmonary nodule follow-up

**Source guideline:** MacMahon H, et al. "Guidelines for Management of Incidental Pulmonary Nodules Detected on CT Images: From the Fleischner Society 2017." *Radiology* 2017;284(1):228-243.

**Task:** Given a structured case description (nodule size, density, multiplicity, patient risk profile, clinical context), output:

1. **`recommendation`** — one of a fixed set of categorical bins (see §4.3)
2. **`rationale`** — free-text reasoning (collected but not scored in v0.1; will be scored in v0.2)

**Input format:** JSON object per case. Example:

```json
{
  "case_id": "RGYM-v01-0001",
  "presentation": "Incidental solid pulmonary nodule, 6 mm, right upper lobe, on a chest CT performed for unrelated trauma evaluation.",
  "nodule": {
    "type": "solid",
    "size_mm": 6,
    "multiplicity": "single",
    "morphology": "smooth"
  },
  "patient": {
    "age": 58,
    "risk_category": "low",
    "smoking_history": "never",
    "asbestos_exposure": false,
    "family_history_lung_ca": false
  },
  "context": "Routine CT abdomen/pelvis for trauma; lung bases included nodule incidentally."
}
```

**Output format:** JSON object.

```json
{
  "case_id": "RGYM-v01-0001",
  "recommendation": "no_routine_followup",
  "rationale": "Per Fleischner 2017, a single solid pulmonary nodule <6 mm in a low-risk patient (never-smoker, no other risk factors) does not require routine follow-up. Optional CT at 12 months may be considered for patient or clinician comfort but is not recommended."
}
```

### 4.2 Why text-only for v0.1

Fleischner reasoning is fundamentally a structured-data decision: nodule size, density, multiplicity, risk category → follow-up interval. Images are not required to apply the algorithm; the radiologist's measurement is the input. By scoping v0.1 to text, we eliminate:

- DICOM tooling
- MIMIC-CXR credentialing
- Vision-model inference cost asymmetry between submitters
- Image-preprocessing variance

This lets v0.1 ship in ~3 weeks and lets *any* LLM (open or closed, vision-capable or not) submit on equal footing. v1.0 will introduce imaging tracks; v0.1 is deliberately the smallest tractable thing.

### 4.3 Recommendation bins

The Fleischner 2017 algorithm collapses to a small, well-defined set of follow-up recommendations. v0.1 uses these bins:

| Bin ID | Recommendation | Approximate clinical content |
|---|---|---|
| `no_routine_followup` | No routine follow-up | Single solid <6 mm, low-risk |
| `optional_ct_12mo` | Optional CT at 12 months | Single solid <6 mm, high-risk; or single sub-solid <6 mm |
| `ct_6_12mo_then_18_24mo_if_stable` | CT at 6-12 mo, then 18-24 mo if stable | Single solid 6-8 mm, low-risk |
| `ct_3_6mo_then_18_24mo` | CT at 3-6 mo, then 9-12 and 24 mo | Single solid 6-8 mm, high-risk; or single solid >8 mm low-risk |
| `consider_pet_or_biopsy` | Consider PET/CT, tissue sampling, or short-interval CT | Single solid >8 mm, high-risk; or sub-solid ≥6 mm with concerning features |
| `ct_3_6mo_subsolid` | CT at 3-6 months for sub-solid nodules ≥6 mm | Sub-solid ≥6 mm, initial workup |
| `multiple_nodule_dominant` | Follow-up keyed to most suspicious nodule | Multiple nodules — see dominant |

The exact bin list and mapping to Fleischner clauses will be reviewed by the maintainer (radiologist background) during case curation; this list is the design-draft starting point.

### 4.4 Out of scope for v0.1

- Imaging input (DICOM, JPG, PNG of CT slices)
- Prior-study comparison
- Tool calls / multi-turn agent loops
- Free-text rationale grading
- Lung-RADS (screening context — different algorithm, v0.3 track)
- ACR incidental-findings white papers (fuzzier guidelines — v0.3+ track)

## 5. Non-goals

RadGym is **not**:

- A clinical decision-support tool.
- A radiologist replacement benchmark ("can the AI replace a radiologist?").
- An FDA-regulated medical device.
- A general medical-QA benchmark (MedQA / MMLU-medical already serve that).
- A vision-language benchmark for image classification.

The benchmark scopes itself narrowly to **agentic radiology workflow reasoning** and treats every track as an instance of *"can the agent correctly apply the established protocol that a competent radiologist would apply?"* — not *"can the agent replace radiologists?"*.

## 6. Success criteria for v0.1

In priority order:

1. **Public leaderboard live** on Hugging Face Spaces with ≥6 reference baselines plus 1 rules-engine baseline within 3 weeks of repo init.
2. **≥10 external submissions** within 30 days of public launch.
3. **≥1 citation or significant mention** (paper, blog post, podcast, X thread by a recognized medical-AI account) within 90 days.
4. **Methodology defensible to a radiology-AI researcher** — i.e. a reviewer at *Radiology: AI* or *NEJM AI* would not reject the methodology section on principle.
5. **Maintainable solo** — total v0.1 codebase ≤1000 LOC excluding case data.

## 7. Build & launch plan

| Week | Work | Output |
|---|---|---|
| 1 | CONCEPT.md + METHODOLOGY.md drafted and redlined | Two design docs merged to main |
| 1-2 | Maintainer curates 200 Fleischner cases (afternoons) | `cases/v0.1/*.json` |
| 2 | Gradio leaderboard skeleton on HF Spaces, scoring code, 6 LLM baselines + rules-engine | Live URL, empty leaderboard |
| 3 | Run baselines, populate scores, write `SUBMISSION.md` | Leaderboard with 7 entries |
| 3 | Soft launch: /r/LocalLLaMA, X ML/medical-AI, HN Show HN | Public, accepting submissions |

## 8. Open questions for v0.1 redline

These are decisions the maintainer should confirm before METHODOLOGY.md is finalized:

1. **Recommendation bin list** — does §4.3 match the maintainer's reading of Fleischner 2017? Any merges, splits, or additions?
2. **Case mix** — what fraction of v0.1's 200 cases should be each bin? Uniform? Weighted toward edge cases (size = exactly 6 mm or 8 mm boundary)? Weighted toward clinical prevalence?
3. **Risk-factor encoding** — Fleischner specifies "high-risk" loosely (smoking, asbestos, family history, emphysema, fibrosis, age). Does v0.1 expose all of these as fields, or collapse to a binary `risk_category: low|high`?
4. **Multiple-nodule cases** — included in v0.1, or deferred to v0.2? The dominant-nodule rule is real Fleischner content but expands the case format.
5. **Sub-solid sub-typing** — does v0.1 distinguish ground-glass from part-solid, or treat as a single `sub_solid` type?

These are noted as TODOs in METHODOLOGY.md.
