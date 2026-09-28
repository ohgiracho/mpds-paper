# Targeted de-leaking target-recovery audit execution v1

Fixed before opening or unblinding de-leaking Pass 1 scores.

- Apply `prompt_deleaking_target_recovery_rubric_v1.md` without changes to all 18 single-answer packets. The unit is one cleaned final answer, and no original/de-leaked labels are sent to the evaluator.
- Use direct Anthropic Messages API, `claude-sonnet-5`, one forced strict tool response per output, max output 2000 tokens, no browsing or other tools. One packet is piloted; remaining packets continue only if its returned model, structure and local validation pass. Failed responses are preserved. Completed packets are not overwritten.
- Report each feature's three-level label and a supporting excerpt; use `none` for absent. The overall label is `explicit_target_like` only under the case-specific definition in the frozen rubric. Otherwise `partial_general` denotes some target-adjacent feature but no full explicit target; `absent` denotes no target feature.
- Do not combine recovery labels with IHQ, validity, or evidence scores. After all 18 pass local validation, unblind using the separately stored key and summarize counts out of three for each condition and case. No significance test is planned for three cases.
- The evidence corpus is held fixed and may itself contain target-associated concepts; persistence of recovery after de-leaking does not isolate the original prompt as the only possible source of a target design.
