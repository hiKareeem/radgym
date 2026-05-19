# RadGym v0.1 — Inter-rater κ review

Thank you for reviewing these cases. Your independent labels will be
compared to my labels to compute Cohen's κ for the methodology section.

## What to do

1. Open `cases_for_reviewer.csv` in Excel, Google Sheets, Numbers, or any
   CSV-aware tool.
2. For each row, read the patient + nodule columns and fill in:
   - **reviewer_recommendation** (required): your Fleischner 2017
     recommendation, picking ONE of these 7 bin IDs:
     - no_routine_followup
     - optional_ct_12mo
     - ct_6_12mo_then_18_24mo_if_stable
     - ct_3_6mo_then_18_24mo
     - subsolid_workup
     - consider_pet_or_biopsy
     - multiple_nodule_dominant
   - **reviewer_dominant_recommendation** (required ONLY if your
     `reviewer_recommendation` is `multiple_nodule_dominant`): the bin
     you would apply per Table 1A/1B's "Multiple" row. Same allowed
     values as above, except not `multiple_nodule_dominant` itself.
   - **reviewer_notes** (optional): any case where you want to flag
     ambiguity, methodology concerns, or "this case doesn't fit
     Fleischner 2017 cleanly."
3. Send the filled CSV back. Whatever you find easiest — email
   attachment, shared link, smoke signal.

## Important framing

- Apply **Fleischner 2017** (MacMahon et al., Radiology 2017). Not 2005.
- Cases are scoped to incidental indeterminate nodules in
  patients ≥35 years, no known primary cancer, not immunocompromised.
  Benign-feature nodules (perifissural, classic granuloma calcification,
  hamartoma fat) are excluded from the case set.
- For multiple-nodule cases, apply the "Multiple" row of Table 1A or 1B,
  NOT the single-nodule rule for the dominant nodule.
- Patient risk classification is up to you (synthesize from the
  `risk_factors` column). The benchmark's own oracle uses a conservative
  rule (any of: current/former smoker, asbestos, FHx, emphysema, fibrosis
  → high; otherwise low) but your clinical judgment is what we want.

## Time estimate

~1-2 minutes per case. ~30-60 minutes total for 30 cases.

## Questions

Just reply to my email. Happy to clarify any case or the methodology.

— Kareem
