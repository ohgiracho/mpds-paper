from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PRICE_PER_MTOK = {
    "input_tokens": 2.00,
    "cache_creation_input_tokens": 2.50,
    "cache_read_input_tokens": 0.20,
    "output_tokens": 10.00,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def percentile(sorted_values: list[float], probability: float) -> float:
    index = (len(sorted_values) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def bootstrap_ci(deltas: list[float], seed: int, iterations: int = 100_000) -> tuple[float, float]:
    rng = random.Random(seed)
    estimates = sorted(
        statistics.mean(rng.choice(deltas) for _ in deltas) for _ in range(iterations)
    )
    return percentile(estimates, 0.025), percentile(estimates, 0.975)


def exact_sign_flip_p(deltas: list[float]) -> float:
    observed = abs(statistics.mean(deltas))
    exceed = 0
    total = 0
    for signs in itertools.product((-1, 1), repeat=len(deltas)):
        statistic = abs(statistics.mean(sign * delta for sign, delta in zip(signs, deltas)))
        exceed += statistic >= observed - 1e-12
        total += 1
    return exceed / total


def paired_summary(
    rows: list[dict[str, Any]], metric: str, seed: int
) -> dict[str, Any]:
    grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(int(row["case_id"]), row["condition"])].append(float(row[metric]))
    deltas: list[float] = []
    cases = sorted({case_id for case_id, _ in grouped})
    for case_id in cases:
        mpds = statistics.mean(grouped[(case_id, "mpds")])
        ds = statistics.mean(grouped[(case_id, "ds")])
        deltas.append(mpds - ds)
    lower, upper = bootstrap_ci(deltas, seed)
    return {
        "metric": metric,
        "case_n": len(deltas),
        "mean_mpds_minus_ds": round(statistics.mean(deltas), 6),
        "bootstrap_95ci_low": round(lower, 6),
        "bootstrap_95ci_high": round(upper, 6),
        "exact_sign_flip_p_two_sided": round(exact_sign_flip_p(deltas), 6),
        "wins": sum(delta > 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
        "case_deltas": "|".join(f"{delta:.6f}" for delta in deltas),
    }


def usage_from_responses(paths: list[Path]) -> tuple[Counter[str], int]:
    usage: Counter[str] = Counter()
    count = 0
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        model_usage = envelope.get("usage")
        if not isinstance(model_usage, dict):
            continue
        count += 1
        for field in PRICE_PER_MTOK:
            usage[field] += int(model_usage.get(field) or 0)
    return usage, count


def cost(usage: dict[str, int]) -> float:
    return sum(usage.get(field, 0) * rate / 1_000_000 for field, rate in PRICE_PER_MTOK.items())


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze official Pass 2 results and API usage")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--extra-billable-root", type=Path, action="append", default=[])
    parser.add_argument("--error-root", type=Path, action="append", default=[])
    parser.add_argument("--seed", type=int, default=7346298)
    args = parser.parse_args()

    results = args.results_dir.resolve()
    candidates = read_csv(results / "pass2_scores_unblinded.csv")
    claims = read_csv(results / "pass2_claims_unblinded.csv")
    if len(candidates) != 150:
        raise RuntimeError(f"Expected 150 candidate rows, found {len(candidates)}")

    candidate_analysis_rows: list[dict[str, Any]] = [
        {
            "case_id": int(row["case_id"]),
            "replicate_id": int(row["replicate_id"]),
            "condition": row["condition"],
            "evidence_support": float(row["evidence_support"]),
            "citation_traceability": float(row["citation_traceability"]),
        }
        for row in candidates
    ]
    claim_groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in claims:
        claim_groups[(row["packet_id"], row["alias"])].append(row)
    candidate_lookup = {(row["packet_id"], row["alias"]): row for row in candidates}
    claim_rate_rows: list[dict[str, Any]] = []
    for key, group in claim_groups.items():
        meta = candidate_lookup[key]
        counts = Counter(row["support_status"] for row in group)
        total = len(group)
        claim_rate_rows.append(
            {
                "case_id": int(meta["case_id"]),
                "replicate_id": int(meta["replicate_id"]),
                "condition": meta["condition"],
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

    inference_rows: list[dict[str, Any]] = []
    for index, metric in enumerate(("evidence_support", "citation_traceability")):
        row = paired_summary(candidate_analysis_rows, metric, args.seed + index)
        row["analysis_unit"] = "case mean of three candidate-level replicates"
        inference_rows.append(row)
    for index, metric in enumerate(
        (
            "strict_supported_rate",
            "supported_or_partial_rate",
            "unsupported_or_contradicted_rate",
            "unverifiable_rate",
        ),
        start=10,
    ):
        row = paired_summary(claim_rate_rows, metric, args.seed + index)
        row["analysis_unit"] = "case mean of three candidate-level claim proportions"
        inference_rows.append(row)
    write_csv(results / "mpds_vs_ds_inference.csv", inference_rows)

    assembly = json.loads((results / "assembly_manifest.json").read_text(encoding="utf-8"))
    selected_usage = {field: int(assembly["selected_usage"].get(field, 0)) for field in PRICE_PER_MTOK}
    response_paths = list(args.run_root.resolve().rglob("candidate_*response.json"))
    for root in args.extra_billable_root:
        response_paths.extend(root.resolve().rglob("*response.json"))
    all_usage, successful_calls = usage_from_responses(response_paths)
    error_paths: list[Path] = []
    for root in [args.run_root, *args.extra_billable_root, *args.error_root]:
        error_paths.extend(root.resolve().rglob("*error_body.txt"))
    usage_audit = {
        "model": "claude-sonnet-5",
        "pricing_checked_date": "2026-09-15",
        "pricing_usd_per_million_tokens": PRICE_PER_MTOK,
        "selected_official_candidate_calls": 150,
        "selected_official_usage": selected_usage,
        "selected_official_estimated_cost_usd": round(cost(selected_usage), 6),
        "all_recorded_http_200_calls_including_discarded_pilots": successful_calls,
        "all_recorded_http_200_usage": dict(all_usage),
        "all_recorded_http_200_estimated_cost_usd": round(cost(all_usage), 6),
        "billable_http_200_overhead_calls": successful_calls - 150,
        "billable_http_200_overhead_estimated_cost_usd": round(
            cost(all_usage) - cost(selected_usage), 6
        ),
        "recorded_http_error_artifacts_no_usage_tokens": len({path.resolve() for path in error_paths}),
        "billing_note": "Estimate from response usage and published global standard rates; provider invoice is authoritative.",
    }
    (results / "api_usage_audit.json").write_text(
        json.dumps(usage_audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (results / "mpds_vs_ds_inference.json").write_text(
        json.dumps(inference_rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"inference": inference_rows, "usage": usage_audit}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
