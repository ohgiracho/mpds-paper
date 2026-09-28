# Two-Expert Human Evaluation Frozen Analysis

The two supplied Word score sheets were hashed and analyzed without editing the originals. Each expert scored all 70 run-2 candidates (10 cases x 7 methods). The 0-5 dimensions were combined as no-CPI IHQ = IN + MO + TR, full IHQ = no-CPI IHQ + CPI, and validity = SC + PP + CA + FA.

## Condition means across 10 cases

| Condition | No-CPI IHQ /15 | Full IHQ /20 | Validity /20 |
|---|---:|---:|---:|
| RAW | 9.80 | 12.70 | 10.40 |
| EO | 10.85 | 14.20 | 13.30 |
| EOP | 10.30 | 13.50 | 12.45 |
| DS | 9.80 | 13.30 | 10.20 |
| MPDS | 11.95 | 16.05 | 14.35 |
| SAIR | 11.65 | 15.35 | 12.40 |
| SES | 11.00 | 14.90 | 12.45 |

## Prespecified human contrast

MPDS - DS on no-CPI IHQ: +2.15 points (95% case-bootstrap CI +1.20 to +3.15); wins/ties/losses 9/0/1; two-sided exact sign-flip p = 0.0039. The unit is 10 paired cases, after averaging the two expert ratings for each candidate.
MPDS - DS on validity: +4.15 points (95% CI +3.00 to +5.35); p = 0.0020. This is a secondary outcome.
The no-CPI IHQ difference was positive for both experts separately: expert 1 +2.20 and expert 2 +2.10 points.
On these same run-2 outputs, the original five-condition Claude batch gave MPDS - DS differences of +0.70 no-CPI IHQ and +0.50 validity points. The human-versus-Claude gap must be reported rather than presenting the human ratings as confirmation of automated validity scoring.

## Inter-rater agreement

- ihq_without_cpi: ICC(2,1) = 0.047 (95% case-cluster-bootstrap CI -0.241 to 0.275).
- full_ihq: ICC(2,1) = 0.199 (95% case-cluster-bootstrap CI -0.094 to 0.401).
- validity: ICC(2,1) = 0.207 (95% case-cluster-bootstrap CI -0.092 to 0.468).

## Important reporting limits

- All 70 case labels and eight dimension scores are present in each frozen source sheet. The source DOCX files were not changed by this analysis.
- The shared packet did not independently randomize candidate aliases per expert, despite the planning prose saying it would. The A-G letters have no fixed method identity across cases.
- The source sheets have blank Expert ID/Date fields, and several notes refer to the held-out paper. Reference-solution blinding should be confirmed before asserting it in a manuscript or reviewer reply.
- At least one candidate answer (C07-G) explicitly calls itself a raw baseline assistant. Thus, condition labels were masked administratively, but some architecture clues remained in the response text.
- Human ratings cover a single prespecified run (run 2), so this analysis does not estimate run-to-run human-score variability.
- Claude concordance is separated by the original five-condition judge batch and the separate four-condition component-control judge batch; batch scores are not merged into a single calibrated scale.
