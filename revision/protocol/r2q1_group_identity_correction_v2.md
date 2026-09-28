# Reviewer 2 Q1 — group-identity correction (post-generation, 2026-09-22)

## Correction

The original group-accounting metadata incorrectly treated Case 4 (`4_R2.pdf`; Eum et al., *Nature Materials* 23, 2024, DOI 10.1038/s41563-024-01899-9) as overlapping the Kang group in the original benchmark. Case 4 includes **Kisuk Kang**. The original benchmark's J.-S. Park collaboration includes **Yun Chan Kang** (e.g., the V2O3 source first page records J.-S. Park and Y. C. Kang together). They are different investigators. Reviewer 2's wording in `리비전V5.docx` uses only “Park/Kang/Cho collaboration network”; the given-name resolution is supported by the original benchmark source and the researcher's clarification, not by the review sentence alone.

Accordingly, Case 4 must **not** be excluded as an overlapping Kang-group case on the basis of the shared surname. All six R2 cases count as external additions with respect to the specifically identified J.-S. Park / Yun Chan Kang / Cho investigator network. This is PI-level accounting, not a claim that every coauthor has been exhaustively screened for every possible historical collaboration.

## Provenance and effect

- The frozen generation configuration `config/r2q1_external_diversity_v1.json` (SHA-256 `3dc844912f2e0389860505cd864969267a505836ae67c795277dceb3a1f55d56`) and raw generation manifests are preserved unchanged because their hashes were recorded during execution.
- The frozen blind key (SHA-256 `bd07d3535ec421853597a3d99ec168434c19754e8fc3c272b5ba672063258d58`) and accepted Claude scores are preserved unchanged.
- The wrong `group_accounting` field in those immutable v1 artifacts is superseded by this correction and `config/r2q1_group_accounting_overlay_v2.json`. Analyses should use the corrected v2 score table and v2 narrative, not the v1 group label.
- Corrected independent external case count: **6/6**, rather than 5/6. No paper replacement, Gemini regeneration, Claude regrading, or numerical score change is required.
- This change does not expand the scientific claim beyond a descriptive six-case battery-domain scope extension with one output per case. It does not establish cross-domain generalizability or stochastic reproducibility.

## Corrected reviewer-facing wording

> We evaluated six additional battery-research problems drawn from source papers outside the J.-S. Park/Yun Chan Kang/Cho investigator network represented in the original benchmark, spanning cathode composition, liquid-electrolyte transport, solid-state interfaces, electrochemomechanical degradation, solid-state sulfur conversion, and sodium-cathode anionic redox. The six single-run outputs are descriptive and show heterogeneous quality; one violated a central material constraint. This extension supports broader problem-class coverage within battery research, but not general scientific autonomy, cross-domain generalizability, or reproducibility across repeated runs.
