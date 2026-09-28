# Exploratory trajectory-analysis runbook v1

## Boundary

This runbook evaluates already stored trajectories. It must not call Gemini or generate new DS, MPDS, SAIR, or SES outputs. Existing Pass 1 and Pass 2 scores remain unchanged.

The trajectory rubric, prompt, schema, preprocessing, aliases, comparisons, and interpretation rules are frozen. The first live packet is part of the official analysis; its result must not be used to revise the rubric.

## 1. Validate frozen inputs

```powershell
python tools/validate_trajectory_analysis_setup.py
```

Proceed only if the result is `PASS`, `READY_FOR_EVALUATION`, 30 packets, 120 trajectories, zero errors, and an available Anthropic key. Do not print the key value.

## 2. Execute the first official packet

```powershell
python tools/run_trajectory_analysis_anthropic.py `
  --packet evaluation/trajectory_analysis_core10_v1/blind_packets/case_01__rep_01.md
```

Check only technical validity: HTTP 200, returned model `claude-sonnet-5`, one forced tool call, four complete Trajectory A–D evaluations, valid 0–4 scores, zero-to-three well-formed events, token usage, and `COMPLETE`. Do not inspect score direction to modify frozen materials.

## 3. Resume all remaining packets

```powershell
python tools/run_trajectory_analysis_anthropic.py --all
```

Completed packets are skipped. A failed HTTP/API call is preserved and stops the active batch. A structurally invalid HTTP-200 response may receive the single frozen retry.

## 4. Assemble and analyze

After 30/30 packets are complete:

```powershell
python tools/analyze_trajectory_evaluations.py
```

The analysis averages three replicates within case before inference. It produces blinded/unblinded scores, revision events, case means, prespecified pairwise statistics, validation, frozen-rule qualitative examples, and the results brief.
