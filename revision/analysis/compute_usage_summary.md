# Compute Usage Summary

This file provides a manifest-derived compute account for the publicly released MPDS revision runs. It was calculated from all 276 `run_manifest_public.json` files under `revision/outputs/`: 271 benchmark and revision runs plus five PBA diagnostic runs. All 276 manifests have `status: COMPLETE`.

## Generation runs

The values below are sums of provider-returned metadata. Input tokens are `prompt_token_count`; candidate output tokens are `candidates_token_count`; thinking tokens are `thoughts_token_count`; and total tokens are the provider-reported `total_token_count`. Cached input tokens are reported separately but are already contained within the prompt-token count and are therefore not added again. API calls are shown as attempted/successful/failed. Summed API elapsed time is the sum of request-level durations, not the end-to-end duration of a concurrently executed batch. Summed run wall time is reported only where every public manifest in a batch retained `wall_clock_seconds`.

| Generation batch | Complete runs | Model | Input tokens | Candidate output tokens | Thinking tokens | Cached input tokens | Total tokens | API calls A/S/F | Summed API elapsed (h) | Summed run wall time (h) | Explicit validation regenerations | Monetary cost |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Core10 repeated generation | 101 | Gemini 2.5 Pro | 67,372,623 | 616,170 | 1,270,740 | 7,224,539 | 69,259,533 | 480/465/15 | 7.69 | NR | NR | Not estimated; billing configuration not retained |
| SAIR/SES component controls | 60 | Gemini 2.5 Pro | 51,453,479 | 602,101 | 1,174,196 | 8,672,429 | 53,229,776 | 356/324/32 | 8.02 | NR | NR | Not estimated; billing configuration not retained |
| Corpus-size sensitivity | 48 | Gemini 2.5 Pro | 63,867,035 | 753,047 | 1,379,906 | 5,870,714 | 65,999,988 | 559/518/41 | 8.38 | 8.60 | NR | Not estimated; billing configuration not retained |
| Lost-in-the-middle position control | 36 | Gemini 2.5 Pro | 47,370,016 | 537,121 | 944,140 | 2,590,259 | 48,851,277 | 386/353/33 | 6.45 | 6.63 | NR | Not estimated; billing configuration not retained |
| Targeted prompt de-leaking | 9 | Gemini 2.5 Pro | 10,550,530 | 143,268 | 265,973 | 421,729 | 10,959,771 | 108/98/10 | 1.68 | 1.73 | NR | Not estimated; billing configuration not retained |
| Reviewer 1 Q4 system integration | 11 | Gemini 2.5 Pro | 12,072,037 | 185,592 | 286,876 | 1,095,521 | 12,544,505 | 117/111/6 | 1.99 | 2.03 | NR | Not estimated; billing configuration not retained |
| Reviewer 2 Q1 external diversity | 6 | Gemini 2.5 Pro | 7,032,572 | 92,610 | 153,939 | 348,114 | 7,279,121 | 62/55/7 | 1.09 | 1.13 | NR | Not estimated; billing configuration not retained |
| PBA failure diagnosis | 5 | Gemini 2.5 Pro | 4,108,445 | 77,223 | 120,463 | 245,692 | 4,306,131 | 55/50/5 | 0.81 | 0.84 | 5 | Not estimated; billing configuration not retained |
| **All public generation manifests** | **276** | **Gemini 2.5 Pro** | **263,826,737** | **3,007,132** | **5,596,233** | **26,468,997** | **272,430,102** | **2,123/1,974/149** | **36.11** | **20.95 for 115 runs** | **5 recorded; NR for 271 runs** | **Not estimated** |

The 101 Core10 manifests comprise 100 second- and third-replicate runs plus one additional canonical EOP run, as described in `revision/README.md`. The original exploratory 30-case first-run outputs under `data/` predate this uniform revision manifest schema. Their token usage and runtime are not retrospectively recoverable from the public artifacts and are not estimated here.

Failed calls in the A/S/F counts are preserved transport or API failures recorded by the public manifests. An explicit `validation_regeneration_calls` field is available for the five PBA diagnostic runs and sums to five; it is not available uniformly for the other 271 runs, so missing values are reported as NR rather than zero.

## Official Claude evidence audit

The official Core10 Pass 2 evidence audit has a separate usage-based estimate. The selected-result and all-recorded-call values below reproduce `revision/results/pass2_sonnet5_core10_n3_official_v1/PASS2_RESULTS_BRIEF_20260915.md`. Cache-creation and cache-read tokens are listed separately because the provider prices these categories differently.

| Scope | Candidate results | HTTP 200 calls | Base input tokens | Cache-creation tokens | Cache-read tokens | Output tokens | Recorded runtime | Estimated cost (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| Selected official results | 150 | 150 | 1,572,022 | 41,134 | 577,216 | 302,389 | NR | 6.386 |
| All recorded billable responses, including discarded format pilots or retries | 150 | 157 | 1,681,063 | 45,271 | 593,672 | 320,239 | NR | 6.796 |

The Claude values are usage-based estimates under the price schedule recorded by the original analysis on 15 September 2026. Provider invoices remain authoritative. Uniform public runtime records were not retained for this audit and are therefore reported as NR.

## Cost interpretation and coverage limits

Monetary cost is not treated as a model-independent compute measure. Gemini billing can depend on provider price schedules, per-request context length, cached-token treatment, service tier, contractual discounts, credits, currency, and account configuration. The public manifests do not retain the account's billing configuration or invoice data. Accordingly, this release reports provider-returned token counts, API-call counts, and recorded runtime as the primary compute descriptors and does not reconstruct Gemini charges from assumptions.

This summary covers the public generation manifests and the official Claude Core10 Pass 2 evidence audit for which an explicit usage-based estimate was already preserved. It does not infer usage for older or other evaluator executions lacking a uniform public usage record. `NR` means not retrospectively recoverable from the released artifacts, not zero.
