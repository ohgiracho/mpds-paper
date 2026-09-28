# Analysis implementation erratum v1

After all 30 blinded evaluator packets were complete, the deterministic post-processing script reached the qualitative-example rendering step and raised a `NameError`: the already selected variable `replicate` was referenced as `rep` in one Markdown heading.

The single reference was changed from `rep` to `replicate`. This correction affects only the heading printed in `trajectory_qualitative_examples.md`. It does not change the frozen rubric, evaluator inputs, API results, unblinding key, scores, event extraction, case aggregation, comparison definitions, bootstrap procedure, hypothesis tests, multiplicity correction, example-selection rule, or selected replicate.

No evaluator API call was repeated after this correction.

The generated results brief was also expanded, using the already computed outputs, to print descriptive revision-event counts and an outcome-specific interpretation paragraph that the frozen analysis plan required. This was a reporting-only change: it did not alter any score, event, case mean, contrast, confidence interval, p-value, correction family, or qualitative-example selection.
