from __future__ import annotations

import argparse
import csv
import itertools
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


CONDITIONS = ("ds", "mpds", "sair", "ses")
CONTRASTS = (
    ("primary", "ds_minus_sair", "ds", "sair"),
    ("primary", "ds_minus_ses", "ds", "ses"),
    ("secondary", "mpds_minus_ds", "mpds", "ds"),
    ("secondary", "mpds_minus_sair", "mpds", "sair"),
    ("secondary", "mpds_minus_ses", "mpds", "ses"),
)
SCORE_METRICS = ("evidence_support", "citation_traceability")
CLAIM_METRICS = (
    "strict_supported_rate",
    "supported_or_partial_rate",
    "unsupported_or_contradicted_rate",
    "unverifiable_rate",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def holm_adjust(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, (total - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator, draws: int = 20_000) -> tuple[float, float]:
    indices = rng.integers(0, len(values), size=(draws, len(values)))
    estimates = values[indices].mean(axis=1)
    return tuple(float(value) for value in np.quantile(estimates, [0.025, 0.975]))


def exact_sign_flip_p(values: np.ndarray) -> float:
    observed = abs(float(values.mean()))
    exceed = 0
    total = 0
    for signs in itertools.product((-1, 1), repeat=len(values)):
        statistic = abs(float(np.mean(values * np.array(signs))))
        exceed += statistic >= observed - 1e-12
        total += 1
    return exceed / total


def rank_biserial(values: np.ndarray) -> float:
    nonzero = values[values != 0]
    if len(nonzero) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / (positive + negative)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze four-condition official Pass 2 results")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    results = args.results_dir.resolve()
    scores = read_csv(results / "pass2_scores_unblinded.csv")
    claims = read_csv(results / "pass2_claims_unblinded.csv")
    if len(scores) != 120:
        raise RuntimeError(f"Expected 120 candidate rows, found {len(scores)}")

    candidate_claims: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in claims:
        candidate_claims[(row["packet_id"], row["alias"])].append(row)

    analysis_rows: list[dict[str, Any]] = []
    for row in scores:
        group = candidate_claims[(row["packet_id"], row["alias"])]
        counts = Counter(claim["support_status"] for claim in group)
        total = len(group)
        if total == 0:
            raise RuntimeError(f"No claims for {row['packet_id']} {row['alias']}")
        analysis_rows.append(
            {
                "case_id": int(row["case_id"]),
                "replicate_id": int(row["replicate_id"]),
                "condition": row["condition"],
                "evidence_support": float(row["evidence_support"]),
                "citation_traceability": float(row["citation_traceability"]),
                "strict_supported_rate": counts["supported"] / total,
                "supported_or_partial_rate": (
                    counts["supported"] + counts["partially_supported"]
                )
                / total,
                "unsupported_or_contradicted_rate": (
                    counts["unsupported"] + counts["contradicted"]
                )
                / total,
                "unverifiable_rate": counts["unverifiable"] / total,
            }
        )

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in analysis_rows:
        grouped[(row["case_id"], row["condition"])].append(row)
    case_ids = sorted({row["case_id"] for row in analysis_rows})
    if len(case_ids) != 10:
        raise RuntimeError(f"Expected 10 cases, found {len(case_ids)}")

    metrics = SCORE_METRICS + CLAIM_METRICS
    case_means: list[dict[str, Any]] = []
    for case_id in case_ids:
        for condition in CONDITIONS:
            subset = grouped[(case_id, condition)]
            if len(subset) != 3:
                raise RuntimeError(
                    f"Expected 3 replicates for case {case_id}, {condition}; found {len(subset)}"
                )
            case_means.append(
                {
                    "case_id": case_id,
                    "condition": condition,
                    "replicates": 3,
                    **{
                        metric: statistics.mean(float(row[metric]) for row in subset)
                        for metric in metrics
                    },
                }
            )
    write_csv(results / "case_means_n10.csv", case_means)
    lookup = {(row["case_id"], row["condition"]): row for row in case_means}

    paired_difference_rows: list[dict[str, Any]] = []
    for metric in metrics:
        for tier, label, left, right in CONTRASTS:
            for case_id in case_ids:
                left_mean = float(lookup[(case_id, left)][metric])
                right_mean = float(lookup[(case_id, right)][metric])
                paired_difference_rows.append(
                    {
                        "metric": metric,
                        "contrast_tier": tier,
                        "comparison": label,
                        "case_id": case_id,
                        "replicates_per_condition": 3,
                        "left_condition": left,
                        "right_condition": right,
                        "left_case_mean": left_mean,
                        "right_case_mean": right_mean,
                        "left_minus_right": left_mean - right_mean,
                    }
                )
    write_csv(results / "case_level_paired_differences.csv", paired_difference_rows)

    rng = np.random.default_rng(args.seed)
    comparison_rows: list[dict[str, Any]] = []
    for metric in metrics:
        pending: list[dict[str, Any]] = []
        p_values: list[float] = []
        for tier, label, left, right in CONTRASTS:
            differences = np.array(
                [
                    float(lookup[(case_id, left)][metric])
                    - float(lookup[(case_id, right)][metric])
                    for case_id in case_ids
                ]
            )
            if np.allclose(differences, 0):
                statistic, p_value = 0.0, 1.0
            else:
                result = stats.wilcoxon(
                    differences, zero_method="pratt", alternative="two-sided", method="auto"
                )
                statistic, p_value = float(result.statistic), float(result.pvalue)
            low, high = bootstrap_ci(differences, rng)
            pending.append(
                {
                    "metric": metric,
                    "contrast_tier": tier,
                    "comparison": label,
                    "left_condition": left,
                    "right_condition": right,
                    "analysis_unit": "case mean across three replicates",
                    "n_cases": len(case_ids),
                    "left_mean": statistics.mean(float(lookup[(case_id, left)][metric]) for case_id in case_ids),
                    "right_mean": statistics.mean(float(lookup[(case_id, right)][metric]) for case_id in case_ids),
                    "mean_difference": float(differences.mean()),
                    "bootstrap_95ci_low": low,
                    "bootstrap_95ci_high": high,
                    "wins": int((differences > 0).sum()),
                    "ties": int((differences == 0).sum()),
                    "losses": int((differences < 0).sum()),
                    "wilcoxon_statistic": statistic,
                    "p_value_raw": p_value,
                    "sign_flip_p_exact": exact_sign_flip_p(differences),
                    "rank_biserial": rank_biserial(differences),
                }
            )
            p_values.append(p_value)
        for row, adjusted in zip(pending, holm_adjust(p_values), strict=True):
            row["p_value_holm_declared_comparison_family"] = adjusted
            comparison_rows.append(row)
    write_csv(results / "component_control_pairwise_case_clustered.csv", comparison_rows)

    manifest = {
        "status": "PASS",
        "input_candidate_rows": len(scores),
        "input_claim_rows": len(claims),
        "cases": len(case_ids),
        "replicates_per_case_condition": 3,
        "conditions": list(CONDITIONS),
        "metrics": list(metrics),
        "contrasts": [label for _, label, _, _ in CONTRASTS],
        "analysis_unit": "case mean across three replicates",
        "paired_tests": "two-sided exact sign-flip and Wilcoxon signed-rank",
        "multiplicity": "Holm adjustment across five declared contrasts within each metric",
        "confidence_interval": f"case bootstrap, 20,000 draws, seed {args.seed}",
        "pseudoreplication_control": (
            "Three stochastic generation replicates were averaged within each scientific case; "
            "all inferential comparisons use the resulting 10 paired case-level differences."
        ),
        "claim_level_role": (
            "Pooled claim counts and percentages are descriptive only; claim-rate inference uses "
            "candidate proportions averaged across replicates within case."
        ),
    }
    (results / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
