from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from build_blind_packets import sha256_file
from corpus_size_common import atomic_write_json
from validate_pass1_r2q1_single import validate_main
from validate_r2q1_setup import REVISION_ROOT


RESULTS = REVISION_ROOT / "results" / "pass1_sonnet5_r2q1_v1"
KEY = REVISION_ROOT / "evaluation" / "r2q1_pass1_blind_key_v1_DO_NOT_SHARE" / "blind_key.json"
INTEGRITY = REVISION_ROOT / "evaluation" / "r2q1_pass1_input_integrity_manifest_v1.json"
PACKETS = REVISION_ROOT / "evaluation" / "blind_packets_r2q1_v1"
OUT = REVISION_ROOT / "analysis" / "r2q1_pass1_sonnet5_v1"
SCORE_FIELDS = ["idea_novelty", "mechanistic_originality", "tradeoff_reframing", "cross_perspective_integration", "scientific_correctness", "physical_plausibility", "constraint_adherence", "falsifiability_actionability"]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = {x["packet_id"]: x for x in json.loads(KEY.read_text(encoding="utf-8"))["mapping"]}
    integrity = {x["packet_id"]: x for x in json.loads(INTEGRITY.read_text(encoding="utf-8"))["packets"]}
    problems: list[str] = []; rows: list[dict[str, Any]] = []; total_attempts = total_in = total_out = first_fail = 0
    for pid, key in sorted(mapping.items()):
        folder = RESULTS / pid; manifest_path, scores_path = folder / "run_manifest.json", folder / "accepted_scores.json"
        if not manifest_path.is_file() or not scores_path.is_file(): problems.append(f"{pid}: missing result"); continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")); data = json.loads(scores_path.read_text(encoding="utf-8"))
        errors, derived = validate_main(data, Path(f"{pid}.json"))
        if errors: problems.extend(f"{pid}: {e}" for e in errors); continue
        if manifest.get("status") != "COMPLETE" or manifest.get("returned_model") != "claude-sonnet-5": problems.append(f"{pid}: incomplete or model mismatch")
        if sha256_file(PACKETS / f"{pid}.md") != integrity[pid]["packet_sha256"]: problems.append(f"{pid}: packet hash mismatch")
        attempts = manifest.get("attempts") or []; total_attempts += len(attempts)
        for i, a in enumerate(attempts):
            u = a.get("usage") or {}; total_in += int(u.get("input_tokens") or 0); total_out += int(u.get("output_tokens") or 0)
            if i == 0 and a.get("validation_errors"): first_fail += 1
        c, d = data["candidate_scores"][0], derived[0]
        rows.append({"packet_id": pid, "case_id": key["case_id"], "problem_class": key["problem_class"], "group_accounting": key["group_accounting"], **{f: c[f] for f in SCORE_FIELDS}, "ihq_without_cpi": d["ihq_without_cpi"], "full_ihq": d["full_ihq"], "validity_composite_descriptive": d["validity_composite_descriptive"], **{f"flag_{n}": v for n, v in c["flags"].items()}, "attempts": len(attempts)})
    rows.sort(key=lambda x: int(x["case_id"]))
    if len(rows) != 6: problems.append(f"expected 6 accepted packets, found {len(rows)}")
    if rows: write_csv(OUT / "scores_by_case.csv", rows)
    summary: dict[str, Any] = {"n_cases": len(rows)}
    if rows:
        for field in [*SCORE_FIELDS, "ihq_without_cpi", "full_ihq", "validity_composite_descriptive"]:
            vals = [float(x[field]) for x in rows]
            summary[f"{field}_median"] = statistics.median(vals); summary[f"{field}_min"] = min(vals); summary[f"{field}_max"] = max(vals)
    flags: Counter[str] = Counter()
    for row in rows:
        for k,v in row.items():
            if k.startswith("flag_") and v != "no": flags[f"{k}:{v}"] += 1
    audit = {"status": "PASS_COMPLETE" if len(rows) == 6 and not problems else "REVIEW", "accepted_packets": len(rows), "requested_and_returned_model": "claude-sonnet-5", "total_api_attempts": total_attempts, "first_attempt_structural_validation_failures": first_fail, "total_input_tokens_all_attempts": total_in, "total_output_tokens_all_attempts": total_out, "non_no_flag_counts": dict(flags), "problems": problems, "score_csv": str(OUT / "scores_by_case.csv")}
    atomic_write_json(OUT / "audit_summary.json", audit); atomic_write_json(OUT / "descriptive_summary.json", summary)
    print(json.dumps({"audit": audit, "summary": summary, "rows": rows}, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "PASS_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
