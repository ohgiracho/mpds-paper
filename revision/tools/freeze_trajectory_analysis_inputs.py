from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trajectory_common import load_config, read_csv, resolve_from_root, sha256_file, write_json
from validate_trajectory_analysis_setup import validate_setup


def artifact(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display = str(resolved.relative_to(root))
    except ValueError:
        display = str(resolved)
    return {"path": display, "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze trajectory inputs before any evaluator call")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(root, args.config)
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    output = analysis_dir / "trajectory_input_integrity_manifest.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite frozen integrity manifest: {output}")
    validation = validate_setup(root, config_path)
    if validation["status"] != "PASS" or validation["existing_complete_packets"] or validation["existing_failed_packets"]:
        raise RuntimeError(f"Inputs are not eligible for pre-call freezing: {json.dumps(validation, ensure_ascii=False)}")

    fixed_paths = [
        config_path,
        root / "protocol" / "trajectory_analysis_protocol_v1.md",
        analysis_dir / "trajectory_evaluation_prompt_frozen.txt",
        analysis_dir / "trajectory_rubric_frozen.json",
        analysis_dir / "trajectory_output_schema_frozen.json",
        analysis_dir / "trajectory_input_manifest.csv",
        analysis_dir / "trajectory_packet_build_summary.json",
        root / "tools" / "trajectory_common.py",
        root / "tools" / "build_trajectory_analysis_packets.py",
        root / "tools" / "validate_trajectory_analysis_setup.py",
        root / "tools" / "run_trajectory_analysis_anthropic.py",
        root / "tools" / "analyze_trajectory_evaluations.py",
        root / "tools" / "freeze_trajectory_analysis_inputs.py",
        root / "protocol" / "trajectory_analysis_runbook_v1.md",
    ]
    for path in fixed_paths:
        if not path.exists():
            raise RuntimeError(f"Fixed file missing: {path}")

    rows = read_csv(analysis_dir / "trajectory_input_manifest.csv")
    packet_paths = sorted({Path(row["evaluation_packet"]) for row in rows})
    source_pairs: dict[str, str] = {}
    for row in rows:
        paths = json.loads(row["source_paths_json"])
        hashes = json.loads(row["source_hashes_json"])
        for path, expected_hash in zip(paths, hashes, strict=True):
            previous = source_pairs.setdefault(path, expected_hash)
            if previous != expected_hash:
                raise RuntimeError(f"Conflicting source hashes: {path}")
    source_files: list[dict[str, Any]] = []
    for value, expected_hash in sorted(source_pairs.items()):
        item = artifact(root, Path(value))
        if item["sha256"] != expected_hash:
            raise RuntimeError(f"Source changed before freeze: {value}")
        source_files.append(item)

    payload = {
        "status": "FROZEN_BEFORE_ANY_TRAJECTORY_EVALUATION_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_id": config["config_id"],
        "analysis_character": config["analysis_character"],
        "expected_packets": config["expected_packets"],
        "expected_trajectories": config["expected_trajectories"],
        "requested_model": config["evaluator"]["requested_model"],
        "temperature_override": config["evaluator"]["temperature_override"],
        "validator": validation,
        "fixed_files": [artifact(root, path) for path in fixed_paths],
        "packets": [artifact(root, path) for path in packet_paths],
        "source_files": source_files,
        "prompt_sha256": sha256_file(analysis_dir / "trajectory_evaluation_prompt_frozen.txt"),
        "rubric_sha256": sha256_file(analysis_dir / "trajectory_rubric_frozen.json"),
        "schema_sha256": sha256_file(analysis_dir / "trajectory_output_schema_frozen.json"),
        "api_key_recorded": False,
        "api_calls_made_before_freeze": 0,
    }
    write_json(output, payload)
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "fixed_files": len(payload["fixed_files"]),
                "packets": len(payload["packets"]),
                "source_files": len(payload["source_files"]),
                "api_calls_made": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
