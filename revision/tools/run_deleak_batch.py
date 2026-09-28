from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from deleak_common import (
    assert_litm_gate_open,
    atomic_write_json,
    frozen_schedule,
    litm_gate_status,
    load_deleak_config,
    manifest_status,
    output_directory,
    sha256_file,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resume-safe batch runner for targeted prompt de-leaking")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-runs", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--run-retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=60.0)
    parser.add_argument("--case", type=int, action="append")
    parser.add_argument("--replicate", type=int, action="append")
    return parser.parse_args()


def archive_failed(path: Path, attempt: int, allowed_root: Path) -> Path | None:
    if not path.exists():
        return None
    resolved = path.resolve()
    root = allowed_root.resolve()
    if root not in resolved.parents:
        raise RuntimeError(f"Refusing to move path outside the de-leaking run root: {resolved}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(path.name + f"_failed_attempt_{attempt:02d}_{stamp}")
    suffix = 1
    while destination.exists():
        destination = path.with_name(path.name + f"_failed_attempt_{attempt:02d}_{stamp}_{suffix:02d}")
        suffix += 1
    path.rename(destination)
    return destination


def status_payload(
    revision_root: Path,
    config_path: Path,
    config: dict[str, Any],
    full_schedule: list[dict[str, int]],
    active_item: dict[str, int] | None,
    failures: list[str],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for index, item in enumerate(full_schedule, start=1):
        status = manifest_status(output_directory(revision_root, config, item["case_id"], item["replicate_id"]))
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
        "batch_failures": failures,
        "litm_execution_gate": litm_gate_status(revision_root, config),
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
    config_path, config = load_deleak_config(revision_root, args.config)
    full_schedule = frozen_schedule(config)
    if len(full_schedule) != int(config["design"]["expected_outputs"]):
        raise SystemExit("Frozen execution order does not match expected output count")
    selected = list(full_schedule)
    if args.case:
        selected = [item for item in selected if item["case_id"] in set(args.case)]
    if args.replicate:
        selected = [item for item in selected if item["replicate_id"] in set(args.replicate)]
    complete = [
        item
        for item in selected
        if manifest_status(output_directory(revision_root, config, item["case_id"], item["replicate_id"])) == "COMPLETE"
    ]
    pending = [
        item
        for item in selected
        if manifest_status(output_directory(revision_root, config, item["case_id"], item["replicate_id"])) != "COMPLETE"
    ]
    plan = {
        "dry_run": not args.execute,
        "config_id": config["config_id"],
        "config": str(config_path),
        "full_schedule_outputs": len(full_schedule),
        "selected_outputs": len(selected),
        "already_complete": len(complete),
        "pending_outputs": len(pending),
        "pending_minimum_generation_calls": len(pending)
        * int(config["design"]["expected_logical_generation_calls_per_output"]),
        "first_pending": pending[:10],
        "run_set": config["output"]["run_set"],
        "litm_execution_gate": litm_gate_status(revision_root, config),
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.confirm_config_id != config["config_id"]:
        raise SystemExit(f"Live execution requires --confirm-config-id {config['config_id']}")
    assert_litm_gate_open(revision_root, config)

    selected_now = pending[: args.max_runs]
    failures: list[str] = []
    run_root = revision_root / str(config["output"]["run_set"])
    status_file = revision_root / str(config["output"]["batch_status_file"])
    atomic_write_json(
        status_file,
        status_payload(revision_root, config_path, config, full_schedule, selected_now[0] if selected_now else None, failures),
    )
    for item in selected_now:
        run_id = f"case_{item['case_id']:02d}__mpds_deleaked__rep_{item['replicate_id']:02d}"
        command = [
            sys.executable,
            str(revision_root / "tools" / "run_deleak_condition.py"),
            "--config",
            str(config_path),
            "--case",
            str(item["case_id"]),
            "--replicate",
            str(item["replicate_id"]),
            "--execute",
            "--confirm-config-id",
            str(config["config_id"]),
        ]
        result: subprocess.CompletedProcess[str] | None = None
        for attempt in range(1, args.run_retries + 2):
            result = subprocess.run(command, cwd=revision_root, text=True)
            if result.returncode == 0:
                break
            archive_failed(
                output_directory(revision_root, config, item["case_id"], item["replicate_id"]),
                attempt,
                run_root,
            )
            if attempt <= args.run_retries:
                time.sleep(args.retry_delay_seconds)
        if result is None or result.returncode != 0:
            failures.append(run_id)
        atomic_write_json(
            status_file,
            status_payload(revision_root, config_path, config, full_schedule, None, failures),
        )
        if failures and not args.continue_on_error:
            break
    print(
        json.dumps(
            {"attempted_outputs": len(selected_now), "failed_run_ids": failures, "status_file": str(status_file)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
