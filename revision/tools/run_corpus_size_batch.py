from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corpus_size_common import atomic_write_json, load_config, sha256_file


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume-safe batch runner for the frozen 48-output corpus-size experiment")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-runs", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--run-retries", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=float, default=60.0)
    parser.add_argument("--case", type=int, action="append")
    parser.add_argument("--corpus-size", type=int, action="append")
    parser.add_argument("--replicate", type=int, action="append")
    parser.add_argument("--vertex-project")
    return parser.parse_args()


def schedule(config: dict[str, Any]) -> list[dict[str, int]]:
    design = config["design"]
    out: list[dict[str, int]] = []
    for replicate in design["replicates"]:
        block = [
            {"case_id": int(case_id), "corpus_size": int(size), "replicate_id": int(replicate)}
            for case_id in design["selected_case_ids"]
            for size in design["corpus_sizes"]
        ]
        random.Random(int(design["execution_order_seed"]) + int(replicate)).shuffle(block)
        out.extend(block)
    return out


def run_dir(revision_root: Path, run_set: str, item: dict[str, int]) -> Path:
    return (
        revision_root
        / run_set
        / f"case_{item['case_id']:02d}"
        / f"corpus_{item['corpus_size']:04d}"
        / f"replicate_{item['replicate_id']:02d}"
    )


def manifest_status(path: Path) -> str:
    manifest = path / "run_manifest.json"
    if not manifest.exists():
        return "MISSING"
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("status") or "UNKNOWN")
    except (OSError, json.JSONDecodeError):
        return "INVALID"


def archive_failed(path: Path, attempt: int, allowed_root: Path) -> Path | None:
    if not path.exists():
        return None
    resolved = path.resolve()
    root = allowed_root.resolve()
    if root not in resolved.parents:
        raise RuntimeError(f"Refusing to move path outside run root: {resolved}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(path.name + f"_failed_attempt_{attempt:02d}_{stamp}")
    suffix = 1
    while destination.exists():
        destination = path.with_name(path.name + f"_failed_attempt_{attempt:02d}_{stamp}_{suffix:02d}")
        suffix += 1
    path.rename(destination)
    return destination


def status_payload(
    *,
    config_path: Path,
    config: dict[str, Any],
    full_schedule: list[dict[str, int]],
    revision_root: Path,
    run_set: str,
    active_item: dict[str, int] | None,
    batch_failures: list[str],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    rows = []
    for index, item in enumerate(full_schedule, start=1):
        status = manifest_status(run_dir(revision_root, run_set, item))
        counts[status] = counts.get(status, 0) + 1
        rows.append({"order": index, **item, "status": status})
    return {
        "updated_utc": utc_now(),
        "config_id": config["config_id"],
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "expected_outputs": config["design"]["expected_outputs"],
        "status_counts": counts,
        "active_item": active_item,
        "batch_failures": batch_failures,
        "schedule": rows,
    }


def main() -> int:
    args = parse_args()
    if args.max_runs < 1:
        raise SystemExit("--max-runs must be positive")
    if args.run_retries < 0:
        raise SystemExit("--run-retries must be non-negative")
    if not 0 <= args.retry_delay_seconds <= 600:
        raise SystemExit("--retry-delay-seconds must be between 0 and 600")
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    full_schedule = schedule(config)
    selected = list(full_schedule)
    if args.case:
        selected = [item for item in selected if item["case_id"] in set(args.case)]
    if args.corpus_size:
        selected = [item for item in selected if item["corpus_size"] in set(args.corpus_size)]
    if args.replicate:
        selected = [item for item in selected if item["replicate_id"] in set(args.replicate)]
    run_set = str(config["output"]["run_set"])
    run_root = revision_root / run_set
    complete = [item for item in selected if manifest_status(run_dir(revision_root, run_set, item)) == "COMPLETE"]
    pending = [item for item in selected if manifest_status(run_dir(revision_root, run_set, item)) != "COMPLETE"]
    plan = {
        "dry_run": not args.execute,
        "config_id": config["config_id"],
        "config": str(config_path),
        "schedule_seed": config["design"]["execution_order_seed"],
        "full_schedule_outputs": len(full_schedule),
        "selected_outputs": len(selected),
        "already_complete": len(complete),
        "pending_outputs": len(pending),
        "pending_minimum_generation_calls": len(pending)
        * int(config["design"]["expected_logical_generation_calls_per_output"]),
        "first_pending": pending[:10],
        "run_set": run_set,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.confirm_config_id != config["config_id"]:
        raise SystemExit(f"Live execution requires --confirm-config-id {config['config_id']}")

    selected_now = pending[: args.max_runs]
    failures: list[str] = []
    status_file = revision_root / config["output"]["batch_status_file"]
    atomic_write_json(
        status_file,
        status_payload(
            config_path=config_path,
            config=config,
            full_schedule=full_schedule,
            revision_root=revision_root,
            run_set=run_set,
            active_item=selected_now[0] if selected_now else None,
            batch_failures=failures,
        ),
    )
    for item in selected_now:
        run_id = (
            f"case_{item['case_id']:02d}__mpds__corpus_{item['corpus_size']:04d}"
            f"__rep_{item['replicate_id']:02d}"
        )
        command = [
            sys.executable,
            str(revision_root / "tools" / "run_corpus_size_condition.py"),
            "--config",
            str(config_path),
            "--case",
            str(item["case_id"]),
            "--corpus-size",
            str(item["corpus_size"]),
            "--replicate",
            str(item["replicate_id"]),
            "--execute",
        ]
        if args.vertex_project:
            command.extend(["--vertex-project", args.vertex_project])
        result: subprocess.CompletedProcess[str] | None = None
        for attempt in range(1, args.run_retries + 2):
            result = subprocess.run(command, cwd=revision_root, text=True)
            if result.returncode == 0:
                break
            archive_failed(run_dir(revision_root, run_set, item), attempt, run_root)
            if attempt <= args.run_retries:
                time.sleep(args.retry_delay_seconds)
        if result is None or result.returncode != 0:
            failures.append(run_id)
        atomic_write_json(
            status_file,
            status_payload(
                config_path=config_path,
                config=config,
                full_schedule=full_schedule,
                revision_root=revision_root,
                run_set=run_set,
                active_item=None,
                batch_failures=failures,
            ),
        )
        if failures and not args.continue_on_error:
            break
    print(
        json.dumps(
            {
                "attempted_outputs": len(selected_now),
                "failed_run_ids": failures,
                "status_file": str(status_file),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
