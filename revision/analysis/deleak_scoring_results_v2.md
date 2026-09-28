# Targeted de-leaking blind scoring results v2

Scope: Cases 1, 8, 22; three paired original/de-leaked replicates each. Pass 1 uses official direct-Anthropic Claude Sonnet 5, unchanged IHQ and supplementary Pass 1 rubrics. All original and de-leaked final answers were freshly rescored in nine A/B packets. The target-recovery audit was a separate single-answer blind evaluation.

## Case-level results

| Case | IHQ w/o CPI original → de-leaked (Δ) | Full IHQ original → de-leaked (Δ) | Validity sum original → de-leaked (Δ) | Explicit target recovery original → de-leaked |
| --- | ---: | ---: | ---: | ---: |
| 1 | 9.33 → 9.00 (-0.33) | 13.00 → 12.33 (-0.67) | 12.33 → 9.00 (-3.33) | 2/3 → 0/3 |
| 8 | 10.00 → 6.00 (-4.00) | 13.67 → 8.33 (-5.33) | 12.67 → 13.00 (+0.33) | 0/3 → 0/3 |
| 22 | 8.67 → 7.67 (-1.00) | 12.00 → 10.67 (-1.33) | 13.00 → 13.33 (+0.33) | 0/3 → 0/3 |

Deltas are de-leaked minus original. The IHQ-without-CPI scale is 0–15, Full IHQ 0–20, and the descriptive four-dimension validity sum 0–20. The validity sum does not contribute to IHQ. Replicate-level scores, ranges, output lengths and four validity dimensions are in the companion CSVs.

## Interpretation and audit status

- ihq_without_cpi: de-leaked case means higher in 0/3, lower in 3/3, equal in 0/3 cases.
- full_ihq: de-leaked case means higher in 0/3, lower in 3/3, equal in 0/3 cases.
- validity_composite_descriptive: de-leaked case means higher in 2/3, lower in 1/3, equal in 0/3 cases.
- Pass 1: 9/9 packets COMPLETE; 9 actual API attempts; 97,580 input and 17,302 output tokens.
- Target-recovery audit: 18/18 packets received model responses in 30 API attempts; 129,577 input and 21,488 output tokens. Original strict validation accepted 7/18. A condition-blind, uniformly applied format adjudication accepted 18/18 without changing feature labels; it corrected 7 model overall labels by the frozen case-specific rule. Nine quoted excerpts required ellipsis/Markdown/literal-fragment normalization. This is a disclosed post-format repair, not 18/18 strict original success.
- After unblinding and the initial aggregate, a Case 8 consistency review found one response whose combined-feature label was explicit while its porous/permeable-wall feature was only partial. Full recovery requires all constituent features in the frozen definition; a key-independent but post-unblinding v3 correction changed this response's overall label to partial without changing any feature label. The earlier v1 aggregate is superseded by this version. Because this extra correction was noticed after unblinding, treat the target-recovery result as exploratory pending independent human review.
- Three original replicate-1 controls are public legacy outputs verified by file/body hashes but lack full run manifests. Replicates 2–3 have checked Gemini 2.5 Pro, temperature 0.5, and evidence hashes.
- This is a targeted sensitivity analysis of the three very-high-risk cases in Core10, not proof of robustness across all 30 cases. The revised prompt broadened some design choices as well as removing target cues; a fixed evidence corpus may still contain target-associated concepts. No p-values are reported for n=3 cases.

## Reproducibility files

- `analysis/deleak_pass1_scores_by_replicate_v2.csv`
- `analysis/deleak_target_recovery_by_replicate_v2.csv`
- `analysis/deleak_case_comparison_v2.csv`
- `analysis/deleak_recovery_blind_adjudication_v3.json`
