# Reviewer 2 Q1 external-diversity extension protocol v1

Status: prespecified; generation is blocked until all Introduction-derived inputs and target-excluded evidence snapshots pass preflight.

Generation model: Vertex AI `gemini-2.5-pro`  
Temperature: `0.5`

## Objective

Reviewer 2 questioned whether the original benchmark, which is concentrated in a limited collaboration network and particle-morphology-centered problem classes, supports broad claims about automated scientific hypothesis generation. This extension tests six additional battery-research problems spanning cathode composition, liquid-electrolyte transport, all-solid-state interfaces, electrochemomechanical degradation, solid-state sulfur reaction kinetics, and sodium-cathode anionic redox.

This is a descriptive scope-extension study. It does not establish general-purpose scientific reasoning, cross-domain generalizability, or independent rediscovery of the held-out papers.

## Frozen design

1. Six cases are derived only from the Introduction-level problem framing of `1_R2.pdf` through `6_R2.pdf`.
2. Each case is generated once (`6 cases × 1 replicate = 6 trajectories`). No stochastic reproducibility or inferential-statistical claim is permitted.
3. The current auditable MPDS implementation is unchanged: three debate rounds, two evidence-specialist roles, at least three evidence pointers in evidence-using turns, and an expected nine logical generation calls per trajectory.
4. Case order is fixed as 1 through 6 before generation.
5. Generation outputs are evaluated independently and descriptively with the unchanged public IHQ rubric plus the frozen supplementary scientific/practical-validity Pass 1 module. Only the final moderator synthesis is sent to the judge.

## Introduction-only and leakage-control rules

Permitted input content is limited to background, observed or anticipated failure modes, unresolved trade-offs, operating constraints, and research goals stated before the source-specific contribution in the Introduction.

Excluded from generation inputs:

- title, author names, affiliations, DOI, journal, and paper identity;
- abstract text;
- sentences beginning the source-specific contribution (`Here`, `Herein`, `In this work`, or equivalent);
- the source paper's proposed composition, additive, coating, interlayer, process, mediator, control variable, or named mechanism when it discloses the reported solution;
- performance values, Results, Discussion, Methods, and Conclusion claims.

The target paper is excluded from both evidence pools by normalized DOI and full-title matching before the top-500 snapshot is selected. Retrieval ends in the calendar year before formal publication. These controls limit direct prompt and retrieval exposure but cannot eliminate possible parametric exposure from model pretraining.

## Evidence design

Each case receives two frozen evidence pools:

- Pool A: the battery system, material class, and operating regime;
- Pool B: the central transport, interface, structural, or reaction mechanism.

Each pool contains the top 500 usable OpenAlex abstracts from a prespecified ten-year window, after target-paper exclusion. Relevance ordering is frozen before generation.

## Group-independence accounting

Cases 1, 2, 3, 5, and 6 are from research groups outside the collaboration network identified by Reviewer 2. Case 4 is scientifically useful as a distinct electrochemomechanical problem class, but it includes the Kisuk Kang group named in the reviewer's concentration critique. Therefore:

- all six cases are retained in the mechanistic breadth demonstration;
- only five are counted as independent-group additions;
- Case 4 must be explicitly labeled as an overlapping-network mechanistic-diversity case;
- the manuscript must not claim that all six cases come from non-overlapping groups unless Case 4 is replaced prospectively before generation.

## Analysis lock

For each output, report descriptively:

- problem class and central bottleneck;
- primary MPDS hypothesis;
- cross-perspective integration;
- falsifiable validation plan;
- relation to the held-out source strategy (`full`, `partial`, `different`, or `not assessable`), coded only after generation;
- IHQ dimensions and IHQ-without-CPI / Full-IHQ aliases;
- scientific correctness, physical plausibility, constraint adherence, and falsifiability/actionability;
- major unsupported assumption or limitation.

No p-values are calculated for six non-replicated heterogeneous cases. Scores are summarized by case, median and range only.

## Claim boundary

Allowed claim: MPDS produced evaluable hypotheses across six additional battery problem classes, including five cases from non-overlapping research groups, under a common retrieval, generation, and blinded evaluation workflow.

Disallowed claims: general scientific autonomy, proof of independent recovery, performance superiority, robustness across arbitrary disciplines, or six fully independent external groups.
