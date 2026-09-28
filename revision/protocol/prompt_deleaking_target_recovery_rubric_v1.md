# Target-solution recovery audit rubric v1

Status: frozen before de-leaked generation  
Scope: Cases 1, 8, and 22; original versus de-leaked final moderator outputs  
Purpose: descriptive auxiliary audit; not part of IHQ and not a new composite score

## Blinding and scoring unit

The scorer receives only the cleaned final answer and case identifier. Prompt condition, replicate condition, prior scores, and candidate identity are hidden. Original and de-leaked outputs are randomized under balanced aliases. The unit is one final answer.

For every predefined target feature, assign exactly one label:

- `absent`: the feature is not proposed.
- `partial_general`: a generic adjacent idea is present, but the distinctive target feature is not explicit.
- `explicit_target_like`: the output explicitly proposes the predefined target feature or an unambiguous functional equivalent.

Do not infer a feature from generic statements about porosity, buffering, conductivity, or transport. Record a short supporting excerpt or state `none`. Do not combine the labels into a numerical score.

## Case 1 target features

1. `surface_lpscl_contact`: LPSCl is deliberately placed as partial or conformal contact/coverage at NCM811 particle surfaces.
2. `interstitial_lpscl_network`: LPSCl is deliberately retained or placed between particles to maintain a through-electrode ionic network.
3. `combined_dual_allocation`: the answer explicitly combines the two roles in a balanced, graded, bimodal, or otherwise dual allocation rather than choosing only one.

Overall recovery is `explicit_target_like` only if feature 3 is explicit and features 1 and 2 are at least partial. A generic recommendation to optimize contact is insufficient.

## Case 8 target features

1. `hollow_cube_like_unit`: a hollow PBA-derived sulfide cube/nanocube or an unambiguous retained cubic hollow derivative is proposed.
2. `porous_or_permeable_wall`: the active sulfide unit has an explicitly porous/permeable wall or shell that preserves electrolyte access.
3. `graphene_network_integration`: reduced graphene oxide/graphene is explicitly integrated as a long-range conductive network around or between the active units.
4. `combined_cube_wall_graphene_architecture`: the answer explicitly integrates features 1–3 into one architecture.

Overall recovery is `explicit_target_like` only if feature 4 is explicit. Generic carbon coating or a generic hollow particle does not qualify.

## Case 22 target features

1. `one_dimensional_nio_body`: the answer proposes a belt-, fiber-, wire-, or tube-like NiO body.
2. `nested_inner_outer_tubes`: the body contains an explicit inner tube nested within an outer tube or a clear concentric double-tube equivalent.
3. `internal_void_as_strain_buffer`: the nested internal void is explicitly linked to conversion-strain accommodation while preserving transport/contact.

Overall recovery is `explicit_target_like` only if feature 2 is explicit and feature 3 is at least partial. A generic porous or hollow NiO structure is only `partial_general`.

## Reporting

Report feature labels and overall recovery separately for every replicate. Summarize within case as counts out of three and compare original versus de-leaked conditions descriptively. Do not calculate inferential p-values from three scientific cases and do not describe target recovery as scientific correctness.
