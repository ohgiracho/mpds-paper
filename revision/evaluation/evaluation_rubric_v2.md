# Revision evaluation rubric

## Scope and blinding

Score every anonymized candidate independently. Do not infer the system from tone, length, formatting, citation density, or references to debate. System identity and display order are randomized outside the scoring packet. Evaluate only what is present in the candidate and the supplied task/evidence materials.

## Hypothesis quality dimensions

Each dimension is scored from 0 to 5.

1. **Idea novelty**: from conventional restatement (0) to a genuinely distinctive and task-relevant design principle (5).
2. **Mechanistic originality**: from no causal reasoning (0) to a novel, coherent, and testable mechanism with observable implications (5).
3. **Trade-off reframing**: from ignoring trade-offs (0) to materially reorganizing or bypassing the original design conflict (5).
4. **Cross-perspective integration**: from one perspective only (0) to a solution whose structure depends on reconciling multiple constraints or viewpoints (5).

Report both:

- **Full IHQ** = dimensions 1+2+3+4, range 0–20.
- **IHQ without CPI** = dimensions 1+2+3, range 0–15.

## Scientific validity dimensions

Each dimension is scored from 0 to 5.

5. **Scientific correctness**: consistency with established materials science and electrochemistry within the time cutoff.
6. **Physical plausibility**: feasibility of the proposed structure, process, transport pathway, and stability mechanism.
7. **Evidence support**: degree to which central claims are supported by the supplied evidence rather than assertion.
8. **Citation traceability**: ease of mapping important claims to valid, relevant evidence identifiers.
9. **Constraint adherence**: compliance with the fixed materials, process, date, and scope stated in the task.
10. **Falsifiability and actionability**: presence of discriminating predictions, measurable failure criteria, and a practical validation path.

## Global flags

Record each as `yes`, `no`, or `uncertain`:

- Contains a scientifically consequential unsupported claim.
- Contains a fabricated or invalid citation identifier.
- Violates the temporal cutoff.
- Violates a fixed task constraint.
- Recommends an infeasible primary process without acknowledging the obstacle.

## Required output

For each anonymous candidate, return all ten scores, the two IHQ totals, the five flags, and a concise evidence-based rationale. Do not rank candidates until all candidates have been scored independently. After independent scoring, provide an overall ordering and identify any practical ties.

## Automatic metrics kept separate from judgment

The analysis pipeline, not the evaluator, calculates output characters/tokens, valid evidence-ID rate, citation position quartiles, citation-validation pass/fail, runtime, API calls, and token usage. These metrics must not be shown to evaluators before scoring because they can reveal system identity or create length/citation-density bias.
