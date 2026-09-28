# MPDS Major Revision Experiment Protocol v1

Status: draft, frozen before any new model generation

## 1. Canonical sources

- Repository: https://github.com/ohgiracho/mpds-paper
- Commit: `fe30cc5f3c6bd2f20be3e2bf116b758b0e8c6314`
- Benchmark mapping: `data/benchmark_cases/benchmark_cases_release_final.xlsx`
- Local full evidence snapshots: the 60 files recorded in `../audit/knowledge_snapshot_manifest.csv`
- Existing result eligibility: `../audit/replicate1_eligibility.csv`

The tracked repository files must remain unchanged. New runs and derived analyses must be written only under this revision workspace.

## 2. Case crosswalk

- Manuscript Case Study 2 = repository `case_01` = Glitter-Cake = `retest7` / `재7실험`
- Manuscript Case Study 1 = repository `case_02` = Mo/Ni chalcogenide = `rerun`

Repository files will not be renumbered. Scripts, tables, and audit records must use repository case IDs. Manuscript labels are display aliases only.

## 3. Fixed generation settings

- Candidate model: `models/gemini-2.5-pro`
- Temperature: `0.5`
- Maximum output tokens per call: `8192`
- Language: English
- DS and MPDS rounds: `3`
- Minimum evidence pointers for citation-validated turns: `3`
- Simulation date: the case-specific cutoff in the canonical benchmark workbook
- Topic: the exact canonical topic in the benchmark workbook
- User context: the tracked `data/case_inputs/case_XX/user_context.txt`
- Evidence ordering: byte-identical local snapshot files recorded in the snapshot manifest

Only stochastic model execution may vary across replicates. Prompt text, case input, evidence order, model settings, and code must remain fixed within each condition.

## 4. Conditions and nominal calls

| Condition | Evidence | Persona | Interaction | Nominal generation calls |
| --- | --- | --- | --- | ---: |
| Raw | None | None | Single pass | 1 |
| EO | Merged A+B | None | Single pass | 1 |
| EOP | Merged A+B | Generated from 35,000 characters per pool | Single answer after persona synthesis | 2 |
| DS | Split A/B | Neutral roles | 3 rounds, two turns per round, moderator | 7 |
| MPDS | Split A/B | One generated persona per pool using the first 70,000 characters | 3 rounds, two turns per round, moderator | 9 |
| SAIR | Merged A+B | None | Initial answer followed by three critique/revision cycles | 7 |
| SES | Split A/B | Neutral independent roles | Independent A, independent B, moderator synthesis | 3 |

Personas are regenerated for every EOP and MPDS replicate. They are not fixed across replicates.

## 5. Replicate policies under consideration

### Practical legacy-reuse policy — recommended for the deadline

Reuse an existing output as Replicate 1 when all observable settings match the canonical topic, cutoff, model, temperature, output-token limit, rounds, tracked case code, and frozen evidence snapshot. Disclose that the legacy run lacks an embedded code hash and exact token metadata.

- Reusable legacy outputs: 141 of 150 case-condition cells
- Ineligible legacy outputs: EOP cases 3, 5, 6, 9, 10, 11, 12, 13, and 14
- New core generation calls required for n=3: 1,218
- New SAIR/SES generation calls: 900
- Total candidate generation calls: 2,118 before retries

### Strict clean-rerun policy

Require every replicate to contain a run timestamp, exact code hash, prompt/input hashes, and API usage metadata. No legacy output meets every strict requirement.

- New core generation calls required for n=3: 1,800
- New SAIR/SES generation calls: 900
- Total candidate generation calls: 2,700 before retries

No API run may start until one policy is selected.

## 6. Required run metadata

Every physical API request must append one JSONL record containing:

- run ID, case ID, condition, replicate ID
- source repository commit and executing code hash
- prompt hash and prompt character count
- evidence file hashes and character counts
- model, temperature, maximum output tokens
- request start/end timestamps and elapsed seconds
- API call sequence number
- success/failure and error type
- response character count
- prompt, candidate, cached, thoughts, and total tokens when supplied by the API

The experiment-level manifest must also record logical-step status, validation result, regeneration count, final output hash, and completion status.

## 7. Failure and retry rules

- Preserve the canonical scripts' transient-error retry policy.
- Preserve DS/MPDS citation validation and regeneration behavior.
- Never silently overwrite a completed replicate.
- A failed replicate remains in the registry with its error metadata.
- Resume must continue from the first incomplete run, not restart completed runs.
- Manual editing of generated candidate text is prohibited.

## 8. Pilot gate

Before batch execution, run one full case through all seven conditions with n=3 in an isolated pilot directory. The pilot must demonstrate:

- correct canonical topic and cutoff
- exact evidence hashes
- separate replicate outputs
- complete per-call token and retry logs
- valid final extraction for DS, MPDS, SAIR, and SES
- successful interruption and resume
- one blind judge packet containing all seven conditions

Batch generation may begin only after the pilot audit passes.

## 9. Evaluation plan

- Blind aliases randomized within each case and replicate
- One independent judge request per case-replicate packet containing all available conditions
- At least one judge from a different model family than the candidate model
- Two domain experts independently score a balanced subset
- Report Full IHQ and IHQ without Cross-Perspective Integration
- Additional dimensions: scientific correctness, physical plausibility, evidence support, and citation traceability
- Automatic metrics: output length, exact token usage, valid evidence-ID rate, citation count, citation-position quartile, and evidence diversity
- Human/model-assisted metrics: claim-citation support and unsupported-claim rate

## 10. Statistical plan

- Unit of paired analysis: matched case-replicate
- Descriptive results: mean ± SD and median [IQR]
- Pairwise tests: paired Wilcoxon and paired permutation test
- Effect sizes with bootstrap 95% confidence intervals
- Holm correction within each declared comparison family
- Win/tie/loss counts
- Report both per-replicate results and case-level replicate means
- Agreement: ICC for totals/continuous aggregates and weighted kappa for ordinal dimension scores

## 11. Claims held pending results

The manuscript must not claim that persona induction significantly improves DS until the replicated, independent-judge results support it. If not supported, the planned interpretation is that multi-round debate produced the dominant gain and persona induction added only a modest incremental benefit.

The PBA material must be described as an illustrative or qualitative laboratory follow-up unless independent washing-only synthesis replicates and quantitative characterization become available.
