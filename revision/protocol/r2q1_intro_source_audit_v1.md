# Reviewer 2 Q1 Introduction source audit v1

All six PDFs were visually inspected on 2026-09-22 and their first-page/Introduction text was extracted locally. The generation prompts below retain only problem framing and exclude each paper's disclosed solution and results.

| Case | Source and formal publication | Problem class retained | Source-specific content excluded | Group accounting |
|---|---|---|---|---|
| 1 | Zhang et al., *Nature Energy* 8 (2023), DOI 10.1038/s41560-023-01267-y | Low-Ni/Co-free layered-cathode cost–energy–stability trade-off | Complex concentrated doping; exact composition/elements; performance and characterization results | Independent external group |
| 2 | Kim et al., *Nature Energy* 8 (2023), DOI 10.1038/s41560-023-01280-1 | Weak-solvation electrolyte stability–conductivity trade-off in Li-metal cells | High-entropy/molecular-diversity strategy; named solvent mixtures; ion-cluster and pouch-cell results | Independent external group |
| 3 | Wan et al., *Nature* 623 (2023), DOI 10.1038/s41586-023-06653-w | Coupled anode/cathode interface failure in low-pressure ASSLBs | Mg–Bi and F-rich interlayers; conversion products; exact capacities and performance | Independent external group |
| 4 | Eum et al., *Nature Materials* 23 (2024), DOI 10.1038/s41563-024-01899-9 | High-voltage intragranular cracking and unexplained electrochemomechanical degradation | Rotational stacking faults as the reported cause; thermal defect annihilation; reported results | Overlaps reviewer-named Kang network; mechanistic-diversity case only |
| 5 | Song et al., *Nature* 637 (2025), DOI 10.1038/s41586-024-08298-9 | Slow solid–solid sulfur redox at sparse three-phase boundaries | Iodine-redox glass electrolyte mediator; LBPSI composition; rate/cycling results | Independent external group |
| 6 | Wang et al., *Nature Energy* 9 (2024), DOI 10.1038/s41560-023-01425-2 | Anionic-redox capacity versus irreversible phase distortion/migration in P2 Na cathodes | OP4 boundary control and charge-depth solution; exact composition and pouch-cell results | Independent external group |

## Leakage audit decision

Each final `user_context.txt` was checked against the exclusions above. The prompt asks an open design question and does not name the held-out material, additive, interlayer, mediator, defect, or process used by the source paper. Target title and DOI are retained only in the private configuration for evidence exclusion and are never sent to the generation model.
