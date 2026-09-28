# SAIR/SES Component-Control Pass 2 Results Brief

## Completion and protocol

- Status: PASS.
- Design: 10 cases × 3 generation replicates × 4 conditions (DS, MPDS, SAIR, SES) = 120 candidate-level audits.
- Pass 2 execution unit: one blinded candidate per Anthropic request. Candidates were not shown together and the evaluator was not asked to rank conditions.
- Evaluator: official Anthropic Messages API, `claude-sonnet-5`, frozen single-candidate prompt/schema, strict forced tool output, no external tools.
- DS and MPDS: reused from the prior official Pass 2 only after 60/60 source-output hash matches, 60/60 evidence-record-group matches, and 10/10 case-knowledge snapshot matches.
- SAIR and SES: 60 new candidate audits. All 30 packets are COMPLETE and final strict-validation errors are zero.

## Descriptive results

The claim rates below pool all audited claims within each condition. They are descriptive; formal comparisons use the case as the analysis unit after averaging the three generation replicates.

| Condition | Evidence support, mean (SD) | Citation traceability, mean (SD) | Strictly supported claims | Supported or partially supported claims |
|---|---:|---:|---:|---:|
| DS | 1.77 (1.14) | 1.83 (1.32) | 23.97% | 67.81% |
| MPDS | 2.10 (0.88) | 2.07 (0.98) | 28.77% | 81.51% |
| SAIR | 2.37 (1.00) | 1.93 (0.94) | 34.25% | 90.41% |
| SES | 2.57 (0.50) | 2.27 (0.64) | 43.33% | 94.00% |

## Case-clustered comparisons

The declared comparison family contains five contrasts within each metric: DS−SAIR, DS−SES, MPDS−DS, MPDS−SAIR, and MPDS−SES. Two-sided Wilcoxon tests are Holm-adjusted within each metric; exact sign-flip tests and case-bootstrap 95% intervals are also reported.

- DS versus SES, evidence support: mean DS−SES difference −0.80 points; case-bootstrap 95% CI −1.30 to −0.37; wins/ties/losses 0/2/8; raw Wilcoxon p=0.0078; Holm-adjusted p=0.0391; exact sign-flip p=0.0078. This was the only comparison/metric surviving the declared Holm correction at 0.05.
- DS versus SAIR, evidence support: mean difference −0.60; 95% CI −1.20 to approximately 0; wins/ties/losses 3/0/7; Holm-adjusted p=0.3164. Directionally favorable to SAIR but not multiplicity-adjusted significant.
- MPDS versus DS, evidence support: mean difference +0.33; 95% CI −0.23 to +0.83; Holm-adjusted p=0.3906. The estimate favors MPDS descriptively but is inconclusive at n=10 cases.
- Citation traceability: none of the five contrasts survived Holm correction. Descriptive means were close, with SES highest.
- Supported-or-partially-supported claim rate: DS was lower than both SAIR and SES by case-clustered mean differences of 0.187 and 0.171, respectively. Each raw Wilcoxon p was 0.0313, but each Holm-adjusted p was 0.1563.
- Strict supported-claim rate: DS−SES was −0.101 by the case-clustered analysis; raw Wilcoxon p=0.0469 and Holm-adjusted p=0.2344.

## Interpretation for the revision

The evidence-audit results should not be presented as showing that MPDS dominates the two component controls on every axis. Instead, they show that retrieval- and evidence-focused controls, especially SES, can obtain stronger evidence support under this audit. That is informative rather than fatal: Pass 2 measures grounding and traceability, whereas Pass 1 separately measures the IHQ/validity dimensions relevant to the multi-persona debate hypothesis.

A defensible revision claim is therefore that MPDS improves over DS descriptively on evidence support and supported-or-partial claim coverage, while SAIR/SES establish that part of the observed grounding performance can be reproduced or exceeded by simpler evidence-oriented controls. Any distinct MPDS contribution should be argued from the joint Pass 1 and Pass 2 pattern, not from Pass 2 alone.

Because the formal unit is only 10 cases, non-significant contrasts must not be described as equivalence. Likewise, pooled claim rates should not be used as inferential p-values because candidates contribute different numbers of central claims.

## API and retry audit

- Selected final SAIR/SES results: 60 candidate audits.
- Actual HTTP 200 calls: 61.
- Retry overhead: one discarded call. `case_18__rep_01`, Candidate C reached the frozen 4,000-output-token limit; the incomplete response was preserved and the candidate succeeded on attempt 2 without changing the protocol.
- All calls including retry: 1,353,703 input tokens; 166,565 output tokens; 16,548 cache-creation tokens; 235,809 cache-read tokens.
- Selected accepted outputs: 1,325,933 input tokens; 162,565 output tokens; 16,548 cache-creation tokens; 231,672 cache-read tokens.
- Approximate summed request-to-response time from artifact timestamps: 1,763.6 seconds (29.4 minutes). Provider billing records remain authoritative.

## Principal output files

- `pass2_scores_unblinded.csv`: 120 candidate-level audit rows.
- `pass2_claims_unblinded.csv`: 588 central-claim audit rows.
- `condition_summary.csv`: candidate-level descriptive scores.
- `claim_status_summary.csv`: pooled claim-status counts and rates.
- `component_control_pairwise_case_clustered.csv`: declared case-level paired comparisons.
- `case_means_n10.csv`: case means across three replicates.
- `api_usage_audit_new_sair_ses.json`: actual-call and retry audit.
- `assembly_manifest.json` and `analysis_manifest.json`: provenance and analysis declarations.
