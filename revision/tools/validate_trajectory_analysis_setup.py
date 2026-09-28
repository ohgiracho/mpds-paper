from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from trajectory_common import ALIASES, CONDITIONS, DIMENSIONS, load_config, read_csv, resolve_from_root, sha256_file


def environment_available(name: str) -> bool:
    if os.environ.get(name, "").strip():
        return True
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
            return bool(str(value).strip())
        except (FileNotFoundError, OSError):
            return False
    return False


def validate_setup(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    resolved_config, config = load_config(root, config_path)
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    packet_dir = resolve_from_root(root, config["packet_directory"])
    input_manifest = analysis_dir / "trajectory_input_manifest.csv"
    build_summary_path = analysis_dir / "trajectory_packet_build_summary.json"
    prompt_path = analysis_dir / "trajectory_evaluation_prompt_frozen.txt"
    rubric_path = analysis_dir / "trajectory_rubric_frozen.json"
    schema_path = analysis_dir / "trajectory_output_schema_frozen.json"
    errors: list[str] = []

    for path in (resolved_config, input_manifest, build_summary_path, prompt_path, rubric_path, schema_path):
        if not path.exists():
            errors.append(f"Missing required file: {path}")
    if errors:
        return {"status": "FAIL", "phase": "NOT_READY", "errors": errors, "api_calls_made": 0}

    rows = read_csv(input_manifest)
    expected_trajectories = int(config["expected_trajectories"])
    expected_packets = int(config["expected_packets"])
    if len(rows) != expected_trajectories:
        errors.append(f"Expected {expected_trajectories} manifest rows, found {len(rows)}")
    if len({row["trajectory_id"] for row in rows}) != len(rows):
        errors.append("Trajectory IDs are not unique")
    if len({row["trajectory_sha256"] for row in rows}) != len(rows):
        errors.append("Normalized trajectory hashes are not unique")

    packet_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    alias_counts: dict[str, Counter[str]] = {alias: Counter() for alias in ALIASES}
    source_files_checked: set[tuple[str, str]] = set()
    for row in rows:
        packet_rows[row["packet_id"]].append(row)
        alias = row["blind_condition_label"]
        condition = row["condition"]
        if alias not in ALIASES or condition not in CONDITIONS:
            errors.append(f"Invalid alias or condition: {row['trajectory_id']}")
        else:
            alias_counts[alias][condition] += 1
        try:
            source_paths = json.loads(row["source_paths_json"])
            source_hashes = json.loads(row["source_hashes_json"])
        except json.JSONDecodeError:
            errors.append(f"Invalid source JSON: {row['trajectory_id']}")
            continue
        if len(source_paths) != len(source_hashes) or not source_paths:
            errors.append(f"Source path/hash mismatch: {row['trajectory_id']}")
            continue
        for value, expected_hash in zip(source_paths, source_hashes, strict=True):
            path = Path(value)
            key = (str(path), expected_hash)
            if key in source_files_checked:
                continue
            source_files_checked.add(key)
            if not path.exists():
                errors.append(f"Missing source file: {path}")
            elif sha256_file(path) != expected_hash:
                errors.append(f"Source hash mismatch: {path}")
        packet_path = Path(row["evaluation_packet"])
        if not packet_path.exists():
            errors.append(f"Missing packet: {packet_path}")
        elif sha256_file(packet_path) != row["evaluation_packet_sha256"]:
            errors.append(f"Packet hash mismatch: {packet_path}")

    if len(packet_rows) != expected_packets:
        errors.append(f"Expected {expected_packets} packets in manifest, found {len(packet_rows)}")
    for packet_id, group in sorted(packet_rows.items()):
        if len(group) != len(CONDITIONS):
            errors.append(f"Packet does not have four trajectories: {packet_id}")
        if {row["blind_condition_label"] for row in group} != set(ALIASES):
            errors.append(f"Packet aliases incomplete: {packet_id}")
        if {row["condition"] for row in group} != set(CONDITIONS):
            errors.append(f"Packet conditions incomplete: {packet_id}")
        if len({row["evaluation_packet_sha256"] for row in group}) != 1:
            errors.append(f"Packet hash differs within manifest rows: {packet_id}")

    lower = expected_packets // len(CONDITIONS)
    upper = lower + (1 if expected_packets % len(CONDITIONS) else 0)
    alias_balance = all(
        lower <= alias_counts[alias][condition] <= upper
        for alias in ALIASES
        for condition in CONDITIONS
    )
    if not alias_balance:
        errors.append("Alias/condition balance failed")

    rubric = json.loads(rubric_path.read_text(encoding="utf-8"))
    if set(rubric.get("dimensions", {})) != set(DIMENSIONS):
        errors.append("Frozen rubric dimensions do not match the analysis dimensions")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    required_item = set(schema["properties"]["trajectory_evaluations"]["items"]["required"])
    if not set(DIMENSIONS).issubset(required_item):
        errors.append("Frozen schema is missing one or more dimensions")
    build_summary = json.loads(build_summary_path.read_text(encoding="utf-8"))
    if build_summary.get("status") != "PASS":
        errors.append("Packet build summary is not PASS")

    judge_root = resolve_from_root(root, config["judge_run_directory"])
    complete = 0
    failed = 0
    if judge_root.exists():
        for manifest in judge_root.glob("case_*__rep_*/run_manifest.json"):
            status = json.loads(manifest.read_text(encoding="utf-8")).get("status")
            complete += status == "COMPLETE"
            failed += status == "FAILED"

    return {
        "status": "PASS" if not errors else "FAIL",
        "phase": "READY_FOR_EVALUATION" if not errors else "NOT_READY",
        "config_id": config["config_id"],
        "packets": len(packet_rows),
        "trajectories": len(rows),
        "unique_source_files_checked": len(source_files_checked),
        "source_kinds": dict(Counter(row["source_kind"] for row in rows)),
        "stage_counts": {
            condition: sorted({int(row["stage_count"]) for row in rows if row["condition"] == condition})
            for condition in CONDITIONS
        },
        "alias_condition_counts": {alias: dict(alias_counts[alias]) for alias in ALIASES},
        "alias_balance_passed": alias_balance,
        "prompt_sha256": sha256_file(prompt_path),
        "rubric_sha256": sha256_file(rubric_path),
        "schema_sha256": sha256_file(schema_path),
        "credentials": {"anthropic_api_key_available": environment_available(config["evaluator"]["api_key_env"])},
        "existing_complete_packets": complete,
        "existing_failed_packets": failed,
        "pending_packets": expected_packets - complete,
        "errors": errors,
        "api_calls_made": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate frozen trajectory-analysis inputs without API calls")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = validate_setup(root, args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
