# MPDS paper release repository candidate

This repository candidate is a public-facing preparation bundle for the MPDS paper release. It focuses on two release components: `code/` and `data/`. The bundle is organized so that readers can inspect the generation code, per-case inputs, safe retrieval metadata, model outputs, and released IHQ scoring artifacts without exposing restricted OpenAlex plaintext abstract dumps.

## One-paragraph summary of MPDS
MPDS (Multi-Persona Debate System) is a debate-based scientific hypothesis generation pipeline that compares multiple inference conditions, including Raw LLM, EO, EOP, DS, and MPDS, on benchmark battery-materials design cases using time-locked evidence snapshots and IHQ-based scoring.

## Repository scope for the paper release
This release candidate contains public code, benchmark metadata, case input files, safe OpenAlex snapshot metadata, outputs for all main conditions, and released IHQ scoring artifacts. It does not aim to be a full local mirror of every working folder used during experimentation.

## Folder structure
- `code/`
  - `01_base_source_code/`: representative base source files and utilities
  - `02_case_specific_generation_code/`: case-specific generation code
    - each case folder directly exposes condition-specific code folders such as `raw_llm/`, `mpds/`, `eo/`, `eop/`, and `ds/`
    - provenance remains `case 1 = retest7` and `cases 2-30 = rerun`
  - `03_scoring_code/`: IHQ scoring, EOP-added scoring, and trajectory scoring scripts
  - `requirements.txt`: Python dependency list for the released code bundle
- `data/`
  - `benchmark_cases/`: benchmark metadata release tables
  - `case_inputs/`: per-case `situation.txt` and `user_context.txt`
  - `snapshots_safe/`: safe snapshot metadata only
  - `outputs/`: outputs organized by condition and case
  - `IHQ rubric/`: released IHQ scoring rubric text and score presentation/spreadsheet artifacts
  - `lab follow-up source files/`: release-approved follow-up text artifacts

## What is included
- Base retrieval and debate-generation code
- Case-specific generation code for Raw LLM, EO, EOP, DS, and MPDS
- Canonical case inputs for 30 benchmark cases
- Safe OpenAlex retrieval metadata for 30 cases
- Outputs for Raw LLM, EO, EOP, DS, MPDS, and MPDS stagewise rounds
- Released IHQ scoring artifacts, including the EOP-added benchmark score workbook

## What is intentionally excluded
- OpenAlex plaintext abstract dumps such as `Topic_*_Knowledge.txt` and `Merged_Knowledge*.txt`
- External/reference/publisher PDFs
- Private notes, unredacted intermediate logs, and secret-bearing files not approved for public release

## Notes on current release layout
- This repository candidate is organized around `code/` and `data/` only.
- The benchmark output layout is condition-first under `data/outputs/`.
- DS and MPDS output folders contain both final synthesis files and full debate logs.
- IHQ scoring materials are stored under `data/IHQ rubric/` rather than a separate `data/scores/` folder.
