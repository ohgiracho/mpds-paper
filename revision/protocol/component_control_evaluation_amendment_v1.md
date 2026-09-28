# Component Control Evaluation Amendment v1

Status: **FROZEN BEFORE ANY COMPONENT-CONTROL JUDGING CALL**

Frozen date: 2026-09-20

This amendment changes only the blinded evaluation set used for the new SAIR and SES component controls. It does not alter any candidate-generation output or the completed five-condition Raw, EO, EOP, DS, and MPDS analyses.

## Rationale

The original component-control protocol proposed a seven-condition packet. Before any SAIR or SES score was generated or inspected, the evaluation scope was narrowed to the four conditions needed to answer the reviewer’s component-attribution question directly: DS, MPDS, SAIR, and SES.

Scoring only SAIR and SES and comparing those scores with the historical five-condition DS score was rejected because the judge context would differ. Re-evaluating DS and MPDS alongside the two new controls preserves a common packet context for every declared component-control contrast while avoiding the unnecessary Raw, EO, and EOP candidates. The completed five-condition analysis remains the authoritative analysis for Raw, EO, and EOP.

## Pass 1 design

- Cases: 1, 2, 3, 4, 8, 15, 18, 22, 29, and 30.
- Replicates: 1, 2, and 3.
- Conditions: DS, MPDS, SAIR, and SES.
- Packets: 30 matched case-replicate packets.
- Candidates: 120 total candidate instances.
- Blinding: Candidate A through Candidate D under a deterministic seeded cyclic schedule.
- Alias balance: because 30 is not divisible by 4, each condition must occupy every alias position either 7 or 8 times, with a maximum imbalance of one.
- Judge: the same independent non-Gemini model family and unchanged IHQ and supplementary Pass 1 rubrics used for the completed five-condition analysis.
- Existing DS and MPDS candidate bodies must hash-match their bodies in the completed five-condition blind packets.

## Declared comparisons

Primary comparisons:

- DS minus SAIR: interactive neutral multi-agent debate versus call-matched and nominal-evidence-exposure-matched single-agent iterative revision.
- DS minus SES: multi-round neutral debate versus independent split-evidence processing followed by non-interactive synthesis. The seven-call versus three-call difference remains explicit.

Secondary comparisons:

- MPDS minus DS: incremental persona-conditioned debate effect within the new packet context.
- MPDS minus SAIR: full MPDS versus single-agent iterative revision.
- MPDS minus SES: full MPDS versus non-interactive split-evidence synthesis.

EO minus SES is not an inferential contrast in this amended pass because EO is not re-evaluated in the same packet context. Any historical EO comparison must be labelled descriptive and cross-context.

## Inference and interpretation

The primary inferential unit remains the case-level mean across three replicates. The analysis uses paired case-level estimates, two-sided exact sign-flip tests, paired Wilcoxon companion tests, case-resampled confidence intervals, and Holm correction within the declared component-control comparison family. Unadjusted scores and prespecified output-length sensitivity analyses are both reported.

The four-condition analysis is a separate control analysis. It does not replace or overwrite the completed five-condition scores. Absolute score shifts between the old and new DS or MPDS evaluations are treated as packet-context sensitivity, not as new stochastic generations.
