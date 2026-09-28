# SAIR·SES Component-Control Core-10 Completion Report

## Scope and fixed execution settings

- Official run set: `runs_component_controls_core10_v2`
- Scope: 10 preselected cases × SAIR and SES × 3 independent replicates = 60 official runs.
- Model and backend: Gemini 2.5 Pro through Vertex ADC (`global`); temperature 0.5.
- The frozen configuration and experimental scripts were not changed during execution. The Vertex project identifier is intentionally not recorded in this report or the run manifests.

## Completion and strict audit

- Completion: 60/60 official runs (100%).
- Strict audit command: `tools/audit_component_control_runs.py --run-set runs_component_controls_core10_v2`.
- Audit result: PASS — 60 audited, 60 passed, 0 failed.
- The audit confirmed each official final output had valid single-source citation syntax, no invalid/bare/malformed citations, and evidence from both A and B pools where required.

## API accounting from `api_calls.jsonl` / run manifests

| Condition | Official runs | Successful calls | Failed transient calls | Prompt tokens | Candidate tokens | Thought tokens | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| SAIR | 30 | 226 | 22 | 39,143,113 | 421,423 | 782,388 | 40,346,924 |
| SES | 30 | 98 | 10 | 12,310,366 | 180,678 | 391,808 | 12,882,852 |
| **Total** | **60** | **324** | **32** | **51,453,479** | **602,101** | **1,174,196** | **53,229,776** |

Successful calls exceed the nominal 300-call plan because citation/evidence validation occasionally required an additional accepted generation. The 32 failed calls are retained in the per-run API logs as transient failed attempts; they did not cause any run-level failure, and all 60 final outputs passed the strict audit.

## Runtime accounting

- Sum of successful-call elapsed times: 28,871.0 seconds (SAIR 20,284.0; SES 8,586.9). This is an API-call total, not wall-clock duration, and excludes any retry waiting time.
- Cached-content tokens reported by the provider: 8,672,429 total (SAIR 3,833,626; SES 4,838,803).

## Provenance

All detailed outputs, manifests, API logs, and final responses remain in `runs_component_controls_core10_v2` under the revision folder. This report is a compact completion record; it does not replace the original run-level audit trail.
