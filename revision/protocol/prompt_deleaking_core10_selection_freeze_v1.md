# Prompt de-leaking Core10 selection freeze v1

Date frozen: 2026-09-21  
Authorization: user-confirmed  
Frozen ordered set: `1, 2, 3, 4, 8, 15, 18, 22, 29, 30`

## What is frozen

The membership and order of the ten primary prompt de-leaking sensitivity cases are frozen. Changing membership or order requires a new versioned selection file and a written pre-result rationale.

This freeze does not yet approve or freeze the rewritten prompt text. Each draft must first be checked for preservation of the scientific task and removal of target-solution cues. Generation parameters and file hashes will be frozen in a later execution manifest.

## Selection rationale

### 1. The set was prespecified for stochastic robustness

These are the existing Core10 cases used for the three-replicate stochastic-robustness analysis. Reusing the same set avoids choosing cases after seeing de-leaking outcomes and reduces the risk of result-driven selection.

### 2. A matched three-replicate original condition already exists

Each selected case already has three frozen original-prompt MPDS outputs. Only the de-leaked condition must be generated, requiring 30 rather than up to 60 new outputs. Replicates can be averaged within case, leaving the scientific case as the independent unit (`n=10`).

### 3. Reviewer-relevant examples are included

- Repository Case 1, corresponding to manuscript Case Study 2, directly tests whether the surface/interstitial LPSCl allocation result depends on a prompt that names that allocation axis.
- Case 8 is the PBA-derived sulfide example explicitly relevant to the reviewer's concern that the expected morphology may have been supplied in the problem statement.

### 4. The set covers a useful leakage-risk spectrum

- Very high: Cases 1, 8, and 22.
- High: Cases 2, 3, 4, 15, 18, and 30.
- Moderate: Case 29.

Case 29 serves as a lower-risk comparison. Testing only the most visibly leaked prompts would exaggerate the expected sensitivity and would not show whether de-leaking matters when the original prompt mainly states confounders rather than a target morphology.

### 5. The scientific tasks are heterogeneous

The set spans solid-state cathode design, Li/Na/K conversion-type anodes, Li-Se host design, aqueous Zn-ion cathode architecture, and protocol-centered evaluation. It includes lithium, sodium, potassium, and zinc systems and multiple leakage mechanisms: target allocation, hierarchical morphology, void architecture, carbon-host geometry, named processing routes, and diagnostic checklists.

### 6. The design is efficient and statistically defensible

The paired comparison is original prompt versus de-leaked prompt within the same case, using identical evidence pools and generation settings. Three stochastic replicates are summarized within case. The inferential sample size remains ten scientific cases, preventing pseudoreplication from treating 30 generated outputs as 30 independent problems.

## Case-level reasons

| Case | Risk | Why it is included |
|---:|---|---|
| 1 | Very high | Reviewer-relevant manuscript case; the current prompt names the LPSCl surface-versus-interstitial allocation axis. |
| 2 | High | Tests whether a Mo/Ni chalcogenide solution persists after removing microsphere, nanovoid, and spray-drying cues. |
| 3 | High | Tests removal of NiMoO4 microsphere/nanovoid and spray-drying solution cues. |
| 4 | High | Adds an aqueous ZIB cathode and tests removal of CNT-microsphere, macrovoid, and assembly cues. |
| 8 | Very high | Reviewer-relevant PBA example; the prompt largely states the hollow porous cube/rGO solution. |
| 15 | High | Extends the test to a Li-Se host and removes bimodal-pore, nanofiber, and MOF-derived route cues. |
| 18 | High | Adds a potassium-ion task and removes nested hollow-carbon/microsphere architecture cues. |
| 22 | Very high | Tests a highly distinctive target phrase: tube-in-tube NiO nanobelt. |
| 29 | Moderate | Lower-risk protocol-centered comparison; no distinctive material morphology is disclosed. |
| 30 | High | Tests removal of hollow-carbon encapsulation while preserving the metal-modified selenide/carbon problem. |

## Next gate

Before any API call, prepare the complete de-leaked `situation.txt` and `user_context.txt` files for these ten cases, perform an author-side side-by-side review, validate that only the prompt condition changes, and freeze the final file hashes. The currently running lost-in-the-middle generation batch remains the execution priority.
