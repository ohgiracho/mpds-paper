from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from litm_common import (
    decode_bytes,
    environment_value,
    load_config,
    ordered_knowledge_path,
    pool_manifest_path,
    read_json,
    sha256_bytes,
    sha256_file,
    split_knowledge_bytes,
)
from prepare_litm_inputs import selection_rows
from run_condition import find_script, load_case


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Strictly validate the frozen lost-in-middle setup")
    parser.add_argument("--config", type=Path)
    return parser.parse_args()


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_membership(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def adc_available() -> bool:
    try:
        import google.auth

        credentials, _ = google.auth.default()
        return credentials is not None
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    errors: list[str] = []
    design = config.get("design", {})
    generation = config.get("generation", {})
    expected_cases = [29, 1, 30, 2]
    if config.get("config_id") != "lost_in_middle_position_control_v1":
        fail(errors, "Unexpected config_id")
    if design.get("selected_case_ids") != expected_cases:
        fail(errors, "Frozen selected-case order changed")
    if design.get("orderings") != ["XYZ", "YZX", "ZXY"]:
        fail(errors, "Frozen cyclic orderings changed")
    if design.get("replicates") != [1, 2, 3] or design.get("expected_outputs") != 36:
        fail(errors, "Frozen replicate/output design changed")
    if generation.get("model") != "gemini-2.5-pro":
        fail(errors, "Generator must remain gemini-2.5-pro")
    if generation.get("backend") != "vertex-adc" or generation.get("vertex_location") != "global":
        fail(errors, "Frozen Vertex backend/location changed")
    if generation.get("temperature") != 0.5 or generation.get("max_output_tokens") != 8192:
        fail(errors, "Frozen generation settings changed")
    if generation.get("rounds") != 3 or generation.get("minimum_evidence_pointers") != 3:
        fail(errors, "Frozen MPDS protocol settings changed")

    recomputed = selection_rows(revision_root, config)
    selected_actual = [int(row["case_id"]) for row in recomputed if row["eligible"]][:4]
    if selected_actual != expected_cases:
        fail(errors, f"Outcome-independent case selection no longer reproduces: {selected_actual}")
    selected_config = config["case_selection_rule"]["selected_cases"]
    for expected, frozen in zip(selected_actual, selected_config, strict=True):
        row = next(item for item in recomputed if int(item["case_id"]) == expected)
        if int(frozen["combined_characters"]) != int(row["combined_characters"]):
            fail(errors, f"Frozen selection character count mismatch for case {expected}")

    input_root = revision_root / str(config["inputs"]["input_root"])
    summary_path = input_root / "build_summary.json"
    if not summary_path.exists():
        fail(errors, "Input build summary is missing; run prepare_litm_inputs.py")
        summary: dict[str, Any] = {}
    else:
        summary = read_json(summary_path)
        if summary.get("status") != "PASS" or summary.get("api_calls_made") != 0:
            fail(errors, "Input build summary is not a zero-API PASS")

    pool_manifests = 0
    ordered_files = 0
    position_counter: Counter[tuple[int, str, str, str]] = Counter()
    for case_id in expected_cases:
        for pool in ("A", "B"):
            manifest_path = pool_manifest_path(revision_root, config, case_id, pool)
            membership_path = manifest_path.parent / "block_membership.csv"
            if not manifest_path.exists() or not membership_path.exists():
                fail(errors, f"Missing pool artifacts for case {case_id}, pool {pool}")
                continue
            manifest = read_json(manifest_path)
            pool_manifests += 1
            source = Path(manifest["source_path"])
            if not source.exists() or sha256_file(source) != manifest["source_sha256"]:
                fail(errors, f"Source evidence hash mismatch for case {case_id}, pool {pool}")
                continue
            source_header, source_records = split_knowledge_bytes(source.read_bytes())
            if len(source_records) != 500 or manifest.get("records") != 500:
                fail(errors, f"Wrong source record count for case {case_id}, pool {pool}")
            if sha256_bytes(source_header) != manifest.get("header_sha256"):
                fail(errors, f"Header hash mismatch for case {case_id}, pool {pool}")
            membership = load_membership(membership_path)
            if len(membership) != 500:
                fail(errors, f"Wrong membership count for case {case_id}, pool {pool}")
            membership_lookup = {int(row["paper_id"]): row for row in membership}
            if len(membership_lookup) != 500:
                fail(errors, f"Duplicate membership ID for case {case_id}, pool {pool}")
            source_hash_lookup = {int(item["paper_id"]): item["sha256"] for item in source_records}
            for paper_id, row in membership_lookup.items():
                if source_hash_lookup.get(paper_id) != row["record_sha256"]:
                    fail(errors, f"Membership record content mismatch for case {case_id}, pool {pool}, ID {paper_id}")
                    break
            block_indices: dict[str, list[int]] = {label: [] for label in ("X", "Y", "Z")}
            for row in membership:
                block_indices[row["block"]].append(int(row["canonical_index"]))
            for label, indices in block_indices.items():
                if not indices or indices != list(range(min(indices), max(indices) + 1)):
                    fail(errors, f"Block {label} is not contiguous for case {case_id}, pool {pool}")

            for ordering in design["orderings"]:
                path = ordered_knowledge_path(revision_root, config, case_id, pool, ordering)
                artifact = manifest.get("orderings", {}).get(ordering, {})
                if not path.exists() or sha256_file(path) != artifact.get("sha256"):
                    fail(errors, f"Ordered-file hash mismatch for case {case_id}, pool {pool}, {ordering}")
                    continue
                ordered_header, ordered_records = split_knowledge_bytes(path.read_bytes())
                ordered_files += 1
                if ordered_header != source_header:
                    fail(errors, f"Header changed for case {case_id}, pool {pool}, {ordering}")
                if len(ordered_records) != 500:
                    fail(errors, f"Wrong ordered record count for case {case_id}, pool {pool}, {ordering}")
                ordered_lookup = {int(item["paper_id"]): item["sha256"] for item in ordered_records}
                if ordered_lookup != source_hash_lookup:
                    fail(errors, f"Evidence content/set changed for case {case_id}, pool {pool}, {ordering}")
                expected_ids = [
                    int(row["paper_id"])
                    for label in ordering
                    for row in membership
                    if row["block"] == label
                ]
                actual_ids = [int(item["paper_id"]) for item in ordered_records]
                if actual_ids != expected_ids:
                    fail(errors, f"Unexpected within-block/order sequence for case {case_id}, pool {pool}, {ordering}")
                positions = artifact.get("positions", {})
                for position, label in positions.items():
                    position_counter[(case_id, pool, label, position)] += 1
                if len(decode_bytes(path.read_bytes())) != int(artifact.get("characters", -1)):
                    fail(errors, f"Ordered character count mismatch for case {case_id}, pool {pool}, {ordering}")

    for case_id in expected_cases:
        for pool in ("A", "B"):
            for label in ("X", "Y", "Z"):
                for position in ("front", "middle", "rear"):
                    if position_counter[(case_id, pool, label, position)] != 1:
                        fail(errors, f"Unbalanced block-position exposure: case {case_id}, pool {pool}, {label}, {position}")

    child_environment = os.environ.copy()
    child_environment["PYTHONIOENCODING"] = "utf-8"
    repo = (revision_root.parent / "mpds_github_prep" / "github_repo").resolve()
    adapter_self_tests = 0
    for case_id in expected_cases:
        source_script = find_script(repo, revision_root, case_id, "mpds").resolve()
        record = load_case(repo, case_id)
        manifest_a = read_json(pool_manifest_path(revision_root, config, case_id, "A"))
        manifest_b = read_json(pool_manifest_path(revision_root, config, case_id, "B"))
        command = [
            sys.executable,
            str(revision_root / "tools" / "run_litm_mpds_adapter.py"),
            "--source-script",
            str(source_script),
            "--expected-source-sha256",
            sha256_file(source_script),
            "--canonical-persona-a",
            manifest_a["persona_source"],
            "--canonical-persona-b",
            manifest_b["persona_source"],
            "--self-test",
            "--simulation-date",
            str(record["cutoff_year"]),
            "--knowledge-a",
            str(ordered_knowledge_path(revision_root, config, case_id, "A", "XYZ")),
            "--knowledge-b",
            str(ordered_knowledge_path(revision_root, config, case_id, "B", "XYZ")),
        ]
        test = subprocess.run(
            command,
            cwd=revision_root,
            env=child_environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if test.returncode != 0:
            fail(errors, f"Persona-control adapter self-test failed for case {case_id}: {test.stderr.strip()}")
        else:
            adapter_self_tests += 1

    dry_runs_checked = 0
    for case_id in expected_cases:
        for ordering in design["orderings"]:
            for replicate in design["replicates"]:
                command = [
                    sys.executable,
                    str(revision_root / "tools" / "run_litm_condition.py"),
                    "--config",
                    str(config_path),
                    "--case",
                    str(case_id),
                    "--ordering",
                    str(ordering),
                    "--replicate",
                    str(replicate),
                ]
                result = subprocess.run(
                    command,
                    cwd=revision_root,
                    env=child_environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if result.returncode != 0:
                    fail(errors, f"Dry-run failed for case {case_id}, {ordering}, replicate {replicate}: {result.stderr.strip()}")
                    continue
                try:
                    plan = json.loads(result.stdout)
                except json.JSONDecodeError:
                    fail(errors, f"Dry-run returned invalid JSON for case {case_id}, {ordering}, replicate {replicate}")
                    continue
                dry_runs_checked += 1
                if plan.get("dry_run") is not True or plan.get("status") != "DRY_RUN":
                    fail(errors, "Dry-run plan is not marked DRY_RUN")
                if plan.get("model") != "gemini-2.5-pro" or plan.get("temperature") != 0.5:
                    fail(errors, "Dry-run model/temperature drift")
                if plan.get("vertex_project_recorded") is not False:
                    fail(errors, "Dry-run would record Vertex project")
                if plan.get("positions") != config["position_manipulation"]["rotations"][ordering]:
                    fail(errors, "Dry-run position map drift")
                if plan.get("persona_control", {}).get("policy") != "canonical source snapshots fixed across all orderings":
                    fail(errors, "Canonical persona control is absent")

    batch = subprocess.run(
        [sys.executable, str(revision_root / "tools" / "run_litm_batch.py"), "--config", str(config_path)],
        cwd=revision_root,
        env=child_environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if batch.returncode != 0:
        fail(errors, f"Batch dry-run failed: {batch.stderr.strip()}")
        batch_plan: dict[str, Any] = {}
    else:
        batch_plan = json.loads(batch.stdout)
        if batch_plan.get("full_schedule_outputs") != 36:
            fail(errors, "Batch schedule does not contain 36 outputs")

    credentials = {
        "google_cloud_project_available": bool(environment_value("GOOGLE_CLOUD_PROJECT")),
        "application_default_credentials_available": adc_available(),
    }
    if not all(credentials.values()):
        fail(errors, "Vertex ADC execution prerequisites are unavailable")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "phase": "READY_FOR_GENERATION" if not errors else "SETUP_INVALID",
        "config_id": config.get("config_id"),
        "selected_cases": expected_cases,
        "pool_manifests": pool_manifests,
        "ordered_knowledge_files": ordered_files,
        "dry_run_cells_checked": dry_runs_checked,
        "persona_adapter_self_tests": adapter_self_tests,
        "expected_outputs": design.get("expected_outputs"),
        "expected_minimum_generation_calls": design.get("expected_minimum_generation_calls"),
        "position_balance_cells": sum(position_counter.values()),
        "persona_control": "canonical source fixed; debate evidence reordered only",
        "credentials": credentials,
        "existing_complete_outputs": int(batch_plan.get("already_complete", 0)),
        "pending_outputs": int(batch_plan.get("pending_outputs", 0)),
        "errors": errors,
        "api_calls_made": 0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
