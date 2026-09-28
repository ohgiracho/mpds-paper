# Lost-in-the-middle position-control runbook v1

## Boundary

The orchestrating model manages execution only. The scientific generator remains frozen Vertex AI `gemini-2.5-pro`. Do not modify the model, temperature, cases, orderings, blocks, prompts, or evidence files. Do not start blind scoring in the generation step.

## 1. Revalidate the frozen setup

```powershell
python tools/validate_litm_setup.py
```

Proceed only if the report says `PASS`, `READY_FOR_GENERATION`, 8 pool manifests, 24 ordered knowledge files, and 36 dry-run cells checked. The validator must also report exact record-content identity across rotations, balanced position exposure, fixed canonical persona inputs, and no pre-existing outputs unless resuming.

## 2. Run one pilot

```powershell
python tools/run_litm_batch.py --execute --confirm-config-id lost_in_middle_position_control_v1 --max-runs 1 --run-retries 1
```

The first pending cell must finish as `COMPLETE`. Confirm `gemini-2.5-pro`, temperature 0.5, nine successful logical calls unless citation validation required regeneration, matching ordered-input and canonical-persona hashes, a valid `final.txt`, and zero invalid final citation pointers.

## 3. Resume the remaining batch

```powershell
python tools/run_litm_batch.py --execute --confirm-config-id lost_in_middle_position_control_v1 --max-runs 36 --continue-on-error --run-retries 2 --retry-delay-seconds 60
```

The runner skips complete cells, preserves failed attempts, and refreshes `runs_lost_in_middle_position_control_v1/batch_status.json` after every attempted output. Continue until 36/36 manifests are `COMPLETE`.

## 4. Deterministic utilization analysis

After 36/36 completion:

```powershell
python tools/analyze_litm_evidence_utilization.py
```

This step uses no model API. It maps debate and final-synthesis citations to fixed blocks and their experimental positions. Review the unmapped/invalid citation count before interpreting position effects.

## 5. Deferred blind quality evaluation

Only after generation and deterministic citation analysis pass should final moderator syntheses be assembled into blinded Pass 1 packets. Claude evaluation is a separate paid step and is not started by this runbook.
