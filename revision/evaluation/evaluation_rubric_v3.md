# Blinded evaluation rubric v3

> **SUPERSEDED BEFORE JUDGING.** No official score was produced with this combined document. The primary IHQ rubric is now loaded verbatim from the public GitHub source `data/IHQ rubric/IHQ Scoring Rules.txt`; reviewer-requested measures are defined separately in `supplementary_evaluation_module_v1.md`.

Status: **FROZEN BEFORE JUDGING**  
Frozen date: 2026-09-13

## 1. Common rules

- Evaluate exactly one packet at a time and score all five anonymous candidates independently.
- Use only the task, cutoff, candidate text, and evidence records supplied in that pass. Do not browse, call tools, or infer the generating system.
- Do not reward length, formatting, citation count, numerical density, procedural detail, or polished prose by themselves.
- A high score requires clear evidence in the candidate text. When genuinely between two scores, use the lower score.
- Do not rank candidates. Return raw dimension scores and rationales only. Totals and comparisons are calculated after blinding is lifted.
- Pass 1 and Pass 2 are separate judge calls. Pass 1 never contains evidence abstracts; Pass 2 contains only the evidence records needed to audit citations and central claims.

## 2. Pass 1: final-output-only assessment

### A. Integrative Hypothesis Quality (IHQ)

These four dimensions preserve the original IHQ definitions and anchors.

#### 1. Idea novelty (0–5)

Evaluates whether the response meaningfully departs from obvious, routine, or standard solutions for the task.

- 0: Entirely conventional response with no meaningful novelty.
- 1: A minor variation on a familiar idea.
- 2: Some new combination or modification is present, but the idea remains close to standard practice.
- 3: A meaningfully different solution or design logic is proposed.
- 4: A clearly non-obvious idea or reconfiguration is introduced, not merely a routine extension.
- 5: A genuinely distinctive and conceptually strong idea that would likely be recognized as notably original within the task context.

Parameter tuning or minor design variation alone cannot justify a high score.

#### 2. Mechanistic originality (0–5)

Evaluates whether the response offers a novel causal or mechanistic explanation rather than only a new surface configuration.

- 0: No mechanistic reasoning.
- 1: Familiar mechanism-level logic repeated without meaningful change.
- 2: Known mechanisms combined in a modest way.
- 3: A more original causal chain, interaction logic, or structure–process–performance linkage.
- 4: A clearly differentiated mechanism-level rationale beyond routine extension.
- 5: A novel mechanism-centered proposal that also yields distinctive experimental implications or observable signatures.

Technical vocabulary without a cause-to-effect chain is not sufficient.

#### 3. Trade-off reframing (0–5)

Evaluates whether the response accepts a known trade-off or structurally redirects it.

- 0: No trade-off reframing.
- 1: A trade-off is acknowledged but the reasoning around it is unchanged.
- 2: The response tries to soften or partially manage the trade-off.
- 3: A new balance point, optimization route, or partial decoupling strategy is proposed.
- 4: The trade-off structure is meaningfully redefined through a new design lever or alternative route.
- 5: The problem is reframed so the original trade-off is substantially bypassed, redistributed, or strategically restructured.

Claiming that all goals improve together is insufficient unless the response explains how the trade-off changes.

#### 4. Cross-perspective integration (0–5)

Evaluates whether distinct viewpoints, constraints, or priorities are synthesized into a stronger proposal.

- 0: Only one perspective.
- 1: A second perspective is mentioned but not integrated.
- 2: Multiple perspectives are present but remain parallel.
- 3: The proposal meaningfully integrates different viewpoints or priorities.
- 4: Integration changes the proposal's structure and produces a more nuanced or hybrid solution.
- 5: The solution clearly depends on combining perspectives that would not likely produce the same outcome independently.

Mandatory caps:

- Maximum 2 if perspectives are merely listed.
- Maximum 2 if one route is selected without explicitly stating what is adopted from competing routes.
- Maximum 4 without explicit adopt/discard logic.

### B. Scientific and practical validity

These dimensions are scored independently of novelty and independently of citation quantity.

#### 5. Scientific correctness (0–5)

Consistency of the central claims and causal reasoning with established materials-science and electrochemical knowledge available by the stated cutoff.

- 0: A central claim contradicts basic principles or makes the proposal fundamentally invalid.
- 1: Multiple major errors or contradictions undermine most of the proposal.
- 2: At least one substantial error or several material omissions weaken the core reasoning.
- 3: Broadly correct, with minor errors, overstatements, or unresolved scientific gaps.
- 4: Correct and internally consistent; any weaknesses are limited and non-consequential.
- 5: Exceptionally careful, correct, and well-qualified reasoning with no material scientific error identified.

Do not reduce this score merely because citations are absent; citation support is assessed in Pass 2.

#### 6. Physical plausibility (0–5)

Feasibility of the proposed materials, geometry, fabrication route, transport pathway, and stability mechanism under the task's stated conditions.

- 0: Physically impossible or incompatible with the fixed system.
- 1: Dominated by severe unaddressed feasibility barriers.
- 2: Possible only after resolving major fabrication, transport, or stability problems that the response overlooks.
- 3: Plausible in principle but important feasibility details or failure modes remain unresolved.
- 4: Plausible with a credible route and explicit handling of the main obstacles.
- 5: Highly plausible and unusually well specified, including relevant boundaries and failure modes.

#### 7. Constraint adherence (0–5)

Compliance with the explicit material, process, composition, date, objective, and scope constraints in the task.

- 0: Replaces or violates a defining fixed constraint.
- 1: Violates several major constraints.
- 2: Violates or evades one major constraint, or repeatedly drifts outside scope.
- 3: Meets the main constraints but has a minor conflict, ambiguity, or unjustified addition.
- 4: Meets all explicit constraints with only negligible ambiguity.
- 5: Meets all constraints and uses them constructively to shape the proposal.

Do not invent unstated constraints.

#### 8. Falsifiability and actionability (0–5)

Presence of discriminating predictions, measurable failure criteria, and a practical validation path.

- 0: No testable prediction or validation route.
- 1: Only generic requests for characterization or testing.
- 2: Some measurable quantities are named, but they do not discriminate the proposed mechanism or lack decision criteria.
- 3: At least one feasible test links a predicted observation to the proposal, though controls or thresholds are incomplete.
- 4: A practical validation sequence includes discriminating measurements, controls, and explicit success or failure logic.
- 5: A rigorous, efficient validation plan could distinguish the proposal from credible alternatives and states quantitative or operational decision criteria.

### C. Pass 1 flags

Return `yes`, `no`, or `uncertain` for each:

- `scientifically_consequential_error`
- `temporal_cutoff_violation`
- `fixed_task_constraint_violation`
- `infeasible_primary_process`

A flag identifies a specific problem; it is not a substitute for the dimension score. Explain every `yes` or `uncertain` flag in the rationale.

## 3. Pass 2: evidence and citation audit

Pass 2 uses the same anonymous candidate text plus the evidence records corresponding to the identifiers cited in that text. It does not rescore IHQ or the four Pass 1 validity dimensions.

### A. Central-claim sampling

Identify up to five central, externally verifiable scientific claims per candidate. Prioritize claims essential to the proposed mechanism, feasibility, or expected performance. Do not select trivial background statements merely because they are easy to verify.

For each selected claim, record one status:

- `supported`: the supplied abstract directly supports the material proposition.
- `partially_supported`: the abstract supports only part of the claim or supports a weaker/adjacent proposition.
- `unsupported`: the cited abstract is available but does not support the claim.
- `contradicted`: the supplied abstract conflicts with the claim.
- `unverifiable`: no uniquely attributable, usable abstract is supplied for the claim.

`Unverifiable` does not mean scientifically false. A candidate with no citations can therefore score poorly on traceability without automatically receiving a scientific-error flag.

### B. Evidence support (0–5)

How well the supplied evidence records support the candidate's selected central claims.

- 0: No selected central claim has usable supporting evidence, or central claims are contradicted.
- 1: Evidence is largely irrelevant or supports only peripheral fragments.
- 2: Some central claims have partial support, but major claims remain unsupported or unverifiable.
- 3: Most central claims have at least partial support; at least one important gap remains.
- 4: Nearly all central claims are directly supported, with only limited overreach.
- 5: All selected central claims are directly and specifically supported without material overstatement.

### C. Citation traceability (0–5)

How clearly important claims map to valid and uniquely identifiable evidence records.

- 0: No usable mapping from central claims to evidence records.
- 1: Most identifiers are missing, invalid, or too ambiguous to attribute.
- 2: Some claims can be mapped, but ambiguity or missing links affect major claims.
- 3: Most important claims map to resolvable records, with at least one material ambiguity or omission.
- 4: Nearly all important claims map clearly to valid records; minor ambiguity remains.
- 5: Every selected central claim maps explicitly and unambiguously to valid, relevant evidence records.

Where the same numeric ID exists in evidence pools A and B, a bare citation such as `[ID: 12]` is ambiguous unless the surrounding text explicitly identifies the intended pool. Do not guess the source.

### D. Pass 2 flags

Return `yes`, `no`, or `uncertain` for:

- `consequential_unsupported_or_contradicted_claim`
- `fabricated_or_invalid_citation_identifier`

## 4. Derived quantities calculated outside the judge

The evaluator must not calculate totals, rankings, or condition comparisons.

- Full IHQ = dimensions 1+2+3+4, range 0–20.
- IHQ without CPI = dimensions 1+2+3, range 0–15.
- Pass 1 validity composite, if reported descriptively = dimensions 5+6+7+8, range 0–20.
- Evidence support and citation traceability remain separate secondary outcomes; they are not added to IHQ.
- Automatic measures include output length, citation count, identifier resolvability, unique-traceability rate, cited-abstract availability, runtime, API calls, and token usage.
- Claim-level support rates use a disclosed denominator. `Unverifiable` is reported separately from `unsupported` and `contradicted`.
