from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from litm_common import atomic_write_json, read_json, sha256_file


CONFIG_ID = "independent_judge_sonnet5_pass1_litm_v1"
OFFICIAL_ENDPOINT = "https://api.anthropic.com/v1/messages"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Resume-safe direct-Anthropic LITM Pass 1 batch runner")
    parser.add_argument("--config", type=Path, default=root / "config" / f"{CONFIG_ID}.json")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-packets", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    return parser.parse_args()


def result_status(result_root: Path, packet_id: str) -> str:
    manifest_path = result_root / packet_id / "run_manifest.json"
    scores_path = result_root / packet_id / "accepted_scores.json"
    if not manifest_path.exists():
        return "MISSING"
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return "INVALID"
    if manifest.get("status") == "COMPLETE" and scores_path.exists():
        return "COMPLETE"
    return str(manifest.get("status") or "INVALID")


def archive_incomplete(path: Path, result_root: Path) -> Path | None:
    if not path.exists():
        return None
    resolved = path.resolve()
    if result_root.resolve() not in resolved.parents:
        raise RuntimeError(f"Refusing to archive path outside result root: {resolved}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = path.with_name(path.name + f"_previous_incomplete_{stamp}")
    suffix = 1
    while destination.exists():
        destination = path.with_name(path.name + f"_previous_incomplete_{stamp}_{suffix:02d}")
        suffix += 1
    path.rename(destination)
    return destination


def verify_frozen_inputs(root: Path) -> None:
    manifest_path = root / "evaluation" / "litm_pass1_input_integrity_manifest_v1.json"
    manifest = read_json(manifest_path)
    if manifest.get("status") != "FROZEN_AFTER_GENERATION_BEFORE_ANY_LITM_PASS1_CALL":
        raise RuntimeError("LITM Pass 1 input integrity manifest is not frozen")
    records = [
        *manifest["fixed_files"],
        *manifest["generation_sources"],
        *manifest["packets"],
        *manifest["transport_dry_run_files"],
    ]
    for record in records:
        path = (root / str(record["path"])).resolve()
        if not path.exists() or sha256_file(path) != record["sha256"]:
            raise RuntimeError(f"Frozen LITM Pass 1 input mismatch: {path}")


def status_payload(
    config_path: Path,
    config: dict[str, Any],
    packet_paths: list[Path],
    result_root: Path,
    active_packet: str | None,
    failures: list[str],
) -> dict[str, Any]:
    rows = [
        {"order": index, "packet_id": packet.stem, "status": result_status(result_root, packet.stem)}
        for index, packet in enumerate(packet_paths, start=1)
    ]
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {
        "updated_utc": utc_now(),
        "config_id": config["config_id"],
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "expected_packets": config["expected_packets"],
        "expected_candidates": config["expected_candidates"],
        "status_counts": counts,
        "active_packet": active_packet,
        "batch_failures": failures,
        "schedule": rows,
    }


def main() -> int:
    args = parse_args()
    if args.max_packets < 1:
        raise SystemExit("--max-packets must be positive")
    root = Path(__file__).resolve().parents[1]
    config_path = args.config.resolve()
    config = read_json(config_path)
    if config.get("config_id") != CONFIG_ID:
        raise SystemExit(f"Unexpected config id: {config.get('config_id')}")
    verify_frozen_inputs(root)
    packet_dir = (root / str(config["packets"])).resolve()
    result_root = (root / str(config["results"])).resolve()
    packet_paths = sorted(packet_dir.glob("case_*__rep_*.md"))
    if len(packet_paths) != int(config["expected_packets"]):
        raise SystemExit(f"Expected {config['expected_packets']} frozen packets, found {len(packet_paths)}")
    complete = [packet for packet in packet_paths if result_status(result_root, packet.stem) == "COMPLETE"]
    pending = [packet for packet in packet_paths if result_status(result_root, packet.stem) != "COMPLETE"]
    plan = {
        "dry_run": not args.execute,
        "config_id": config["config_id"],
        "expected_packets": len(packet_paths),
        "already_complete": len(complete),
        "pending_packets": len(pending),
        "first_pending": [packet.stem for packet in pending[: args.max_packets]],
        "requested_model": config["requested_model"],
        "endpoint": config["endpoint_expected"],
        "api_key_recorded": False,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.confirm_config_id != CONFIG_ID:
        raise SystemExit(f"Live execution requires --confirm-config-id {CONFIG_ID}")

    result_root.mkdir(parents=True, exist_ok=True)
    status_file = result_root / "batch_status.json"
    failures: list[str] = []
    selected = pending[: args.max_packets]
    atomic_write_json(
        status_file,
        status_payload(config_path, config, packet_paths, result_root, selected[0].stem if selected else None, failures),
    )
    for packet in selected:
        packet_id = packet.stem
        packet_output = result_root / packet_id
        if packet_output.exists() and result_status(result_root, packet_id) != "COMPLETE":
            archive_incomplete(packet_output, result_root)
        command = [
            sys.executable,
            str(root / str(config["runner"])),
            "--mode",
            "main",
            "--packet",
            str(packet),
            "--output-dir",
            str(result_root),
            "--model",
            str(config["requested_model"]),
            "--max-output-tokens",
            str(config["max_output_tokens"]),
            "--max-attempts",
            str(config["max_attempts"]),
            "--api-key-env",
            str(config["api_key_env"]),
            "--endpoint",
            OFFICIAL_ENDPOINT,
        ]
        result = subprocess.run(command, cwd=root, text=True)
        if result.returncode != 0 or result_status(result_root, packet_id) != "COMPLETE":
            failures.append(packet_id)
        atomic_write_json(
            status_file,
            status_payload(config_path, config, packet_paths, result_root, None, failures),
        )
        if failures and not args.continue_on_error:
            break
    print(
        json.dumps(
            {
                "attempted_packets": len(selected),
                "failed_packet_ids": failures,
                "status_file": str(status_file),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
