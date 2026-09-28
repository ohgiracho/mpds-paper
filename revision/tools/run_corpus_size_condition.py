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

from corpus_size_common import (
    count_knowledge_records,
    environment_value,
    load_config,
    pool_manifest_path,
    read_json,
    read_knowledge_text,
    selected_knowledge_path,
    sha256_file,
)
from run_condition import api_log_summary, build_command, extract_final, find_script, load_case


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first runner for one MPDS corpus-size sensitivity cell")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--case", type=int, required=True)
    parser.add_argument("--corpus-size", type=int, required=True)
    parser.add_argument("--replicate", type=int, required=True)
    parser.add_argument("--model")
    parser.add_argument("--backend", choices=("developer", "vertex-adc", "vertex-api-key"))
    parser.add_argument("--vertex-project")
    parser.add_argument("--vertex-location")
    parser.add_argument("--run-set")
    parser.add_argument("--execute", action="store_true")
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


def corpus_details(path: Path, manifest: dict[str, Any], corpus_size: int, persona_cap: int) -> dict[str, Any]:
    artifact = manifest["artifacts"][f"top_{corpus_size}"]
    text = read_knowledge_text(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "expected_sha256": artifact["sha256"],
        "bytes": path.stat().st_size,
        "characters": len(text),
        "parsed_paper_count": count_knowledge_records(path),
        "retrieved_master_paper_count": int(manifest["artifacts"]["master_jsonl"]["records"]),
        "selected_paper_count": corpus_size,
        "persona_selected_characters": min(persona_cap, len(text)),
        "persona_truncated": len(text) > persona_cap,
        "debate_knowledge_characters_per_turn": len(text),
        "debate_turns_receiving_this_pool": 3,
        "nominal_debate_knowledge_characters_across_turns": len(text) * 3,
        "retrieval_id": manifest["retrieval_id"],
    }


def main() -> int:
    args = parse_args()
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    design = config["design"]
    generation = config["generation"]
    if args.case not in design["selected_case_ids"]:
        raise SystemExit(f"Case {args.case} is not in the frozen design")
    if args.corpus_size not in design["corpus_sizes"]:
        raise SystemExit(f"Corpus size {args.corpus_size} is not in the frozen design")
    if args.replicate not in design["replicates"]:
        raise SystemExit(f"Replicate {args.replicate} is not in the frozen design")

    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    record = load_case(repo, args.case)
    script = find_script(repo, revision_root, args.case, "mpds").resolve()
    user_context = (repo / str(record["public_case_input_dir"]) / "user_context.txt").resolve()
    situation_file = (repo / str(record["public_case_input_dir"]) / "situation.txt").resolve()
    input_root = revision_root / config["retrieval"]["input_root"]
    knowledge_a = selected_knowledge_path(input_root, args.case, "A", args.corpus_size)
    knowledge_b = selected_knowledge_path(input_root, args.case, "B", args.corpus_size)
    if not knowledge_a.exists() or not knowledge_b.exists():
        raise SystemExit("Sensitivity corpus inputs are missing. Run prepare_corpus_size_corpora.py and validation first.")
    manifest_a = read_json(pool_manifest_path(input_root, args.case, "A"))
    manifest_b = read_json(pool_manifest_path(input_root, args.case, "B"))
    persona_cap = int(generation["persona_excerpt_characters_per_pool"])
    details_a = corpus_details(knowledge_a, manifest_a, args.corpus_size, persona_cap)
    details_b = corpus_details(knowledge_b, manifest_b, args.corpus_size, persona_cap)
    for pool, details in (("A", details_a), ("B", details_b)):
        if details["sha256"] != details["expected_sha256"]:
            raise SystemExit(f"Pool {pool} selected knowledge hash mismatch")
        if details["parsed_paper_count"] != args.corpus_size:
            raise SystemExit(f"Pool {pool} contains {details['parsed_paper_count']} papers, expected {args.corpus_size}")

    model = args.model or str(generation["model"])
    backend = args.backend or str(generation["backend"])
    vertex_location = args.vertex_location or str(generation["vertex_location"])
    effective_model = model.removeprefix("models/") if backend in {"vertex-adc", "vertex-api-key"} else model
    run_set = args.run_set or str(config["output"]["run_set"])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", run_set):
        raise SystemExit("--run-set must be a simple directory name")
    run_id = f"case_{args.case:02d}__mpds__corpus_{args.corpus_size:04d}__rep_{args.replicate:02d}"
    run_dir = revision_root / run_set / f"case_{args.case:02d}" / f"corpus_{args.corpus_size:04d}" / f"replicate_{args.replicate:02d}"
    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    command = build_command(
        script,
        "mpds",
        record,
        user_context,
        situation_file,
        knowledge_a,
        knowledge_b,
        output_file,
        effective_model,
    )
    source_commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    plan: dict[str, Any] = {
        "status": "DRY_RUN" if not args.execute else "RUNNING",
        "purpose": "CORPUS_SIZE_SENSITIVITY",
        "run_id": run_id,
        "config_id": config["config_id"],
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "case_id": args.case,
        "case_name": record["case_name"],
        "condition": "mpds",
        "corpus_size_per_pool": args.corpus_size,
        "replicate_id": args.replicate,
        "source_commit": source_commit,
        "script": str(script),
        "script_sha256": sha256_file(script),
        "runtime_compatibility_layer": str(revision_root / "runtime" / "sitecustomize.py"),
        "runtime_compatibility_layer_sha256": sha256_file(revision_root / "runtime" / "sitecustomize.py"),
        "user_context": str(user_context),
        "user_context_sha256": sha256_file(user_context),
        "situation_file": str(situation_file),
        "situation_file_sha256": sha256_file(situation_file),
        "simulation_date": str(record["cutoff_year"]),
        "debate_topic": record["debate_topic"],
        "model": effective_model,
        "backend": backend,
        "vertex_location": vertex_location if backend != "developer" else None,
        "vertex_project_recorded": False,
        "temperature": generation["temperature"],
        "max_output_tokens": generation["max_output_tokens"],
        "rounds": generation["rounds"],
        "minimum_evidence_pointers": generation["minimum_evidence_pointers"],
        "expected_logical_generation_calls": design["expected_logical_generation_calls_per_output"],
        "corpus": {"A": details_a, "B": details_b},
        "nominal_total_persona_selected_characters": details_a["persona_selected_characters"] + details_b["persona_selected_characters"],
        "nominal_total_debate_knowledge_characters_across_six_turns": details_a["nominal_debate_knowledge_characters_across_turns"] + details_b["nominal_debate_knowledge_characters_across_turns"],
        "run_directory": str(run_dir),
        "command": command,
        "dry_run": not args.execute,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    gemini_api_key = environment_value("GEMINI_API_KEY") or environment_value("GOOGLE_API_KEY")
    vertex_project = args.vertex_project or environment_value("GOOGLE_CLOUD_PROJECT")
    vertex_api_key = environment_value("VERTEX_API_KEY")
    if backend == "developer" and not gemini_api_key:
        raise SystemExit("Execution blocked: GEMINI_API_KEY or GOOGLE_API_KEY is unavailable")
    if backend == "vertex-adc" and not vertex_project:
        raise SystemExit("Execution blocked: --vertex-project or GOOGLE_CLOUD_PROJECT is required")
    if backend == "vertex-api-key" and not vertex_api_key:
        raise SystemExit("Execution blocked: VERTEX_API_KEY is unavailable")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"Execution blocked: run directory is not empty: {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=False)
    plan["dry_run"] = False
    plan["started_utc"] = utc_now()
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    environment = os.environ.copy()
    if gemini_api_key and not (environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY")):
        environment["GEMINI_API_KEY"] = gemini_api_key
    if vertex_api_key and not environment.get("VERTEX_API_KEY"):
        environment["VERTEX_API_KEY"] = vertex_api_key
    runtime_dir = revision_root / "runtime"
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(runtime_dir) + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
    environment["MPDS_REVISION_RUN_ID"] = run_id
    environment["MPDS_REVISION_API_LOG"] = str(api_log)
    environment["MPDS_REVISION_BACKEND"] = backend
    if backend != "developer":
        environment["MPDS_REVISION_VERTEX_LOCATION"] = vertex_location
        if vertex_project:
            environment["MPDS_REVISION_VERTEX_PROJECT"] = vertex_project
        if backend == "vertex-adc" and not (environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY")):
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
    plan["validation_regeneration_calls"] = max(0, len(call_records) - int(plan["expected_logical_generation_calls"]))
    plan["status"] = "COMPLETE" if result.returncode == 0 and output_file.exists() else "FAILED"
    if output_file.exists():
        final = extract_final(output_file.read_text(encoding="utf-8", errors="replace"))
        (run_dir / "final.txt").write_text(final + "\n", encoding="utf-8")
        plan["full_output_sha256"] = sha256_file(output_file)
        plan["full_output_characters"] = len(output_file.read_text(encoding="utf-8", errors="replace"))
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
