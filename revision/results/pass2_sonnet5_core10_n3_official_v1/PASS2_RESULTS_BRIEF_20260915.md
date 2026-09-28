# Official Pass 2 evidence audit — completion brief

## Completion and validation

- Judge model: Claude Sonnet 5 (`claude-sonnet-5`) through the official Anthropic Messages API.
- Scope: 30 blinded case–replicate packets, 150 candidate audits, and 726 sampled central claims.
- Balance: 30 candidate audits per condition (`Raw`, `EO`, `EOP`, `DS`, and `MPDS`).
- Validation: all 30 packet JSON files passed the unchanged canonical Pass 2 validator; 150/150 candidate rows were accepted.
- Candidate identity remained blinded during judging. Unblinding used the frozen `blind_key_DO_NOT_SHARE_WITH_RATERS.csv` only after validation.
- Three repeated evidence labels were removed in order-preserving fashion within claims. These set-preserving normalizations are recorded in `normalization_events.csv`; no score, support status, claim text, or rationale was changed.

## Descriptive scores

| Condition | Evidence support, mean ± SD | Citation traceability, mean ± SD |
|---|---:|---:|
| Raw | 0.00 ± 0.00 | 0.00 ± 0.00 |
| EO | 2.40 ± 1.35 | 2.63 ± 1.50 |
| EOP | 2.37 ± 1.25 | 2.50 ± 1.38 |
| DS | 1.77 ± 1.14 | 1.83 ± 1.32 |
| MPDS | 2.10 ± 0.88 | 2.07 ± 0.98 |

Raw outputs had no supplied citation abstracts by design. Their zero evidence-support and traceability scores therefore indicate absence of auditable supplied evidence, not scientific falsity.

## Claim-status results

| Condition | Claims | Directly supported | Supported or partially supported | Unsupported or contradicted | Unverifiable |
|---|---:|---:|---:|---:|---:|
| Raw | 150 | 0.0% | 0.0% | 0.0% | 100.0% |
| EO | 138 | 51.4% | 80.4% | 13.8% | 5.8% |
| EOP | 146 | 45.2% | 79.5% | 16.4% | 4.1% |
| DS | 146 | 24.0% | 67.8% | 15.1% | 17.1% |
| MPDS | 146 | 28.8% | 81.5% | 9.6% | 8.9% |

These are pooled descriptive proportions over the claims selected by the judge. They are not independent claim-level inferential tests.

## Prespecified MPDS–DS case-level comparison

The inferential unit was the case-level mean across three replicates (`n = 10` paired cases).

| Outcome | Mean MPDS − DS | Case-bootstrap 95% CI | Exact two-sided sign-flip p | Win / tie / loss |
|---|---:|---:|---:|---:|
| Evidence support score | +0.333 | −0.233 to +0.833 | 0.328 | 6 / 2 / 2 |
| Citation traceability score | +0.233 | −0.400 to +0.867 | 0.570 | 5 / 2 / 3 |
| Supported or partially supported claim proportion | +0.133 | −0.033 to +0.307 | 0.227 | 6 / 1 / 3 |
| Unsupported or contradicted claim proportion | −0.080 | −0.180 to +0.013 | 0.195 | 3 / 2 / 5 |
| Unverifiable claim proportion | −0.053 | −0.173 to +0.073 | 0.523 | 3 / 2 / 5 |

All intervals include zero. The data support a directionally favorable but statistically inconclusive MPDS-versus-DS interpretation. They do not establish that MPDS significantly improves citation support or reduces hallucination.

## Manuscript-safe conclusion

An independent blinded Pass 2 audit found that MPDS outputs had descriptively higher evidence-support and citation-traceability scores than DS outputs. At the claim level, 81.5% of sampled MPDS claims were at least partially supported by the supplied abstracts and 9.6% were unsupported or contradicted, compared with 67.8% and 15.1%, respectively, for DS. However, paired case-level confidence intervals included zero for all MPDS–DS contrasts. These findings therefore indicate a favorable trend rather than confirmatory evidence of superiority. Raw outputs lacked supplied citation abstracts by design, so their results quantify non-traceability within this audit and should not be interpreted as scientific incorrectness.

## Claims that should not be made

- Do not claim a statistically significant improvement of MPDS over DS in evidence support or traceability.
- Do not call the unsupported-or-contradicted rate a definitive hallucination rate.
- Do not interpret `unverifiable` as scientifically false.
- Do not treat candidate-level or claim-level observations as 150 or 726 independent experimental units; the paired inferential unit is the case (`n = 10`).
- Do not claim human-expert agreement. A two-domain expert audit remains a separate pending validation step.

## API usage and estimated cost

- Selected official results: 150 successful candidate calls.
- Selected usage: 1,572,022 base input tokens; 41,134 cache-write tokens; 577,216 cache-read tokens; 302,389 output tokens.
- Estimated selected-result cost: USD 6.386.
- Including seven billable HTTP-200 responses discarded during format pilots or retries: 157 calls and approximately USD 6.796 total.
- Six recorded HTTP-error artifacts had no response usage tokens.
- This is a usage-based estimate under the published global standard Claude Sonnet 5 rates; the provider invoice is authoritative.

## Reproducibility files

- `assembly_manifest.json`: completion, balance, hashes, selected usage, and normalization count.
- `strict_validation_summary.json`: independent 30-packet canonical validation.
- `pass2_scores_unblinded.csv`: 150 candidate-level score and flag rows.
- `pass2_claims_unblinded.csv`: 726 claim-level audit rows.
- `condition_summary.csv`, `claim_status_summary.csv`, and `flag_summary.csv`: descriptive summaries.
- `mpds_vs_ds_inference.csv`: paired case-level estimates, confidence intervals, and exact tests.
- `api_usage_audit.json`: selected and all-recorded HTTP-200 token/cost audit.
