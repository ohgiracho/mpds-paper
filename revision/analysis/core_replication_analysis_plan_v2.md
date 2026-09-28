# Core 10-case replication analysis plan v2

Status: **FROZEN BEFORE NEW JUDGING**  
Frozen date: 2026-09-13  
Supersedes: `core_replication_analysis_plan_v1.md` for evaluation mechanics only  
Selection/configuration: `config/core_replication_subset_v1.json`  
Generation run set: `runs_core10_vertex_gemini_2_5_pro_20260912`  
Canonical source commit: `fe30cc5f3c6bd2f20be3e2bf116b758b0e8c6314`

## 1. Reason for the versioned amendment

No new judge scores had been generated or inspected when this amendment was frozen. The v1 implementation audit found that its compressed 0–5 descriptions did not preserve all original IHQ anchors and that evidence support could not validly be judged from final-answer-only packets. Version 2 therefore restores the full original IHQ anchors, removes judge-calculated totals and rankings, and separates final-output assessment from abstract-grounded evidence audit. The selected cases, candidate outputs, aliases, primary endpoint, primary contrast, and inferential unit are unchanged.

## 2. Dataset and replication policy

The selected repository cases are 1, 2, 3, 4, 8, 15, 18, 22, 29, and 30. Conditions are Raw, EO, EOP, DS, and MPDS, yielding 150 candidates: 10 cases × 3 replicates × 5 conditions.

An audited eligible legacy output is Replicate 1 and the Vertex Gemini 2.5 Pro runs are Replicates 2 and 3. Case 3 EOP is the prespecified exception: its mismatched legacy output is excluded and its three newly generated outputs are Replicates 1–3.

## 3. Blinding and evaluation units

Pass 1 uses 30 final-output-only packets, one for every matched case-replicate pair. Each packet contains all five condition outputs under balanced deterministic aliases generated with seed 7346298. Across the 30 packets, every condition occupies every alias position exactly six times. Candidate bodies retain substantive inline citations but exclude appended evidence maps, evidence appendices, reference lists, run metadata, and external system labels. The private key is never sent to raters.

Pass 2 uses 30 separately generated evidence-audit packets with the same aliases and candidate bodies. Only records corresponding to identifiers cited by the candidate are supplied. EO/EOP numeric IDs are resolved against the exact deduplicated merged A+B snapshot used during generation. DS/MPDS numeric IDs are checked against both frozen source pools. If the same numeric ID maps to different records in A and B, both records are supplied and the citation is treated as ambiguous unless the candidate text identifies the intended pool. Raw answers, and any other answers without citations, receive no supplied abstract records.

Both packet sets are derived from hash-verified source files. Pass 1 packet construction must pass completeness, five-candidate uniqueness, and alias-balance checks. Pass 2 construction must verify the candidate-body hashes and frozen knowledge-file hashes.

## 4. Judge design and freeze gate

The selected automated judge is the non-Gemini model `claude-sonnet-5`. It is independent of the Gemini 2.5 Pro generation family. The scoring transport/provider, exact returned model version, API date, output-token limit, prompt hashes, schema hashes, packet hashes, response hashes, retry events, latency, and token usage must be recorded in a run manifest.

Before the first official scoring call, the following must be frozen in that manifest:

- callable provider/account and endpoint;
- requested model ID `claude-sonnet-5` and the exact model/version returned by the provider;
- no web search or external tools;
- no temperature or top-p override unless the provider requires and records one;
- one JSON-schema-constrained response per packet;
- identical prompt, rubric, and schema hashes across all packets within each pass;
- deterministic retry rule limited to transport failure, truncation, or invalid schema, without changing candidate content.

Pass 1 uses one request per packet (30 requests). The judge returns the eight raw dimension scores, four flags, and rationales defined in `evaluation_rubric_v3.md`; it does not return totals or rankings. Pass 2 uses one request per evidence-audit packet (30 requests) and returns evidence support, citation traceability, claim-level support states, two flags, and rationales. The two passes must use separate calls so that evidence quantity and source structure cannot influence the primary IHQ assessment.

Two domain experts independently score the frozen validation subset: Cases 1, 2, 4, 22, and 29 across all three replicates (15 Pass 1 packets; 75 candidates). The same subset is used for a human evidence-audit check where feasible. Automated-versus-human agreement and human-versus-human agreement are reported separately.

## 5. Outcomes and declared comparisons

### Primary outcome and contrast

- Outcome: **IHQ without Cross-Perspective Integration**, range 0–15.
- Contrast: **MPDS minus DS**.
- Rationale: MPDS and DS share split evidence and multi-round interaction. The contrast estimates the incremental persona component, while excluding the IHQ item most likely to structurally favor debate systems.

### Key secondary outcomes and contrasts

- Full IHQ (0–20): MPDS minus DS.
- IHQ without CPI: DS minus EO.
- IHQ without CPI: EOP minus EO.
- IHQ without CPI: MPDS minus EOP.
- IHQ without CPI: MPDS minus Raw.

Scientific correctness, physical plausibility, constraint adherence, falsifiability/actionability, evidence support, citation traceability, individual IHQ dimensions, global flags, and other pairwise comparisons are secondary or exploratory. Evidence dimensions remain separate and are not added to IHQ.

SAIR and SES are planned component controls under `protocol/experiment_protocol_v1.md`, but they are not part of this completed 150-candidate generation set and must not be described as completed. Their results require a separate generation and analysis stage.

## 6. Derived scores and data integrity

The analysis code, not the judge, calculates:

- Full IHQ = novelty + mechanistic originality + trade-off reframing + CPI.
- IHQ without CPI = novelty + mechanistic originality + trade-off reframing.
- Optional descriptive validity composite = correctness + plausibility + constraint adherence + falsifiability/actionability.

Every response must contain Candidate A–E exactly once and match the frozen JSON schema. Scores outside 0–5, duplicate or missing aliases, wrong packet IDs, extra fields, truncated JSON, or non-sequential claim IDs fail validation. Invalid outputs are retried under the frozen rule and never manually repaired without an audit trail.

## 7. Statistical unit and inference

Replicates are nested within cases and are not treated as 30 independent scientific tasks.

- Primary inferential unit: case-level mean across three replicates, giving 10 paired observations per condition.
- Primary test: two-sided exact paired permutation/sign-flip test on the 10 case-level MPDS-minus-DS differences.
- Companion test: paired Wilcoxon signed-rank test.
- Effect estimates: mean and median paired difference with case-resampled bootstrap 95% confidence intervals.
- Multiplicity: the single primary contrast is unadjusted; Holm correction is applied across the five declared key secondary tests.
- Missing data: no imputation. A score is excluded only after the prespecified retry path fails, with the reason reported.
- Replicate-level 30-pair analyses are descriptive or use case-cluster-aware resampling; they are not analysed as 30 independent cases.

## 8. Length and citation sensitivity analyses

Primary IHQ is not length-adjusted. Output characters and tokenizer-specific token counts are reported by condition. As an exploratory robustness check, condition effects are re-estimated with centered log output length as a covariate and random intercepts for case and case-replicate packet. Conclusions are compared with the unadjusted paired analysis; this sensitivity model does not replace the prespecified primary test.

Automatic evidence measures are kept outside judge packets and joined only after scoring is final:

- citation-token occurrence count and unique cited-ID count;
- ID resolvability rate;
- deterministically attributable citation rate from the evidence namespace or an explicit local `Scientist A/B` label, reported separately from mere resolvability and from the semantic Pass 2 judgment;
- cited-abstract availability and evidence-pool diversity;
- position of citations in the answer;
- runtime, physical API calls, regeneration count, and token usage.

Claim-level Pass 2 results report the proportions `supported`, `partially_supported`, `unsupported`, `contradicted`, and `unverifiable` with explicit denominators. The combined unsupported-or-contradicted rate is reported as a central-claim support failure rate, not labelled a general hallucination rate. No-citation answers are reported separately rather than assumed false.

## 9. Required reporting and agreement

For each condition report mean ± SD, median [IQR], within-case replicate SD/range, all replicate points, case-level means with paired lines, and MPDS comparator win/tie/loss counts. Report effect sizes and uncertainty, not p-values alone.

For human validation, use ICC for continuous totals/aggregates and weighted kappa for ordinal dimensions. Flag agreement is reported with raw agreement and an appropriate chance-corrected coefficient. Automated-versus-human agreement is separate from human-versus-human agreement.

## 10. Interpretation rules

- Do not claim a persona benefit unless the primary MPDS-minus-DS result supports it in direction, effect size, and uncertainty.
- If Full IHQ improves but IHQ without CPI does not, interpret the difference as primarily cross-perspective integration rather than broad hypothesis-quality improvement.
- If DS improves over EO but MPDS does not improve over DS, interpret multi-round interaction as the dominant supported component.
- Treat this as a prespecified stochastic-robustness subset, not a new random 30-case benchmark.
- Report null, mixed, and unfavorable results without endpoint switching.
