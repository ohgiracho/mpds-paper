from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCORE_FIELDS = [
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
]
COMPOSITE_FIELDS = ["ihq_without_cpi", "full_ihq", "validity_composite_descriptive"]
FLAG_FIELDS = [
    "scientifically_consequential_error",
    "temporal_cutoff_violation",
    "fixed_task_constraint_violation",
    "infeasible_primary_process",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values: list[float]) -> float:
    return statistics.fmean(values)


def describe(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": round(mean(values), 4),
        "sd": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
        "median": round(statistics.median(values), 4),
        "min": min(values),
        "max": max(values),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"No rows for {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_unblinded_rows(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    packet_dir = root / "evaluation" / "blind_packets_corpus_size_sensitivity_v1"
    judge_dir = root / "judge_runs_sonnet5_20260921" / "pass1_corpus_size_official_anthropic_v1"
    stage_dir = root / "evaluation" / "corpus_size_pass1_accepted_scores_staging_v1"

    with (packet_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        key_rows = list(csv.DictReader(handle))
    key = {(row["packet_id"], row["alias"]): row for row in key_rows}
    if len(key) != 48:
        raise RuntimeError(f"Expected 48 blind-key rows, found {len(key)}")

    rows: list[dict[str, Any]] = []
    staging_hash_matches = 0
    for packet_path in sorted(judge_dir.glob("case_*__rep_*")):
        accepted_path = packet_path / "accepted_scores.json"
        manifest_path = packet_path / "run_manifest.json"
        if not accepted_path.exists() or not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            raise RuntimeError(f"Non-COMPLETE judge packet: {packet_path.name}")
        data = json.loads(accepted_path.read_text(encoding="utf-8"))
        if data.get("packet_id") != packet_path.name:
            raise RuntimeError(f"Packet ID mismatch: {packet_path.name}")
        staged = stage_dir / f"{packet_path.name}.json"
        if staged.exists() and sha256(staged) == sha256(accepted_path):
            staging_hash_matches += 1
        for item in data["candidate_scores"]:
            alias = item["alias"]
            blind = key[(packet_path.name, alias)]
            full_ihq = sum(item[field] for field in SCORE_FIELDS[:4])
            ihq_without_cpi = sum(item[field] for field in SCORE_FIELDS[:3])
            validity = sum(item[field] for field in SCORE_FIELDS[4:])
            row: dict[str, Any] = {
                "packet_id": packet_path.name,
                "case_id": int(blind["case_id"]),
                "replicate_id": int(blind["replicate_id"]),
                "alias": alias,
                "corpus_size": int(blind["corpus_size"]),
                **{field: int(item[field]) for field in SCORE_FIELDS},
                "ihq_without_cpi": ihq_without_cpi,
                "full_ihq": full_ihq,
                "validity_composite_descriptive": validity,
                **{f"flag_{field}": item["flags"][field] for field in FLAG_FIELDS},
                "ihq_rationale": item["ihq_rationale"],
                "validity_rationale": item["validity_rationale"],
                "uncertainty_notes": item["uncertainty_notes"],
                "source_file_sha256": blind["source_file_sha256"],
                "candidate_body_sha256": blind["candidate_body_sha256"],
            }
            rows.append(row)
    if len(rows) != 48:
        raise RuntimeError(f"Expected 48 unblinded rows, found {len(rows)}")
    return rows, {"accepted_score_staging_hash_matches": staging_hash_matches}


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    freeze_path = root / "evaluation" / "corpus_size_pass1_input_integrity_manifest_v1.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    records = freeze["fixed_files"] + freeze["generation_sources"] + freeze["packets"]
    mismatches: list[str] = []
    for record in records:
        path = (root / record["path"]).resolve()
        if not path.exists() or sha256(path) != record["sha256"]:
            mismatches.append(record["path"])
    return {
        "precall_freeze_status": freeze["status"],
        "files_checked_after_scoring": len(records),
        "hash_mismatches_after_scoring": len(mismatches),
        "mismatched_paths": mismatches,
    }


def score_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = SCORE_FIELDS + COMPOSITE_FIELDS
    by_size: dict[str, Any] = {}
    for corpus_size in (100, 250, 500, 1000):
        subset = [row for row in rows if row["corpus_size"] == corpus_size]
        flag_counts = {
            field: dict(Counter(row[f"flag_{field}"] for row in subset)) for field in FLAG_FIELDS
        }
        by_size[str(corpus_size)] = {
            "n": len(subset),
            "metrics": {
                metric: describe([float(row[metric]) for row in subset]) for metric in metrics
            },
            "flags": flag_counts,
        }

    paired: dict[str, Any] = {}
    reference = {
        (row["case_id"], row["replicate_id"]): row for row in rows if row["corpus_size"] == 500
    }
    for corpus_size in (100, 250, 1000):
        subset = [row for row in rows if row["corpus_size"] == corpus_size]
        paired[str(corpus_size)] = {
            metric: describe(
                [
                    float(row[metric])
                    - float(reference[(row["case_id"], row["replicate_id"])][metric])
                    for row in subset
                ]
            )
            for metric in COMPOSITE_FIELDS
        }

    case_rows: list[dict[str, Any]] = []
    for case_id in (2, 4, 15, 29):
        for corpus_size in (100, 250, 500, 1000):
            subset = [
                row
                for row in rows
                if row["case_id"] == case_id and row["corpus_size"] == corpus_size
            ]
            case_rows.append(
                {
                    "case_id": case_id,
                    "corpus_size": corpus_size,
                    "n": len(subset),
                    **{
                        f"mean_{metric}": round(mean([float(row[metric]) for row in subset]), 4)
                        for metric in COMPOSITE_FIELDS
                    },
                }
            )
    return {"by_corpus_size": by_size, "paired_delta_vs_500": paired, "case_means": case_rows}


def generation_usage(root: Path) -> dict[str, Any]:
    runs = root / "runs_corpus_size_sensitivity_v1"
    aggregate: dict[int, dict[str, float | int]] = defaultdict(
        lambda: {
            "complete_outputs": 0,
            "preserved_failed_run_attempts": 0,
            "attempted_api_calls": 0,
            "successful_api_calls": 0,
            "failed_api_calls": 0,
            "prompt_tokens": 0,
            "output_tokens": 0,
            "thought_tokens": 0,
            "total_tokens": 0,
            "cached_content_tokens": 0,
            "wall_clock_seconds": 0.0,
            "actual_prompt_characters": 0,
            "persona_truncated_outputs": 0,
            "complete_only_attempted_api_calls": 0,
            "complete_only_successful_api_calls": 0,
            "complete_only_failed_api_calls": 0,
            "complete_only_prompt_tokens": 0,
            "complete_only_output_tokens": 0,
            "complete_only_thought_tokens": 0,
            "complete_only_total_tokens": 0,
            "complete_only_cached_content_tokens": 0,
            "complete_only_wall_clock_seconds": 0.0,
            "complete_only_actual_prompt_characters": 0,
        }
    )
    attempt_manifests = []
    failed_run_categories: Counter[str] = Counter()
    for manifest_path in sorted(runs.glob("case_*/corpus_*/replicate_*/run_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("dry_run") is True:
            continue
        corpus_size = int(manifest.get("corpus_size_per_pool"))
        item = aggregate[corpus_size]
        if manifest.get("status") == "COMPLETE":
            item["complete_outputs"] += 1
        elif "_failed_attempt_" in manifest_path.parent.name:
            item["preserved_failed_run_attempts"] += 1
            stderr_path = manifest_path.parent / "stderr.log"
            stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
            if "failed validation" in stderr:
                failed_run_categories["final_validation"] += 1
            elif "429" in stderr or "RESOURCE_EXHAUSTED" in stderr:
                failed_run_categories["429_or_resource_exhausted"] += 1
            elif "Empty model response" in stderr:
                failed_run_categories["empty_model_response"] += 1
            elif stderr:
                failed_run_categories["other_exception"] += 1
            else:
                failed_run_categories["wrapper_or_interrupted_without_stderr"] += 1
        api = manifest.get("api_log_summary") or {}
        usage = api.get("usage_metadata_sums") or {}
        item["attempted_api_calls"] += int(api.get("attempted_generate_content_calls") or 0)
        item["successful_api_calls"] += int(api.get("successful_calls") or 0)
        item["failed_api_calls"] += int(api.get("failed_calls") or 0)
        item["prompt_tokens"] += int(usage.get("prompt_token_count") or 0)
        item["output_tokens"] += int(usage.get("candidates_token_count") or 0)
        item["thought_tokens"] += int(usage.get("thoughts_token_count") or 0)
        item["total_tokens"] += int(usage.get("total_token_count") or 0)
        item["cached_content_tokens"] += int(usage.get("cached_content_token_count") or 0)
        item["wall_clock_seconds"] += float(manifest.get("wall_clock_seconds") or 0)
        item["actual_prompt_characters"] += int(manifest.get("actual_prompt_characters_sum") or 0)
        if manifest.get("status") == "COMPLETE":
            item["complete_only_attempted_api_calls"] += int(
                api.get("attempted_generate_content_calls") or 0
            )
            item["complete_only_successful_api_calls"] += int(api.get("successful_calls") or 0)
            item["complete_only_failed_api_calls"] += int(api.get("failed_calls") or 0)
            item["complete_only_prompt_tokens"] += int(usage.get("prompt_token_count") or 0)
            item["complete_only_output_tokens"] += int(usage.get("candidates_token_count") or 0)
            item["complete_only_thought_tokens"] += int(usage.get("thoughts_token_count") or 0)
            item["complete_only_total_tokens"] += int(usage.get("total_token_count") or 0)
            item["complete_only_cached_content_tokens"] += int(
                usage.get("cached_content_token_count") or 0
            )
            item["complete_only_wall_clock_seconds"] += float(
                manifest.get("wall_clock_seconds") or 0
            )
            item["complete_only_actual_prompt_characters"] += int(
                manifest.get("actual_prompt_characters_sum") or 0
            )
        if manifest.get("status") == "COMPLETE" and any(
            bool(pool.get("persona_truncated")) for pool in (manifest.get("corpus") or {}).values()
        ):
            item["persona_truncated_outputs"] += 1
        attempt_manifests.append(manifest_path)
    totals: dict[str, float | int] = defaultdict(int)
    for item in aggregate.values():
        for key, value in item.items():
            totals[key] += value
    return {
        "by_corpus_size": {str(size): dict(aggregate[size]) for size in sorted(aggregate)},
        "totals": dict(totals),
        "attempt_manifest_count": len(attempt_manifests),
        "preserved_failed_run_categories": dict(failed_run_categories),
        "context_note": (
            "The 70,000-character selector is applied per persona/pool, but full corpus text is also "
            "present in debate-turn prompts; actual prompt characters and tokens therefore continue "
            "to grow with corpus size. Persona truncation is not equivalent to a 70k total request cap."
        ),
    }


def judge_usage(root: Path) -> dict[str, Any]:
    judge_dir = root / "judge_runs_sonnet5_20260921" / "pass1_corpus_size_official_anthropic_v1"
    totals = Counter()
    returned_models = Counter()
    for manifest_path in sorted(judge_dir.glob("case_*__rep_*/run_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        totals["packets"] += 1
        totals[f"status_{manifest['status']}"] += 1
        returned_models[str(manifest.get("returned_model"))] += 1
        attempts = manifest.get("attempts") or []
        totals["attempts"] += len(attempts)
        for attempt in attempts:
            totals["http_200"] += int(attempt.get("http_status") == 200)
            totals["validation_error_attempts"] += int(bool(attempt.get("validation_errors")))
            totals["elapsed_seconds"] += float(attempt.get("elapsed_seconds") or 0)
            usage = attempt.get("usage") or {}
            totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            totals["cache_creation_input_tokens"] += int(
                usage.get("cache_creation_input_tokens") or 0
            )
            totals["cache_read_input_tokens"] += int(usage.get("cache_read_input_tokens") or 0)
    return {"totals": dict(totals), "returned_models": dict(returned_models)}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    rows, integrity = load_unblinded_rows(root)
    integrity.update(verify_frozen_inputs(root))
    scores = score_summaries(rows)
    generation = generation_usage(root)
    judge = judge_usage(root)

    detailed_path = root / "evaluation" / "corpus_size_pass1_unblinded_scores_v1.csv"
    case_means_path = root / "evaluation" / "corpus_size_pass1_case_means_v1.csv"
    summary_path = root / "evaluation" / "corpus_size_pass1_analysis_summary_v1.json"
    write_csv(detailed_path, rows)
    write_csv(case_means_path, scores["case_means"])

    summary = {
        "status": "PASS",
        "analysis_scope": "descriptive corpus-size sensitivity; 4 cases x 4 sizes x 3 replicates",
        "evaluator_protocol": (
            "same frozen blind Pass 1 protocol used in the previous official Anthropic evaluation; "
            "only the candidate conditions differed"
        ),
        "rows": len(rows),
        "integrity": integrity,
        "scores": scores,
        "generation_usage": generation,
        "judge_usage": judge,
        "outputs": {
            "detailed_scores": str(detailed_path),
            "case_means": str(case_means_path),
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
