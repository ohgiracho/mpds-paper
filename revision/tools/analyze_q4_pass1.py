from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from corpus_size_common import atomic_write_json
from validate_pass1_q4_single import validate_main
from validate_q4_setup import REVISION_ROOT


RESULTS = REVISION_ROOT / "results" / "pass1_sonnet5_q4_v1"
KEY = REVISION_ROOT / "evaluation" / "q4_pass1_blind_key_v1_DO_NOT_SHARE" / "blind_key.json"
INTEGRITY = REVISION_ROOT / "evaluation" / "q4_pass1_input_integrity_manifest_v1.json"
OUT = REVISION_ROOT / "analysis" / "q4_pass1_sonnet5_v1"
SCORE_FIELDS = [
    "idea_novelty", "mechanistic_originality", "tradeoff_reframing", "cross_perspective_integration",
    "scientific_correctness", "physical_plausibility", "constraint_adherence", "falsifiability_actionability",
]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def mean_sd(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    mapping = {row["packet_id"]: row for row in json.loads(KEY.read_text(encoding="utf-8"))["mapping"]}
    integrity = {row["packet_id"]: row for row in json.loads(INTEGRITY.read_text(encoding="utf-8"))["packets"]}
    problems: list[str] = []
    rows: list[dict[str, Any]] = []
    total_attempts = 0
    total_input_tokens = 0
    total_output_tokens = 0
    first_attempt_validation_failures = 0
    for packet_id, key in sorted(mapping.items()):
        folder = RESULTS / packet_id
        manifest_path = folder / "run_manifest.json"
        scores_path = folder / "accepted_scores.json"
        if not manifest_path.is_file() or not scores_path.is_file():
            problems.append(f"{packet_id}: missing result")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        data = json.loads(scores_path.read_text(encoding="utf-8"))
        errors, derived = validate_main(data, Path(f"{packet_id}.json"))
        if errors:
            problems.extend(f"{packet_id}: {error}" for error in errors)
            continue
        if manifest.get("status") != "COMPLETE" or manifest.get("returned_model") != "claude-sonnet-5":
            problems.append(f"{packet_id}: incomplete or returned-model mismatch")
        packet_path = REVISION_ROOT / "evaluation" / "blind_packets_q4_v1" / f"{packet_id}.md"
        from build_blind_packets import sha256_file
        if sha256_file(packet_path) != integrity[packet_id]["packet_sha256"]:
            problems.append(f"{packet_id}: packet hash mismatch")
        attempts = manifest.get("attempts") or []
        total_attempts += len(attempts)
        for index, attempt in enumerate(attempts):
            usage = attempt.get("usage") or {}
            total_input_tokens += int(usage.get("input_tokens") or 0)
            total_output_tokens += int(usage.get("output_tokens") or 0)
            if index == 0 and attempt.get("validation_errors"):
                first_attempt_validation_failures += 1
        candidate = data["candidate_scores"][0]
        derived_row = derived[0]
        row = {
            "packet_id": packet_id,
            "kind": key["kind"],
            "case_id": key["case_id"],
            "replicate_id": key["replicate_id"],
            **{field: candidate[field] for field in SCORE_FIELDS},
            "ihq_without_cpi": derived_row["ihq_without_cpi"],
            "full_ihq": derived_row["full_ihq"],
            "validity_composite_descriptive": derived_row["validity_composite_descriptive"],
            **{f"flag_{name}": value for name, value in candidate["flags"].items()},
            "attempts": len(attempts),
            "accepted_input_tokens": int((attempts[-1].get("usage") or {}).get("input_tokens") or 0),
            "accepted_output_tokens": int((attempts[-1].get("usage") or {}).get("output_tokens") or 0),
        }
        rows.append(row)
    rows.sort(key=lambda row: (0 if row["kind"] == "breadth" else 1, int(row["case_id"]), int(row["replicate_id"])))
    if len(rows) != 11:
        problems.append(f"expected 11 accepted packets, found {len(rows)}")
    if rows:
        write_csv(OUT / "scores_by_output.csv", rows)

    summaries: list[dict[str, Any]] = []
    for kind in ("breadth", "integrated"):
        subset = [row for row in rows if row["kind"] == kind]
        summary: dict[str, Any] = {"group": kind, "n_outputs": len(subset)}
        for field in [*SCORE_FIELDS, "ihq_without_cpi", "full_ihq", "validity_composite_descriptive"]:
            avg, sd = mean_sd([float(row[field]) for row in subset])
            summary[f"{field}_mean"] = round(avg, 3)
            summary[f"{field}_sd"] = round(sd, 3)
            summary[f"{field}_min"] = min(row[field] for row in subset)
            summary[f"{field}_max"] = max(row[field] for row in subset)
        summaries.append(summary)
    write_csv(OUT / "group_summary.csv", summaries)

    flag_counts: Counter[str] = Counter()
    for row in rows:
        for key, value in row.items():
            if key.startswith("flag_") and value != "no":
                flag_counts[f"{key}:{value}"] += 1
    audit = {
        "status": "PASS_COMPLETE" if len(rows) == 11 and not problems else "REVIEW",
        "accepted_packets": len(rows),
        "requested_and_returned_model": "claude-sonnet-5",
        "total_api_attempts": total_attempts,
        "first_attempt_structural_validation_failures": first_attempt_validation_failures,
        "total_input_tokens_all_attempts": total_input_tokens,
        "total_output_tokens_all_attempts": total_output_tokens,
        "non_no_flag_counts": dict(flag_counts),
        "problems": problems,
        "score_csv": str(OUT / "scores_by_output.csv"),
        "summary_csv": str(OUT / "group_summary.csv"),
    }
    atomic_write_json(OUT / "audit_summary.json", audit)
    print(json.dumps({"audit": audit, "group_summary": summaries}, ensure_ascii=False, indent=2))
    return 0 if audit["status"] == "PASS_COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
