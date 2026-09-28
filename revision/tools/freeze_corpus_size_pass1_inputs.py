from __future__ import annotations

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
    root = Path(__file__).resolve().parents[1]
    packet_dir = root / "evaluation" / "blind_packets_corpus_size_sensitivity_v1"
    output = root / "evaluation" / "corpus_size_pass1_input_integrity_manifest_v1.json"

    packets = sorted(packet_dir.glob("case_*__rep_*.md"))
    if len(packets) != 12:
        raise RuntimeError(f"Expected 12 packets, found {len(packets)}")

    build_summary_path = packet_dir / "build_summary.json"
    build_summary = json.loads(build_summary_path.read_text(encoding="utf-8"))
    if (
        build_summary.get("status") != "PASS"
        or build_summary.get("packets") != 12
        or build_summary.get("candidates") != 48
        or build_summary.get("candidate_body_hash_matches") != 48
        or build_summary.get("alias_balance_passed") is not True
    ):
        raise RuntimeError("Packet build summary is not a passing 12-packet/48-candidate build")

    fixed = [
        root / "protocol" / "corpus_size_sensitivity_terra_runbook_v1.md",
        root / "config" / "corpus_size_sensitivity_v1.json",
        root / "config" / "independent_judge_sonnet5_pass1_corpus_size_v1.json",
        root / "evaluation" / "judge_prompt_pass1_component_controls_4condition_v1.md",
        root / "evaluation" / "independent_judge_main_output_schema_4condition_v1.json",
        root / "evaluation" / "supplementary_evaluation_module_v1.md",
        root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt",
        root / "tools" / "build_corpus_size_pass1_packets.py",
        root / "tools" / "validate_pass1_component_controls.py",
        root / "tools" / "run_pass1_component_controls_anthropic.py",
        root / "tools" / "run_independent_judge_anthropic_v3.py",
        root / "tools" / "freeze_corpus_size_pass1_inputs.py",
        root / "runs_corpus_size_sensitivity_v1" / "batch_status.json",
        build_summary_path,
        packet_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
        packet_dir / "hash_validation.csv",
    ]
    missing = [str(path) for path in fixed if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing frozen input files: {missing}")

    source_files: list[Path] = []
    for case_id in (2, 4, 15, 29):
        for corpus_size in (100, 250, 500, 1000):
            for replicate_id in (1, 2, 3):
                run_dir = (
                    root
                    / "runs_corpus_size_sensitivity_v1"
                    / f"case_{case_id:02d}"
                    / f"corpus_{corpus_size:04d}"
                    / f"replicate_{replicate_id:02d}"
                )
                source_files.extend([run_dir / "run_manifest.json", run_dir / "final.txt"])

    source_missing = [str(path) for path in source_files if not path.exists()]
    if source_missing:
        raise RuntimeError(f"Missing generation source files: {source_missing}")

    manifest = {
        "status": "FROZEN_AFTER_GENERATION_BEFORE_ANY_CORPUS_SIZE_PASS1_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": 12,
        "candidate_count": 48,
        "corpus_sizes": [100, 250, 500, 1000],
        "cases": [2, 4, 15, 29],
        "replicates": [1, 2, 3],
        "evaluator_protocol": "unchanged official Anthropic Pass 1 four-candidate implementation",
        "fixed_files": [record(root, path) for path in fixed],
        "generation_sources": [record(root, path) for path in source_files],
        "packets": [record(root, path) for path in packets],
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "packets": len(packets),
                "generation_source_files": len(source_files),
                "fixed_files": len(fixed),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
