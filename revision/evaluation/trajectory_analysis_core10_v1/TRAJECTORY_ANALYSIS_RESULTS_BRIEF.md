# Exploratory trajectory-level analysis results

## Purpose and relationship to prior evaluation

This post-hoc exploratory analysis examines how critiques and alternative perspectives changed or integrated into final hypotheses. Pass 1 assessed final-output quality and Pass 2 assessed evidence grounding; neither is replaced or rescored here.

## Data and integrity

All 120 trajectories were evaluated: 10 scientific cases × 3 replicates × 4 conditions. Condition labels were masked, but full architectural blinding was impossible because stage structures differed. Inferential comparisons use case-level means (n = 10), not 120 trajectories.

## Rubric

Four independent 0–4 dimensions were frozen before evaluation: tension recognition, adaptive revision, integrative trade-off resolution, and non-additive synthesis. The optional 0–16 sum is reported only as an exploratory composite.

## Case-level descriptive means

| Condition | Tension | Adaptive revision | Trade-off resolution | Non-additive synthesis | Exploratory composite |
|---|---:|---:|---:|---:|---:|
| DS | 3.267 | 3.033 | 2.900 | 2.800 | 12.000 |
| MPDS | 3.400 | 3.367 | 3.133 | 3.067 | 12.967 |
| SAIR | 2.867 | 2.967 | 2.867 | 2.067 | 10.767 |
| SES | 2.333 | 2.033 | 2.133 | 2.133 | 8.633 |

## Prespecified case-level comparisons

| Contrast | Dimension | Mean difference | Bootstrap 95% CI | W/T/L | Sign-flip p (Holm) | Wilcoxon p (Holm) |
|---|---|---:|---:|---:|---:|---:|
| mpds_minus_ds | tension_recognition | 0.133 | [0.033, 0.233] | 4/6/0 | 0.2812 | 0.2812 |
| mpds_minus_ds | adaptive_revision | 0.333 | [0.133, 0.533] | 6/4/0 | 0.1641 | 0.1641 |
| mpds_minus_ds | tradeoff_resolution | 0.233 | [0.033, 0.400] | 6/3/1 | 0.2812 | 0.2812 |
| mpds_minus_ds | nonadditive_synthesis | 0.267 | [-0.000, 0.500] | 7/2/1 | 0.2812 | 0.2812 |
| mpds_minus_sair | tension_recognition | 0.533 | [0.400, 0.667] | 10/0/0 | 0.0234 | 0.0234 |
| mpds_minus_sair | adaptive_revision | 0.400 | [0.167, 0.633] | 8/1/1 | 0.1641 | 0.1641 |
| mpds_minus_sair | tradeoff_resolution | 0.267 | [0.067, 0.433] | 7/2/1 | 0.2188 | 0.2188 |
| mpds_minus_sair | nonadditive_synthesis | 1.000 | [0.800, 1.200] | 10/0/0 | 0.0234 | 0.0234 |
| mpds_minus_ses | tension_recognition | 1.067 | [0.867, 1.300] | 10/0/0 | 0.0234 | 0.0234 |
| mpds_minus_ses | adaptive_revision | 1.333 | [1.067, 1.633] | 10/0/0 | 0.0234 | 0.0234 |
| mpds_minus_ses | tradeoff_resolution | 1.000 | [0.767, 1.267] | 10/0/0 | 0.0234 | 0.0234 |
| mpds_minus_ses | nonadditive_synthesis | 0.933 | [0.633, 1.233] | 9/1/0 | 0.0273 | 0.0273 |

## Revision-event patterns

Revision-event extraction is descriptive; event counts are not treated as independent observations.

| Condition | Extracted events | Substantive events | Trajectories with ≥1 substantive event |
|---|---:|---:|---:|
| DS | 90 | 83 | 30/30 |
| MPDS | 90 | 90 | 30/30 |
| SAIR | 89 | 82 | 30/30 |
| SES | 82 | 58 | 28/30 |

Type-specific descriptive counts are provided in `trajectory_event_type_frequencies.csv`; event texts and substantive flags are retained in `trajectory_revision_events.csv`. Frozen-rule examples are in `trajectory_qualitative_examples.md`.

## Exploratory interpretation

MPDS had higher case-level means than DS in all four dimensions, but none of the MPDS–DS comparisons survived Holm correction. Relative to SAIR, MPDS showed corrected evidence of higher tension recognition and non-additive synthesis, while adaptive revision and trade-off resolution remained directionally positive but uncertain. Relative to SES, MPDS was higher in all four dimensions across nearly every case, and all four corrected tests were below 0.05. These patterns are consistent with a process-level integration benefit of interactive debate in the tested cases, while the smaller and statistically uncertain MPDS–DS differences indicate that the incremental contribution of persona conditioning cannot be isolated confidently here.

## Limitations

This analysis is exploratory and post hoc. Architecture could be inferred from trajectory form, evaluator scores are not human-expert ratings, and the 10-case sample limits precision. Longer or multi-agent trajectories were explicitly not rewarded by default. Non-significance is not evidence of equivalence.

## Manuscript wording recommendation

“To better understand how the reasoning architectures differed mechanistically, we conducted an exploratory trajectory-level analysis of the existing Core10 replicates. Condition labels were masked, although complete architectural blinding was not possible because trajectory structures differed. Scores were aggregated within case before paired comparisons (n = 10 cases). MPDS showed consistently higher process-level scores than SES and higher tension-recognition and non-additive-synthesis scores than SAIR after multiplicity correction, whereas its smaller advantages over DS were statistically uncertain. These findings are consistent with greater adaptive integration in the tested interactive-debate trajectories, but do not establish universal architectural superiority or isolate a definitive incremental effect of persona conditioning.”
