from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deleak_common import assert_hash, assert_litm_gate_open, load_deleak_config, output_directory, sha256_file
from litm_common import environment_value
from run_condition import api_log_summary, extract_final, find_script, load_case


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first runner for one frozen de-leaked MPDS output")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--case", type=int, required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    return parser.parse_args()


def successful_call_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("event") == "generate_content" and item.get("status") == "success":
            records.append(item)
    return records


def main() -> int:
    args = parse_args()
    revision_root = Path(__file__).resolve().parents[1]
    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    config_path, config = load_deleak_config(revision_root, args.config)
    selected_cases = [int(value) for value in config["selection"]["selected_case_ids"]]
    replicates = [int(value) for value in config["design"]["replicates"]]
    if args.case not in selected_cases:
        raise SystemExit(f"Case {args.case} is not in the frozen targeted design")
    if args.replicate not in replicates:
        raise SystemExit(f"Replicate {args.replicate} is not in the frozen targeted design")

    generation = config["generation"]
    case = config["cases"][str(args.case)]
    record = load_case(repo, args.case)
    source_script = find_script(repo, revision_root, args.case, "mpds").resolve()
    expected_script = (repo / str(case["source_script"])).resolve()
    if source_script != expected_script:
        raise SystemExit("Canonical MPDS source-script path does not match the frozen configuration")
    situation_file = (revision_root / str(case["deleaked_situation"])).resolve()
    user_context = (revision_root / str(case["deleaked_user_context"])).resolve()
    original_situation = (repo / str(case["original_situation"])).resolve()
    original_user_context = (repo / str(case["original_user_context"])).resolve()
    knowledge_a = Path(str(case["knowledge_a"])).resolve()
    knowledge_b = Path(str(case["knowledge_b"])).resolve()
    runtime = (revision_root / str(config["runtime"]["compatibility_layer"])).resolve()
    for path, expected, label in (
        (source_script, case["source_script_sha256"], "source MPDS script"),
        (situation_file, case["deleaked_situation_sha256"], "de-leaked situation"),
        (user_context, case["deleaked_user_context_sha256"], "de-leaked user context"),
        (original_situation, case["original_situation_sha256"], "original situation"),
        (original_user_context, case["original_user_context_sha256"], "original user context"),
        (knowledge_a, case["knowledge_a_sha256"], "knowledge A"),
        (knowledge_b, case["knowledge_b_sha256"], "knowledge B"),
        (runtime, config["runtime"]["compatibility_layer_sha256"], "runtime compatibility layer"),
    ):
        assert_hash(path, str(expected), label)

    source_commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    if source_commit != str(generation["source_commit"]):
        raise SystemExit("Repository commit differs from the frozen generation source commit")

    run_id = f"case_{args.case:02d}__mpds_deleaked__rep_{args.replicate:02d}"
    run_dir = output_directory(revision_root, config, args.case, args.replicate)
    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    model = str(generation["model"]).removeprefix("models/")
    command = [
        sys.executable,
        str(source_script),
        "--simulation-date",
        str(case["simulation_date"]),
        "--debate-topic",
        str(case["debate_topic"]),
        "--user-context-file",
        str(user_context),
        "--situation-file",
        str(situation_file),
        "--knowledge-a",
        str(knowledge_a),
        "--knowledge-b",
        str(knowledge_b),
        "--rounds",
        str(generation["rounds"]),
        "--min-evidence-pointers",
        str(generation["minimum_evidence_pointers"]),
        "--turn-sleep-sec",
        str(generation["turn_sleep_seconds"]),
        "--model",
        model,
        "--temperature",
        str(generation["temperature"]),
        "--max-output-tokens",
        str(generation["max_output_tokens"]),
        "--output-file",
        str(output_file),
    ]
    plan: dict[str, Any] = {
        "status": "DRY_RUN" if not args.execute else "RUNNING",
        "purpose": config["purpose"],
        "run_id": run_id,
        "config_id": config["config_id"],
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "case_id": args.case,
        "case_name": record["case_name"],
        "condition": "mpds_deleaked",
        "replicate_id": args.replicate,
        "source_commit": source_commit,
        "source_mpds_script": str(source_script),
        "source_mpds_script_sha256": sha256_file(source_script),
        "runtime_compatibility_layer": str(runtime),
        "runtime_compatibility_layer_sha256": sha256_file(runtime),
        "original_input_hashes": {
            "situation": sha256_file(original_situation),
            "user_context": sha256_file(original_user_context),
        },
        "deleaked_inputs": {
            "situation_file": str(situation_file),
            "situation_sha256": sha256_file(situation_file),
            "user_context_file": str(user_context),
            "user_context_sha256": sha256_file(user_context),
        },
        "simulation_date": str(case["simulation_date"]),
        "debate_topic": case["debate_topic"],
        "model": model,
        "backend": generation["backend"],
        "vertex_location": generation["vertex_location"],
        "vertex_project_recorded": False,
        "temperature": generation["temperature"],
        "max_output_tokens": generation["max_output_tokens"],
        "rounds": generation["rounds"],
        "minimum_evidence_pointers": generation["minimum_evidence_pointers"],
        "expected_logical_generation_calls": config["design"]["expected_logical_generation_calls_per_output"],
        "evidence": {
            "A": {"path": str(knowledge_a), "sha256": sha256_file(knowledge_a)},
            "B": {"path": str(knowledge_b), "sha256": sha256_file(knowledge_b)},
        },
        "run_directory": str(run_dir),
        "command": command,
        "dry_run": not args.execute,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if args.confirm_config_id != config["config_id"]:
        raise SystemExit(f"Live execution requires --confirm-config-id {config['config_id']}")
    assert_litm_gate_open(revision_root, config)
    vertex_project = environment_value("GOOGLE_CLOUD_PROJECT")
    if not vertex_project:
        raise SystemExit("Execution blocked: GOOGLE_CLOUD_PROJECT is not configured for Vertex ADC")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"Execution blocked: run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    plan["dry_run"] = False
    plan["started_utc"] = utc_now()
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    environment = os.environ.copy()
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(runtime.parent) + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
    environment["MPDS_REVISION_RUN_ID"] = run_id
    environment["MPDS_REVISION_API_LOG"] = str(api_log)
    environment["MPDS_REVISION_BACKEND"] = str(generation["backend"])
    environment["MPDS_REVISION_VERTEX_LOCATION"] = str(generation["vertex_location"])
    environment["MPDS_REVISION_VERTEX_PROJECT"] = vertex_project
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
    wall_seconds = round(time.perf_counter() - started, 6)
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    call_records = successful_call_records(api_log)
    plan["finished_utc"] = utc_now()
    plan["wall_clock_seconds"] = wall_seconds
    plan["return_code"] = result.returncode
    plan["api_log_summary"] = api_log_summary(api_log)
    plan["actual_successful_api_calls"] = len(call_records)
    plan["actual_prompt_characters_sum"] = sum(int(item.get("prompt_characters") or 0) for item in call_records)
    plan["validation_regeneration_calls"] = max(
        0, len(call_records) - int(plan["expected_logical_generation_calls"])
    )
    final = ""
    if output_file.exists():
        full_text = output_file.read_text(encoding="utf-8", errors="replace")
        final = extract_final(full_text)
        (run_dir / "final.txt").write_text(final + "\n", encoding="utf-8")
        plan["full_output_sha256"] = sha256_file(output_file)
        plan["full_output_characters"] = len(full_text)
        plan["final_sha256"] = sha256_file(run_dir / "final.txt")
        plan["final_characters"] = len(final)
    expected_calls = int(plan["expected_logical_generation_calls"])
    plan["citation_validation_completed"] = result.returncode == 0 and len(call_records) >= expected_calls
    plan["status"] = (
        "COMPLETE"
        if result.returncode == 0 and output_file.exists() and bool(final.strip()) and len(call_records) >= expected_calls
        else "FAILED"
    )
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": plan["status"],
                "return_code": result.returncode,
                "successful_api_calls": len(call_records),
                "wall_clock_seconds": wall_seconds,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if plan["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
