# Reviewer 1 Q4 system-level extension protocol v1

Status: frozen analysis intent; generation inputs and evidence snapshots must pass preflight before API execution  
Primary manuscript case: Case Study 1, Mo/Ni chalcogenide microsphere sodium-ion anode  
Generation model: Vertex AI `gemini-2.5-pro`  
Temperature: `0.5`

## Objective

Reviewer 1 noted that the original Case Study 1 hypothesis emphasized particle-level architectural buffering while leaving electrolyte design and dynamic solid-electrolyte interphase regulation outside the manipulated design space. This supplementary extension tests whether MPDS can address electrolyte and interphase problem classes and whether an expanded version of Case Study 1 can combine particle architecture, electrolyte regulation, and dynamic interphase stabilization in one hypothesis.

The experiment is a scope-extension demonstration. It does not replace the original Case Study 1 output and is not presented as a controlled superiority test against the original prompt.

## Frozen design

1. Eight breadth cases are derived from the Introduction sections of the eight references named by Reviewer 1.
2. Each breadth case is generated once. These eight outputs provide descriptive breadth only; no stochastic reproducibility or inferential statistics will be claimed.
3. One integrated Case Study 1 prompt is generated three times. The only intended conceptual change from the original case is expansion of the design boundary to include electrolyte solvation, parasitic reaction control, and dynamic SEI regulation alongside particle architecture and processing.
4. Total expected MPDS trajectories: 11.
5. Each trajectory uses the unchanged current auditable MPDS implementation, three debate rounds, at least three evidence pointers per evidence-using turn, and an expected nine logical generation calls.

## Introduction-only and leakage-control rules

For each breadth case, the problem statement may contain only background, failure modes, trade-offs, design constraints, and unresolved questions stated in the source Introduction. The following are excluded from the generation input:

- paper title, authors, DOI, and journal identity;
- abstract and graphical abstract;
- the source paper's proposed material, solvent, salt, additive, probe, interphase composition, or processing solution;
- achieved performance values and all Results, Discussion, and Conclusion claims;
- Introduction sentences beginning the source-specific contribution, including `Here`, `Herein`, `In this work`, or equivalent language.

The target paper is excluded from its breadth-case OpenAlex evidence pools by normalized DOI and title checks. The retrieval cutoff precedes the publication year. These measures restrict direct retrieval and in-context exposure but cannot remove possible parametric exposure in the pretrained model. The outputs therefore must not be described as proof of independent rediscovery.

## Evidence design

For each breadth case:

- Pool A represents the battery system and operating regime.
- Pool B represents the central interfacial or transport mechanism.
- Each pool contains the top 500 usable OpenAlex abstracts from a frozen ten-year window ending in the year before formal publication.
- The target paper is removed before the top-500 snapshot is frozen.

For the integrated Case Study 1:

- Pool A reuses the frozen original particle/structural evidence snapshot for metal-chalcogenide anodes.
- Pool B contains eight auditable Introduction-derived mechanism records from the reviewer-named papers.
- The simulation date is 2026 because this is a revision-stage extension incorporating literature explicitly supplied by the reviewer, not a historical time-locked recovery test.

## Integrated-case consensus rule

The final moderator synthesis only is coded. A stable integrated consensus is declared only when at least two of the three independent runs contain the same primary coupled mechanism linking:

1. particle or electrode architecture;
2. electrolyte solvation, additive, or transport regulation; and
3. dynamic SEI formation, failure, or reconstruction.

If no two runs share the same primary coupled mechanism, the result is reported as `no stable integrated consensus`. No favorable run may be selected post hoc as the representative output.

## Descriptive evaluation fields

The eight breadth outputs will be summarized without p-values using:

- central bottleneck identified;
- MPDS primary proposal;
- electrolyte or interphase element;
- particle-electrolyte-interphase coupling, if present;
- proposed falsification or validation experiment;
- relation to the held-out source strategy: full, partial, different, or not assessable;
- major limitation or unsupported assumption.

The integrated case will additionally report agreement across the three runs and whether the consensus satisfies all three coupled-mechanism components.

## Claim boundary

The analysis may support the claim that MPDS can be extended to generate electrolyte- and interphase-aware hypotheses and, in the integrated demonstration, can attempt a coupled particle-electrolyte-SEI design. It cannot establish experimental efficacy, complete independence from model pretraining, or statistical generalizability beyond the tested cases.
