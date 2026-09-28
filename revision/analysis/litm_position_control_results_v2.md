# Lost-in-the-middle position-control: verified local analysis

Analysis date: 2026-09-22. Generation and Claude Pass 1 were already complete. This report uses no new model calls. The 36 frozen Gemini 2.5 Pro outputs, generation config, 12 blinded Claude packets, and 36 Claude scores were not changed.

## Attribution repair and checks

The original fail-closed analyzer recognized only singleton `[ID: n]` citations—1,812 debate pointers and 307 final-answer pointers—while many citations used comma-separated lists. The versioned post-processing rule in `protocol/litm_citation_attribution_v2.md` counts each numeric pointer in those lists. It also handles six pointers explicitly marked as the opponent's data in debate turns. The verified parser found 6,475 debate citation pointers and 1,197 final-answer pointers across all 36 outputs. All parsed IDs were present in the attributed frozen pool. The sums of the output-level rows reconcile to these totals. The old singleton counts must not be reported as citation totals.

Among final-answer pointers, 61 occurrences in 35 brackets do not name Scientist A/B. Both possible pool records occupy the *same* front/middle/rear position in every one of these 61 instances. Their position is therefore exact, but their source paper/pool is not. Final pooled citation occurrences and shares include them; final unique-paper results are presented as assignment bounds. Pool-specific final metrics in the raw table include explicitly scoped citations only and must not be reported as complete final-answer totals. The original v1 failure audit remains untouched. The final verified result set is `results/lost_in_middle_position_control_v2_verified/` (manifest status `PASS_WITH_POSITION_ONLY_FINAL_ATTRIBUTION`).

## Primary debate-stage evidence utilization

Each fixed evidence block occurred once at the front, middle and rear in the cyclic orderings. Three stochastic replicates were averaged within each case–pool–block–position cell, and the six pool/block units were averaged within each of four cases. Numbers below are equal-weighted means of the four case means, not 36 independent observations.

| Position | Citation share | Citation occurrences per pool/block | Unique cited papers per pool/block | Block coverage |
|---|---:|---:|---:|---:|
| Front | 39.35% | 35.15 | 13.38 | 7.97% |
| Middle | 29.19% | 27.60 | 12.08 | 7.20% |
| Rear | 31.46% | 27.18 | 12.39 | 7.38% |

Front minus middle citation share was +10.16 percentage points and positive in all four cases (exact two-sided sign-flip p = 0.125; Holm-adjusted within the metric = 0.375). Rear minus middle was only +2.27 points, positive in three cases and negative in one (exact p = 0.375). Front minus middle citation occurrences averaged +7.56 per pool/block and were positive in all four cases. However, front minus middle *unique cited papers* was positive in only two of four cases, and block coverage likewise in only two. The stronger signal is repeated citation frequency/share, not consistent expansion of the distinct-paper set.

| Case | Front share | Middle share | Rear share |
|---|---:|---:|---:|
| 1 | 40.60% | 26.46% | 32.94% |
| 2 | 40.82% | 31.25% | 27.93% |
| 29 | 36.45% | 31.59% | 31.95% |
| 30 | 39.53% | 27.46% | 33.01% |

## Final moderator synthesis and blinded quality

Pooled final-answer citation share was 38.27% front, 31.31% middle and 30.42% rear. Front minus middle was +6.96 percentage points, positive in all four cases (exact two-sided sign-flip p = 0.125). Rear minus middle was -0.88 points and positive in only one case. The mean final pooled unique-paper bounds were front 7.47–7.64, middle 6.14–6.42 and rear 5.83–6.08 per output; the bounds acknowledge unresolved A/B paper identity for bare citations.

The already-completed blind Claude Pass 1 scored only the final moderator answer. Mean IHQ without CPI for orderings XYZ/YZX/ZXY was 8.92/8.42/8.17 out of 15; full IHQ was 11.83/11.58/11.08 out of 20. Order-specific quality directions varied by case, so these secondary scores do not establish a consistent quality penalty for any evidence position. Ordering means are not themselves fixed-block position effects.

## Interpretation and limits

The tested subset shows a **front-position citation-frequency advantage**. It does **not** establish the stronger U-shaped claim that middle evidence is consistently used less than both front and rear evidence: rear and middle were close, and unique-paper/coverage outcomes were heterogeneous. With only four independent scientific cases, exact two-sided tests cannot reach p < 0.05 when all four differences have the same sign; a nonsignificant result is not evidence of equivalence. Citation use is also a proxy for evidence utilization, not an audit of whether each cited abstract substantively supports the claim. The grouped-citation correction was a transparent post-generation technical repair, not part of the original frozen analysis implementation.

Suggested reviewer-facing wording:

> In a four-case cyclic position-control analysis, fixed evidence blocks were rotated through the front, middle, and rear of the debate context while their content and the generation settings were held constant. Debate-stage citation share was higher for front-position blocks (39.35%) than for middle-position blocks (29.19%), with a positive front-minus-middle difference in all four cases. Rear-position share (31.46%) was only modestly above middle-position share, and unique-paper coverage did not show a consistent directional difference. We therefore interpret these findings as a limited front-position citation bias rather than definitive evidence of a generalized lost-in-the-middle effect or a demonstrated deterioration in final hypothesis quality. Because only four independent cases were tested, the analysis is descriptive and exploratory.
