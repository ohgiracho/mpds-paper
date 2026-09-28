from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def read_registry(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Registry-driven, dry-run-first revision batch runner")
    parser.add_argument("--policy", choices=("practical", "strict"), required=True)
    parser.add_argument(
        "--case-config",
        type=Path,
        help="JSON file containing a selected_case_ids list; --case may further narrow it",
    )
    parser.add_argument("--case", type=int, action="append", choices=range(1, 31))
    parser.add_argument("--condition", action="append", choices=("raw", "eo", "eop", "ds", "mpds", "sair", "ses"))
    parser.add_argument("--replicate", type=int, action="append", choices=(1, 2, 3))
    parser.add_argument("--model", default="models/gemini-2.5-pro")
    parser.add_argument("--thinking-level", choices=("low", "medium", "high"))
    parser.add_argument(
        "--backend",
        choices=("developer", "vertex-adc", "vertex-api-key"),
        default="developer",
    )
    parser.add_argument("--vertex-project")
    parser.add_argument("--vertex-location", default="global")
    parser.add_argument("--run-set", default="runs")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-runs", type=int, default=1, help="Execution safety cap; ignored for dry-run")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--run-retries", type=int, default=0)
    parser.add_argument("--retry-delay-seconds", type=float, default=60.0)
    return parser.parse_args()


def is_complete(root: Path, run_set: str, row: dict[str, str]) -> bool:
    manifest = (
        root
        / run_set
        / f"case_{int(row['case_id']):02d}"
        / row["condition"]
        / f"replicate_{int(row['replicate_id']):02d}"
        / "run_manifest.json"
    )
    if not manifest.exists():
        return False
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("status") == "COMPLETE"
    except (OSError, json.JSONDecodeError):
        return False


def run_directory(root: Path, run_set: str, row: dict[str, str]) -> Path:
    return (
        root
        / run_set
        / f"case_{int(row['case_id']):02d}"
        / row["condition"]
        / f"replicate_{int(row['replicate_id']):02d}"
    )


def transient_failure(run_dir: Path) -> bool:
    api_log = run_dir / "api_calls.jsonl"
    if not api_log.exists():
        return False
    text = api_log.read_text(encoding="utf-8", errors="replace").upper()
    if "GENERATEREQUESTSPERDAYPERPROJECTPERMODEL-FREETIER" in text:
        return False
    return any(marker in text for marker in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))


def archive_failed_run(run_dir: Path, attempt: int) -> Path | None:
    if not run_dir.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = run_dir.with_name(f"{run_dir.name}_failed_batch_attempt_{attempt:02d}_{stamp}")
    suffix = 1
    while destination.exists():
        destination = run_dir.with_name(
            f"{run_dir.name}_failed_batch_attempt_{attempt:02d}_{stamp}_{suffix:02d}"
        )
        suffix += 1
    run_dir.rename(destination)
    return destination


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    rows = read_registry(root / "audit" / f"run_registry_{args.policy}.csv")
    selected = [row for row in rows if row["status"] == "PLANNED"]
    configured_cases: set[int] | None = None
    if args.case_config:
        config_path = args.case_config.resolve()
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot read case config {config_path}: {exc}") from exc
        configured = config.get("selected_case_ids")
        if not isinstance(configured, list) or not configured:
            raise SystemExit("Case config must contain a non-empty selected_case_ids list")
        if any(not isinstance(case_id, int) or not 1 <= case_id <= 30 for case_id in configured):
            raise SystemExit("Every selected_case_ids entry must be an integer from 1 to 30")
        if len(configured) != len(set(configured)):
            raise SystemExit("selected_case_ids contains duplicates")
        configured_cases = set(configured)
        selected = [row for row in selected if int(row["case_id"]) in configured_cases]
    if args.case:
        selected = [row for row in selected if int(row["case_id"]) in set(args.case)]
    if args.condition:
        selected = [row for row in selected if row["condition"] in set(args.condition)]
    if args.replicate:
        selected = [row for row in selected if int(row["replicate_id"]) in set(args.replicate)]
    skipped_complete = [row for row in selected if is_complete(root, args.run_set, row)]
    selected = [row for row in selected if not is_complete(root, args.run_set, row)]

    total_calls = sum(int(row["logical_generation_calls"]) for row in selected)
    if not args.execute:
        by_condition: dict[str, dict[str, int]] = {}
        for row in selected:
            item = by_condition.setdefault(row["condition"], {"runs": 0, "calls": 0})
            item["runs"] += 1
            item["calls"] += int(row["logical_generation_calls"])
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "policy": args.policy,
                    "case_config": str(args.case_config.resolve()) if args.case_config else None,
                    "configured_case_ids": sorted(configured_cases) if configured_cases else None,
                    "selected_runs": len(selected),
                    "expected_generation_calls": total_calls,
                    "skipped_complete_runs": len(skipped_complete),
                    "by_condition": by_condition,
                    "first_run_ids": [row["run_id"] for row in selected[:20]],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.max_runs < 1:
        raise SystemExit("--max-runs must be positive")
    if args.run_retries < 0:
        raise SystemExit("--run-retries must be non-negative")
    if not 0 <= args.retry_delay_seconds <= 60:
        raise SystemExit("--retry-delay-seconds must be between 0 and 60")
    selected = selected[: args.max_runs]
    failures = []
    attempt_counts: dict[str, int] = {}
    for row in selected:
        command = [
            sys.executable,
            str(root / "tools" / "run_condition.py"),
            "--case",
            row["case_id"],
            "--condition",
            row["condition"],
            "--replicate",
            row["replicate_id"],
            "--model",
            args.model,
            "--backend",
            args.backend,
            "--run-set",
            args.run_set,
            "--execute",
        ]
        if args.backend != "developer":
            command.extend(["--vertex-location", args.vertex_location])
            if args.vertex_project:
                command.extend(["--vertex-project", args.vertex_project])
        if args.thinking_level:
            command.extend(["--thinking-level", args.thinking_level])
        run_dir = run_directory(root, args.run_set, row)
        result = None
        for attempt in range(1, args.run_retries + 2):
            attempt_counts[row["run_id"]] = attempt
            result = subprocess.run(command, cwd=root)
            if result.returncode == 0:
                break
            is_transient = transient_failure(run_dir)
            archive_failed_run(run_dir, attempt)
            if not is_transient or attempt > args.run_retries:
                break
            time.sleep(args.retry_delay_seconds)
        if result is None or result.returncode != 0:
            failures.append(row["run_id"])
            if not args.continue_on_error:
                break
    print(
        json.dumps(
            {
                "attempted_runs": len(selected),
                "failures": failures,
                "run_attempt_counts": attempt_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
