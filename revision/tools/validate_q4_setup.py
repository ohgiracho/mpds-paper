from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from corpus_size_common import count_knowledge_records, read_jsonl, sha256_file
from prepare_q4_system_integration_evidence import normalize_doi, normalize_title


REVISION_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REVISION_ROOT.parents[1]
DEFAULT_CONFIG = REVISION_ROOT / "config" / "q4_system_integration_v1.json"


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Q4 config must be a JSON object")
    return payload


def checked_hash(path: Path, expected: str, label: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return
    actual = sha256_file(path)
    if actual != expected:
        errors.append(f"hash mismatch for {label}: {path}")


def validate_setup(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    errors: list[str] = []
    config = load_config(config_path)
    if config.get("config_id") != "q4_system_integration_v1":
        errors.append("config_id mismatch")
    if config.get("status") != "INPUTS_AND_EVIDENCE_FROZEN_READY_FOR_PREFLIGHT":
        errors.append("config is not in frozen preflight state")
    design = config["design"]
    schedule = design["execution_order"]
    if len(schedule) != 11 or int(design["expected_outputs"]) != 11:
        errors.append("execution schedule is not 11 outputs")
    expected_breadth = {(case_id, 1) for case_id in range(1, 9)}
    actual_breadth = {
        (int(item["case_id"]), int(item["replicate_id"]))
        for item in schedule
        if item["kind"] == "breadth"
    }
    if actual_breadth != expected_breadth:
        errors.append("breadth schedule mismatch")
    actual_integrated = {
        int(item["replicate_id"]) for item in schedule if item["kind"] == "integrated"
    }
    if actual_integrated != {1, 2, 3}:
        errors.append("integrated schedule mismatch")
    generation = config["generation"]
    if generation["model"] != "gemini-2.5-pro" or float(generation["temperature"]) != 0.5:
        errors.append("generation model or temperature mismatch")
    if int(generation["rounds"]) != 3 or int(generation["max_output_tokens"]) != 8192:
        errors.append("generation rounds or token limit mismatch")

    implementation = config["implementation"]
    checked_hash(
        WORKSPACE_ROOT / implementation["source_script_from_workspace"],
        implementation["source_script_sha256"],
        "MPDS source",
        errors,
    )
    checked_hash(
        REVISION_ROOT / implementation["runtime_instrumentation"],
        implementation["runtime_instrumentation_sha256"],
        "Q4 instrumentation",
        errors,
    )
    summary_path = REVISION_ROOT / "q4_system_integration_inputs_v1" / "evidence" / "retrieval_summary.json"
    if not summary_path.is_file():
        errors.append("retrieval summary missing")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("status") != "PASS" or int(summary.get("pool_count", 0)) != 16:
            errors.append("retrieval summary is not PASS/16")

    for key, case in config["breadth_cases"].items():
        case_id = int(key)
        for name in ("situation", "user_context"):
            checked_hash(
                REVISION_ROOT / case[name], case[name + "_sha256"], f"case {case_id} {name}", errors
            )
        target_doi = normalize_doi(case["target_doi"])
        target_title = normalize_title(case["target_title"])
        for pool in ("a", "b"):
            label = f"case {case_id} pool {pool.upper()}"
            path = REVISION_ROOT / case[f"pool_{pool}"]
            checked_hash(path, case[f"pool_{pool}_sha256"], label, errors)
            manifest_path = path.parent / "pool_manifest.json"
            selected_path = path.parent / "selected_top_0500.jsonl"
            if not manifest_path.is_file() or not selected_path.is_file():
                errors.append(f"{label} manifest or selected JSONL missing")
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "PASS" or int(manifest.get("selected_records", 0)) != 500:
                errors.append(f"{label} manifest not PASS/500")
            if manifest.get("query") != case[f"pool_{pool}_query"]:
                errors.append(f"{label} query differs from frozen config")
            if manifest.get("artifacts", {}).get("knowledge", {}).get("sha256") != case[f"pool_{pool}_sha256"]:
                errors.append(f"{label} manifest knowledge hash mismatch")
            if path.is_file() and count_knowledge_records(path) != 500:
                errors.append(f"{label} knowledge does not contain 500 records")
            selected = read_jsonl(selected_path)
            if len(selected) != 500:
                errors.append(f"{label} selected JSONL does not contain 500 records")
            if any(
                normalize_doi(row.get("doi", "")) == target_doi
                or normalize_title(row.get("title", "")) == target_title
                for row in selected
            ):
                errors.append(f"{label} includes target paper")
            cutoff = int(case["simulation_date"])
            if any(int(row.get("year", 9999)) > cutoff for row in selected):
                errors.append(f"{label} includes post-cutoff paper")

    integrated = config["integrated_case"]
    for name in ("situation", "user_context", "pool_b"):
        checked_hash(
            REVISION_ROOT / integrated[name], integrated[name + "_sha256"], f"integrated {name}", errors
        )
    checked_hash(
        WORKSPACE_ROOT / integrated["pool_a_path_from_workspace"],
        integrated["pool_a_sha256"],
        "integrated pool A",
        errors,
    )
    if (REVISION_ROOT / integrated["pool_b"]).is_file() and count_knowledge_records(
        REVISION_ROOT / integrated["pool_b"]
    ) != 8:
        errors.append("integrated pool B does not contain eight mechanism records")

    return {
        "validation": "PASS_SETUP" if not errors else "FAIL_SETUP",
        "generation_readiness": "READY_FOR_GENERATION" if not errors else "BLOCKED",
        "config_id": config["config_id"],
        "expected_outputs": len(schedule),
        "breadth_outputs": len(actual_breadth),
        "integrated_outputs": len(actual_integrated),
        "breadth_evidence_pools": len(config["breadth_cases"]) * 2,
        "api_calls_made": 0,
        "errors": errors,
    }


def main() -> int:
    report = validate_setup()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["validation"] == "PASS_SETUP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
