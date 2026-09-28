# Targeted de-leaking blind evaluation runbook v1

Status: prepared and frozen before any de-leaking evaluation API call. Generation outputs remain unchanged.

## Inputs and audit boundary

- Nine pairs: Cases 1, 8, 22 × replicates 1–3. Each pair contains one original-prompt MPDS final answer and its de-leaked counterpart. Existing original scores are not reused.
- The 9 pair packets are in `evaluation/blind_packets_deleak_pair_v1`; the separate condition key is in `evaluation/deleak_pair_blind_key_v1_DO_NOT_SHARE`. Never give the key to a judge.
- Only the frozen final-answer cleaner (`build_blind_packets.clean_final`) is applied. Debate trajectories and evidence appendices are excluded, exactly as in the earlier official Pass 1.
- The identical neutral, de-leaked debate topic is displayed for both candidates within a pair. The original solution-cue prompt and target-recovery rubric are not supplied during Pass 1.
- Source hashes, Gemini model/temperature and evidence hashes are checked when building the packets. Historical replicate-1 controls have public output files but no complete run manifests; their output and cleaned-body hashes are verified, but their original API invocation cannot be independently reconstructed from a run manifest.

## Pass 1: unchanged scoring instruments

Use the official direct Anthropic Messages transport from `run_independent_judge_anthropic_v3.py`, requested model `claude-sonnet-5`, max output 6000, required tool call, and strict local validation. The public GitHub IHQ rubric and `supplementary_evaluation_module_v1.md` remain verbatim and separate. A/B candidate cardinality is the only schema/validator adaptation. The supplementary document's generic “all five candidates” sentence is superseded solely for cardinality by the A/B prompt and schema; no anchors, caps, dimensions, flags, or scoring rules change.

First verify the frozen input manifest and perform a no-API batch plan. Then run one paid format pilot on `case_01__rep_01`; inspect COMPLETE status, returned model, two accepted candidates, source hashes, input/output tokens and any validation retry. Only after it passes, run the remaining eight with the resume-safe batch runner. A failed attempt is retained; a completed packet is never overwritten. An HTTP/API failure stops that packet rather than silently changing request content.

Do not unblind until all accepted Pass 1 packets have passed strict validation. On unblinding, compute per-case mean of the three replicates for IHQ without CPI (primary descriptive outcome), Full IHQ, the four scientific/practical validity dimensions, and output length. Keep IHQ and validity separate. Cases, not responses, are the independent units (`n=3`); report case-specific changes, ranges and direction counts, without emphasizing p-values.

## Separate target-solution recovery audit

The 18 single-answer packets in `evaluation/blind_packets_deleak_target_recovery_v1` contain only case ID and one cleaned final answer. Use the previously frozen `protocol/prompt_deleaking_target_recovery_rubric_v1.md` to label each predefined feature as `absent`, `partial_general`, or `explicit_target_like`, with a short supporting excerpt (or `none`). No new composite score is created, and these labels do not enter IHQ or validity. The separate condition key is in `evaluation/deleak_recovery_blind_key_v1_DO_NOT_SHARE`. This audit has no paid-call runner in the frozen Pass 1 implementation; its human or model scoring method must be explicitly selected and documented before execution. No recovery audit has been performed yet.

## Interpretation limitations fixed before scoring

The generation intervention changed topic, situation, and user context together. In Cases 8 and 22, removal of target-shaping phrases also broadened permitted process/carbon/architecture choices; Case 1 loosened some original restrictions. Therefore this is a targeted prompt-framing/solution-cue sensitivity analysis, not a clean one-factor causal ablation of cue words. Scoring against the common neutral task avoids reintroducing the target to the judge, but necessarily does not assess compliance with original-only constraints. Inferences are limited to these three very-high-risk Core10 cases, and the legacy replicate-1 provenance limitation remains.
