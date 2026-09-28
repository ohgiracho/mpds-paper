from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_deleak_pass1_packets import read_json, resolve, validated_deleaked, validated_original


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root: Path, path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Missing frozen input file: {path}")
    return {"path": os.path.relpath(path.resolve(), root).replace("\\", "/"), "sha256": sha256(path), "bytes": path.stat().st_size}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config_path = root / "config" / "independent_judge_sonnet5_pass1_deleak_pair_v1.json"
    config = read_json(config_path)
    generation_path = resolve(root, config["source_generation_config"])
    generation = read_json(generation_path)
    output = root / "evaluation" / "deleak_pass1_input_integrity_manifest_v1.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite frozen integrity manifest: {output}")
    result_root = resolve(root, config["results"])
    if result_root.exists() and list(result_root.glob("*/run_manifest.json")):
        raise RuntimeError("Evaluation results already exist; cannot label this manifest as frozen before first call")
    packet_dir = resolve(root, config["packets"])
    key_dir = resolve(root, config["blind_key_dir"])
    recovery_dir = resolve(root, config["target_recovery_packets"])
    recovery_key_dir = resolve(root, config["target_recovery_key_dir"])
    dry_dir = resolve(root, config["dry_run_output"])
    packet_paths = sorted(packet_dir.glob("case_*__rep_*.md"))
    recovery_paths = sorted(recovery_dir.glob("audit_*.md"))
    if len(packet_paths) != 9 or len(recovery_paths) != 18:
        raise RuntimeError("Expected exactly nine Pass 1 pair packets and 18 recovery packets")
    pair_summary = read_json(key_dir / "build_summary.json")
    recovery_summary = read_json(recovery_key_dir / "build_summary.json")
    if (pair_summary.get("status"), pair_summary.get("candidate_body_hash_matches"), pair_summary.get("api_calls_made")) != ("PASS", 18, 0):
        raise RuntimeError("Pair packet build did not pass")
    if (recovery_summary.get("status"), recovery_summary.get("body_hash_matches"), recovery_summary.get("api_calls_made")) != ("PASS", 18, 0):
        raise RuntimeError("Recovery packet build did not pass")
    dry_summary_path = dry_dir / "run_summary.json"
    dry_summary = json.loads(dry_summary_path.read_text(encoding="utf-8"))
    if len(dry_summary) != 9 or any(row.get("status") != "DRY_RUN" for row in dry_summary):
        raise RuntimeError("Nine-packet direct Anthropic dry-run did not pass")
    dry_files = [dry_summary_path]
    for packet in packet_paths:
        schema_path = dry_dir / packet.stem / "provider_tool_schema.json"
        request_path = dry_dir / packet.stem / "request_payload.json"
        schema = read_json(schema_path)
        request = read_json(request_path)
        if schema.get("required") != ["p", "a", "b"] or set(schema.get("properties", {})) != {"p", "a", "b"}:
            raise RuntimeError(f"Dry-run compact schema is not exactly p+a+b: {packet.stem}")
        if request.get("model") != "claude-sonnet-5" or request.get("max_tokens") != 6000:
            raise RuntimeError(f"Dry-run model/token mismatch: {packet.stem}")
        if request.get("tool_choice") != {"type": "tool", "name": "submit_blinded_scores"}:
            raise RuntimeError(f"Dry-run tool choice mismatch: {packet.stem}")
        messages = request.get("messages", [])
        if len(messages) != 1 or packet.read_text(encoding="utf-8") not in messages[0].get("content", ""):
            raise RuntimeError(f"Dry-run packet content mismatch: {packet.stem}")
        case_id = int(packet.stem.split("__")[0].split("_")[1])
        neutral_task = generation["cases"][str(case_id)]["debate_topic"]
        if f"Task: {neutral_task}" not in packet.read_text(encoding="utf-8"):
            raise RuntimeError(f"Packet does not contain frozen neutral task: {packet.stem}")
        dry_files.extend([schema_path, request_path])
    original_manifest_path = resolve(root, config["original_control_manifest"])
    with original_manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        originals = list(csv.DictReader(handle))
    if len(originals) != 9:
        raise RuntimeError("Expected nine original control rows")
    sources: list[Path] = []
    legacy_controls = 0
    for row in originals:
        case_id, rep = int(row["case_id"]), int(row["replicate_id"])
        original = validated_original(row, generation["cases"][str(case_id)])
        deleaked = validated_deleaked(root, generation, case_id, rep)
        sources.extend([original["path"], deleaked["path"], deleaked["manifest_path"]])
        if original["manifest_path"]:
            sources.append(original["manifest_path"])
        else:
            legacy_controls += 1
    if legacy_controls != 3:
        raise RuntimeError("Expected exactly three legacy replicate-1 controls without run manifests")
    fixed = [
        config_path, generation_path, original_manifest_path,
        root / "protocol" / "prompt_deleaking_targeted_v2_analysis_plan.md",
        root / "protocol" / "prompt_deleaking_target_recovery_rubric_v1.md",
        root / "protocol" / "deleak_pass1_runbook_v1.md",
        root / "evaluation" / "judge_prompt_pass1_deleak_pair_v1.md",
        root / "evaluation" / "independent_judge_main_output_schema_deleak_pair_v1.json",
        root / "evaluation" / "supplementary_evaluation_module_v1.md",
        root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt",
        root / "tools" / "build_blind_packets.py",
        root / "tools" / "build_deleak_pass1_packets.py",
        root / "tools" / "build_deleak_recovery_packets.py",
        root / "tools" / "validate_pass1_deleak_pair.py",
        root / "tools" / "validate_pass1_litm.py",
        root / "tools" / "run_pass1_deleak_anthropic.py",
        root / "tools" / "run_independent_judge_anthropic_v3.py",
        root / "tools" / "run_deleak_pass1_batch.py",
        root / "tools" / "run_litm_pass1_batch.py",
        root / "tools" / "freeze_deleak_pass1_inputs.py",
        key_dir / "build_summary.json",
        key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
        key_dir / "hash_validation.csv",
        recovery_key_dir / "build_summary.json",
        recovery_key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
    ]
    integrity = {
        "status": "FROZEN_BEFORE_ANY_DELEAK_PASS1_API_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cases": [1, 8, 22], "replicates": [1, 2, 3],
        "pair_packets": 9, "pass1_candidates": 18, "target_recovery_packets": 18,
        "legacy_original_controls_without_run_manifest": legacy_controls,
        "api_calls_made_during_preparation": 0,
        "api_key_recorded": False,
        "fixed_files": [record(root, path) for path in fixed],
        "generation_sources": [record(root, path) for path in sources],
        "packets": [record(root, path) for path in packet_paths],
        "recovery_packets": [record(root, path) for path in recovery_paths],
        "transport_dry_run_files": [record(root, path) for path in dry_files],
    }
    output.write_text(json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "pair_packets": 9, "candidates": 18, "recovery_packets": 18, "dry_runs": 9, "legacy_controls_without_manifests": legacy_controls, "api_calls_made": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
