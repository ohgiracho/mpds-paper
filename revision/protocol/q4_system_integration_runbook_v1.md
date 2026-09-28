# Reviewer 1 Q4 system-level extension runbook v1

Status: inputs and evidence frozen; one pilot is required before the remaining resume-safe batch  
Config: `config/q4_system_integration_v1.json`  
Model: Vertex AI `gemini-2.5-pro`, temperature 0.5  
Design: eight breadth cases x one output, plus one integrated Case Study 1 x three outputs

## Preflight without generation API calls

From the revision root:

```powershell
python tools\validate_q4_setup.py
python tools\run_q4_system_integration_batch.py --max-runs 11
```

Required results are `PASS_SETUP`, `READY_FOR_GENERATION`, 11 scheduled outputs, and zero generation API calls.

## First pilot

The first frozen item is breadth Case Q4-01, replicate 1:

```powershell
python tools\run_q4_system_integration_batch.py --execute --confirm-config-id q4_system_integration_v1 --max-runs 1 --run-retries 2 --retry-delay-seconds 60
```

Before continuation, inspect its `run_manifest.json` for `COMPLETE`, `gemini-2.5-pro`, temperature 0.5, the frozen situation/context and both evidence hashes, at least nine successful API calls, non-empty `final.txt`, input/output usage metadata, and `citation_validation = passed_by_unchanged_mpds_source`. The source implementation exits successfully only after its evidence-pointer validation passes.

## Resume-safe continuation

```powershell
python tools\run_q4_system_integration_batch.py --execute --confirm-config-id q4_system_integration_v1 --max-runs 11 --continue-on-error --run-retries 2 --retry-delay-seconds 60
```

Completed outputs are skipped. Failed attempts are preserved under timestamped sibling directories; a complete output is never overwritten. Progress is tracked in `runs_q4_system_integration_v1/batch_status.json`.

## Post-generation audit and analysis

1. Require 11/11 `COMPLETE`; verify each final answer and evidence-pointer audit, model, temperature, input/evidence hashes, API usage, retries, and runtime.
2. Summarize the eight breadth cases descriptively in the single SI table template at `analysis/q4_si_table_template_v1.md`.
3. Independently code the primary coupled mechanism in the three integrated final moderator syntheses. Apply the frozen 2-of-3 consensus rule; report `no stable integrated consensus` if it fails.
4. Compare each breadth proposal with its held-out target paper only after generation. Do not claim independent rediscovery or statistical generalizability.
5. Draft the main-text/SI addition and Reviewer 1 Q4 response with the original narrow design boundary explicitly acknowledged.

The Q4-specific Vertex instrumentation records model, usage, timing, prompt hashes, and error types/codes but not credentials, project ID, prompt text, or provider error messages. Runner stdout/stderr logs are also redacted before saving.
