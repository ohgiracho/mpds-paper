# Lost-in-the-middle position-control protocol v1

## Purpose

This MPDS-only experiment tests whether utilization of an unchanged long-context evidence set depends on whether a fixed evidence block is presented at the front, middle, or rear of the context. It addresses the reviewer's concern that evidence placed in the middle of a several-hundred-paper context may be underused.

## Frozen design

- Cases: 29, 1, 30, and 2.
- Evidence orderings: `XYZ`, `YZX`, and `ZXY`.
- Replicates: three independently generated outputs per case-ordering cell.
- Total: 4 cases × 3 orderings × 3 replicates = 36 MPDS outputs.
- Nominal calls: 36 × 9 = 324 Gemini calls, excluding citation-validation regenerations and transport retries.
- Generator: Vertex AI `gemini-2.5-pro`, temperature 0.5, maximum output 8192 tokens.
- Only manipulated factor: evidence-block position during debate turns.

## Outcome-independent case selection

The eligible set is the prespecified Core10 robustness subset. Cases must have exactly 500 records in both submitted frozen evidence pools. Eligible cases are ranked by the combined character count of their two frozen evidence files. No generation or evaluation score enters selection.

The top four are Case 29 (1,793,576 characters), Case 1 (1,751,882), Case 30 (1,652,646), and Case 2 (1,624,818).

## Fixed block construction

Each case has two evidence pools, one per scientist. Each pool is partitioned independently into three contiguous blocks `X`, `Y`, and `Z`. Complete record text and original record IDs are preserved exactly, and within-block canonical order is unchanged. The two cut points are chosen deterministically to minimize squared character imbalance across the three blocks.

The blocks are presented in three cyclic rotations:

- `XYZ`: X front, Y middle, Z rear.
- `YZX`: Y front, Z middle, X rear.
- `ZXY`: Z front, X middle, Y rear.

Thus every fixed block occupies every position exactly once. No block labels or position hints are inserted into model-visible knowledge files.

## Persona confound control

The submitted MPDS implementation derives each persona from the first 70,000 characters of its knowledge file. Reordering that same file would change both the persona and debate evidence position. To isolate debate-stage position, the controlled adapter supplies the canonical source snapshot to persona synthesis in all 36 runs and supplies the reordered snapshot only to the six debate turns. All original MPDS prompt builders, validation rules, moderator logic, and output formatting remain in the submitted case-specific script.

## Primary evidence-utilization outcomes

Citation pointers are mapped to the frozen case-pool-block membership table. The primary deterministic outcomes are:

- citation occurrences by front/middle/rear position;
- unique cited papers by position;
- citation share by position within each scientist pool and output;
- block coverage, defined as unique cited block records divided by records in that block;
- the same unique/occurrence measures restricted to the final moderator synthesis.

Pooled counts are descriptive. For inference, replicate values are first averaged within each fixed case-pool-block-position cell. Pool/block values are then averaged within case, leaving four paired case-level front/middle/rear estimates. Given only four cases, estimates, paired differences, and uncertainty are emphasized; absence of significance is not treated as equivalence.

## Secondary quality outcomes

After all 36 outputs pass generation and integrity validation, only final moderator syntheses enter a blinded three-candidate Pass 1 packet for each case-replicate. The frozen IHQ and scientific-practical validity rubric is reused. Intermediate personas and debate turns remain hidden from the evaluator.

## Recovery and logging

Live execution requires the exact config ID and explicit `--execute`. Completed cells are skipped. Failed cells are preserved under timestamped adjacent directories before retry. Each run records source/input hashes, block position maps, prompt characters, API token metadata, validation regenerations, runtime, and final-output hashes. API keys and the Google project identifier are never recorded.
