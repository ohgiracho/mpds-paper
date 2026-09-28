from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats


SYSTEMS = ("raw", "eo", "eop", "ds", "mpds")


def descriptive(values: np.ndarray) -> dict[str, float]:
    return {
        "n": int(values.size),
        "mean": round(float(np.mean(values)), 4),
        "sd": round(float(np.std(values, ddof=1)), 4),
        "median": round(float(np.median(values)), 4),
        "q1": round(float(np.quantile(values, 0.25)), 4),
        "q3": round(float(np.quantile(values, 0.75)), 4),
    }


def paired_permutation(diff: np.ndarray, rng: np.random.Generator, permutations: int) -> float:
    observed = abs(float(np.mean(diff)))
    batch = 10_000
    extreme = 0
    done = 0
    while done < permutations:
        size = min(batch, permutations - done)
        signs = rng.choice((-1.0, 1.0), size=(size, diff.size))
        permuted = np.abs(np.mean(signs * diff, axis=1))
        extreme += int(np.sum(permuted >= observed))
        done += size
    return (extreme + 1) / (permutations + 1)


def bootstrap_ci(diff: np.ndarray, rng: np.random.Generator, draws: int) -> list[float]:
    indices = rng.integers(0, diff.size, size=(draws, diff.size))
    means = np.mean(diff[indices], axis=1)
    return [round(float(value), 4) for value in np.quantile(means, (0.025, 0.975))]


def rank_biserial(diff: np.ndarray) -> float:
    nonzero = diff[diff != 0]
    if not nonzero.size:
        return 0.0
    ranks = stats.rankdata(np.abs(nonzero))
    positive = float(np.sum(ranks[nonzero > 0]))
    negative = float(np.sum(ranks[nonzero < 0]))
    return (positive - negative) / (positive + negative)


def holm(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        value = min(1.0, (count - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted.tolist()


def analyze(score_map: dict[str, np.ndarray], rng: np.random.Generator, permutations: int, bootstraps: int) -> dict[str, Any]:
    comparisons = []
    raw_p = []
    for comparator in ("raw", "eo", "eop", "ds"):
        diff = score_map["mpds"] - score_map[comparator]
        try:
            wilcoxon_p = float(stats.wilcoxon(diff, zero_method="wilcox", alternative="two-sided").pvalue)
        except ValueError:
            wilcoxon_p = 1.0
        raw_p.append(wilcoxon_p)
        comparisons.append(
            {
                "comparison": f"mpds_vs_{comparator}",
                "mean_paired_difference": round(float(np.mean(diff)), 4),
                "bootstrap_95ci_mean_difference": bootstrap_ci(diff, rng, bootstraps),
                "wilcoxon_p_raw": wilcoxon_p,
                "permutation_p_two_sided": paired_permutation(diff, rng, permutations),
                "rank_biserial": round(rank_biserial(diff), 4),
                "cohen_dz": round(float(np.mean(diff) / np.std(diff, ddof=1)), 4) if np.std(diff, ddof=1) else 0.0,
                "wins_ties_losses": {
                    "wins": int(np.sum(diff > 0)),
                    "ties": int(np.sum(diff == 0)),
                    "losses": int(np.sum(diff < 0)),
                },
            }
        )
    for row, adjusted in zip(comparisons, holm(raw_p)):
        row["wilcoxon_p_holm"] = adjusted
    return {
        "descriptive": {system: descriptive(values) for system, values in score_map.items()},
        "paired_comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    default_scores = root.parent / "코드" / "논문실험_코드정리_20260409" / "04_채점결과" / "04_EOP_추가_5system" / "ihq_Universal IHQ Scoring Rules_EOP_added_case1_재7실험_20260408" / "scores.json"
    parser.add_argument("--scores", type=Path, default=default_scores)
    parser.add_argument("--output-dir", type=Path, default=root / "analysis")
    parser.add_argument("--permutations", type=int, default=200_000)
    parser.add_argument("--bootstraps", type=int, default=50_000)
    args = parser.parse_args()

    payload = json.loads(args.scores.read_text(encoding="utf-8"))
    case_rows = []
    full = {system: [] for system in SYSTEMS}
    no_cpi = {system: [] for system in SYSTEMS}
    for case in payload["scored_cases"]:
        for system in SYSTEMS:
            score = case["system_scores"][system]
            full_score = int(score["total"])
            reduced = full_score - int(score["cross_perspective_integration"])
            full[system].append(full_score)
            no_cpi[system].append(reduced)
            case_rows.append(
                {
                    "case_id": case["case"],
                    "case_folder": case["folder"],
                    "system": system,
                    "idea_novelty": score["idea_novelty"],
                    "mechanistic_originality": score["mechanistic_originality"],
                    "tradeoff_reframing": score["tradeoff_reframing"],
                    "cross_perspective_integration": score["cross_perspective_integration"],
                    "full_ihq": full_score,
                    "ihq_without_cpi": reduced,
                }
            )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "existing_ihq_case_scores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(case_rows[0]))
        writer.writeheader()
        writer.writerows(case_rows)

    result = {
        "source": str(args.scores.resolve()),
        "warning": "Exploratory legacy analysis only: the same model family generated and judged candidates, and n=1 per case-condition.",
        "full_ihq": analyze({key: np.asarray(value, dtype=float) for key, value in full.items()}, np.random.default_rng(7346298), args.permutations, args.bootstraps),
        "ihq_without_cpi": analyze({key: np.asarray(value, dtype=float) for key, value in no_cpi.items()}, np.random.default_rng(7346299), args.permutations, args.bootstraps),
    }
    (args.output_dir / "existing_ihq_statistics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
