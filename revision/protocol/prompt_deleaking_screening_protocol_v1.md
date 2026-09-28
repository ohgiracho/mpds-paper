# Prompt de-leaking full-screening protocol v1

Status: static screening complete; generation not authorized by this file  
API use: none  
Screening unit: one scientific case  
Source inputs: the frozen `data/case_inputs/case_XX/situation.txt` and `user_context.txt` files

## Purpose

This screening identifies solution-specific information in the problem statements that could make the held-out design easier to recover. It does not assert that a prompt is contaminated merely because it fixes the material system or states a genuine experimental constraint. The purpose is to create a conservative sensitivity condition in which the scientific problem remains recognizable but the target morphology, target assembly, or target fabrication solution is not supplied in advance.

## Information inspected

Only the frozen input text is used for the risk classification. Generated answers and evaluation scores must not be consulted when assigning risk or rewriting a question.

The following are normally preserved:

- active-material identity or material family;
- battery chemistry and ion carrier;
- genuinely fixed experimental components;
- performance bottlenecks and practical constraints;
- simulation-date cutoff.

The following are removed when they encode the held-out solution rather than an independently fixed constraint:

- distinctive target morphology such as tube-in-tube, cubic nanoroom, multishell, yolk-shell, or trimodal pores;
- a target component arrangement or allocation axis;
- a named template, assembly, or conversion route that directly produces the target morphology;
- a target support geometry or carbon architecture;
- wording that asks only how to optimize an already disclosed target solution.

## Risk levels

- `very_high`: the prompt states a distinctive target architecture or allocation and substantially narrows the answer to the held-out design family.
- `high`: the prompt fixes a material–architecture or material–process combination that strongly points to the held-out solution, but leaves meaningful architectural choices open.
- `moderate`: the prompt supplies relevant mechanisms or testing factors but does not disclose a distinctive final design.
- `low`: the prompt states the scientific problem and constraints without a recognizable target-solution cue.

Risk is a prompt-design assessment, not a finding that a generated answer copied the source paper.

## Rewrite acceptance rules

A de-leaked question is accepted only when all of the following hold:

1. The material/system, ion carrier, and main failure mechanisms remain unchanged.
2. The question remains answerable using the same frozen evidence pools and time cutoff.
3. No distinctive target morphology or target-producing route from the original prompt remains unless it is an independently fixed experimental constraint.
4. The rewrite does not introduce a new material, mechanism, or performance target.
5. The rewrite asks for a design or evaluation strategy rather than naming the expected design.

## Frozen primary sensitivity set

Use the existing Core10 cases: `1, 2, 3, 4, 8, 15, 18, 22, 29, 30`. This membership and order were frozen by user confirmation on 2026-09-21; changes require a new versioned selection config.

Rationale:

- all ten already have frozen original-prompt MPDS outputs with three replicates;
- only the de-leaked condition therefore requires new generation: 10 cases × 3 replicates = 30 new outputs;
- the set includes the two reviewer-relevant examples (repository Case 1 / manuscript Case Study 2 and PBA Case 8);
- it contains both very-high/high-risk prompts and Case 29 as a moderate-risk negative-control-like case;
- inference can remain case-clustered at `n=10`, with the three replicates averaged within case.

The preliminary severity-focused shortlist (`1, 8, 12, 17, 22, 23, 24, 26, 27, 28`) is retained as an audit artifact and optional follow-up set. It should not replace Core10 as the primary execution set unless corresponding original-prompt replicates are newly generated.

## Frozen comparison design to use after author review

- Conditions: original-prompt MPDS versus de-leaked-prompt MPDS.
- Repeats: three per case.
- Reuse: the existing original-prompt Core10 MPDS outputs; do not regenerate them merely to create a new control.
- Fixed factors: Gemini 2.5 Pro, temperature 0.5, debate protocol, rounds, evidence pools and ordering, cutoff, max output tokens, evaluation prompt and schema.
- Only intended change: problem statement/user context after de-leaking.
- Primary outcome: IHQ without CPI, averaged over three replicates within case.
- Secondary outcomes: Full IHQ, the four scientific/practical validity dimensions and their descriptive composite, output length, citation traceability, and semantic evidence support when evaluated under the already frozen procedures.
- Statistical unit: scientific case (`n=10`), not 30 outputs.
- Reporting: paired case-level mean difference, bootstrap 95% interval, exact sign-flip test, Wilcoxon sensitivity test, and win/tie/loss.

## Execution boundary

This protocol and the accompanying CSV prepare the screening only. No Gemini generation or Claude evaluation may begin until the 30 rewrites receive author review and the selected Core10 input files and hashes are frozen. The running lost-in-the-middle batch must finish before de-leaked generation begins to avoid Vertex quota competition and mixed retry accounting.
