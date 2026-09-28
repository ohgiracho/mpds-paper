# Q4 OpenAlex query adjustment log v1

These changes were made before any Q4 MPDS generation and before the affected evidence pools were frozen. The requirement of 500 selected abstracts per pool and each publication cutoff remained unchanged. Failed retrieval staging directories were preserved for audit.

| Case/pool | Original query | Observed usable count or OpenAlex count | Final query | Reason |
|---|---|---:|---|---|
| Q4-03/B | `operando characterization dynamic SEI inorganic fluoride` | 458 usable | `operando characterization solid electrolyte interphase battery` | Original mechanism-specific query could not supply 550 pre-exclusion records. |
| Q4-04/B | `dual electrode compatibility SEI CEI electrolyte` | 61 usable | `high voltage lithium metal battery interphase` | Original literal combination was too restrictive. |
| Q4-05/B | `lithium ion desolvation interfacial ion transport SEI` | 245 OpenAlex records | `lithium metal electrolyte interfacial transport` | Broadens the same interface-transport domain sufficiently for a 500-paper snapshot. |
| Q4-06/B | `SEI ion transport dead lithium reactivation current collector` | 16 OpenAlex records | `anode free lithium battery solid electrolyte interphase` | Avoids an extremely narrow, solution-cue-heavy query. |
| Q4-07/B | `temperature dependent solvation desolvation electrode electrolyte interphase` | 369 OpenAlex records | `lithium metal battery electrolyte low temperature high temperature` | Preserves wide-temperature focus with adequate evidence breadth. |
| Q4-08/B | `SEI charge transport desolvation electron blocking solvent adsorption` | 185 OpenAlex records | `low temperature graphite solid electrolyte interphase` | Preserves graphite/SEI/low-temperature focus with adequate evidence breadth. |

One additional pre-generation leakage correction removed the word `regeneration` from the Q4-03 goal. The source Introduction identifies dynamic interphase evolution, but the exact formation-breakdown-regeneration profile is a reported finding rather than a safe problem-only input.
