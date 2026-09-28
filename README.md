# MPDS paper: public code, data, and revision results

This folder is the curated GitHub upload candidate as of 2026-09-28. It extends the preserved 2026-09-26 candidate with the latest Data S1, public two-expert evaluation summaries, and the five-run PBA diagnostic series. Copy the **contents of this folder** into the intended GitHub repository after author approval. This folder is not itself a Git checkout, and preparing it did not publish or push anything.

## Contents

| Location | Contents |
| --- | --- |
| `code/` | Original 30-case generation and scoring source bundle, including the working-tree `score_ihq.py` file. |
| `data/` | Original benchmark inputs, safe retrieval metadata, released outputs, and IHQ artifacts. |
| `revision/data_s1/` | Latest `Data_S1_revision_260928_v3.xlsx`, including `Human_Expert` and `PBA_Followup` sheets. |
| `revision/config/`, `revision/protocol/`, `revision/tools/` | Revision experiment settings, frozen procedures, and analysis/generation scripts. |
| `revision/inputs/` | Public-safe situation/context files and retrieval/block metadata. Plaintext OpenAlex abstract pools are not included. |
| `revision/outputs/` | Final answers, sanitized debate outputs, and public run manifests for completed revision runs. |
| `revision/evaluation/`, `revision/analysis/`, `revision/results/` | Rubrics, frozen judge prompts/schemas, scores, two-expert public summaries, PBA diagnostic analyses, and selected final analyses. |
| `RELEASE_FILE_MANIFEST.csv` | Per-file byte counts and SHA-256 hashes for the publishable files; ignored Python bytecode caches are excluded. |

The original baseline repository was based on commit `fe30cc5f3c6bd2f20be3e2bf116b758b0e8c6314` of `ohgiracho/mpds-paper`. The benchmark/revision output bundle contains **271 complete canonical runs**: Core10 repeats 101, SAIR/SES component controls 60, corpus-size sensitivity 48, lost-in-the-middle 36, targeted prompt de-leaking 9, Reviewer 1 Q4 system integration 11, and Reviewer 2 Q1 external diversity 6. An additional **five complete PBA diagnostic runs** are a separate laboratory case study, not five independent benchmark cases.

The `revision/outputs/*/run_manifest_public.json` files retain the run settings, source-file hashes, execution summaries, and both source/public output hashes. Their `full_output.txt` and `final.txt` are public copies with local filesystem paths and project identifiers removed. Use the public hashes when checking files in this repository; source hashes identify the original local artifacts and may differ because of redaction.

## Scope and limitations

- The original IHQ rubric and scores remain in `data/IHQ rubric/`. Revision-specific scientific/practical validity and evidence-support materials are separate under `revision/evaluation/` and `revision/results/`; they do not retroactively replace the original IHQ definition.
- The `Human_Expert` worksheet contains anonymized ratings from two experts on 70 run-2 outputs. Public aggregate summaries are in `revision/analysis/human_expert_2rater_public_v1/`. Inter-rater agreement was low, and masking of the answer text was imperfect; see `analysis_brief.md` before interpreting the expert results. Original filled score sheets and the administrative blind key are not included.
- The five PBA outputs and their rank coding are in `revision/outputs/pba_failure_diagnostic/` and `revision/analysis/`. They test reproducibility of broad diagnostic categories, not causal validity or laboratory reproducibility; two outputs showed substantial scope drift. The `PBA_Followup` worksheet gives the reported washing comparison, but raw SEM/XRD instrument files are not included because an unambiguous sample-to-condition mapping was not established in this release.
- The release supports inspection of saved results and analysis. Full generation cannot be reproduced from this repository alone because copyrighted/full-text evidence pools and OpenAlex plaintext abstract snapshots are intentionally omitted. Public-safe retrieval and block metadata remain available.
- Failed/interrupted attempts, raw API request/response logs, credentials, local Google project identifiers, blind keys, internal working notes, and external publisher PDFs are excluded.
- The manuscript, SI, reviewer-response, and figure draft documents are not part of this public data release. Those remain in the private working folder and should be checked against the final submission files before public posting.
- This is a curated upload candidate, not a claim that every analysis is independently validated or that the journal permits public posting of every manuscript file. Author and journal-policy review should precede publication.

## Suggested upload check

1. Review this README and the file manifest.
2. Confirm that the repository's current files and history can be safely merged with this candidate; this folder intentionally has no `.git` directory.
3. Obtain the authors' approval for the revision data release.
4. Upload the folder contents, then compare the GitHub file list with `RELEASE_FILE_MANIFEST.csv`.

No API key is required to inspect the saved outputs and score tables. Generating new results requires separately configured model access and the excluded evidence snapshots.
