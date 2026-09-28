# PBA failure diagnostic: five-run statistics and Top 1-3 validation v1

## Execution status

- Original series: Replicates 1-3, 3/3 COMPLETE
- Frozen extension: Replicates 4-5, 2/2 COMPLETE
- Combined independent runs: 5/5 COMPLETE
- Fixed factors: English input and its hash, two evidence pools and hashes, MPDS source script, Vertex AI `gemini-2.5-pro`, temperature 0.5, three debate rounds, moderator prompt, and citation-validation policy
- Historical `Auto_Debate_With_Summary.txt`: excluded from the five-run count

Across the five runs there were 45 successful logical MPDS calls, five additional successful citation-validation regenerations, and five transient failed attempts. The failures were HTTP 429 responses and were preserved in the API logs; unchanged retries succeeded.

| Run | Attempts | Successful calls | 429/errors | Validation regenerations | Runtime (s) |
|---:|---:|---:|---:|---:|---:|
| 1 | 11 | 11 | 0 | 2 | 602.85 |
| 2 | 9 | 9 | 0 | 0 | 500.96 |
| 3 | 11 | 9 | 2 | 0 | 538.98 |
| 4 | 10 | 10 | 0 | 1 | 589.67 |
| 5 | 14 | 11 | 3 | 2 | 778.78 |

Combined usage metadata over successful calls:

- Prompt tokens: 4,108,445
- Candidate/output tokens: 77,223
- Thoughts tokens: 120,463
- Total tokens: 4,306,131
- Cached-content tokens reported: 245,692
- Combined wall-clock runtime: 3,011.24 s (50.19 min)

## Final-moderator Top 1-3 coding

| Run | Top 1 | Top 2 | Top 3 | Constraint assessment |
|---:|---|---|---|---|
| 1 | Nucleation/growth control | Separation/washing | Drying/capillary stress | Major: falsely treats citrate as present and shifts to a PBA-citrate lithium-anode layer |
| 2 | Nucleation/growth control | Separation/washing | Drying/capillary stress | Partial drift into lithium-metal-anode architecture |
| 3 | Separation/washing | Nucleation/growth control | Surfactant/surface stabilization | Partial drift, but stated chemistry retained |
| 4 | Nucleation/growth control | Surfactant/chemical-speciation control | Aging/intrinsic stability | Partial drift; introduces new chelators/reactor design and device validation |
| 5 | Surfactant/organic-modifier strategy | Nucleation/growth and defect control | Engineered surface coating | Major: replaces the stated SDBS strategy and reframes the goal around a coated lithium-metal device material |

## Descriptive rank statistics

An unlisted category in a run was assigned rank 4 only for calculating a conservative mean rank. This convention does not convert an absent category into a fourth-place moderator finding.

| Bottleneck category | Rank 1 | Rank 2 | Rank 3 | Top-3 presence | Mean rank (absent=4) |
|---|---:|---:|---:|---:|---:|
| Nucleation/growth control | 3/5 (60%) | 2/5 (40%) | 0/5 | 5/5 (100%) | **1.40** |
| Separation/washing | 1/5 (20%) | 2/5 (40%) | 0/5 | 3/5 (60%) | **2.60** |
| Surfactant/surface stabilization | 1/5 (20%) | 1/5 (20%) | 1/5 (20%) | 3/5 (60%) | **2.80** |
| Drying/capillary stress | 0/5 | 0/5 | 2/5 (40%) | 2/5 (40%) | 3.60 |
| Aging/intrinsic stability | 0/5 | 0/5 | 1/5 (20%) | 1/5 (20%) | 3.80 |
| Engineered surface coating | 0/5 | 0/5 | 1/5 (20%) | 1/5 (20%) | 3.80 |

## Consensus result

The frozen five-run rule required the same valid broad category at Rank 1 in at least three of five runs. **Nucleation/growth control meets this threshold exactly: 3/5 Rank-1 and 5/5 Top-2.** Its Rank-1 proportion is 60%; because n=5 is small, the approximate 95% Wilson interval is wide (23%-88%) and should not be presented as precise population-level reliability.

The aggregate Top 1-3 ordering by conservative mean rank is:

1. Nucleation/growth control (mean rank 1.40)
2. Separation/washing (mean rank 2.60)
3. Surfactant/surface stabilization (mean rank 2.80)

Drying/capillary stress falls from the earlier three-run Top 3 to fourth after Replicates 4 and 5 did not prioritize it.

## Constraint-sensitivity analysis

Runs 1 and 5 contain major task/chemistry drift and should not be allowed to determine an experimental recipe without qualification. Restricting the sensitivity analysis to the comparatively interpretable Runs 2-4 gives:

- Nucleation/growth control at Rank 1: 2/3
- Separation/washing at Rank 1: 1/3
- Nucleation/growth control present in the Top 2: 3/3

Thus the broad nucleation/growth conclusion is directionally retained after excluding the two most problematic outputs. However, the three interpretable runs still disagree on the exact variable: temperature, feed/mixing, pH/speciation, reactant ratio, and aging are not interchangeable interventions.

## Scientific-validation boundary

- The five-run statistics validate repeatability of a **broad diagnostic category**, not the actual causal mechanism of this batch failure.
- The result does not justify stating that manual injection, room-temperature aging, SDBS, vacuum filtration, ethanol volume, or 60 °C drying has individually been proven causal.
- Direct evidence is strongest for the general proposition that PBA-family nucleation/growth conditions affect morphology, crystallinity, water content, and defects. It is weaker for the specific claim that 600 mL ethanol or vacuum filtration damaged these Co-PBA particles.
- No single numerical recipe modification reached majority agreement.
- A prospective experiment must therefore freeze one variable and a discriminating XRD/SEM prediction before the outcome is viewed.

## Recommended reporting sentence

> Across five independent MPDS runs under identical generation settings, nucleation/growth control was the most reproducible broad diagnostic category (Rank 1 in 3/5 runs and within the Top 2 in 5/5 runs). Work-up severity and surfactant-mediated surface control were the next-ranked categories. Because individual runs diverged on the responsible process variable and two outputs showed substantial scope drift, these rankings were treated as hypotheses for prospective testing rather than causal conclusions.
