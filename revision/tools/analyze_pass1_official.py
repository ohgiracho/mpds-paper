from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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


def bootstrap_ci(values: np.ndarray, rng: np.random.Generator, draws: int = 20000) -> tuple[float, float]:
    indices = rng.integers(0, len(values), size=(draws, len(values)))
    means = values[indices].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def rank_biserial(differences: np.ndarray) -> float:
    nonzero = differences[differences != 0]
    if len(nonzero) == 0:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(ranks[nonzero > 0].sum())
    negative = float(ranks[nonzero < 0].sum())
    return (positive - negative) / (positive + negative)


def exact_sign_flip_p(differences: np.ndarray) -> float:
    observed = abs(float(differences.mean()))
    count = 0
    total = 1 << len(differences)
    for mask in range(total):
        signs = np.array([1.0 if mask & (1 << index) else -1.0 for index in range(len(differences))])
        if abs(float((differences * signs).mean())) >= observed - 1e-12:
            count += 1
    return count / total


def main() -> int:
    parser = argparse.ArgumentParser(description="Case-clustered analysis of official Pass 1 scores")
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows = read_csv(args.scores.resolve())
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260914)

    grouped: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["case_id"]), row["condition"])].append(row)

    case_mean_rows: list[dict[str, Any]] = []
    stability_rows: list[dict[str, Any]] = []
    for (case_id, condition), subset in sorted(grouped.items()):
        if len(subset) != 3:
            raise RuntimeError(f"Expected three replicates for case {case_id}, {condition}; found {len(subset)}")
        mean_row: dict[str, Any] = {"case_id": case_id, "condition": condition, "replicates": len(subset)}
        for metric in METRICS:
            values = np.array([float(row[metric]) for row in subset])
            mean_row[metric] = float(values.mean())
            stability_rows.append(
                {
                    "case_id": case_id,
                    "condition": condition,
                    "metric": metric,
                    "within_case_mean": float(values.mean()),
                    "within_case_sd": float(values.std(ddof=1)),
                    "within_case_range": float(values.max() - values.min()),
                }
            )
        case_mean_rows.append(mean_row)
    write_csv(output / "case_means_n10.csv", case_mean_rows)
    write_csv(output / "replicate_stability.csv", stability_rows)

    descriptive_rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in rows if row["condition"] == condition]
        for metric in METRICS:
            values = np.array([float(row[metric]) for row in subset])
            descriptive_rows.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n_outputs": len(values),
                    "mean": float(values.mean()),
                    "sd": float(values.std(ddof=1)),
                    "median": float(np.median(values)),
                    "q1": float(np.quantile(values, 0.25)),
                    "q3": float(np.quantile(values, 0.75)),
                    "min": float(values.min()),
                    "max": float(values.max()),
                }
            )
    write_csv(output / "condition_descriptive.csv", descriptive_rows)

    lookup = {(int(row["case_id"]), row["condition"]): row for row in case_mean_rows}
    case_ids = sorted({int(row["case_id"]) for row in case_mean_rows})
    if len(case_ids) != 10:
        raise RuntimeError(f"Expected ten cases; found {len(case_ids)}")

    omnibus_rows: list[dict[str, Any]] = []
    pairwise_rows: list[dict[str, Any]] = []
    for metric in METRICS:
        arrays = {
            condition: np.array([float(lookup[(case_id, condition)][metric]) for case_id in case_ids])
            for condition in CONDITIONS
        }
        friedman = stats.friedmanchisquare(*(arrays[condition] for condition in CONDITIONS))
        omnibus_rows.append(
            {
                "metric": metric,
                "analysis_unit": "case mean across three replicates",
                "n_cases": len(case_ids),
                "friedman_chi_square": float(friedman.statistic),
                "df": len(CONDITIONS) - 1,
                "p_value": float(friedman.pvalue),
                "kendalls_w": float(friedman.statistic / (len(case_ids) * (len(CONDITIONS) - 1))),
            }
        )
        metric_rows: list[dict[str, Any]] = []
        raw_p: list[float] = []
        for comparator in CONDITIONS[:-1]:
            differences = arrays["mpds"] - arrays[comparator]
            if np.allclose(differences, 0):
                statistic, p_value = 0.0, 1.0
            else:
                test = stats.wilcoxon(differences, zero_method="pratt", alternative="two-sided", method="auto")
                statistic, p_value = float(test.statistic), float(test.pvalue)
            low, high = bootstrap_ci(differences, rng)
            row = {
                "metric": metric,
                "comparison": f"mpds - {comparator}",
                "analysis_unit": "case mean across three replicates",
                "n_cases": len(case_ids),
                "mpds_mean": float(arrays["mpds"].mean()),
                "comparator_mean": float(arrays[comparator].mean()),
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
            metric_rows.append(row)
            raw_p.append(p_value)
        adjusted = holm_adjust(raw_p)
        for row, p_adjusted in zip(metric_rows, adjusted):
            row["p_value_holm_within_metric"] = p_adjusted
            pairwise_rows.append(row)

    write_csv(output / "friedman_tests.csv", omnibus_rows)
    write_csv(output / "mpds_pairwise_case_clustered.csv", pairwise_rows)

    stability_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        for metric in METRICS:
            subset = [row for row in stability_rows if row["condition"] == condition and row["metric"] == metric]
            stability_summary.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n_cases": len(subset),
                    "mean_within_case_sd": float(np.mean([row["within_case_sd"] for row in subset])),
                    "median_within_case_sd": float(np.median([row["within_case_sd"] for row in subset])),
                    "mean_within_case_range": float(np.mean([row["within_case_range"] for row in subset])),
                }
            )
    write_csv(output / "replicate_stability_summary.csv", stability_summary)

    summary = {
        "status": "PASS",
        "input_rows": len(rows),
        "cases": len(case_ids),
        "replicates_per_case_condition": 3,
        "conditions": list(CONDITIONS),
        "primary_analysis_unit": "case mean across three replicates",
        "omnibus_test": "Friedman",
        "pairwise_test": "two-sided Wilcoxon signed-rank, Holm adjusted within metric",
        "confidence_interval": "case bootstrap, 20,000 draws, seed 20260914",
    }
    (output / "analysis_manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
