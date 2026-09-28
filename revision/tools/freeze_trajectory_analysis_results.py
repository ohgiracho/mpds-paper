from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trajectory_common import load_config, resolve_from_root, sha256_file, write_json


def artifact(root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        display = str(resolved.relative_to(root))
    except ValueError:
        display = str(resolved)
    return {"path": display, "sha256": sha256_file(resolved), "bytes": resolved.stat().st_size}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    _, config = load_config(root)
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    judge_root = resolve_from_root(root, config["judge_run_directory"])
    output = analysis_dir / "trajectory_results_integrity_manifest_v2.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite results integrity manifest: {output}")
    required = [
        "trajectory_evaluation_prompt_frozen.txt",
        "trajectory_rubric_frozen.json",
        "trajectory_input_manifest.csv",
        "trajectory_scores_blinded.csv",
        "trajectory_scores_unblinded.csv",
        "trajectory_revision_events.csv",
        "trajectory_case_means.csv",
        "trajectory_pairwise_statistics.csv",
        "trajectory_validation_summary.json",
        "TRAJECTORY_ANALYSIS_RESULTS_BRIEF.md",
        "trajectory_descriptive_statistics.csv",
        "trajectory_event_type_frequencies.csv",
        "trajectory_qualitative_examples.md",
        "trajectory_input_integrity_manifest.json",
        "analysis_code_erratum_v1.md",
    ]
    result_paths = [analysis_dir / name for name in required]
    missing = [str(path) for path in result_paths if not path.exists()]
    if missing:
        raise RuntimeError(f"Required results missing: {missing}")
    validation = json.loads((analysis_dir / "trajectory_validation_summary.json").read_text(encoding="utf-8"))
    if validation.get("status") != "PASS" or validation.get("packets_complete") != 30 or validation.get("trajectories_complete") != 120:
        raise RuntimeError("Trajectory validation summary is not complete")
    judge_files: list[dict[str, Any]] = []
    for run_dir in sorted(judge_root.glob("case_*__rep_*")):
        accepted = run_dir / "accepted_scores.json"
        manifest = run_dir / "run_manifest.json"
        if not accepted.exists() or not manifest.exists():
            continue
        run_data = json.loads(manifest.read_text(encoding="utf-8"))
        if run_data.get("status") != "COMPLETE":
            raise RuntimeError(f"Judge run is not COMPLETE: {manifest}")
        judge_files.extend([artifact(root, accepted), artifact(root, manifest)])
    if len(judge_files) != 60:
        raise RuntimeError(f"Expected 60 accepted-score/manifest files, found {len(judge_files)}")
    input_integrity = json.loads((analysis_dir / "trajectory_input_integrity_manifest.json").read_text(encoding="utf-8"))
    frozen_analyzer = next(
        item for item in input_integrity["fixed_files"] if item["path"].replace("\\", "/").endswith("tools/analyze_trajectory_evaluations.py")
    )
    payload = {
        "status": "COMPLETE_AND_HASHED",
        "supersedes": "trajectory_results_integrity_manifest.json; v2 was created after the reporting-only brief expansion documented in analysis_code_erratum_v1.md",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config_id": config["config_id"],
        "packets_complete": 30,
        "trajectories_complete": 120,
        "api_calls": 30,
        "returned_models": validation["returned_models"],
        "usage": validation["usage"],
        "result_files": [artifact(root, path) for path in result_paths],
        "judge_files": judge_files,
        "analysis_implementation": {
            "frozen_pre_call_analyzer_sha256": frozen_analyzer["sha256"],
            "executed_post_erratum_analyzer": artifact(root, root / "tools" / "analyze_trajectory_evaluations.py"),
            "erratum": artifact(root, analysis_dir / "analysis_code_erratum_v1.md"),
        },
        "api_key_recorded": False,
    }
    write_json(output, payload)
    print(json.dumps({"status": "PASS", "output": str(output), "result_files": len(result_paths), "judge_files": len(judge_files)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
