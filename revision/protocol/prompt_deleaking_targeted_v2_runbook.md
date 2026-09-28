# Targeted prompt de-leaking generation runbook v2

Status: inputs and execution plan frozen; no API call authorized by preparation alone  
Config: `config/prompt_deleaking_targeted_v2.json`  
Cases: 1, 8, 22  
New outputs: 9 de-leaked MPDS outputs  
Generation model: Vertex AI `gemini-2.5-pro`, temperature 0.5

## Frozen design

The selection rule is all and only Very High prompt-leakage-risk cases within the previously replicated Core10 subset. The 30-case screening identified eight Very High cases; their intersection with Core10 is exactly Cases 1, 8, and 22. The selection was fixed before de-leaked outcomes existed.

Only the debate topic, situation file, and user context change. The MPDS scripts, two evidence snapshots per case, evidence order, cutoff date, model, temperature, token limit, debate rounds, evidence-pointer requirement, and runtime instrumentation remain frozen. The nine existing original-prompt MPDS outputs are not regenerated.

## Safety gate

Do not run this batch while lost-in-the-middle generation remains incomplete. Both the cell runner and batch runner enforce 36/36 COMPLETE in `runs_lost_in_middle_position_control_v1/batch_status.json` before any output directory is created or any API request can occur.

Do not begin Claude evaluation during generation. After generation, build new blinded pair packets and rescore original and de-leaked answers together.

## Preflight without API

From the revision root:

```powershell
python tools\validate_deleak_setup.py
```

Required result:

- `validation: PASS_SETUP`
- `dry_runs_passed: 9`
- `original_controls_verified: 9`
- `api_calls_made: 0`
- `generation_readiness: READY_FOR_GENERATION`

If the final field is `WAIT_FOR_LITM`, do not override the gate.

## Pilot after the gate opens

The first pending frozen cell is Case 1, Replicate 1. Run exactly one output:

```powershell
python tools\run_deleak_batch.py --execute --confirm-config-id prompt_deleaking_targeted_v2 --max-runs 1 --continue-on-error --run-retries 2 --retry-delay-seconds 60
```

Before continuing, require the cell manifest to report `COMPLETE`, model `gemini-2.5-pro`, temperature 0.5, matching input/evidence hashes, a non-empty `final.txt`, at least nine successful API calls, usage logging, and completed built-in citation validation.

## Resume-safe continuation

After the pilot passes, run all remaining cells in the frozen order:

```powershell
python tools\run_deleak_batch.py --execute --confirm-config-id prompt_deleaking_targeted_v2 --max-runs 9 --continue-on-error --run-retries 2 --retry-delay-seconds 60
```

Completed cells are skipped. Failed attempts are preserved under timestamped sibling directories. Never delete or overwrite a completed output.

## Post-generation work, not part of this run

1. Verify 9/9 COMPLETE and aggregate API-call, token, retry, and runtime logs.
2. Construct nine matched, balanced blind pair packets containing original and de-leaked final answers.
3. Run the unchanged official Pass 1 IHQ plus supplementary validity rubric.
4. Run the separate target-solution recovery audit using `protocol/prompt_deleaking_target_recovery_rubric_v1.md`.
5. Aggregate three replicates within each case and report descriptively at `n = 3` scientific cases.
