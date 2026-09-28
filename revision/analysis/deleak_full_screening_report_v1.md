# Prompt de-leaking full screening — preparation report v1

Date: 2026-09-21  
API calls: 0  
Generation: not started  
Claude evaluation: not started

## Completion status

- Frozen input files reviewed: 30/30 cases.
- Case-level risk classifications recorded: 30/30.
- De-leaked question drafts prepared: 30/30.
- Primary execution set frozen by user confirmation: existing Core10 (`1, 2, 3, 4, 8, 15, 18, 22, 29, 30`).
- Inputs frozen for generation: not yet; author review is required first.

## Screening distribution

| Risk level | Cases | Count |
|---|---|---:|
| Very high | 1, 8, 17, 22, 23, 24, 26, 28 | 8 |
| High | 2–7, 9–16, 18–21, 25, 27, 30 | 21 |
| Moderate | 29 | 1 |
| Low | — | 0 |

This distribution reflects a conservative lexical screening: most prompts identify a target morphology, assembly, or fabrication family. It is not evidence that the generated answer copied a held-out paper. Instead, it justifies a controlled sensitivity test using prompts that preserve the scientific problem while removing target-solution wording.

## Change from the preliminary shortlist

The preliminary shortlist prioritized ten cases with especially visible solution cues: `1, 8, 12, 17, 22, 23, 24, 26, 27, 28`.

For the primary experiment, Core10 is more efficient and statistically cleaner because its original-prompt MPDS condition already contains three frozen replicates. The user froze Core10 as the primary set on 2026-09-21. This means only 30 new de-leaked outputs are needed. Running the preliminary shortlist at three replicates would require generating missing original-prompt replicates for seven non-Core10 cases as well as the de-leaked condition, or accepting an imbalanced comparison.

The preliminary shortlist remains useful as an optional severity-focused follow-up and has not been deleted or overwritten.

## Recommended execution boundary

Do not start generation while the lost-in-the-middle batch is active. When that batch reaches 36/36:

1. Have an author/domain reviewer approve each Core10 rewrite against the original scientific objective.
2. Expand each approved one-sentence question into a de-leaked `situation.txt` and `user_context.txt` without reintroducing target architecture cues.
3. Freeze file hashes and a generation manifest.
4. Validate that the evidence pools, evidence order, cutoff, model, temperature, rounds, and generation code match the existing Core10 MPDS condition.
5. Run 10 cases × 3 replicates = 30 new Gemini 2.5 Pro outputs.
6. Build blind original-versus-de-leaked packets and reuse the frozen official evaluation implementation.
7. Average replicates within case and perform paired inference at `n=10`.

## Interpretation guardrails

- Similar quality after de-leaking supports robustness to solution-specific prompt wording in the tested subset.
- Lower quality after de-leaking indicates that part of the original performance depended on architectural cues; report the magnitude without relabeling it as model failure.
- A difference in output morphology alone is not enough; use frozen blinded quality and validity scoring.
- Case 29 is a useful lower-risk comparison but should not be used to claim that all prompts were equally leakage-prone.
- Do not call the screening blinded or independent; it is an author-side input audit.
