from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_condition import api_log_summary, extract_final


REVISION_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REVISION_ROOT.parents[1]
CONFIG_PATH = REVISION_ROOT / "config" / "pba_failure_diagnostic_n3_v1.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def checked_file(path: Path, expected_hash: str, expected_bytes: int | None = None) -> None:
    if not path.exists():
        raise RuntimeError(f"Frozen input is missing: {path}")
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        raise RuntimeError(f"Frozen input size mismatch: {path}")
    if sha256_file(path) != expected_hash:
        raise RuntimeError(f"Frozen input hash mismatch: {path}")


def paths(config: dict[str, Any]) -> dict[str, Path]:
    return {
        "context": REVISION_ROOT / config["input"]["user_context"],
        "knowledge_a": WORKSPACE_ROOT / config["knowledge"]["pool_a"]["path_from_workspace"],
        "knowledge_b": WORKSPACE_ROOT / config["knowledge"]["pool_b"]["path_from_workspace"],
        "source": WORKSPACE_ROOT / config["implementation"]["source_script_from_workspace"],
        "runtime": REVISION_ROOT / config["implementation"]["runtime_instrumentation"],
        "run_set": REVISION_ROOT / config["output"]["run_set"],
    }


def validate(config: dict[str, Any], frozen: dict[str, Path]) -> None:
    checked_file(
        frozen["context"],
        config["input"]["user_context_sha256"],
        config["input"]["user_context_bytes"],
    )
    for key, path_key in (("pool_a", "knowledge_a"), ("pool_b", "knowledge_b")):
        entry = config["knowledge"][key]
        checked_file(frozen[path_key], entry["sha256"], entry["bytes"])
    implementation = config["implementation"]
    checked_file(
        frozen["source"],
        implementation["source_script_sha256"],
        implementation["source_script_bytes"],
    )
    checked_file(frozen["runtime"], implementation["runtime_instrumentation_sha256"])


def manifest_status(path: Path) -> str:
    if not path.exists():
        return "PENDING"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status", "UNKNOWN"))
    except Exception:
        return "INVALID"


def summarize(
    run_set: Path,
    replicates: list[int],
    config_id: str,
    active_item: str | None = None,
) -> dict[str, Any]:
    counts = {"COMPLETE": 0, "FAILED": 0, "RUNNING": 0, "PENDING": 0, "OTHER": 0}
    items: list[dict[str, Any]] = []
    for replicate in replicates:
        run_id = f"pba_failure_diagnostic__rep_{replicate:02d}"
        manifest = run_set / f"replicate_{replicate:02d}" / "run_manifest.json"
        status = manifest_status(manifest)
        bucket = status if status in counts else "OTHER"
        counts[bucket] += 1
        items.append({"run_id": run_id, "replicate": replicate, "status": status})
    return {
        "config_id": config_id,
        "updated_utc": utc_now(),
        "expected": len(replicates),
        "counts": counts,
        "active_item": active_item,
        "items": items,
    }


def write_status(
    run_set: Path,
    replicates: list[int],
    config_id: str,
    active_item: str | None = None,
) -> None:
    run_set.mkdir(parents=True, exist_ok=True)
    status = summarize(run_set, replicates, config_id, active_item)
    (run_set / "batch_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run_one(config: dict[str, Any], frozen: dict[str, Path], replicate: int) -> int:
    generation = config["generation"]
    run_id = f"pba_failure_diagnostic__rep_{replicate:02d}"
    run_dir = frozen["run_set"] / f"replicate_{replicate:02d}"
    manifest_path = run_dir / "run_manifest.json"
    existing = manifest_status(manifest_path)
    if existing == "COMPLETE":
        return 0
    if run_dir.exists() and any(run_dir.iterdir()):
        raise RuntimeError(f"Non-empty non-COMPLETE run is preserved and requires review: {run_dir}")

    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    command = [
        sys.executable,
        str(frozen["source"]),
        "--simulation-date",
        str(generation["simulation_date"]),
        "--debate-topic",
        config["input"]["topic"],
        "--user-context-file",
        str(frozen["context"]),
        "--knowledge-a",
        str(frozen["knowledge_a"]),
        "--knowledge-b",
        str(frozen["knowledge_b"]),
        "--name-a",
        config["knowledge"]["pool_a"]["role_name"],
        "--name-b",
        config["knowledge"]["pool_b"]["role_name"],
        "--rounds",
        str(generation["rounds"]),
        "--model",
        str(generation["model"]),
        "--temperature",
        str(generation["temperature"]),
        "--max-output-tokens",
        str(generation["max_output_tokens"]),
        "--min-evidence-pointers",
        str(generation["minimum_evidence_pointers"]),
        "--turn-sleep-sec",
        str(generation["turn_sleep_seconds"]),
        "--output-file",
        str(output_file),
    ]
    plan: dict[str, Any] = {
        "status": "RUNNING",
        "purpose": "PBA_FAILURE_DIAGNOSTIC_REPRODUCIBILITY",
        "run_id": run_id,
        "config_id": config["config_id"],
        "config": str(CONFIG_PATH),
        "config_sha256": sha256_file(CONFIG_PATH),
        "replicate": replicate,
        "model": generation["model"],
        "backend": generation["backend"],
        "vertex_location": generation["vertex_location"],
        "vertex_project_recorded": False,
        "temperature": generation["temperature"],
        "rounds": generation["rounds"],
        "expected_logical_generation_calls": generation["expected_logical_calls_per_replicate"],
        "source_script": str(frozen["source"]),
        "source_script_sha256": sha256_file(frozen["source"]),
        "user_context": str(frozen["context"]),
        "user_context_sha256": sha256_file(frozen["context"]),
        "knowledge_a_sha256": sha256_file(frozen["knowledge_a"]),
        "knowledge_b_sha256": sha256_file(frozen["knowledge_b"]),
        "historical_output_injected": False,
        "started_utc": utc_now(),
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    environment = os.environ.copy()
    project = environment.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        plan["status"] = "FAILED"
        plan["error"] = "GOOGLE_CLOUD_PROJECT is not configured"
        manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 2
    runtime_dir = str(frozen["runtime"].parent)
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = runtime_dir + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
    environment["MPDS_REVISION_RUN_ID"] = run_id
    environment["MPDS_REVISION_API_LOG"] = str(api_log)
    environment["MPDS_REVISION_BACKEND"] = generation["backend"]
    environment["MPDS_REVISION_VERTEX_LOCATION"] = generation["vertex_location"]
    environment["MPDS_REVISION_VERTEX_PROJECT"] = project
    if not (environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY")):
        environment["GEMINI_API_KEY"] = "vertex-adc-authentication"

    started = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=run_dir,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    plan["finished_utc"] = utc_now()
    plan["wall_clock_seconds"] = round(time.perf_counter() - started, 6)
    plan["return_code"] = result.returncode
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    plan["api_log_summary"] = api_log_summary(api_log)
    successful = int(plan["api_log_summary"].get("successful_calls", 0))
    plan["actual_successful_api_calls"] = successful
    plan["validation_regeneration_calls"] = max(
        0, successful - int(generation["expected_logical_calls_per_replicate"])
    )
    if output_file.exists():
        full_text = output_file.read_text(encoding="utf-8", errors="replace")
        final = extract_final(full_text)
        final_file = run_dir / "final.txt"
        final_file.write_text(final + "\n", encoding="utf-8")
        plan["full_output_sha256"] = sha256_file(output_file)
        plan["full_output_characters"] = len(full_text)
        plan["final_sha256"] = sha256_file(final_file)
        plan["final_characters"] = len(final)
    complete = (
        result.returncode == 0
        and output_file.exists()
        and (run_dir / "final.txt").exists()
        and successful >= int(generation["expected_logical_calls_per_replicate"])
    )
    plan["status"] = "COMPLETE" if complete else "FAILED"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if complete else (result.returncode or 1)


def main() -> int:
    global CONFIG_PATH
    parser = argparse.ArgumentParser(description="Resume-safe PBA diagnostic n=3 runner")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-runs", type=int, default=3)
    args = parser.parse_args()

    CONFIG_PATH = args.config.resolve()
    config = load_config()
    frozen = paths(config)
    validate(config, frozen)
    replicates = [int(value) for value in config["generation"]["replicates"]]
    if args.max_runs < 1:
        raise SystemExit("--max-runs must be at least 1")

    if not args.execute:
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "ready_for_generation": True,
                    "config_id": config["config_id"],
                    "planned_replicates": replicates[: args.max_runs],
                    "expected_calls": len(replicates[: args.max_runs])
                    * int(config["generation"]["expected_logical_calls_per_replicate"]),
                    "api_calls_made": 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.confirm_config_id != config["config_id"]:
        raise SystemExit("Execution blocked: --confirm-config-id does not match the frozen config")

    selected = replicates[: args.max_runs]
    write_status(frozen["run_set"], replicates, config["config_id"])
    for replicate in selected:
        run_id = f"pba_failure_diagnostic__rep_{replicate:02d}"
        write_status(frozen["run_set"], replicates, config["config_id"], run_id)
        code = run_one(config, frozen, replicate)
        write_status(frozen["run_set"], replicates, config["config_id"])
        if code != 0:
            return code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
