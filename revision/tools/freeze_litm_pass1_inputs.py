from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": os.path.relpath(path, root).replace("\\", "/"),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "config" / "independent_judge_sonnet5_pass1_litm_v1.json"
    config = read_json(config_path)
    packet_dir = root / str(config["packets"])
    dry_run_dir = root / str(config["dry_run_output"])
    output = root / "evaluation" / "litm_pass1_input_integrity_manifest_v1.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite frozen integrity manifest: {output}")

    packets = sorted(packet_dir.glob("case_*__rep_*.md"))
    if len(packets) != 12:
        raise RuntimeError(f"Expected 12 packets, found {len(packets)}")
    build_summary_path = packet_dir / "build_summary.json"
    build_summary = read_json(build_summary_path)
    if (
        build_summary.get("status") != "PASS"
        or build_summary.get("packets") != 12
        or build_summary.get("candidates") != 36
        or build_summary.get("candidate_body_hash_matches") != 36
        or build_summary.get("alias_balance_passed") is not True
        or build_summary.get("duplicate_candidate_packets")
        or build_summary.get("api_calls_made") != 0
    ):
        raise RuntimeError("Packet build summary is not a passing 12-packet/36-candidate build")

    expected_counts = {
        alias: {ordering: 4 for ordering in ("XYZ", "YZX", "ZXY")}
        for alias in ("Candidate A", "Candidate B", "Candidate C")
    }
    if build_summary.get("alias_ordering_counts") != expected_counts:
        raise RuntimeError("Alias-ordering balance differs from the frozen 4-per-cell design")

    dry_summary_path = dry_run_dir / "run_summary.json"
    dry_summary = read_json(dry_summary_path)
    if len(dry_summary) != 12 or any(row.get("status") != "DRY_RUN" for row in dry_summary):
        raise RuntimeError("Direct Anthropic transport dry-run did not pass all 12 packets")
    dry_files: list[Path] = [dry_summary_path]
    for packet in packets:
        packet_id = packet.stem
        schema_path = dry_run_dir / packet_id / "provider_tool_schema.json"
        request_path = dry_run_dir / packet_id / "request_payload.json"
        schema = read_json(schema_path)
        request = read_json(request_path)
        required = schema.get("required")
        if required != ["p", "a", "b", "c"] or "d" in (schema.get("properties") or {}):
            raise RuntimeError(f"Dry-run compact schema is not exactly p+a+b+c: {packet_id}")
        if request.get("model") != "claude-sonnet-5" or request.get("max_tokens") != 6000:
            raise RuntimeError(f"Dry-run model/token setting mismatch: {packet_id}")
        if request.get("tool_choice") != {"type": "tool", "name": "submit_blinded_scores"}:
            raise RuntimeError(f"Dry-run tool choice mismatch: {packet_id}")
        serialized = request_path.read_text(encoding="utf-8")
        if "Candidate D" in serialized or "all four" in serialized:
            raise RuntimeError(f"Four-candidate instruction leaked into three-candidate request: {packet_id}")
        dry_files.extend([schema_path, request_path])

    fixed = [
        root / "protocol" / "litm_pass1_evaluation_protocol_v1.md",
        root / "protocol" / "litm_pass1_runbook_v1.md",
        config_path,
        root / "config" / "lost_in_middle_position_control_v1.json",
        root / "evaluation" / "judge_prompt_pass1_component_controls_4condition_v1.md",
        root / "evaluation" / "judge_prompt_pass1_litm_3ordering_v1.md",
        root / "evaluation" / "independent_judge_main_output_schema_4condition_v1.json",
        root / "evaluation" / "independent_judge_main_output_schema_litm_3ordering_v1.json",
        root / "evaluation" / "supplementary_evaluation_module_v1.md",
        root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt",
        root / "tools" / "build_blind_packets.py",
        root / "tools" / "build_litm_pass1_packets.py",
        root / "tools" / "validate_pass1_litm.py",
        root / "tools" / "run_pass1_litm_anthropic.py",
        root / "tools" / "run_independent_judge_anthropic_v3.py",
        root / "tools" / "freeze_litm_pass1_inputs.py",
        root / "runs_lost_in_middle_position_control_v1" / "batch_status.json",
        build_summary_path,
        packet_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
        packet_dir / "hash_validation.csv",
    ]
    missing = [str(path) for path in [*fixed, *dry_files] if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing frozen input files: {missing}")

    source_files: list[Path] = []
    for case_id in (29, 1, 30, 2):
        for ordering in ("XYZ", "YZX", "ZXY"):
            for replicate_id in (1, 2, 3):
                run_dir = (
                    root
                    / "runs_lost_in_middle_position_control_v1"
                    / f"case_{case_id:02d}"
                    / f"order_{ordering}"
                    / f"replicate_{replicate_id:02d}"
                )
                source_files.extend([run_dir / "run_manifest.json", run_dir / "final.txt"])
    source_missing = [str(path) for path in source_files if not path.exists()]
    if source_missing:
        raise RuntimeError(f"Missing generation source files: {source_missing}")

    manifest = {
        "status": "FROZEN_AFTER_GENERATION_BEFORE_ANY_LITM_PASS1_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": 12,
        "candidate_count": 36,
        "orderings": ["XYZ", "YZX", "ZXY"],
        "cases": [29, 1, 30, 2],
        "replicates": [1, 2, 3],
        "alias_ordering_counts": expected_counts,
        "evaluator_protocol": "unchanged official Anthropic Pass 1 instruments and transport; candidate cardinality only adapted from A-D to A-C",
        "api_calls_made_during_preparation": 0,
        "api_key_recorded": False,
        "fixed_files": [record(root, path) for path in fixed],
        "generation_sources": [record(root, path) for path in source_files],
        "packets": [record(root, path) for path in packets],
        "transport_dry_run_files": [record(root, path) for path in dry_files],
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "packets": len(packets),
                "candidates": 36,
                "generation_source_files": len(source_files),
                "transport_dry_runs": len(dry_summary),
                "api_calls_made": 0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
