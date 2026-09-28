# SAIR and SES Component Control Protocol v2

Status: frozen before any SAIR or SES model call

Frozen date: 2026-09-15

This amendment governs only the two new component controls requested in Reviewer 2 Question 2. It does not alter, replace, or overwrite the completed Raw, EO, EOP, DS, MPDS, Pass 1, or Pass 2 results. The historical `experiment_protocol_v1.md` remains the record of the earlier planning stage.

## 1. Scope

- Cases: repository cases 1, 2, 3, 4, 8, 15, 18, 22, 29, and 30
- Replicates: three independent stochastic generations per case and condition
- New conditions: SAIR and SES
- Candidate model: Gemini 2.5 Pro
- Temperature: 0.5
- Maximum output tokens per logical call: 8192
- Case topic, user context, simulation cutoff, evidence files, evidence ordering, and evidence hashes: identical to the corresponding completed Core10 runs
- Planned nominal calls before validation regenerations or transport retries: SAIR 210 and SES 90, for 300 total
- No SAIR or SES output is eligible for legacy replicate reuse

## 2. Bias controls common to SAIR and SES

1. Candidate-generation prompts do not name IHQ, novelty, Cross-Perspective Integration, scientific correctness, physical plausibility, falsifiability/actionability, or the numerical scoring anchors. This prevents the new controls from being coached more directly toward the evaluation rubric than the submitted conditions.
2. The generic task framing follows the submitted baselines: diagnose the problem, propose a solution, remain within the fixed constraints, and preserve evidence traceability.
3. All final answers must contain at least three distinct valid citations, cite both source pools, use the established `Scientist A [ID: n]` / `Scientist B [ID: n]` syntax, and contain no bare or invented IDs. Each bracket contains exactly one numeric ID; the complete scientist label is repeated when multiple records are cited.
4. Citation validation permits an initial attempt plus at most five validation regenerations, matching DS/MPDS. A response that never passes is a failed stage and therefore a failed run; it is never written as a completed candidate.
5. Physical API calls, prompt/candidate/thought/cached/total tokens, prompt characters, response characters, runtime, validation regenerations, transport retries, and final hashes are retained. Nominal logical calls and actual physical calls are reported separately.

## 3. SAIR design and allowed claim

SAIR is a single neutral agent that produces an initial answer and completes three self-critique/revision cycles. It has seven nominal logical calls, the same as DS. Persona mining and simulated multi-agent debate are prohibited.

DS presents evidence pool A in three debater calls and evidence pool B in three debater calls. Its moderator receives the transcript rather than the raw snapshots. To avoid the original SAIR design's seven repeated A+B contexts, revised SAIR supplies merged, source-scoped A+B evidence only to the initial answer and revisions 1 and 2. The three critique calls and final revision receive the evolving answer/critique text but no raw evidence. Nominal raw-evidence exposure is therefore three A+B equivalents, equal to DS's three A plus three B exposures.

This controls the observable budget more closely but does not establish exact internal-compute, token, latency, or price equality. The permitted description is:

> a call-matched and nominal-evidence-exposure-matched single-agent iterative-revision control

The phrases `exactly compute matched`, `token matched`, and `cost matched` are prohibited unless a later empirical equivalence analysis supports the specific quantity named.

Primary control contrast: SAIR versus DS. This contrast asks whether interactive exchange between two neutral evidence-isolated agents adds value beyond the same number of sequential single-agent generation/revision calls under matched nominal raw-evidence exposure.

## 4. SES design and allowed claim

SES gives pool A to one neutral independent one-pass analyst and pool B to a second neutral independent one-pass analyst. Neither analyst sees the other pool or proposal. A neutral synthesizer receives the two proposals but no raw evidence and may not introduce new evidence-derived content or IDs.

SES has three nominal calls and one A+B raw-evidence exposure equivalent. It is not compute matched to DS or MPDS. The permitted description is:

> a split-evidence independent single-pass plus synthesis component control

Primary control contrast: SES versus DS. This asks whether three rounds of interactive exchange improve on independent split-pool processing followed by synthesis. The three-call-versus-seven-call difference must accompany the interpretation.

Secondary descriptive contrast: SES versus EO. This explores whether split-pool processing plus synthesis differs from a merged evidence-only single pass. EO deduplicates its merged union, whereas SES preserves the original split snapshots, including any cross-pool duplicate records; therefore this contrast is not a pure test of partitioning and must be labelled exploratory.

## 5. Pilot gate

Run repository Case 1, replicate 1, for SAIR and SES in a new isolated run set. Do not start the remaining 58 runs until both candidates meet all of the following:

- canonical topic, user-context hash, cutoff, model, temperature, output cap, and A/B evidence hashes match the completed Core10 record;
- nominal logical stages occur in the frozen order;
- SAIR has exactly three raw-evidence-bearing logical stages and SES has exactly two;
- final extraction succeeds;
- each required stage passes citation validation;
- API token and retry logs are complete;
- final and trajectory/intermediate hashes are retained;
- actual SAIR usage can be compared with the existing matched Case 1 DS usage without claiming equality in advance.

## 6. Blinded evaluation

The completed five-condition Pass 1 and Pass 2 analyses remain unchanged. After SAIR/SES generation, create a separate frozen 30-packet evaluation set containing all seven conditions for each matched case-replicate unit. Re-evaluate all seven conditions in that new control-analysis pass so packet-composition effects do not arise from scoring only the two new candidates.

Because 30 packets are not divisible by seven, exact alias-position balance is impossible. Use a deterministic seeded cyclic schedule that makes every condition occupy each position either four or five times, verify the imbalance bound programmatically, and withhold the key until every response passes validation.

Use the same independent non-Gemini model family, complete original IHQ anchors, separate scientific/practical validity module, Pass 2 evidence audit, and strict machine validation. Candidate-generation prompts remain rubric-unaware; evaluator prompts necessarily contain the frozen rubric.

## 7. Analysis

- Primary inferential unit: case-level mean across three replicates, giving 10 paired cases
- Primary contrasts: DS versus SAIR and DS versus SES
- Secondary exploratory contrasts: MPDS versus SAIR, MPDS versus SES, and EO versus SES
- Descriptive reporting: mean and standard deviation, median and interquartile range, win/tie/loss counts, actual calls, tokens, runtime, output length, citation validity, and evidence utilization
- Inference: paired sign-flip/permutation test, paired Wilcoxon companion test, case-resampled 95% confidence interval, and Holm correction within the frozen new-control comparison family
- Replicate-level results are descriptive or use case-cluster-aware resampling; the 30 replicate pairs are not treated as 30 independent scientific tasks

## 8. Interpretation boundary

SAIR can test whether repeated revision under a matched nominal call/evidence-exposure design explains DS performance. SES can test whether split evidence plus non-interactive synthesis explains DS performance. Neither control eliminates every architectural difference, and neither result alone establishes general scientific-discovery superiority. Conclusions must be limited to the frozen Core10 battery-materials subset and the observable budget quantities actually recorded.
