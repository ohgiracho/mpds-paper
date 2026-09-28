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

from litm_common import (
    environment_value,
    load_config,
    ordered_knowledge_path,
    pool_manifest_path,
    read_json,
    sha256_file,
)
from run_condition import api_log_summary, extract_final, find_script, load_case


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first runner for one position-control cell")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--case", type=int, required=True)
    parser.add_argument("--ordering", required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--vertex-project")
    parser.add_argument("--run-set")
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
    config_path, config = load_config(revision_root, args.config)
    design = config["design"]
    generation = config["generation"]
    if args.case not in [int(value) for value in design["selected_case_ids"]]:
        raise SystemExit(f"Case {args.case} is not in the frozen design")
    if args.ordering not in design["orderings"]:
        raise SystemExit(f"Ordering {args.ordering} is not in the frozen design")
    if args.replicate not in [int(value) for value in design["replicates"]]:
        raise SystemExit(f"Replicate {args.replicate} is not in the frozen design")

    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    record = load_case(repo, args.case)
    source_script = find_script(repo, revision_root, args.case, "mpds").resolve()
    adapter = (revision_root / "tools" / "run_litm_mpds_adapter.py").resolve()
    user_context = (repo / str(record["public_case_input_dir"]) / "user_context.txt").resolve()
    situation_file = (repo / str(record["public_case_input_dir"]) / "situation.txt").resolve()
    manifest_a = read_json(pool_manifest_path(revision_root, config, args.case, "A"))
    manifest_b = read_json(pool_manifest_path(revision_root, config, args.case, "B"))
    ordered_a = ordered_knowledge_path(revision_root, config, args.case, "A", args.ordering)
    ordered_b = ordered_knowledge_path(revision_root, config, args.case, "B", args.ordering)
    for pool, manifest, path in (
        ("A", manifest_a, ordered_a),
        ("B", manifest_b, ordered_b),
    ):
        artifact = manifest["orderings"][args.ordering]
        if not path.exists() or sha256_file(path) != artifact["sha256"]:
            raise SystemExit(f"Frozen ordered knowledge mismatch for pool {pool}")
        if artifact["record_count"] != 500:
            raise SystemExit(f"Ordered pool {pool} does not contain 500 records")
    canonical_a = Path(manifest_a["persona_source"]).resolve()
    canonical_b = Path(manifest_b["persona_source"]).resolve()
    if sha256_file(canonical_a) != manifest_a["persona_source_sha256"]:
        raise SystemExit("Canonical persona source A hash mismatch")
    if sha256_file(canonical_b) != manifest_b["persona_source_sha256"]:
        raise SystemExit("Canonical persona source B hash mismatch")

    run_set = args.run_set or str(config["output"]["run_set"])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_set):
        raise SystemExit("--run-set must be a simple directory name")
    run_id = f"case_{args.case:02d}__mpds__order_{args.ordering}__rep_{args.replicate:02d}"
    run_dir = (
        revision_root
        / run_set
        / f"case_{args.case:02d}"
        / f"order_{args.ordering}"
        / f"replicate_{args.replicate:02d}"
    )
    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    model = str(generation["model"])
    command = [
        sys.executable,
        str(adapter),
        "--source-script",
        str(source_script),
        "--expected-source-sha256",
        sha256_file(source_script),
        "--canonical-persona-a",
        str(canonical_a),
        "--canonical-persona-b",
        str(canonical_b),
        "--simulation-date",
        str(record["cutoff_year"]),
        "--debate-topic",
        str(record["debate_topic"]),
        "--user-context-file",
        str(user_context),
        "--situation-file",
        str(situation_file),
        "--knowledge-a",
        str(ordered_a),
        "--knowledge-b",
        str(ordered_b),
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
    source_commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    plan: dict[str, Any] = {
        "status": "DRY_RUN" if not args.execute else "RUNNING",
        "purpose": "LOST_IN_MIDDLE_POSITION_CONTROL",
        "run_id": run_id,
        "config_id": config["config_id"],
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "case_id": args.case,
        "case_name": record["case_name"],
        "condition": "mpds",
        "ordering": args.ordering,
        "positions": config["position_manipulation"]["rotations"][args.ordering],
        "replicate_id": args.replicate,
        "source_commit": source_commit,
        "source_mpds_script": str(source_script),
        "source_mpds_script_sha256": sha256_file(source_script),
        "position_control_adapter": str(adapter),
        "position_control_adapter_sha256": sha256_file(adapter),
        "runtime_compatibility_layer": str(revision_root / "runtime" / "sitecustomize.py"),
        "runtime_compatibility_layer_sha256": sha256_file(revision_root / "runtime" / "sitecustomize.py"),
        "user_context": str(user_context),
        "user_context_sha256": sha256_file(user_context),
        "situation_file": str(situation_file),
        "situation_file_sha256": sha256_file(situation_file),
        "simulation_date": str(record["cutoff_year"]),
        "debate_topic": record["debate_topic"],
        "model": model,
        "backend": generation["backend"],
        "vertex_location": generation["vertex_location"],
        "vertex_project_recorded": False,
        "temperature": generation["temperature"],
        "max_output_tokens": generation["max_output_tokens"],
        "rounds": generation["rounds"],
        "minimum_evidence_pointers": generation["minimum_evidence_pointers"],
        "expected_logical_generation_calls": design["expected_logical_generation_calls_per_output"],
        "persona_control": {
            "policy": "canonical source snapshots fixed across all orderings",
            "A": {"sha256": manifest_a["persona_source_sha256"], "characters": manifest_a["source_characters"]},
            "B": {"sha256": manifest_b["persona_source_sha256"], "characters": manifest_b["source_characters"]},
        },
        "debate_evidence": {
            "A": {
                "path": str(ordered_a),
                "sha256": manifest_a["orderings"][args.ordering]["sha256"],
                "characters": manifest_a["orderings"][args.ordering]["characters"],
                "records": 500,
                "record_multiset_sha256": manifest_a["record_multiset_sha256"],
            },
            "B": {
                "path": str(ordered_b),
                "sha256": manifest_b["orderings"][args.ordering]["sha256"],
                "characters": manifest_b["orderings"][args.ordering]["characters"],
                "records": 500,
                "record_multiset_sha256": manifest_b["record_multiset_sha256"],
            },
        },
        "run_directory": str(run_dir),
        "command": command,
        "dry_run": not args.execute,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    vertex_project = args.vertex_project or environment_value("GOOGLE_CLOUD_PROJECT")
    if not vertex_project:
        raise SystemExit("Execution blocked: Vertex ADC requires --vertex-project or GOOGLE_CLOUD_PROJECT")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"Execution blocked: run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)
    plan["dry_run"] = False
    plan["started_utc"] = utc_now()
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    environment = os.environ.copy()
    runtime_dir = revision_root / "runtime"
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(runtime_dir) + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
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
    plan["finished_utc"] = utc_now()
    plan["wall_clock_seconds"] = wall_seconds
    plan["return_code"] = result.returncode
    plan["api_log_summary"] = api_log_summary(api_log)
    call_records = successful_call_records(api_log)
    plan["actual_prompt_characters_sum"] = sum(int(item.get("prompt_characters") or 0) for item in call_records)
    plan["actual_prompt_characters_by_call"] = [int(item.get("prompt_characters") or 0) for item in call_records]
    plan["actual_successful_api_calls"] = len(call_records)
    plan["validation_regeneration_calls"] = max(
        0, len(call_records) - int(plan["expected_logical_generation_calls"])
    )
    plan["status"] = "COMPLETE" if result.returncode == 0 and output_file.exists() else "FAILED"
    if output_file.exists():
        full_text = output_file.read_text(encoding="utf-8", errors="replace")
        final = extract_final(full_text)
        (run_dir / "final.txt").write_text(final + "\n", encoding="utf-8")
        plan["full_output_sha256"] = sha256_file(output_file)
        plan["full_output_characters"] = len(full_text)
        plan["final_sha256"] = sha256_file(run_dir / "final.txt")
        plan["final_characters"] = len(final)
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": plan["status"],
                "return_code": result.returncode,
                "wall_clock_seconds": wall_seconds,
                "api_log_summary": plan["api_log_summary"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
