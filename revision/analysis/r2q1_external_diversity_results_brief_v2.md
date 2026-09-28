# Reviewer 2 Q1 external-diversity extension — corrected results brief v2

Group-accounting correction: `../protocol/r2q1_group_identity_correction_v2.md`. The source papers, generation inputs and outputs, blind packets, accepted scores, and all API usage are unchanged from v1. The correction is that Case 4's Kisuk Kang is not the original benchmark's Yun Chan Kang.

## Completion and integrity

- Generation: 6/6 COMPLETE; Vertex AI `gemini-2.5-pro`; temperature 0.5; three debate rounds.
- Evidence: two target-excluded OpenAlex pools per case, 500 abstracts per pool, ending in the year before formal target publication.
- Generation API log: 55 successful calls and 7 transient failed calls; 7,032,572 prompt tokens; 92,610 candidate-output tokens; 153,939 thought tokens; 7,279,121 total tokens; summed trajectory wall-clock time 4,065.26 s.
- Case 6 used one additional successful generation because Scientist A Round 1 initially supplied only two evidence pointers; the frozen minimum was three. The regenerated response passed citation validation.
- Blinded Pass 1: 6/6 COMPLETE with official Anthropic `claude-sonnet-5`; seven API attempts because one first response failed only the required output structure and was retried once.
- Pass 1 usage across all attempts: 70,434 input tokens and 9,986 output tokens.

## Descriptive score summary

The six heterogeneous n=1 cases are descriptive. No p-values or reproducibility claims are appropriate.

| Measure | Median | Range |
|---|---:|---:|
| IHQ without CPI | 8.5 | 6–9 |
| Full IHQ | 11.5 | 8–12 |
| Scientific correctness | 3.0 | 3–4 |
| Physical plausibility | 3.0 | 3–3 |
| Constraint adherence | 4.0 | 1–4 |
| Falsifiability/actionability | 3.0 | 2–4 |
| Validity composite, descriptive only | 12.5 | 10–15 |

No candidate received a flag for a scientifically consequential error, temporal-cutoff violation, or infeasible primary process. Case 1 received `fixed_task_constraint_violation=yes` because its primary recommendation was a cobalt-free but approximately 95%-Ni cathode, contrary to the requirement to reduce dependence on both nickel and cobalt.

## Reviewer-facing interpretation

All six source papers are external to the specifically identified J.-S. Park / Yun Chan Kang / Cho investigator network at the PI-identity level. Case 4, authored with **Kisuk Kang**, is retained as an independent external addition; the former 5/6 count arose from conflating two different investigators with the same surname. This does not assert an exhaustive all-coauthor network audit.

The same MPDS workflow produced evaluable hypotheses across six additional battery problem classes, but performance was heterogeneous. Case 1 failed a central nickel-reduction constraint; Cases 2 and 4 had the lowest IHQ results; Cases 3, 5, and 6 had the strongest combined hypothesis and validity profiles. This is a descriptive battery-domain breadth demonstration, not proof of general scientific autonomy, independent recovery of the held-out papers, cross-domain generalizability, or run-to-run reproducibility.

## Suggested revision wording

> We extended the benchmark to six additional battery-research problems, sourced outside the J.-S. Park/Yun Chan Kang/Cho investigator network represented in the original cases, spanning cathode composition, liquid-electrolyte transport, solid-state interfaces, electrochemomechanical degradation, solid-state sulfur conversion, and sodium-cathode anionic redox. Under a common target-excluded retrieval, MPDS-generation, and blinded-evaluation workflow, all six single-run outputs were evaluable, though performance was heterogeneous and one violated a central material constraint. This extension supports broader battery-problem coverage but does not establish general scientific autonomy, cross-domain generalizability, or stochastic reproducibility.
