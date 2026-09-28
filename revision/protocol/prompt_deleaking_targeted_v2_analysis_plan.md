# Targeted prompt de-leaking sensitivity analysis plan v2

Status: frozen before generation  
Cases: 1, 8, 22  
New generation: 3 cases × 3 replicates = 9 de-leaked MPDS outputs

## Selection rule

All 30 benchmark prompts were screened before this experiment. Eight were classified as very high risk. The targeted experiment includes all and only the very-high-risk cases that belong to the previously replicated Core10 subset: Cases 1, 8, and 22. Case membership was fixed without observing de-leaked outputs.

## Generation comparison

- Reuse the nine existing original-prompt MPDS outputs as generation controls.
- Generate only nine de-leaked MPDS outputs.
- Fix Gemini 2.5 Pro, Vertex ADC/global, temperature 0.5, maximum output tokens 8,192, three debate rounds, minimum three evidence pointers, original MPDS source scripts, frozen evidence pools and evidence order, simulation-date cutoff, and all runtime instrumentation.
- Change only debate topic, situation text, and user context to the frozen de-leaked versions.
- Do not run concurrently with the lost-in-the-middle generation batch.

## Blind evaluation

After all nine new outputs pass integrity checks, construct nine new packets. Each packet contains the corresponding original and de-leaked final answer under balanced randomized aliases. Both candidates are rescored together; existing original-prompt scores are not reused as the comparator because a new packet/evaluation context would otherwise confound the comparison.

Pass 1 uses the frozen official IHQ and supplementary scientific/practical validity rubric without modification. Target-solution recovery is evaluated in a separate auxiliary audit using `prompt_deleaking_target_recovery_rubric_v1.md`; it is not added to IHQ or validity.

Semantic evidence support is optional and secondary. It should be run only under the existing frozen Pass 2 procedure and should not delay the direct prompt-leakage result.

## Outcomes and aggregation

- Primary descriptive outcome: within-case change in IHQ without CPI.
- Secondary: Full IHQ; scientific correctness; physical plausibility; constraint adherence; falsifiability/actionability; validity composite; output length.
- Direct leakage outcome: per-feature and overall target-solution recovery labels.
- Average the three replicates within each case.
- Report case-specific means, replicate dispersion/range, direction counts, and target-recovery counts.
- Do not treat nine outputs as nine independent scientific cases.
- With three scientific cases, do not center the response on p-values or broad generalization.

## Interpretation boundaries

- Stable quality and recovery after de-leaking: limited evidence that performance in these severe-risk replicated cases was not wholly dependent on prompt cues.
- Lower recovery with stable quality: cues affected reproduction of the held-out design more than general hypothesis quality.
- Lower recovery and lower quality: acknowledge cue dependence and narrow interpretation of the original benchmark result.
- These results do not establish prompt-leakage robustness across all 30 benchmark cases.
