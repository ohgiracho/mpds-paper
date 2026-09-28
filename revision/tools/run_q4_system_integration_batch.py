from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corpus_size_common import atomic_write_json, environment_value, sha256_file
from run_condition import api_log_summary, extract_final
from validate_q4_setup import DEFAULT_CONFIG, REVISION_ROOT, WORKSPACE_ROOT, load_config, validate_setup


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def output_dir(run_root: Path, item: dict[str, Any]) -> Path:
    kind = str(item["kind"])
    case_id = int(item["case_id"])
    replicate_id = int(item["replicate_id"])
    return run_root / f"{kind}_case_{case_id:02d}" / f"replicate_{replicate_id:02d}"


def run_id(item: dict[str, Any]) -> str:
    return f"q4_{item['kind']}_case_{int(item['case_id']):02d}__mpds__rep_{int(item['replicate_id']):02d}"


def manifest_status(run_dir: Path) -> str:
    path = run_dir / "run_manifest.json"
    if not path.is_file():
        return "PENDING"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status", "UNKNOWN"))
    except (OSError, ValueError):
        return "INVALID"


def status_payload(config: dict[str, Any], run_root: Path, active_item: str | None) -> dict[str, Any]:
    rows = []
    counts = {"COMPLETE": 0, "FAILED": 0, "RUNNING": 0, "PENDING": 0, "OTHER": 0}
    for position, item in enumerate(config["design"]["execution_order"], start=1):
        status = manifest_status(output_dir(run_root, item))
        bucket = status if status in counts else "OTHER"
        counts[bucket] += 1
        rows.append({"order": position, "run_id": run_id(item), "status": status})
    return {
        "config_id": config["config_id"],
        "updated_utc": utc_now(),
        "expected_outputs": len(rows),
        "status_counts": counts,
        "active_item": active_item,
        "schedule": rows,
    }


def redacted(text: str, environment: dict[str, str]) -> str:
    result = text
    for name in (
        "GOOGLE_CLOUD_PROJECT",
        "MPDS_REVISION_VERTEX_PROJECT",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "VERTEX_API_KEY",
    ):
        value = str(environment.get(name) or "").strip()
        if len(value) >= 8 and value != "vertex-adc-authentication":
            result = result.replace(value, f"[{name}_REDACTED]")
    result = re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[API_KEY_REDACTED]", result)
    return result


def archive_failed(run_dir: Path, attempt: int, run_root: Path) -> Path | None:
    if not run_dir.exists():
        return None
    resolved = run_dir.resolve()
    allowed = run_root.resolve()
    if allowed not in resolved.parents:
        raise RuntimeError("Failed run directory is outside the intended Q4 run root")
    if manifest_status(run_dir) == "COMPLETE":
        raise RuntimeError("Refusing to archive a COMPLETE Q4 run")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = run_dir.with_name(run_dir.name + f"_failed_attempt_{attempt:02d}_{stamp}")
    suffix = 1
    while destination.exists():
        destination = run_dir.with_name(run_dir.name + f"_failed_attempt_{attempt:02d}_{stamp}_{suffix:02d}")
        suffix += 1
    run_dir.rename(destination)
    return destination


def case_material(config: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    if item["kind"] == "breadth":
        case = config["breadth_cases"][str(item["case_id"])]
        return {
            "simulation_date": case["simulation_date"],
            "debate_topic": case["debate_topic"],
            "context": REVISION_ROOT / case["user_context"],
            "situation": REVISION_ROOT / case["situation"],
            "knowledge_a": REVISION_ROOT / case["pool_a"],
            "knowledge_b": REVISION_ROOT / case["pool_b"],
            "name_a": "Battery-system specialist (Scientist A)",
            "name_b": "Electrolyte and interphase specialist (Scientist B)",
        }
    case = config["integrated_case"]
    return {
        "simulation_date": case["simulation_date"],
        "debate_topic": case["debate_topic"],
        "context": REVISION_ROOT / case["user_context"],
        "situation": REVISION_ROOT / case["situation"],
        "knowledge_a": WORKSPACE_ROOT / case["pool_a_path_from_workspace"],
        "knowledge_b": REVISION_ROOT / case["pool_b"],
        "name_a": case["name_a"],
        "name_b": case["name_b"],
    }


def execute_one(config_path: Path, config: dict[str, Any], item: dict[str, Any], run_root: Path) -> int:
    run_dir = output_dir(run_root, item)
    existing_status = manifest_status(run_dir)
    if existing_status == "COMPLETE":
        return 0
    if run_dir.exists():
        raise RuntimeError(f"Existing non-COMPLETE Q4 run requires review: {run_dir}")

    project = environment_value("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise RuntimeError("Google Cloud project is not configured for Vertex ADC")
    generation = config["generation"]
    material = case_material(config, item)
    source = WORKSPACE_ROOT / config["implementation"]["source_script_from_workspace"]
    runtime = REVISION_ROOT / config["implementation"]["runtime_instrumentation"]
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=False, exist_ok=False)
    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    command = [
        sys.executable,
        str(source),
        "--simulation-date", str(material["simulation_date"]),
        "--debate-topic", str(material["debate_topic"]),
        "--user-context-file", str(material["context"]),
        "--knowledge-a", str(material["knowledge_a"]),
        "--knowledge-b", str(material["knowledge_b"]),
        "--name-a", str(material["name_a"]),
        "--name-b", str(material["name_b"]),
        "--rounds", str(generation["rounds"]),
        "--model", str(generation["model"]),
        "--temperature", str(generation["temperature"]),
        "--max-output-tokens", str(generation["max_output_tokens"]),
        "--min-evidence-pointers", str(generation["minimum_evidence_pointers"]),
        "--turn-sleep-sec", str(generation["turn_sleep_seconds"]),
        "--output-file", str(output_file),
    ]
    manifest: dict[str, Any] = {
        "status": "RUNNING",
        "run_id": run_id(item),
        "config_id": config["config_id"],
        "config_sha256": sha256_file(config_path),
        "kind": item["kind"],
        "case_id": item["case_id"],
        "replicate_id": item["replicate_id"],
        "model": generation["model"],
        "backend": generation["backend"],
        "vertex_location": generation["vertex_location"],
        "vertex_project_recorded": False,
        "temperature": generation["temperature"],
        "rounds": generation["rounds"],
        "expected_logical_generation_calls": config["design"]["expected_logical_generation_calls_per_output"],
        "simulation_date": material["simulation_date"],
        "source_script_sha256": sha256_file(source),
        "runtime_instrumentation_sha256": sha256_file(runtime),
        "situation_sha256": sha256_file(material["situation"]),
        "user_context_sha256": sha256_file(material["context"]),
        "knowledge_a_sha256": sha256_file(material["knowledge_a"]),
        "knowledge_b_sha256": sha256_file(material["knowledge_b"]),
        "started_utc": utc_now(),
    }
    manifest_path = run_dir / "run_manifest.json"
    atomic_write_json(manifest_path, manifest)

    environment = os.environ.copy()
    environment["GOOGLE_CLOUD_PROJECT"] = project
    environment["MPDS_REVISION_VERTEX_PROJECT"] = project
    environment["MPDS_REVISION_VERTEX_LOCATION"] = str(generation["vertex_location"])
    environment["MPDS_REVISION_BACKEND"] = str(generation["backend"])
    environment["MPDS_REVISION_RUN_ID"] = run_id(item)
    environment["MPDS_REVISION_API_LOG"] = str(api_log)
    environment["PYTHONPATH"] = str(runtime.parent) + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    if not (environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY")):
        environment["GEMINI_API_KEY"] = "vertex-adc-authentication"

    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=run_dir,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        manifest["return_code"] = result.returncode
        (run_dir / "stdout.log").write_text(redacted(result.stdout, environment), encoding="utf-8")
        (run_dir / "stderr.log").write_text(redacted(result.stderr, environment), encoding="utf-8")
    except Exception as exc:
        manifest["return_code"] = None
        manifest["error_type"] = type(exc).__name__
    manifest["finished_utc"] = utc_now()
    manifest["wall_clock_seconds"] = round(time.perf_counter() - started, 6)
    manifest["api_log_summary"] = api_log_summary(api_log)
    successful = int(manifest["api_log_summary"].get("successful_calls", 0))
    manifest["actual_successful_api_calls"] = successful
    manifest["citation_validation"] = "passed_by_unchanged_mpds_source" if manifest["return_code"] == 0 else "not_passed"
    if output_file.is_file():
        full_text = output_file.read_text(encoding="utf-8", errors="replace")
        final = extract_final(full_text)
        final_path = run_dir / "final.txt"
        final_path.write_text(final + "\n", encoding="utf-8")
        manifest["full_output_sha256"] = sha256_file(output_file)
        manifest["final_sha256"] = sha256_file(final_path)
        manifest["final_characters"] = len(final)
    complete = (
        manifest["return_code"] == 0
        and output_file.is_file()
        and (run_dir / "final.txt").is_file()
        and int(manifest.get("final_characters", 0)) > 0
        and successful >= int(config["design"]["expected_logical_generation_calls_per_output"])
    )
    manifest["status"] = "COMPLETE" if complete else "FAILED"
    atomic_write_json(manifest_path, manifest)
    return 0 if complete else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Resume-safe Reviewer 1 Q4 MPDS generation batch")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-runs", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--run-retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=60.0)
    args = parser.parse_args()
    if args.max_runs < 1 or args.run_retries < 0 or not 0 <= args.retry_delay_seconds <= 600:
        raise SystemExit("Invalid batch limit or retry settings")
    config_path = args.config.resolve()
    validation = validate_setup(config_path)
    if validation["validation"] != "PASS_SETUP":
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return 2
    config = load_config(config_path)
    run_root = REVISION_ROOT / config["output"]["run_set"]
    schedule = config["design"]["execution_order"]
    pending = [item for item in schedule if manifest_status(output_dir(run_root, item)) != "COMPLETE"]
    plan = {
        "config_id": config["config_id"],
        "dry_run": not args.execute,
        "expected_outputs": len(schedule),
        "already_complete": len(schedule) - len(pending),
        "pending_outputs": len(pending),
        "first_pending": run_id(pending[0]) if pending else None,
        "selected_now": min(len(pending), args.max_runs),
        "minimum_successful_generation_calls_pending": len(pending)
        * int(config["design"]["expected_logical_generation_calls_per_output"]),
        "api_calls_made": 0,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.confirm_config_id != config["config_id"]:
        raise SystemExit("Execution blocked: --confirm-config-id mismatch")
    if not environment_value("GOOGLE_CLOUD_PROJECT"):
        raise SystemExit("Execution blocked: Google Cloud project is not configured")

    run_root.mkdir(parents=True, exist_ok=True)
    status_path = REVISION_ROOT / config["output"]["batch_status_file"]
    failures: list[str] = []
    for item in pending[: args.max_runs]:
        identifier = run_id(item)
        atomic_write_json(status_path, status_payload(config, run_root, identifier))
        success = False
        for attempt in range(1, args.run_retries + 2):
            try:
                code = execute_one(config_path, config, item, run_root)
            except Exception as exc:
                print(json.dumps({"run_id": identifier, "error_type": type(exc).__name__}, ensure_ascii=False))
                code = 1
            if code == 0:
                success = True
                break
            archive_failed(output_dir(run_root, item), attempt, run_root)
            if attempt <= args.run_retries:
                time.sleep(args.retry_delay_seconds)
        if not success:
            failures.append(identifier)
        atomic_write_json(status_path, status_payload(config, run_root, None))
        if failures and not args.continue_on_error:
            break
    final_status = status_payload(config, run_root, None)
    atomic_write_json(status_path, final_status)
    print(
        json.dumps(
            {
                "status_counts": final_status["status_counts"],
                "failed_run_ids": failures,
                "batch_status": str(status_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
