# Terra handoff: corpus-size sensitivity v1

## Boundary

Terra orchestrates the run. The scientific generator remains the frozen Vertex AI `gemini-2.5-pro`; do not substitute Terra as the experimental generator. Do not start paid Gemini generation until corpus retrieval and all 48 dry-run cells pass validation.

## 1. Inspect the frozen design

Run the validator in setup mode. The expected phase before corpus retrieval is `READY_FOR_RETRIEVAL`.

```powershell
python tools/validate_corpus_size_setup.py --allow-missing-inputs
python tools/prepare_corpus_size_corpora.py
```

The retrieval dry-run must report 4 cases, 8 queries, top-1000 masters, and 80 expected OpenAlex requests. If `OPENALEX_API_KEY` is absent, stop and ask the user to configure it; do not silently broaden a query or accept fewer than 1000 records.

## 2. Freeze the eight master pools

```powershell
python tools/prepare_corpus_size_corpora.py --execute
python tools/validate_corpus_size_setup.py
```

Proceed only if validation reports `PASS`, `READY_FOR_GENERATION`, eight pool summaries, and 48 dry-run cells checked. Preserve retrieval artifacts exactly.

## 3. Gemini one-output pilot

The batch schedule is frozen. Run only its first pending output:

```powershell
python tools/run_corpus_size_batch.py --execute --confirm-config-id corpus_size_sensitivity_v1 --max-runs 1 --run-retries 1
```

Inspect the completed manifest, API log, full output, final synthesis, evidence-ID validation outcome, actual input/output tokens, and prompt-character list. The result must be `COMPLETE`; the model must be `gemini-2.5-pro`; temperature must be 0.5; and both selected pools must have the requested paper count and matching hashes.

## 4. Resume the remaining batch

After the pilot passes:

```powershell
python tools/run_corpus_size_batch.py --execute --confirm-config-id corpus_size_sensitivity_v1 --max-runs 48 --continue-on-error --run-retries 2 --retry-delay-seconds 60
```

The runner skips completed cells, preserves failed attempts under timestamped adjacent directories, and updates `runs_corpus_size_sensitivity_v1/batch_status.json` after every attempted output. Continue until 48 manifests are `COMPLETE`; do not replace successful runs.

## 5. What to report

Report completed/48, failed cells, actual calls, input/output tokens, runtime, and whether any 1000-paper request approached or exceeded the model context. Do not begin Claude scoring in the same step. Blind scoring is a separate frozen follow-up after the 48 final outputs pass integrity checks.
