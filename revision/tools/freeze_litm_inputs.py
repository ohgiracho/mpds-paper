from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from litm_common import load_config, pool_manifest_path, read_json, sha256_file
from run_condition import find_script, load_case


def artifact(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display = str(resolved.relative_to(root)).replace("\\", "/")
    except ValueError:
        display = str(resolved)
    return {"path": display, "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def main() -> int:
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root)
    child_environment = os.environ.copy()
    child_environment["PYTHONIOENCODING"] = "utf-8"
    validation = subprocess.run(
        [sys.executable, str(revision_root / "tools" / "validate_litm_setup.py"), "--config", str(config_path)],
        cwd=revision_root,
        env=child_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if validation.returncode != 0:
        raise RuntimeError(f"Cannot freeze invalid setup: {validation.stdout}\n{validation.stderr}")
    validation_report = json.loads(validation.stdout)
    if validation_report.get("status") != "PASS" or validation_report.get("api_calls_made") != 0:
        raise RuntimeError("Validator did not return a zero-API PASS")

    fixed_paths = [
        config_path,
        revision_root / "protocol" / "lost_in_middle_position_control_protocol_v1.md",
        revision_root / "protocol" / "lost_in_middle_position_control_runbook_v1.md",
        revision_root / "tools" / "litm_common.py",
        revision_root / "tools" / "prepare_litm_inputs.py",
        revision_root / "tools" / "run_litm_mpds_adapter.py",
        revision_root / "tools" / "run_litm_condition.py",
        revision_root / "tools" / "run_litm_batch.py",
        revision_root / "tools" / "validate_litm_setup.py",
        revision_root / "tools" / "analyze_litm_evidence_utilization.py",
        revision_root / "tools" / "freeze_litm_inputs.py",
        revision_root / "runtime" / "sitecustomize.py",
        revision_root / str(config["inputs"]["audit_manifest"]),
        revision_root / "lost_in_middle_inputs_v1" / "case_selection_audit.csv",
        revision_root / "lost_in_middle_inputs_v1" / "build_summary.json",
    ]
    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    source_scripts: list[dict[str, Any]] = []
    case_contexts: list[dict[str, Any]] = []
    source_evidence: list[dict[str, Any]] = []
    generated_inputs: list[dict[str, Any]] = []
    seen_sources: set[Path] = set()
    for case_id in config["design"]["selected_case_ids"]:
        source_script = find_script(repo, revision_root, int(case_id), "mpds").resolve()
        source_scripts.append(artifact(source_script, revision_root))
        record = load_case(repo, int(case_id))
        user_context = (repo / str(record["public_case_input_dir"]) / "user_context.txt").resolve()
        situation = (repo / str(record["public_case_input_dir"]) / "situation.txt").resolve()
        case_contexts.extend([artifact(user_context, revision_root), artifact(situation, revision_root)])
        for pool in ("A", "B"):
            manifest_path = pool_manifest_path(revision_root, config, int(case_id), pool)
            manifest = read_json(manifest_path)
            source = Path(manifest["source_path"]).resolve()
            if source not in seen_sources:
                source_evidence.append(artifact(source, revision_root))
                seen_sources.add(source)
            generated_inputs.extend(
                [
                    artifact(manifest_path, revision_root),
                    artifact(manifest_path.parent / "block_membership.csv", revision_root),
                    *[
                        artifact(manifest_path.parent / f"knowledge_order_{ordering}.txt", revision_root)
                        for ordering in config["design"]["orderings"]
                    ],
                ]
            )

    payload = {
        "status": "FROZEN_BEFORE_ANY_LOST_IN_MIDDLE_API_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_id": config["config_id"],
        "selected_cases": config["design"]["selected_case_ids"],
        "orderings": config["design"]["orderings"],
        "replicates": config["design"]["replicates"],
        "expected_outputs": config["design"]["expected_outputs"],
        "expected_minimum_generation_calls": config["design"]["expected_minimum_generation_calls"],
        "validator": validation_report,
        "fixed_files": [artifact(path, revision_root) for path in fixed_paths],
        "source_mpds_scripts": source_scripts,
        "case_context_files": case_contexts,
        "canonical_source_evidence": source_evidence,
        "generated_position_control_inputs": generated_inputs,
        "secrets_recorded": False,
        "google_project_id_recorded": False,
    }
    output = revision_root / "evaluation" / "lost_in_middle_input_integrity_manifest_v1.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing integrity freeze: {output}")
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(output),
                "fixed_files": len(payload["fixed_files"]),
                "source_mpds_scripts": len(source_scripts),
                "canonical_source_evidence": len(source_evidence),
                "generated_position_control_inputs": len(generated_inputs),
                "api_calls_made": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
