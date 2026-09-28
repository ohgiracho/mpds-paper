# Lost-in-the-middle blind Pass 1 evaluation protocol v1

Status: frozen before any LITM Claude evaluation call  
Generation source: 36 COMPLETE outputs from `lost_in_middle_position_control_v1`  
Evaluation model: direct Anthropic `claude-sonnet-5`

## Packet unit

Create one packet for each case–replicate pair. Each of the 12 packets contains the cleaned final moderator answer from all three frozen evidence orderings: `XYZ`, `YZX`, and `ZXY`. The three orderings are assigned to Candidate A–C using the same seeded balanced cyclic aliasing method used in the prior official Pass 1 evaluations. Each ordering occupies every alias exactly four times.

Only the final moderator synthesis is scored. Persona descriptions, debate trajectories, evidence appendices, source ordering labels, run metadata, and deterministic citation-attribution results are excluded from the packet.

## Evaluation instruments

Use without substantive change:

1. the verbatim public GitHub IHQ Scoring Rules;
2. Pass 1 of `supplementary_evaluation_module_v1.md`;
3. the official direct-Anthropic forced-tool submission and strict local validation implementation.

The only implementation adaptation is candidate cardinality: Candidate A–C instead of Candidate A–D. Score candidates independently and do not rank or compare candidates inside the prompt.

## Outcomes and aggregation

- IHQ without CPI
- Full IHQ
- Scientific correctness
- Physical plausibility
- Constraint adherence
- Falsifiability/actionability
- Descriptive validity composite
- Prespecified validity flags

Average the three replicate scores within each case and ordering. Inferential comparisons use four paired scientific cases, not 36 independent outputs. Emphasize estimates, direction counts, and heterogeneity; do not interpret non-significance as equivalence.

## Separation from deterministic citation analysis

The blind Pass 1 evaluation concerns final-answer hypothesis quality and validity. It does not resolve or use Scientist A/B citation-pool attribution. The versioned post-processing required for unscoped final citations is a separate deterministic evidence-utilization analysis and does not alter packet contents or the scoring rubric.
