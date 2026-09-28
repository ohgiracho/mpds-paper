# Supplementary evaluation module v1

Status: **FROZEN BEFORE JUDGING**  
Frozen date: 2026-09-13

This module does not replace, rewrite, or contribute points to the original Integrative Hypothesis Quality (IHQ) rubric. IHQ must be scored from the verbatim public GitHub file `data/IHQ rubric/IHQ Scoring Rules.txt`. The measures below were added in response to peer review and are reported separately.

## Common rules

- Evaluate exactly one packet at a time and score all five anonymous candidates independently.
- Use only the task, cutoff, candidate text, and evidence records supplied in the relevant pass. Do not browse, call tools, or infer the generating system.
- Do not reward length, formatting, citation count, numerical density, procedural detail, or polished prose by themselves.
- When genuinely between two scores, choose the lower score.
- Do not rank candidates or calculate totals. Return only raw dimension scores, flags, and rationales.
- Pass 1 and Pass 2 are separate judge calls. Pass 1 never contains evidence abstracts. Pass 2 contains only records needed to audit citations and central claims.

## Pass 1: supplementary scientific and practical validity

### Scientific correctness (0–5)

Consistency of central claims and causal reasoning with established materials-science and electrochemical knowledge available by the stated cutoff.

- 0: A central claim contradicts basic principles or makes the proposal fundamentally invalid.
- 1: Multiple major errors or contradictions undermine most of the proposal.
- 2: At least one substantial error or several material omissions weaken the core reasoning.
- 3: Broadly correct, with minor errors, overstatements, or unresolved scientific gaps.
- 4: Correct and internally consistent; any weaknesses are limited and non-consequential.
- 5: Exceptionally careful, correct, and well-qualified reasoning with no material scientific error identified.

Do not reduce this score merely because citations are absent; citation support is assessed in Pass 2.

### Physical plausibility (0–5)

Feasibility of the proposed materials, geometry, fabrication route, transport pathway, and stability mechanism under the task's stated conditions.

- 0: Physically impossible or incompatible with the fixed system.
- 1: Dominated by severe unaddressed feasibility barriers.
- 2: Possible only after resolving major fabrication, transport, or stability problems that the response overlooks.
- 3: Plausible in principle but important feasibility details or failure modes remain unresolved.
- 4: Plausible with a credible route and explicit handling of the main obstacles.
- 5: Highly plausible and unusually well specified, including relevant boundaries and failure modes.

### Constraint adherence (0–5)

Compliance with explicit material, process, composition, date, objective, and scope constraints in the task.

- 0: Replaces or violates a defining fixed constraint.
- 1: Violates several major constraints.
- 2: Violates or evades one major constraint, or repeatedly drifts outside scope.
- 3: Meets the main constraints but has a minor conflict, ambiguity, or unjustified addition.
- 4: Meets all explicit constraints with only negligible ambiguity.
- 5: Meets all constraints and uses them constructively to shape the proposal.

Do not invent unstated constraints.

### Falsifiability and actionability (0–5)

Presence of discriminating predictions, measurable failure criteria, and a practical validation path.

- 0: No testable prediction or validation route.
- 1: Only generic requests for characterization or testing.
- 2: Some measurable quantities are named, but they do not discriminate the proposed mechanism or lack decision criteria.
- 3: At least one feasible test links a predicted observation to the proposal, though controls or thresholds are incomplete.
- 4: A practical validation sequence includes discriminating measurements, controls, and explicit success or failure logic.
- 5: A rigorous, efficient validation plan could distinguish the proposal from credible alternatives and states quantitative or operational decision criteria.

### Pass 1 flags

Return `yes`, `no`, or `uncertain` for:

- `scientifically_consequential_error`
- `temporal_cutoff_violation`
- `fixed_task_constraint_violation`
- `infeasible_primary_process`

Explain every `yes` or `uncertain` flag. Flags do not replace dimension scores.

## Pass 2: evidence and citation audit

Pass 2 uses the same anonymous candidate text plus evidence records corresponding to identifiers cited in that text. It does not rescore IHQ or Pass 1 validity dimensions.

### Central-claim sampling

Identify up to five central, externally verifiable scientific claims per candidate. Prioritize claims essential to the mechanism, feasibility, or expected performance. Do not select trivial background statements merely because they are easy to verify.

For each selected claim, record:

- `supported`: the supplied abstract directly supports the material proposition.
- `partially_supported`: the abstract supports only part of the claim or a weaker/adjacent proposition.
- `unsupported`: the cited abstract is available but does not support the claim.
- `contradicted`: the supplied abstract conflicts with the claim.
- `unverifiable`: no uniquely attributable, usable abstract is supplied for the claim.

`Unverifiable` does not mean scientifically false. A no-citation answer may therefore score poorly on traceability without automatically receiving a scientific-error flag.

### Evidence support (0–5)

- 0: No selected central claim has usable supporting evidence, or central claims are contradicted.
- 1: Evidence is largely irrelevant or supports only peripheral fragments.
- 2: Some central claims have partial support, but major claims remain unsupported or unverifiable.
- 3: Most central claims have at least partial support; at least one important gap remains.
- 4: Nearly all central claims are directly supported, with only limited overreach.
- 5: All selected central claims are directly and specifically supported without material overstatement.

### Citation traceability (0–5)

- 0: No usable mapping from central claims to evidence records.
- 1: Most identifiers are missing, invalid, or too ambiguous to attribute.
- 2: Some claims can be mapped, but ambiguity or missing links affect major claims.
- 3: Most important claims map to resolvable records, with at least one material ambiguity or omission.
- 4: Nearly all important claims map clearly to valid records; minor ambiguity remains.
- 5: Every selected central claim maps explicitly and unambiguously to valid, relevant evidence records.

If one numeric ID exists in evidence pools A and B, a bare `[ID: n]` is ambiguous unless the surrounding text identifies the intended pool. Do not guess.

### Pass 2 flags

Return `yes`, `no`, or `uncertain` for:

- `consequential_unsupported_or_contradicted_claim`
- `fabricated_or_invalid_citation_identifier`

## Derived quantities outside the judge

- Full IHQ and IHQ without CPI are calculated from original-IHQ item scores after validation.
- Supplementary validity dimensions and evidence dimensions remain separate outcomes and are never added to IHQ.
- Automatic measures include output length, citation count, identifier resolvability, source attribution, cited-abstract availability, runtime, API calls, and token usage.
- `Unverifiable`, `unsupported`, and `contradicted` claim rates are reported separately with explicit denominators.

