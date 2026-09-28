# Revision data map

All paths below are relative to this `revision/` directory. The parent README describes the overall release scope and exclusions.

| Experiment | Saved complete runs | Primary saved analysis |
| --- | ---: | --- |
| Core10 repeated generation | 101 | `results/pass1_sonnet5_core10_n3_official_v1/`, `results/pass2_sonnet5_core10_n3_official_v1/` |
| SAIR/SES component controls | 60 | `analysis/pass1_component_controls_4condition_official_anthropic_v4/`, `results/pass2_sonnet5_component_controls_core10_n3_official_v1/` |
| Corpus-size sensitivity | 48 | `evaluation/corpus_size_pass1_*` |
| Lost-in-the-middle position control | 36 | `results/lost_in_middle_position_control_v2_verified/`, `analysis/litm_position_control_results_v2.md` |
| Targeted prompt de-leaking | 9 | `analysis/deleak_case_comparison_v2.csv`, `analysis/deleak_target_recovery_by_replicate_v2.csv` |
| Reviewer 1 Q4 system integration | 11 | `analysis/q4_si_table_results_v1.md`, `analysis/q4_pass1_sonnet5_v1/` |
| Reviewer 2 Q1 external diversity | 6 | `analysis/r2q1_si_table_results_v2.md`, `analysis/r2q1_pass1_sonnet5_v1/` |
| PBA failure diagnostic (separate laboratory case study) | 5 | `analysis/pba_failure_diagnostic_n5_statistics_v1.md`, `analysis/pba_failure_diagnostic_top3_validation_v1.md` |

`data_s1/Data_S1_revision_260928_v3.xlsx` is the current analysis workbook. The `Human_Expert` worksheet has two anonymized raters' scores for 70 run-2 outputs, and `analysis/human_expert_2rater_public_v1/` contains public aggregate analyses without the original filled evaluator forms or administrative blind key. The `PBA_Followup` worksheet summarizes the reported washing comparison; raw instrument files are not included.

The source run status was required to be `COMPLETE`, with both `final.txt` and `full_output.txt` present and their source hashes matching the original manifest. Excluded failed and interrupted run directories were not silently converted to complete records. The Core10 count includes one additional canonical EOP run beyond the 100 second/third-replicate runs; the original first-replicate benchmark material remains under the parent `data/` bundle.

The publication unit for paired Core10 analyses is the scientific case, not each stochastic response. The score files retain replicate-level values for audit, while case-level comparisons and summaries are in the named analysis folders.

The five PBA diagnostic outputs are separate from the 271 benchmark/revision runs. Their public manifests omit source-local paths and project metadata while retaining model, temperature, hashes, call usage, and runtime. The two original knowledge pools are represented by hashes but not redistributed. Two of the five runs showed major scope drift, so the diagnosis should not be read as experimental proof.

`config/` and `protocol/` preserve experiment definitions. `inputs/` preserves shareable prompts and retrieval/block metadata, but not full abstract pools. Source-local absolute paths in text artifacts were replaced with `[LOCAL_PATH_REDACTED]`; project identifiers were omitted or replaced with `[REDACTED_PROJECT_ID]`. Neither marker is a model input or a scientific result.
