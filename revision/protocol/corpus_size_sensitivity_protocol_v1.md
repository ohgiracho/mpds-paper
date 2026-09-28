# Corpus-size sensitivity protocol v1

## Purpose

This experiment addresses the reviewer's request for a justification of the 500-abstract evidence-pool setting. It is a separate MPDS-only sensitivity analysis and does not replace the original five-condition experiment.

## Frozen design

- Cases: 2, 4, 15, and 29.
- Corpus sizes: 100, 250, 500, and 1000 records **per evidence pool**.
- Replicates: three independently generated MPDS outputs per case-size cell.
- Total outputs: 4 cases × 4 corpus sizes × 3 replicates = 48.
- Nominal generation calls: 48 × 9 = 432, excluding validation regenerations and transport retries.
- Generator: Gemini 2.5 Pro through Vertex AI, temperature 0.5, maximum output 8192 tokens.
- Only manipulated factor: the number of relevance-ranked OpenAlex records retained in each evidence pool.

## Nested retrieval control

Each case has two submitted OpenAlex queries and its original publication-year cutoff. Each query is executed once to obtain an ordered master snapshot of 1000 abstract-bearing works. Smaller corpora are exact ordered prefixes:

`top 100 ⊂ top 250 ⊂ top 500 ⊂ top 1000`

The master JSONL, all derived knowledge files, query parameters, retrieval time, OpenAlex identifiers, ranks, relevance scores, record counts, and SHA-256 hashes are frozen before any Gemini generation begins. A condition is not allowed to run unless both pools pass the prefix, uniqueness, cutoff, record-count, and hash checks.

The sensitivity snapshots are newly frozen retrievals. Their top-500 condition is internally comparable with the other sizes but is not assumed to reproduce the historical 500-paper snapshot exactly, because the live OpenAlex index and relevance ranking can change over time.

## Exact meaning of the 70,000-character limit

The submitted MPDS code uses only the first 70,000 characters of each selected knowledge file for the two persona-synthesis calls. It does **not** truncate the evidence supplied to the debate turns: the full selected top-N snapshot is inserted into each of the three turns for the corresponding scientist. The moderator receives the debate transcript rather than the raw evidence pools.

Accordingly, every run records two separate exposure measures:

1. Persona exposure: selected characters from each pool, capped at 70,000.
2. Debate exposure: full selected knowledge-file characters per turn and their nominal cumulative injection across three turns.

The call-level log additionally records the actual complete prompt characters and provider-reported input/output token counts. This prevents a false claim that the 500- and 1000-paper conditions had identical effective inputs merely because persona construction saturated at 70,000 characters.

## Case selection

- Case 2: manuscript Case Study 1 and a sodium-ion composition/process problem.
- Case 4: aqueous zinc-ion cathode and multivalent-ion transport.
- Case 15: lithium-selenium cathode, host confinement, and shuttle suppression.
- Case 29: protocol-centered aqueous zinc-ion reasoning.

Case 1 was considered because it is manuscript Case Study 2, but its unchanged pool-A search currently contains only 782 abstract-bearing core OpenAlex works in the 2015-2024 window. Expanding its query or retrieval corpus solely to reach 1000 would confound corpus size with retrieval definition, so it is excluded from the balanced four-case experiment and the reason is retained in the configuration.

## Run order and recovery

The run order is deterministically block-randomized within each replicate using the frozen seed in the configuration. Completed runs are skipped on resume. A failed run is preserved under an adjacent timestamped directory before a retry begins. The batch status file is refreshed after every attempted output.

The default command is dry-run only. Live generation additionally requires an explicit `--execute`, the frozen configuration ID, Vertex authentication, and a positive execution cap.

## Logged fields

- master retrieval count and selected top-N count for each pool;
- parsed downstream paper count;
- source and selected-file hashes;
- selected knowledge-file characters and bytes;
- persona-selected characters after the 70,000-character cap;
- full debate knowledge characters per turn and nominal cumulative injection;
- actual prompt characters for every API call;
- provider input, output, thought, and total tokens when available;
- attempted, successful, and failed API calls;
- wall-clock and API elapsed time;
- retries, validation regenerations, error class, and error message;
- final and full-output hashes.

## Deferred evaluation

After all 48 outputs pass generation validation, only the final moderator syntheses will be placed in blinded evaluation packets. Intermediate personas and debate turns are excluded. IHQ without CPI, Full IHQ, and scientific-practical validity will be scored using the already frozen evaluation instruments. Citation utilization, tokens, cost, and runtime will be calculated deterministically from the run artifacts.

No claim requires 500 papers to be best. A plateau from 250 to 500 with no material gain at 1000 supports describing 500 as a practical operating point rather than a formally optimized value.
