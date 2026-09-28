from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

from corpus_size_common import (
    atomic_write_json,
    case_map,
    count_knowledge_records,
    load_config,
    pool_manifest_path,
    read_json,
    read_jsonl,
    selected_knowledge_path,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the frozen corpus-size design, nested inputs, and 48 dry-run cells")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--allow-missing-inputs", action="store_true")
    return parser.parse_args()


def add_error(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def validate_pool(
    *,
    input_root: Path,
    case_id: int,
    pool: str,
    sizes: list[int],
    errors: list[str],
) -> dict[str, Any] | None:
    manifest_path = pool_manifest_path(input_root, case_id, pool)
    if not manifest_path.exists():
        errors.append(f"Missing pool manifest: {manifest_path}")
        return None
    manifest = read_json(manifest_path)
    add_error(errors, manifest.get("status") == "PASS", f"Pool manifest not PASS: {manifest_path}")
    master_path = manifest_path.parent / manifest["artifacts"]["master_jsonl"]["path"]
    add_error(errors, master_path.exists(), f"Missing master JSONL: {master_path}")
    if not master_path.exists():
        return manifest
    add_error(
        errors,
        sha256_file(master_path) == manifest["artifacts"]["master_jsonl"]["sha256"],
        f"Master hash mismatch: {master_path}",
    )
    papers = read_jsonl(master_path)
    ids = [str(item.get("openalex_id") or "") for item in papers]
    add_error(errors, len(papers) == 1000, f"Master record count is {len(papers)}, expected 1000: {master_path}")
    add_error(errors, len(ids) == len(set(ids)), f"Duplicate OpenAlex IDs in {master_path}")
    query = manifest["query"]
    bad_years = [item.get("year") for item in papers if not int(query["start_year"]) <= int(item.get("year")) <= int(query["end_year"])]
    add_error(errors, not bad_years, f"Out-of-window publication years in {master_path}: {bad_years[:10]}")
    add_error(
        errors,
        [int(item.get("rank")) for item in papers] == list(range(1, len(papers) + 1)),
        f"Master ranks are not consecutive: {master_path}",
    )
    for size in sizes:
        path = selected_knowledge_path(input_root, case_id, pool, size)
        artifact = manifest["artifacts"].get(f"top_{size}")
        add_error(errors, artifact is not None, f"Missing top_{size} artifact in {manifest_path}")
        if artifact is None:
            continue
        add_error(errors, path.exists(), f"Missing selected knowledge file: {path}")
        if not path.exists():
            continue
        add_error(errors, sha256_file(path) == artifact["sha256"], f"Selected hash mismatch: {path}")
        add_error(errors, count_knowledge_records(path) == size, f"Selected record count mismatch: {path}")
        add_error(
            errors,
            artifact.get("first_openalex_id") == papers[0]["openalex_id"]
            and artifact.get("last_openalex_id") == papers[size - 1]["openalex_id"],
            f"Top-{size} endpoint IDs do not match master prefix: {path}",
        )
    return manifest


def main() -> int:
    args = parse_args()
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    errors: list[str] = []
    design = config["design"]
    cases = case_map(config)
    selected_ids = [int(value) for value in design["selected_case_ids"]]
    sizes = [int(value) for value in design["corpus_sizes"]]
    replicates = [int(value) for value in design["replicates"]]
    add_error(errors, selected_ids == sorted(cases), "Selected case IDs and case definitions differ")
    add_error(errors, sizes == sorted(set(sizes)), "Corpus sizes must be unique and ascending")
    add_error(errors, sizes == [100, 250, 500, 1000], "Unexpected corpus-size grid")
    expected = len(selected_ids) * len(sizes) * len(replicates)
    add_error(errors, expected == int(design["expected_outputs"]), "Expected output count is inconsistent")
    add_error(
        errors,
        int(design["expected_minimum_generation_calls"])
        == expected * int(design["expected_logical_generation_calls_per_output"]),
        "Expected generation-call count is inconsistent",
    )
    repo = revision_root.parent / "mpds_github_prep" / "github_repo"
    commit = subprocess.check_output(
        ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
    ).strip()
    add_error(errors, commit == config["source_repository_commit"], f"Repository commit changed: {commit}")
    input_root = revision_root / config["retrieval"]["input_root"]
    inputs_ready = (input_root / "retrieval_manifest.json").exists()
    if not inputs_ready and not args.allow_missing_inputs:
        errors.append(f"Missing retrieval manifest: {input_root / 'retrieval_manifest.json'}")
    pool_summaries = []
    pool_manifests: dict[tuple[int, str], dict[str, Any]] = {}
    if inputs_ready:
        for case_id in selected_ids:
            for pool in ("A", "B"):
                manifest = validate_pool(
                    input_root=input_root,
                    case_id=case_id,
                    pool=pool,
                    sizes=sizes,
                    errors=errors,
                )
                if manifest:
                    pool_manifests[(case_id, pool)] = manifest
                    pool_summaries.append(
                        {
                            "case_id": case_id,
                            "pool": pool,
                            "retrieval_id": manifest.get("retrieval_id"),
                            "meta_count": (manifest.get("retrieval_stats") or {}).get("openalex_meta_count"),
                        }
                    )
    dry_run_cells_checked = 0
    if inputs_ready and not errors:
        for case_id in selected_ids:
            for size in sizes:
                for replicate in replicates:
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(revision_root / "tools" / "run_corpus_size_condition.py"),
                            "--config",
                            str(config_path),
                            "--case",
                            str(case_id),
                            "--corpus-size",
                            str(size),
                            "--replicate",
                            str(replicate),
                        ],
                        cwd=revision_root,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    if result.returncode != 0:
                        errors.append(
                            f"Dry-run failed for case={case_id}, size={size}, replicate={replicate}: {result.stderr[-1000:]}"
                        )
                        break
                    dry_run_cells_checked += 1
    input_size_summary = []
    if inputs_ready and len(pool_manifests) == len(selected_ids) * 2:
        persona_cap = int(config["generation"]["persona_excerpt_characters_per_pool"])
        for size in sizes:
            combined_by_case = []
            persona_by_case = []
            debate_by_case = []
            for case_id in selected_ids:
                characters = [
                    int(pool_manifests[(case_id, pool)]["artifacts"][f"top_{size}"]["characters"])
                    for pool in ("A", "B")
                ]
                combined = sum(characters)
                combined_by_case.append(combined)
                persona_by_case.append(sum(min(persona_cap, value) for value in characters))
                debate_by_case.append(3 * combined)
            input_size_summary.append(
                {
                    "corpus_size_per_pool": size,
                    "mean_selected_characters_across_two_pools": round(statistics.mean(combined_by_case)),
                    "min_selected_characters_across_two_pools": min(combined_by_case),
                    "max_selected_characters_across_two_pools": max(combined_by_case),
                    "mean_persona_selected_characters_across_two_pools": round(statistics.mean(persona_by_case)),
                    "mean_nominal_debate_knowledge_characters_across_six_turns": round(statistics.mean(debate_by_case)),
                    "nominal_debate_knowledge_characters_for_all_12_outputs": sum(debate_by_case) * len(replicates),
                }
            )

    payload = {
        "status": "PASS" if not errors else "FAIL",
        "phase": "READY_FOR_GENERATION" if inputs_ready and not errors else "READY_FOR_RETRIEVAL" if not errors else "BLOCKED",
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "source_commit": commit,
        "selected_case_ids": selected_ids,
        "corpus_sizes": sizes,
        "replicates": replicates,
        "expected_outputs": expected,
        "expected_minimum_generation_calls": design["expected_minimum_generation_calls"],
        "inputs_ready": inputs_ready,
        "pool_summaries": pool_summaries,
        "input_size_summary": input_size_summary,
        "dry_run_cells_checked": dry_run_cells_checked,
        "vertex_preflight": {
            "google_cloud_project_configured": bool((os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()),
            "adc_credentials_file_exists": bool(os.getenv("APPDATA"))
            and (Path(os.environ["APPDATA"]) / "gcloud" / "application_default_credentials.json").exists(),
            "project_identifier_recorded": False,
            "credential_value_recorded": False,
        },
        "errors": errors,
    }
    preflight_path = revision_root / "qa" / "corpus_size_sensitivity_preflight_v1.json"
    payload["preflight_manifest"] = str(preflight_path)
    atomic_write_json(preflight_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
