from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corpus_size_common import atomic_write_json, sha256_file
from run_q4_system_integration_batch import case_material, output_dir, run_id
from validate_q4_setup import DEFAULT_CONFIG, REVISION_ROOT, WORKSPACE_ROOT, load_config


def read_api_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if item.get("event") == "generate_content":
            rows.append(item)
    return rows


def usage_totals(records: list[dict[str, Any]]) -> Counter[str]:
    totals: Counter[str] = Counter()
    for entry in records:
        if entry.get("status") != "success":
            continue
        usage = entry.get("usage_metadata") or {}
        if isinstance(usage, dict):
            for key, value in usage.items():
                if isinstance(value, int) and "token" in key.lower():
                    totals[key] += value
    return totals


def main() -> int:
    config = load_config(DEFAULT_CONFIG)
    run_root = REVISION_ROOT / config["output"]["run_set"]
    rows: list[dict[str, Any]] = []
    problems: list[str] = []
    total_codes: Counter[str] = Counter()
    for item in config["design"]["execution_order"]:
        identifier = run_id(item)
        folder = output_dir(run_root, item)
        manifest_path = folder / "run_manifest.json"
        archived = sorted(folder.parent.glob(folder.name + "_failed_attempt_*"))
        archived_api = [entry for attempt in archived for entry in read_api_records(attempt / "api_calls.jsonl")]
        archived_successful = [entry for entry in archived_api if entry.get("status") == "success"]
        archived_failed = [entry for entry in archived_api if entry.get("status") == "error"]
        archived_usage = usage_totals(archived_api)
        for entry in archived_failed:
            total_codes[str(entry.get("error_code") or entry.get("error_type") or "unknown")] += 1
        if not manifest_path.is_file():
            rows.append({"run_id": identifier, "status": "PENDING", "archived_failed_attempts": len(archived)})
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        api = read_api_records(folder / "api_calls.jsonl")
        successful = [entry for entry in api if entry.get("status") == "success"]
        failed = [entry for entry in api if entry.get("status") == "error"]
        for entry in failed:
            total_codes[str(entry.get("error_code") or entry.get("error_type") or "unknown")] += 1
        token_totals = usage_totals(api)
        if manifest.get("status") == "COMPLETE":
            if manifest.get("model") != config["generation"]["model"]:
                problems.append(f"{identifier}: model mismatch")
            if float(manifest.get("temperature", -1)) != float(config["generation"]["temperature"]):
                problems.append(f"{identifier}: temperature mismatch")
            if manifest.get("config_id") != config["config_id"]:
                problems.append(f"{identifier}: config mismatch")
            if manifest.get("config_sha256") != sha256_file(DEFAULT_CONFIG):
                problems.append(f"{identifier}: frozen config hash mismatch")
            material = case_material(config, item)
            for field, path in (
                ("situation_sha256", material["situation"]),
                ("user_context_sha256", material["context"]),
                ("knowledge_a_sha256", material["knowledge_a"]),
                ("knowledge_b_sha256", material["knowledge_b"]),
            ):
                if manifest.get(field) != sha256_file(path):
                    problems.append(f"{identifier}: {field} mismatch")
            source = WORKSPACE_ROOT / config["implementation"]["source_script_from_workspace"]
            runtime = REVISION_ROOT / config["implementation"]["runtime_instrumentation"]
            if manifest.get("source_script_sha256") != sha256_file(source):
                problems.append(f"{identifier}: source script hash mismatch")
            if manifest.get("runtime_instrumentation_sha256") != sha256_file(runtime):
                problems.append(f"{identifier}: runtime instrumentation hash mismatch")
            if any(entry.get("model") != config["generation"]["model"] for entry in api):
                problems.append(f"{identifier}: API model mismatch")
            final_path = folder / "final.txt"
            if not final_path.is_file() or not final_path.read_text(encoding="utf-8").strip():
                problems.append(f"{identifier}: final answer missing")
            elif sha256_file(final_path) != manifest.get("final_sha256"):
                problems.append(f"{identifier}: final hash mismatch")
            if manifest.get("citation_validation") != "passed_by_unchanged_mpds_source":
                problems.append(f"{identifier}: citation validation missing")
            if len(successful) < 9:
                problems.append(f"{identifier}: fewer than nine successful generation calls")
            if token_totals.get("prompt_token_count", 0) <= 0 or token_totals.get("candidates_token_count", 0) <= 0:
                problems.append(f"{identifier}: missing input/output token usage")
        rows.append(
            {
                "run_id": identifier,
                "kind": item["kind"],
                "case_id": item["case_id"],
                "replicate_id": item["replicate_id"],
                "status": manifest.get("status", "UNKNOWN"),
                "successful_calls": len(successful),
                "failed_calls": len(failed),
                "archived_failed_attempts": len(archived),
                "archived_successful_calls": len(archived_successful),
                "archived_failed_calls": len(archived_failed),
                "validation_regeneration_calls": max(0, len(successful) - 9),
                "input_tokens": token_totals.get("prompt_token_count", 0),
                "output_tokens": token_totals.get("candidates_token_count", 0),
                "thinking_tokens": token_totals.get("thoughts_token_count", 0),
                "archived_input_tokens": archived_usage.get("prompt_token_count", 0),
                "archived_output_tokens": archived_usage.get("candidates_token_count", 0),
                "runtime_seconds": manifest.get("wall_clock_seconds", 0),
                "final_characters": manifest.get("final_characters", 0),
                "final_sha256": manifest.get("final_sha256", ""),
            }
        )
    analysis_dir = REVISION_ROOT / "analysis"
    csv_path = analysis_dir / "q4_generation_audit_v1.csv"
    fields = [
        "run_id", "kind", "case_id", "replicate_id", "status", "successful_calls", "failed_calls",
        "archived_failed_attempts", "archived_successful_calls", "archived_failed_calls",
        "validation_regeneration_calls", "input_tokens", "output_tokens", "thinking_tokens",
        "archived_input_tokens", "archived_output_tokens",
        "runtime_seconds", "final_characters", "final_sha256",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    completed = [row for row in rows if row["status"] == "COMPLETE"]
    by_kind: dict[str, dict[str, int | float]] = defaultdict(lambda: {
        "complete": 0, "calls": 0, "failed_calls": 0, "archived_failed_attempts": 0,
        "input_tokens": 0, "output_tokens": 0, "runtime_seconds": 0.0,
    })
    for row in completed:
        group = by_kind[str(row["kind"])]
        group["complete"] += 1
        group["calls"] += int(row["successful_calls"]) + int(row["archived_successful_calls"])
        group["failed_calls"] += int(row["failed_calls"]) + int(row["archived_failed_calls"])
        group["archived_failed_attempts"] += int(row["archived_failed_attempts"])
        group["input_tokens"] += int(row["input_tokens"]) + int(row["archived_input_tokens"])
        group["output_tokens"] += int(row["output_tokens"]) + int(row["archived_output_tokens"])
        group["runtime_seconds"] += float(row["runtime_seconds"])
    summary = {
        "updated_utc": datetime.now(timezone.utc).isoformat(),
        "config_id": config["config_id"],
        "expected": len(rows),
        "complete": len(completed),
        "status": "PASS_COMPLETE" if len(completed) == 11 and not problems else "IN_PROGRESS_OR_REVIEW",
        "problems": problems,
        "api_error_codes": dict(total_codes),
        "by_kind": dict(by_kind),
        "audit_csv": str(csv_path),
    }
    json_path = analysis_dir / "q4_generation_audit_v1.json"
    atomic_write_json(json_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
