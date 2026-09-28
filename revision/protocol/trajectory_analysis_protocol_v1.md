# Exploratory trajectory-level analysis protocol v1

## Scope

This is a post-hoc exploratory mechanistic analysis of the already generated Core10 × three-replicate DS, MPDS, SAIR, and SES trajectories. It is not a new generation experiment, a replacement for Pass 1 or Pass 2, or a primary superiority benchmark.

The analysis asks one question: how did critiques, alternative perspectives, or independent branches substantively modify and integrate into the final scientific hypothesis?

## Inputs

- DS and MPDS replicate 1: the public submitted debate logs in the frozen GitHub repository.
- DS and MPDS replicates 2–3: accepted `full_output.txt` files in the Core10 Vertex run set.
- SAIR: accepted seven-stage `trajectory.json` files.
- SES: accepted `independent_answers.json` plus `final.txt`.

All 120 source trajectories are read-only. Each source file, normalized trajectory body, and evaluation packet is hashed.

## Deterministic packet preprocessing

Run metadata, local paths, API metadata, citation-validation metadata, and automatically generated evidence appendices are excluded. They are not part of the reasoning transition being judged and would create architecture-dependent length differences. No substantive reasoning text is truncated. The scientific task, chronological stage text, speaker/stage labels, and final synthesis are retained.

MPDS persona summaries are not uniformly available for legacy replicate 1. To avoid replicate-dependent treatment, only the enacted persona labels already embedded in all debate transcripts are retained. Persona labels alone must not affect scores.

## Masking

Each case–replicate packet contains four trajectories under a seeded, balanced cyclic assignment to Trajectory A–D. The condition key is stored separately. Condition names are absent from evaluator-visible packets. This is label-masked, not fully architecture-blinded, because the number and form of stages reveal aspects of the architecture.

## Evaluation

The frozen trajectory-specific rubric independently scores four 0–4 dimensions: tension/conflict recognition, adaptive revision/responsiveness, integrative trade-off resolution, and non-additive synthesis. Up to three major revision events are extracted per trajectory. General correctness, evidence support, citation density, answer length, novelty, writing, and formatting are excluded.

One packet is one paid evaluator call containing four independently scored trajectories. The evaluator is Claude Sonnet 5 through the official Anthropic Messages API, with no temperature override and no external tools except the forced structured submission tool.

## Analysis

Trajectory-level values are descriptive. Inferential comparisons first average the three replicates within each condition and case. The independent unit is therefore the scientific case (`n = 10`). Prespecified contrasts are MPDS–DS, MPDS–SAIR, and MPDS–SES for each dimension.

Reported statistics are paired mean difference, case-bootstrap 95% CI, win/tie/loss, exact paired sign-flip p-value, and Wilcoxon signed-rank p-value. Holm correction is applied separately across the 12 dimension-level tests in each p-value family. The optional 0–16 sum is always called the exploratory composite and is excluded from the primary multiplicity family.

## Interpretation

Results are reported regardless of direction. Non-significance is not equivalence. Claims are limited to the tested cases and to exploratory process-level patterns.
