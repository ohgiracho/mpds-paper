from __future__ import annotations

import json
from pathlib import Path

from corpus_size_common import count_knowledge_records, read_jsonl, sha256_file
from prepare_q4_system_integration_evidence import normalize_doi, normalize_title


REVISION_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REVISION_ROOT.parents[1]
DEFAULT_CONFIG = REVISION_ROOT / "config" / "r2q1_external_diversity_v1.json"


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("R2 Q1 config must be a JSON object")
    return data


def check_hash(path: Path, expected: str | None, label: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
    elif not expected or sha256_file(path) != expected:
        errors.append(f"hash mismatch for {label}: {path}")


def validate_setup(config_path: Path = DEFAULT_CONFIG) -> dict:
    errors: list[str] = []
    cfg = load_config(config_path)
    if cfg.get("config_id") != "r2q1_external_diversity_v1":
        errors.append("config_id mismatch")
    if cfg.get("status") != "INPUTS_AND_EVIDENCE_FROZEN_READY_FOR_PREFLIGHT":
        errors.append("config is not in frozen preflight state")
    schedule = cfg["design"]["execution_order"]
    actual = {(int(x["case_id"]), int(x["replicate_id"])) for x in schedule}
    if len(schedule) != 6 or actual != {(i, 1) for i in range(1, 7)}:
        errors.append("execution schedule is not cases 1-6, replicate 1")
    gen = cfg["generation"]
    if gen["model"] != "gemini-2.5-pro" or float(gen["temperature"]) != 0.5:
        errors.append("generation model or temperature mismatch")
    if int(gen["rounds"]) != 3 or int(gen["max_output_tokens"]) != 8192:
        errors.append("generation rounds or token limit mismatch")
    impl = cfg["implementation"]
    check_hash(WORKSPACE_ROOT / impl["source_script_from_workspace"], impl["source_script_sha256"], "MPDS source", errors)
    check_hash(REVISION_ROOT / impl["runtime_instrumentation"], impl["runtime_instrumentation_sha256"], "runtime instrumentation", errors)
    summary_path = REVISION_ROOT / "r2q1_external_diversity_inputs_v1" / "evidence" / "retrieval_summary.json"
    if not summary_path.is_file():
        errors.append("retrieval summary missing")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary.get("status") != "PASS" or int(summary.get("pool_count", 0)) != 12:
            errors.append("retrieval summary is not PASS/12")
    for key, case in cfg["cases"].items():
        case_id = int(key)
        for name in ("source_pdf", "situation", "user_context"):
            check_hash(REVISION_ROOT / case[name], case.get(name + "_sha256"), f"case {case_id} {name}", errors)
        target_doi, target_title = normalize_doi(case["target_doi"]), normalize_title(case["target_title"])
        for pool in ("a", "b"):
            label = f"case {case_id} pool {pool.upper()}"
            path = REVISION_ROOT / case[f"pool_{pool}"]
            check_hash(path, case.get(f"pool_{pool}_sha256"), label, errors)
            manifest_path, selected_path = path.parent / "pool_manifest.json", path.parent / "selected_top_0500.jsonl"
            if not manifest_path.is_file() or not selected_path.is_file():
                errors.append(f"{label} manifest or selected JSONL missing")
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "PASS" or int(manifest.get("selected_records", 0)) != 500:
                errors.append(f"{label} manifest not PASS/500")
            if manifest.get("query") != case[f"pool_{pool}_query"]:
                errors.append(f"{label} query differs from frozen config")
            if path.is_file() and count_knowledge_records(path) != 500:
                errors.append(f"{label} does not contain 500 records")
            rows = read_jsonl(selected_path)
            if len(rows) != 500:
                errors.append(f"{label} selected JSONL does not contain 500 records")
            if any(normalize_doi(x.get("doi", "")) == target_doi or normalize_title(x.get("title", "")) == target_title for x in rows):
                errors.append(f"{label} includes target paper")
            if any(int(x.get("year", 9999)) > int(case["simulation_date"]) for x in rows):
                errors.append(f"{label} includes post-cutoff paper")
    return {
        "validation": "PASS_SETUP" if not errors else "FAIL_SETUP",
        "generation_readiness": "READY_FOR_GENERATION" if not errors else "BLOCKED",
        "config_id": cfg.get("config_id"),
        "expected_outputs": len(schedule),
        "evidence_pools": len(cfg.get("cases", {})) * 2,
        "independent_group_cases": sum(x.get("group_accounting") == "independent_external" for x in cfg.get("cases", {}).values()),
        "overlapping_network_cases": [int(k) for k, x in cfg.get("cases", {}).items() if x.get("group_accounting") != "independent_external"],
        "api_calls_made": 0,
        "errors": errors,
    }


def main() -> int:
    report = validate_setup()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["validation"] == "PASS_SETUP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
