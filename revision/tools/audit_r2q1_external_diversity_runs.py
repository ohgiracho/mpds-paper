from __future__ import annotations

import csv
import json
from pathlib import Path

from corpus_size_common import atomic_write_json, sha256_file
from run_r2q1_external_diversity_batch import output_dir, run_id
from validate_r2q1_setup import DEFAULT_CONFIG, REVISION_ROOT, load_config, validate_setup


def main() -> int:
    setup = validate_setup(DEFAULT_CONFIG)
    cfg = load_config(DEFAULT_CONFIG)
    run_root = REVISION_ROOT / cfg["output"]["run_set"]
    rows, errors = [], list(setup.get("errors", []))
    for item in cfg["design"]["execution_order"]:
        folder = output_dir(run_root, item)
        manifest_path, final_path, api_path = folder / "run_manifest.json", folder / "final.txt", folder / "api_calls.jsonl"
        if not manifest_path.is_file():
            errors.append(f"missing manifest: {run_id(item)}"); continue
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        case = cfg["cases"][str(item["case_id"])]
        checks = {
            "status": m.get("status") == "COMPLETE",
            "model": m.get("model") == "gemini-2.5-pro",
            "temperature": float(m.get("temperature", -1)) == 0.5,
            "final": final_path.is_file() and m.get("final_sha256") == sha256_file(final_path),
            "context": m.get("user_context_sha256") == case["user_context_sha256"],
            "pool_a": m.get("knowledge_a_sha256") == case["pool_a_sha256"],
            "pool_b": m.get("knowledge_b_sha256") == case["pool_b_sha256"],
            "calls": int(m.get("actual_successful_api_calls", 0)) >= 9,
            "citation": m.get("citation_validation") == "passed_by_unchanged_mpds_source",
            "api_log": api_path.is_file(),
        }
        failed = [k for k, ok in checks.items() if not ok]
        if failed:
            errors.append(f"{run_id(item)} failed: {failed}")
        s = m.get("api_log_summary", {})
        usage = s.get("usage_metadata_sums", {})
        rows.append({
            "run_id": run_id(item), "case_id": item["case_id"], "problem_class": case["problem_class"],
            "group_accounting": case["group_accounting"], "status": m.get("status"),
            "successful_calls": s.get("successful_calls", 0), "failed_calls": s.get("failed_calls", 0),
            "input_tokens": usage.get("prompt_token_count", 0),
            "output_tokens": usage.get("candidates_token_count", 0),
            "thoughts_tokens": usage.get("thoughts_token_count", 0),
            "total_tokens": usage.get("total_token_count", 0),
            "wall_clock_seconds": m.get("wall_clock_seconds", 0), "final_characters": m.get("final_characters", 0),
            "audit_pass": not failed,
        })
    analysis = REVISION_ROOT / "analysis"
    analysis.mkdir(exist_ok=True)
    csv_path = analysis / "r2q1_generation_audit_v1.csv"
    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    total = {
        key: sum(int(r.get(key, 0) or 0) for r in rows)
        for key in (
            "successful_calls",
            "failed_calls",
            "input_tokens",
            "output_tokens",
            "thoughts_tokens",
            "total_tokens",
        )
    }
    total["wall_clock_seconds"] = round(sum(float(r.get("wall_clock_seconds", 0) or 0) for r in rows), 6)
    report = {"status": "PASS" if len(rows) == 6 and not errors else "FAIL", "runs": len(rows), "expected_runs": 6, "totals": total, "errors": errors, "rows": rows}
    atomic_write_json(analysis / "r2q1_generation_audit_v1.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
