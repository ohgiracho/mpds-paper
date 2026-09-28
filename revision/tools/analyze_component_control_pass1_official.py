from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


METRICS = (
    "full_ihq",
    "ihq_without_cpi",
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
    "validity_composite_descriptive",
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
)
CONTRASTS = (
    ("primary", "ds_minus_sair", "ds", "sair"),
    ("primary", "ds_minus_ses", "ds", "ses"),
    ("secondary", "mpds_minus_ds", "mpds", "ds"),
    ("secondary", "mpds_minus_sair", "mpds", "sair"),
    ("secondary", "mpds_minus_ses", "mpds", "ses"),
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
    means = values[indices].mean(axis=1)
    return tuple(float(value) for value in np.quantile(means, [0.025, 0.975]))


def exact_sign_flip_p(differences: np.ndarray) -> float:
    observed = abs(float(differences.mean()))
    total = 1 << len(differences)
    count = 0
    for mask in range(total):
        signs = np.array([1.0 if mask & (1 << index) else -1.0 for index in range(len(differences))])
        if abs(float((differences * signs).mean())) >= observed - 1e-12:
            count += 1
    return count / total


def rank_biserial(differences: np.ndarray) -> float:
    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / (positive + negative)


def length_adjusted_intercept(score_difference: np.ndarray, length_difference: np.ndarray) -> dict[str, float | None]:
    x = length_difference / 1000.0
    if np.allclose(x, x[0]):
        return {"equal_length_intercept": float(score_difference.mean()), "slope_per_1000_characters": None, "r_squared": None}
    design = np.column_stack([np.ones(len(x)), x])
    coefficients, _, _, _ = np.linalg.lstsq(design, score_difference, rcond=None)
    fitted = design @ coefficients
    total = float(((score_difference - score_difference.mean()) ** 2).sum())
    residual = float(((score_difference - fitted) ** 2).sum())
    return {
        "equal_length_intercept": float(coefficients[0]),
        "slope_per_1000_characters": float(coefficients[1]),
        "r_squared": None if total == 0 else float(1 - residual / total),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Case-level analysis for four-condition component controls")
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = read_csv(args.scores.resolve())
    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing output directory: {output}")
    output.mkdir(parents=True)
    grouped: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["case_id"]), row["condition"])].append(row)

    case_means: list[dict[str, Any]] = []
    stability: list[dict[str, Any]] = []
    for (case_id, condition), subset in sorted(grouped.items()):
        if len(subset) != 3:
            raise RuntimeError(f"Expected three replicates for case {case_id}, {condition}; found {len(subset)}")
        mean_row: dict[str, Any] = {"case_id": case_id, "condition": condition, "replicates": 3}
        for metric in (*METRICS, "output_characters"):
            values = np.array([float(row[metric]) for row in subset])
            mean_row[metric] = float(values.mean())
            stability.append(
                {
                    "case_id": case_id,
                    "condition": condition,
                    "metric": metric,
                    "within_case_mean": float(values.mean()),
                    "within_case_sd": float(values.std(ddof=1)),
                    "within_case_range": float(values.max() - values.min()),
                }
            )
        case_means.append(mean_row)
    write_csv(output / "case_means_n10.csv", case_means)
    write_csv(output / "replicate_stability.csv", stability)

    lookup = {(int(row["case_id"]), row["condition"]): row for row in case_means}
    case_ids = sorted({int(row["case_id"]) for row in case_means})
    if len(case_ids) != 10:
        raise RuntimeError(f"Expected 10 cases, found {len(case_ids)}")
    for _, _, left, right in CONTRASTS:
        for case_id in case_ids:
            if (case_id, left) not in lookup or (case_id, right) not in lookup:
                raise RuntimeError(f"Incomplete pair for case {case_id}: {left}, {right}")

    rng = np.random.default_rng(20260920)
    pairwise: list[dict[str, Any]] = []
    length_rows: list[dict[str, Any]] = []
    for metric in METRICS:
        pending: list[dict[str, Any]] = []
        raw_p_values: list[float] = []
        for tier, label, left, right in CONTRASTS:
            left_values = np.array([float(lookup[(case_id, left)][metric]) for case_id in case_ids])
            right_values = np.array([float(lookup[(case_id, right)][metric]) for case_id in case_ids])
            differences = left_values - right_values
            if np.allclose(differences, 0):
                statistic, p_value = 0.0, 1.0
            else:
                test = stats.wilcoxon(differences, zero_method="pratt", alternative="two-sided", method="auto")
                statistic, p_value = float(test.statistic), float(test.pvalue)
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
                    "left_mean": float(left_values.mean()),
                    "right_mean": float(right_values.mean()),
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
            length_differences = np.array(
                [
                    float(lookup[(case_id, left)]["output_characters"])
                    - float(lookup[(case_id, right)]["output_characters"])
                    for case_id in case_ids
                ]
            )
            length_rows.append(
                {
                    "metric": metric,
                    "comparison": label,
                    "analysis_unit": "case mean across three replicates",
                    "n_cases": len(case_ids),
                    "mean_score_difference": float(differences.mean()),
                    "mean_length_difference_characters": float(length_differences.mean()),
                    "score_length_spearman_rho": float(stats.spearmanr(differences, length_differences).statistic),
                    **length_adjusted_intercept(differences, length_differences),
                }
            )
            raw_p_values.append(p_value)
        for row, adjusted in zip(pending, holm_adjust(raw_p_values), strict=True):
            row["p_value_holm_declared_comparison_family"] = adjusted
            pairwise.append(row)

    write_csv(output / "component_control_pairwise_case_clustered.csv", pairwise)
    write_csv(output / "output_length_sensitivity.csv", length_rows)

    stability_summary: list[dict[str, Any]] = []
    for condition in ("ds", "mpds", "sair", "ses"):
        for metric in (*METRICS, "output_characters"):
            subset = [row for row in stability if row["condition"] == condition and row["metric"] == metric]
            stability_summary.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n_cases": len(subset),
                    "mean_within_case_sd": float(np.mean([row["within_case_sd"] for row in subset])),
                    "mean_within_case_range": float(np.mean([row["within_case_range"] for row in subset])),
                }
            )
    write_csv(output / "replicate_stability_summary.csv", stability_summary)

    manifest = {
        "status": "PASS",
        "input_rows": len(rows),
        "cases": len(case_ids),
        "replicates_per_case_condition": 3,
        "conditions": ["ds", "mpds", "sair", "ses"],
        "contrasts": [label for _, label, _, _ in CONTRASTS],
        "analysis_unit": "case mean across three replicates",
        "paired_tests": "two-sided exact sign-flip and Wilcoxon signed-rank",
        "multiplicity": "Holm adjustment across the five declared contrasts within each metric",
        "confidence_interval": "case bootstrap, 20,000 draws, seed 20260920",
        "length_sensitivity": "case-level paired score difference regressed descriptively on paired mean output-character difference",
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
