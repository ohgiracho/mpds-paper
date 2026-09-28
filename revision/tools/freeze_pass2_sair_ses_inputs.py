from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record(root: Path, path: Path) -> dict[str, Any]:
    return {
        "path": os.path.relpath(path, root).replace("\\", "/"),
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_evidence_rows(rows: list[dict[str, str]]) -> list[tuple[str, ...]]:
    fields = (
        "cited_id",
        "source_pool",
        "source_original_id",
        "resolution_status",
        "title",
        "doi",
        "openalex_id",
    )
    return sorted(tuple(row[field] for field in fields) for row in rows)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    filtered_dir = root / "evaluation" / "evidence_audit_packets_component_controls_sair_ses_v1"
    full_dir = root / "evaluation" / "evidence_audit_packets_component_controls_core10_n3_4condition_v1"
    component_blind_dir = root / "evaluation" / "blind_packets_component_controls_core10_n3_4condition_v1"
    old_evidence_dir = root / "evaluation" / "evidence_audit_packets_core10_n3_v2"
    old_blind_dir = root / "evaluation" / "blind_packets_core10_n3_v3"
    output = root / "evaluation" / "pass2_sair_ses_input_integrity_manifest_v1.json"

    summary = json.loads((filtered_dir / "build_summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "PASS" or summary.get("packets") != 30 or summary.get("candidates") != 60:
        raise RuntimeError("Filtered SAIR/SES build is not a passing 30-packet/60-candidate build")
    full_summary = json.loads((full_dir / "build_summary.json").read_text(encoding="utf-8"))
    if full_summary.get("status") != "PASS" or full_summary.get("candidates") != 120:
        raise RuntimeError("Full four-condition evidence build is not PASS")

    packets = sorted(filtered_dir.glob("case_*__rep_*.md"))
    if len(packets) != 30:
        raise RuntimeError(f"Expected 30 filtered packets, found {len(packets)}")

    component_key = read_csv(component_blind_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv")
    source_rows = [row for row in component_key if row["condition"] in {"sair", "ses"}]
    source_files = [Path(row["source_file"]) for row in source_rows]
    if len(source_files) != 60 or any(not path.exists() for path in source_files):
        raise RuntimeError("Expected 60 existing SAIR/SES source files")
    for row, path in zip(source_rows, source_files):
        if sha256(path) != row["source_file_sha256"].lower():
            raise RuntimeError(f"Source hash mismatch: {path}")

    old_component_key = read_csv(old_blind_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv")
    old_source = {
        (row["packet_id"], row["condition"]): row
        for row in old_component_key
        if row["condition"] in {"ds", "mpds"}
    }
    new_source = {
        (row["packet_id"], row["condition"]): row
        for row in component_key
        if row["condition"] in {"ds", "mpds"}
    }
    source_matches = sum(
        old_source[key]["source_file_sha256"] == row["source_file_sha256"]
        for key, row in new_source.items()
        if key in old_source
    )

    old_evidence_rows = read_csv(old_evidence_dir / "evidence_audit_key_DO_NOT_SHARE_WITH_RATERS.csv")
    new_evidence_rows = read_csv(full_dir / "evidence_audit_key_DO_NOT_SHARE_WITH_RATERS.csv")
    evidence_matches = 0
    for key in sorted(new_source):
        packet_id, condition = key
        old_group = [
            row
            for row in old_evidence_rows
            if row["packet_id"] == packet_id and row["condition"] == condition
        ]
        new_group = [
            row
            for row in new_evidence_rows
            if row["packet_id"] == packet_id and row["condition"] == condition
        ]
        evidence_matches += canonical_evidence_rows(old_group) == canonical_evidence_rows(new_group)

    old_build = json.loads((old_evidence_dir / "build_summary.json").read_text(encoding="utf-8"))
    knowledge_matches = sum(
        old_build["case_evidence"].get(case_id) == case_data
        for case_id, case_data in full_summary["case_evidence"].items()
    )
    if source_matches != 60 or evidence_matches != 60 or knowledge_matches != 10:
        raise RuntimeError(
            f"DS/MPDS reuse audit failed: source={source_matches}, evidence={evidence_matches}, knowledge={knowledge_matches}"
        )

    fixed = [
        root / "evaluation" / "judge_prompt_pass2_single_candidate_v1.md",
        root / "evaluation" / "supplementary_evaluation_module_v1.md",
        root / "evaluation" / "evidence_audit_output_schema_v1.json",
        root / "tools" / "build_evidence_audit_packets.py",
        root / "tools" / "build_evidence_audit_packets_4condition.py",
        root / "tools" / "filter_pass2_sair_ses_packets.py",
        root / "tools" / "run_pass2_split_anthropic.py",
        root / "tools" / "run_pass2_split_anthropic_subset.py",
        root / "tools" / "validate_judge_outputs.py",
        root / "tools" / "freeze_pass2_sair_ses_inputs.py",
        full_dir / "build_summary.json",
        full_dir / "evidence_audit_key_DO_NOT_SHARE_WITH_RATERS.csv",
        full_dir / "citation_occurrence_audit_DO_NOT_SHARE_WITH_RATERS.csv",
        filtered_dir / "build_summary.json",
        filtered_dir / "selection_key_DO_NOT_SHARE_WITH_RATERS.csv",
        component_blind_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
    ]
    missing = [str(path) for path in fixed if not path.exists()]
    if missing:
        raise RuntimeError(f"Missing fixed files: {missing}")

    manifest = {
        "status": "FROZEN_BEFORE_ANY_SAIR_SES_PASS2_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": 30,
        "new_candidate_calls_planned": 60,
        "conditions": ["sair", "ses"],
        "evaluator_protocol": (
            "same official split single-candidate Anthropic Pass 2 prompt, schema, tool call, "
            "normalization, and candidate validation; thin alias-subset input adapter only"
        ),
        "ds_mpds_reuse_audit": {
            "source_output_sha256_matches": source_matches,
            "evidence_record_group_matches": evidence_matches,
            "case_knowledge_snapshot_matches": knowledge_matches,
            "decision": "REUSE_EXISTING_OFFICIAL_DS_MPDS_PASS2_RESULTS",
        },
        "fixed_files": [record(root, path) for path in fixed],
        "source_outputs": [record(root, path) for path in source_files],
        "packets": [record(root, path) for path in packets],
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "fixed_files": len(fixed),
                "source_outputs": len(source_files),
                "packets": len(packets),
                "ds_mpds_reuse_audit": manifest["ds_mpds_reuse_audit"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
