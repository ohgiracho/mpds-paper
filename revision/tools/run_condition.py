from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import openpyxl


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds", "sair", "ses")
EXPECTED_CALLS = {"raw": 1, "eo": 1, "eop": 2, "ds": 7, "mpds": 9, "sair": 7, "ses": 3}
DEFAULT_MODEL = "models/gemini-2.5-pro"
TEMPERATURE = 0.5
MAX_OUTPUT_TOKENS = 8192


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_case(repo: Path, case_id: int) -> dict[str, Any]:
    workbook_path = repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx"
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    sheet = workbook["BenchmarkCases"]
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value) for value in next(rows)]
    for values in rows:
        record = dict(zip(headers, values))
        if int(record["case_id"]) == case_id:
            return record
    raise ValueError(f"Unknown case id: {case_id}")


def find_script(repo: Path, revision_root: Path, case_id: int, condition: str) -> Path:
    if condition in {"sair", "ses"}:
        return revision_root / "conditions" / f"run_{condition}.py"

    code_root = repo / "code" / "02_case_specific_generation_code"
    case_dirs = [path for path in code_root.iterdir() if path.is_dir() and f"({case_id})" in path.name]
    if len(case_dirs) != 1:
        raise RuntimeError(f"Expected one code directory for case {case_id}, found {case_dirs}")
    condition_dir = case_dirs[0] / ({"raw": "raw_llm"}.get(condition, condition))
    candidates = [
        path
        for path in condition_dir.glob("*.py")
        if path.name != "merge_knowledge.py" and path.name.startswith("run_")
    ]
    # The submitted release preserves the case-06 DS script in a tracked
    # ``__tmp__...`` subdirectory rather than ``ds/``.  Treat that path as the
    # canonical submitted implementation without moving or renaming it.
    if not candidates and condition == "ds" and case_id == 6:
        candidates = [path for path in case_dirs[0].rglob("run_ds.py") if path.is_file()]
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one {condition} run script for case {case_id}, found {candidates}")
    return candidates[0]


def knowledge_paths(audit_dir: Path, case_id: int) -> tuple[Path, Path, dict[str, str]]:
    rows = [row for row in read_csv(audit_dir / "knowledge_snapshot_manifest.csv") if int(row["case_id"]) == case_id]
    by_pool = {row["pool"]: row for row in rows}
    if set(by_pool) != {"A", "B"}:
        raise RuntimeError(f"Knowledge manifest incomplete for case {case_id}")
    paths = Path(by_pool["A"]["local_path"]), Path(by_pool["B"]["local_path"])
    for pool, path in zip(("A", "B"), paths):
        if not path.exists() or sha256_file(path) != by_pool[pool]["sha256"]:
            raise RuntimeError(f"Frozen evidence mismatch for case {case_id}, pool {pool}: {path}")
    return paths[0], paths[1], {"A": by_pool["A"]["sha256"], "B": by_pool["B"]["sha256"]}


def build_command(
    script: Path,
    condition: str,
    record: dict[str, Any],
    user_context: Path,
    situation_file: Path,
    knowledge_a: Path,
    knowledge_b: Path,
    output_file: Path,
    model: str,
) -> list[str]:
    command = [
        sys.executable,
        str(script),
        "--simulation-date",
        str(record["cutoff_year"]),
        "--debate-topic",
        str(record["debate_topic"]),
        "--user-context-file",
        str(user_context),
    ]
    if condition == "mpds":
        command.extend(["--situation-file", str(situation_file)])
    if condition != "raw":
        command.extend(["--knowledge-a", str(knowledge_a), "--knowledge-b", str(knowledge_b)])
    if condition in {"ds", "mpds"}:
        command.extend(["--rounds", "3", "--turn-sleep-sec", "0.2"])
    if condition in {"ds", "mpds", "sair", "ses"}:
        command.extend(["--min-evidence-pointers", "3"])
    command.extend(
        [
            "--model",
            model,
            "--temperature",
            str(TEMPERATURE),
            "--max-output-tokens",
            str(MAX_OUTPUT_TOKENS),
            "--output-file",
            str(output_file),
        ]
    )
    return command


def extract_final(text: str) -> str:
    markers = (
        "[FINAL SYNTHESIS]",
        "[Final Synthesis]",
        "[EOP Answer]",
        "[EO Answer]",
        "[Raw LLM Answer]",
    )
    positions = [(text.rfind(marker), marker) for marker in markers if marker in text]
    if not positions:
        return text.strip()
    position, marker = max(positions)
    return text[position + len(marker) :].strip()


def api_log_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"attempted_generate_content_calls": 0, "successful_calls": 0, "failed_calls": 0}
    records = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if item.get("event") == "generate_content":
            records.append(item)
    successes = [item for item in records if item.get("status") == "success"]
    failures = [item for item in records if item.get("status") == "error"]
    token_totals: dict[str, int] = {}
    for item in successes:
        usage = item.get("usage_metadata") or {}
        if isinstance(usage, dict):
            for key, value in usage.items():
                if isinstance(value, int) and ("token" in key.lower() or "count" in key.lower()):
                    token_totals[key] = token_totals.get(key, 0) + value
    return {
        "attempted_generate_content_calls": len(records),
        "successful_calls": len(successes),
        "failed_calls": len(failures),
        "usage_metadata_sums": token_totals,
        "elapsed_seconds_sum": round(sum(float(item.get("elapsed_seconds", 0)) for item in records), 6),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run-first revision condition runner")
    parser.add_argument("--case", type=int, required=True, choices=range(1, 31))
    parser.add_argument("--condition", required=True, choices=CONDITIONS)
    parser.add_argument("--replicate", type=int, required=True, choices=(1, 2, 3))
    parser.add_argument("--execute", action="store_true", help="Actually call the model API; default is dry-run")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking-level", choices=("low", "medium", "high"))
    parser.add_argument(
        "--backend",
        choices=("developer", "vertex-adc", "vertex-api-key"),
        default="developer",
        help="Gemini Developer API or Vertex AI authentication mode",
    )
    parser.add_argument("--vertex-project")
    parser.add_argument("--vertex-location", default="global")
    parser.add_argument("--run-set", default="runs")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--revision-root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.run_set):
        raise SystemExit("--run-set must be a simple directory name")
    revision_root = (args.revision_root or Path(__file__).resolve().parents[1]).resolve()
    repo = (args.repo or revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    audit_dir = revision_root / "audit"
    record = load_case(repo, args.case)
    script = find_script(repo, revision_root, args.case, args.condition).resolve()
    user_context = (repo / str(record["public_case_input_dir"]) / "user_context.txt").resolve()
    situation_file = (repo / str(record["public_case_input_dir"]) / "situation.txt").resolve()
    knowledge_a, knowledge_b, evidence_hashes = knowledge_paths(audit_dir, args.case)
    requested_model = args.model
    # Vertex AI expects the publisher model ID without the Developer API's
    # resource-style ``models/`` prefix.
    effective_model = (
        requested_model.removeprefix("models/")
        if args.backend in {"vertex-adc", "vertex-api-key"}
        else requested_model
    )
    run_id = f"case_{args.case:02d}__{args.condition}__rep_{args.replicate:02d}"
    run_dir = revision_root / args.run_set / f"case_{args.case:02d}" / args.condition / f"replicate_{args.replicate:02d}"
    output_file = run_dir / "full_output.txt"
    api_log = run_dir / "api_calls.jsonl"
    command = build_command(
        script,
        args.condition,
        record,
        user_context,
        situation_file,
        knowledge_a,
        knowledge_b,
        output_file,
        effective_model,
    )

    plan = {
        "run_id": run_id,
        "case_id": args.case,
        "repo_case_slug": record["case_slug"],
        "case_name": record["case_name"],
        "manuscript_case_label": "Case Study 2" if args.case == 1 else "Case Study 1" if args.case == 2 else "",
        "condition": args.condition,
        "replicate_id": args.replicate,
        "source_commit": subprocess.check_output(
            ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
            text=True,
            encoding="utf-8",
        ).strip(),
        "script": str(script),
        "script_sha256": sha256_file(script),
        "runtime_compatibility_layer": str(revision_root / "runtime" / "sitecustomize.py"),
        "runtime_compatibility_layer_sha256": sha256_file(revision_root / "runtime" / "sitecustomize.py"),
        "user_context": str(user_context),
        "user_context_sha256": sha256_file(user_context),
        "situation_file": str(situation_file) if args.condition == "mpds" else None,
        "situation_file_sha256": sha256_file(situation_file) if args.condition == "mpds" else None,
        "knowledge_a": str(knowledge_a),
        "knowledge_b": str(knowledge_b),
        "knowledge_sha256": evidence_hashes,
        "simulation_date": str(record["cutoff_year"]),
        "debate_topic": record["debate_topic"],
        "requested_model": requested_model,
        "model": effective_model,
        "thinking_level": args.thinking_level,
        "backend": args.backend,
        "vertex_project": args.vertex_project,
        "vertex_location": args.vertex_location if args.backend != "developer" else None,
        "run_set": args.run_set,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "rounds": 3 if args.condition in {"ds", "mpds"} else None,
        "minimum_evidence_pointers": 3 if args.condition in {"ds", "mpds", "sair", "ses"} else None,
        "validation_regeneration_limit_per_stage": 5 if args.condition in {"ds", "mpds", "sair", "ses"} else None,
        "expected_logical_generation_calls": EXPECTED_CALLS[args.condition],
        "run_directory": str(run_dir),
        "command": command,
        "dry_run": not args.execute,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if args.backend == "developer" and not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        raise SystemExit("Execution blocked: GEMINI_API_KEY or GOOGLE_API_KEY is not available.")
    if args.backend == "vertex-adc" and not (args.vertex_project or os.getenv("GOOGLE_CLOUD_PROJECT")):
        raise SystemExit("Execution blocked: --vertex-project or GOOGLE_CLOUD_PROJECT is required for Vertex ADC.")
    if args.backend == "vertex-api-key" and not os.getenv("VERTEX_API_KEY"):
        raise SystemExit("Execution blocked: VERTEX_API_KEY is not available.")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise SystemExit(f"Execution blocked: run directory is not empty: {run_dir}")

    run_dir.mkdir(parents=True, exist_ok=False)
    plan["dry_run"] = False
    plan["status"] = "RUNNING"
    plan["started_utc"] = datetime.now(timezone.utc).isoformat()
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    environment = os.environ.copy()
    runtime_dir = revision_root / "runtime"
    prior_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(runtime_dir) + (os.pathsep + prior_pythonpath if prior_pythonpath else "")
    environment["MPDS_REVISION_RUN_ID"] = run_id
    environment["MPDS_REVISION_API_LOG"] = str(api_log)
    environment["MPDS_REVISION_BACKEND"] = args.backend
    if args.backend != "developer":
        environment["MPDS_REVISION_VERTEX_LOCATION"] = args.vertex_location
        if args.vertex_project:
            environment["MPDS_REVISION_VERTEX_PROJECT"] = args.vertex_project
        # Submitted scripts require a Gemini API key before constructing their
        # client.  The runtime wrapper discards this placeholder for Vertex ADC.
        if args.backend == "vertex-adc" and not (environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY")):
            environment["GEMINI_API_KEY"] = "vertex-adc-authentication"
    if args.thinking_level:
        environment["MPDS_REVISION_THINKING_LEVEL"] = args.thinking_level
    result = subprocess.run(
        command,
        cwd=run_dir,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")

    plan["finished_utc"] = datetime.now(timezone.utc).isoformat()
    plan["return_code"] = result.returncode
    plan["api_log_summary"] = api_log_summary(api_log)
    plan["status"] = "COMPLETE" if result.returncode == 0 and output_file.exists() else "FAILED"
    if output_file.exists():
        final = extract_final(output_file.read_text(encoding="utf-8", errors="replace"))
        (run_dir / "final.txt").write_text(final + "\n", encoding="utf-8")
        plan["full_output_sha256"] = sha256_file(output_file)
        plan["final_sha256"] = sha256_file(run_dir / "final.txt")
    manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: plan[key] for key in ("run_id", "status", "return_code", "api_log_summary")}, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
