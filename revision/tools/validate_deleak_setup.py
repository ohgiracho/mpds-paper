from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from build_blind_packets import clean_final
from deleak_common import (
    assert_hash,
    frozen_schedule,
    litm_gate_status,
    load_deleak_config,
    output_directory,
    sha256_file,
)
from run_condition import find_script, load_case


FORBIDDEN_CUES = {
    1: (
        "surface-versus-interstitial",
        "interstitial filling",
        "particle-size allocation",
        "coverage degree",
        "bimodal",
    ),
    8: (
        "hollow",
        "nanocube",
        "porous wall",
        "reduced graphene oxide",
        "spray pyrolysis",
        "sulfidation",
        "rgo",
    ),
    22: (
        "tube-in-tube",
        "nanobelt",
        "inner tube",
        "outer tube",
        "electrospinning",
    ),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def embedded_user_context(situation_text: str) -> str:
    match = re.search(r'USER_CONTEXT\s*=\s*"""(.*?)"""', situation_text, flags=re.S)
    if not match:
        raise RuntimeError("Situation file has no triple-quoted USER_CONTEXT block")
    return match.group(1).strip()


def validate_design(revision_root: Path, config: dict[str, Any]) -> None:
    if config["config_id"] != "prompt_deleaking_targeted_v2":
        raise RuntimeError("Unexpected config id")
    if config["selection"]["selected_case_ids"] != [1, 8, 22]:
        raise RuntimeError("Frozen case selection changed")
    if config["design"]["replicates"] != [1, 2, 3]:
        raise RuntimeError("Frozen replicate design changed")
    schedule = frozen_schedule(config)
    if len(schedule) != 9 or len({(row["case_id"], row["replicate_id"]) for row in schedule}) != 9:
        raise RuntimeError("Frozen schedule must contain nine unique cells")
    generation = config["generation"]
    expected = {
        "model": "gemini-2.5-pro",
        "backend": "vertex-adc",
        "vertex_location": "global",
        "temperature": 0.5,
        "max_output_tokens": 8192,
        "rounds": 3,
        "minimum_evidence_pointers": 3,
    }
    for key, value in expected.items():
        if generation.get(key) != value:
            raise RuntimeError(f"Frozen generation parameter changed: {key}")
    if generation.get("vertex_project_recorded") is not False:
        raise RuntimeError("Vertex project identifiers must not be recorded")

    screening = read_csv(revision_root / str(config["selection"]["screening_file"]))
    very_high = {int(row["repo_case_id"]) for row in screening if row["risk_level"] == "very_high"}
    if len(screening) != 30 or len(very_high) != 8:
        raise RuntimeError("Screening population or very-high-risk count changed")
    core10 = json.loads(
        (revision_root / "config" / "prompt_deleaking_core10_selection_v1.json").read_text(encoding="utf-8")
    )["ordered_case_ids"]
    if sorted(very_high.intersection(set(core10))) != [1, 8, 22]:
        raise RuntimeError("Selected cases no longer equal the prespecified Very High x Core10 intersection")


def validate_inputs(revision_root: Path, config: dict[str, Any]) -> None:
    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    source_commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    if source_commit != config["generation"]["source_commit"]:
        raise RuntimeError("Repository commit differs from the frozen source commit")
    runtime = revision_root / str(config["runtime"]["compatibility_layer"])
    assert_hash(runtime, config["runtime"]["compatibility_layer_sha256"], "runtime compatibility layer")
    assert_hash(
        revision_root / str(config["controls"]["analysis_plan"]),
        config["controls"]["analysis_plan_sha256"],
        "analysis plan",
    )
    assert_hash(
        revision_root / str(config["controls"]["target_recovery_rubric"]),
        config["controls"]["target_recovery_rubric_sha256"],
        "target recovery rubric",
    )
    for case_id in config["selection"]["selected_case_ids"]:
        case = config["cases"][str(case_id)]
        record = load_case(repo, int(case_id))
        script = find_script(repo, revision_root, int(case_id), "mpds").resolve()
        expected_script = (repo / case["source_script"]).resolve()
        if script != expected_script or str(record["case_name"]) != case["case_name"]:
            raise RuntimeError(f"Case {case_id}: source identity changed")
        items = (
            (script, case["source_script_sha256"], "source script"),
            (repo / case["original_situation"], case["original_situation_sha256"], "original situation"),
            (repo / case["original_user_context"], case["original_user_context_sha256"], "original user context"),
            (revision_root / case["deleaked_situation"], case["deleaked_situation_sha256"], "de-leaked situation"),
            (revision_root / case["deleaked_user_context"], case["deleaked_user_context_sha256"], "de-leaked user context"),
            (Path(case["knowledge_a"]), case["knowledge_a_sha256"], "knowledge A"),
            (Path(case["knowledge_b"]), case["knowledge_b_sha256"], "knowledge B"),
        )
        for path, digest, label in items:
            assert_hash(path.resolve(), digest, f"case {case_id} {label}")
        situation_text = (revision_root / case["deleaked_situation"]).read_text(encoding="utf-8")
        user_text = (revision_root / case["deleaked_user_context"]).read_text(encoding="utf-8").strip()
        if embedded_user_context(situation_text) != user_text:
            raise RuntimeError(f"Case {case_id}: situation/user-context mismatch")
        if f'SIMULATION_DATE = "{case["simulation_date"]}"' not in situation_text:
            raise RuntimeError(f"Case {case_id}: simulation date mismatch")
        if f'DEBATE_TOPIC = "{case["debate_topic"]}"' not in situation_text:
            raise RuntimeError(f"Case {case_id}: debate topic mismatch")
        lower = (case["debate_topic"] + "\n" + situation_text + "\n" + user_text).lower()
        found = [cue for cue in FORBIDDEN_CUES[int(case_id)] if cue in lower]
        if found:
            raise RuntimeError(f"Case {case_id}: solution-revealing cue remains: {found}")


def validate_original_controls(revision_root: Path, config: dict[str, Any]) -> None:
    rows = read_csv(revision_root / str(config["controls"]["original_output_manifest"]))
    expected_pairs = {(case_id, replicate) for case_id in (1, 8, 22) for replicate in (1, 2, 3)}
    actual_pairs = {(int(row["case_id"]), int(row["replicate_id"])) for row in rows}
    if len(rows) != 9 or actual_pairs != expected_pairs:
        raise RuntimeError("Original-control manifest must contain exactly the nine matched controls")
    for row in rows:
        source = Path(row["source_file"]).resolve()
        assert_hash(source, row["source_file_sha256"], "original control source")
        final = clean_final(source.read_text(encoding="utf-8", errors="replace"))
        if sha256_text(final) != row["cleaned_output_sha256"]:
            raise RuntimeError(f"Cleaned original-control hash mismatch: {source}")
        if len(final) != int(row["output_characters"]):
            raise RuntimeError(f"Original-control character count mismatch: {source}")
        if row["source_manifest"]:
            manifest_path = Path(row["source_manifest"]).resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "COMPLETE":
                raise RuntimeError(f"Original generated control is not COMPLETE: {manifest_path}")


def validate_dry_runs(revision_root: Path, config_path: Path, config: dict[str, Any]) -> None:
    child_environment = os.environ.copy()
    child_environment["PYTHONUTF8"] = "1"
    for item in frozen_schedule(config):
        destination = output_directory(revision_root, config, item["case_id"], item["replicate_id"])
        existed_before = destination.exists()
        command = [
            sys.executable,
            str(revision_root / "tools" / "run_deleak_condition.py"),
            "--config",
            str(config_path),
            "--case",
            str(item["case_id"]),
            "--replicate",
            str(item["replicate_id"]),
        ]
        result = subprocess.run(
            command,
            cwd=revision_root,
            env=child_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError(f"Dry-run failed for {item}: {result.stderr.strip()}")
        plan = json.loads(result.stdout)
        if plan["dry_run"] is not True or plan["model"] != "gemini-2.5-pro" or plan["temperature"] != 0.5:
            raise RuntimeError(f"Dry-run parameters changed for {item}")
        if plan["config_id"] != config["config_id"] or plan["condition"] != "mpds_deleaked":
            raise RuntimeError(f"Dry-run identity mismatch for {item}")
        if not existed_before and destination.exists():
            raise RuntimeError(f"Dry-run unexpectedly created an output directory: {destination}")
    batch = subprocess.run(
        [sys.executable, str(revision_root / "tools" / "run_deleak_batch.py"), "--config", str(config_path)],
        cwd=revision_root,
        env=child_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if batch.returncode != 0:
        raise RuntimeError(f"Batch dry-run failed: {batch.stderr.strip()}")
    batch_plan = json.loads(batch.stdout)
    if batch_plan["full_schedule_outputs"] != 9:
        raise RuntimeError("Batch dry-run did not preserve the nine-cell frozen schedule")


def main() -> int:
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_deleak_config(revision_root)
    validate_design(revision_root, config)
    validate_inputs(revision_root, config)
    validate_original_controls(revision_root, config)
    validate_dry_runs(revision_root, config_path, config)
    gate = litm_gate_status(revision_root, config)
    result = {
        "validation": "PASS_SETUP",
        "config_id": config["config_id"],
        "config_sha256": sha256_file(config_path),
        "cases": config["selection"]["selected_case_ids"],
        "dry_runs_passed": 9,
        "expected_new_outputs": 9,
        "expected_minimum_generation_calls": 81,
        "original_controls_verified": 9,
        "api_calls_made": 0,
        "litm_gate": gate,
        "generation_readiness": "READY_FOR_GENERATION" if gate["open"] else "WAIT_FOR_LITM",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
