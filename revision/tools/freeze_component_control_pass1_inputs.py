from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": os.path.relpath(path, root).replace("\\", "/"),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze four-condition component-control Pass 1 inputs")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--packet-dir",
        type=Path,
        default=root / "evaluation" / "blind_packets_component_controls_core10_n3_4condition_v1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "evaluation" / "component_control_pass1_input_integrity_manifest_v1.json",
    )
    parser.add_argument(
        "--status",
        default="FROZEN_BEFORE_ANY_COMPONENT_CONTROL_PASS1_CALL",
        help="Human-readable freeze status recorded in the manifest.",
    )
    args = parser.parse_args()

    packet_dir = args.packet_dir.resolve()
    packets = sorted(packet_dir.glob("case_*__rep_*.md"))
    if len(packets) != 30:
        raise RuntimeError(f"Expected 30 packets, found {len(packets)}")
    build_summary_path = packet_dir / "build_summary.json"
    build_summary = json.loads(build_summary_path.read_text(encoding="utf-8"))
    if build_summary.get("status") != "PASS" or build_summary.get("candidates") != 120:
        raise RuntimeError("Packet build summary is not a passing 120-candidate build")

    fixed = [
        root / "protocol" / "component_control_evaluation_amendment_v1.md",
        root / "config" / "independent_judge_sonnet5_pass1_component_controls_v1.json",
        root / "evaluation" / "judge_prompt_pass1_component_controls_4condition_v1.md",
        root / "evaluation" / "independent_judge_main_output_schema_4condition_v1.json",
        root / "evaluation" / "supplementary_evaluation_module_v1.md",
        root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt",
        root / "tools" / "build_component_control_pass1_packets.py",
        root / "tools" / "validate_pass1_component_controls.py",
        root / "tools" / "run_pass1_component_controls_anthropic.py",
        root / "tools" / "run_independent_judge_anthropic_v3.py",
        root / "tools" / "freeze_component_control_pass1_inputs.py",
        build_summary_path,
        packet_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
    ]
    missing = [str(path) for path in fixed if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing frozen input files: {missing}")

    manifest = {
        "status": args.status,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": len(packets),
        "candidate_count": 120,
        "conditions": ["ds", "mpds", "sair", "ses"],
        "fixed_files": [record(root, path) for path in fixed],
        "packets": [record(root, path) for path in packets],
    }
    output = args.output.resolve()
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(output), "packets": len(packets)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
