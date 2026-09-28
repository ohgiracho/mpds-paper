from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from run_independent_judge_anthropic_v2 import TOOL_NAMES, extract_tool_input, normalize_tool_input
from validate_judge_outputs import MAIN_FLAG_FIELDS, SCORE_FIELDS_MAIN, validate_main


IHQ_FIELDS = (
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
)
VALIDITY_FIELDS = (
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
)
DERIVED_FIELDS = ("full_ihq", "ihq_without_cpi", "validity_composite_descriptive")
CONDITION_ORDER = ("raw", "eo", "eop", "ds", "mpds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def iso_key(value: str | None) -> str:
    if not value:
        return "9999-12-31T23:59:59+00:00"
    try:
        return datetime.fromisoformat(value).isoformat()
    except ValueError:
        return value


def candidate_responses(roots: list[Path]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_hashes: set[tuple[str, str]] = set()
    for root in roots:
        for packet_dir in sorted(root.glob("case_*__rep_*")):
            manifest_path = packet_dir / "run_manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            started = iso_key(manifest.get("started_utc"))
            for response_path in sorted(packet_dir.glob("attempt_*_response.json")):
                response_bytes = response_path.read_bytes()
                digest = sha256_bytes(response_bytes)
                dedup_key = (packet_dir.name, digest)
                if dedup_key in seen_hashes:
                    continue
                seen_hashes.add(dedup_key)
                attempt = int(response_path.stem.split("_")[1])
                found[packet_dir.name].append(
                    {
                        "sort_key": (started, attempt, str(response_path)),
                        "attempt": attempt,
                        "response_path": response_path,
                        "response_sha256": digest,
                        "manifest_path": manifest_path,
                        "started_utc": manifest.get("started_utc"),
                    }
                )
    for entries in found.values():
        entries.sort(key=lambda item: item["sort_key"])
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble the earliest valid Pass 1 response for each packet")
    parser.add_argument("--attempt-root", type=Path, action="append", required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    roots = [path.resolve() for path in args.attempt_root]
    blind_key_path = args.blind_key.resolve()
    output = args.output_dir.resolve()
    scores_dir = output / "blinded_scores"
    scores_dir.mkdir(parents=True, exist_ok=False)

    key_rows = read_csv(blind_key_path)
    expected_packets = sorted({row["packet_id"] for row in key_rows})
    key_lookup = {(row["packet_id"], row["alias"]): row for row in key_rows}
    candidates = candidate_responses(roots)

    provenance: list[dict[str, Any]] = []
    blinded_rows: list[dict[str, Any]] = []
    unblinded_rows: list[dict[str, Any]] = []
    rejected_attempts: list[dict[str, Any]] = []

    for packet_id in expected_packets:
        selected: tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], str, dict[str, Any]] | None = None
        for entry in candidates.get(packet_id, []):
            envelope = json.loads(entry["response_path"].read_text(encoding="utf-8"))
            try:
                raw, _ = extract_tool_input(envelope, TOOL_NAMES["main"])
                normalized, normalization = normalize_tool_input("main", raw)
                errors, derived = validate_main(normalized, Path(f"{packet_id}.json"))
            except Exception as exc:
                errors = [f"{type(exc).__name__}: {exc}"]
                normalized, derived, normalization = {}, [], "failed_before_normalization"
            if errors:
                rejected_attempts.append(
                    {
                        "packet_id": packet_id,
                        "response_path": str(entry["response_path"]),
                        "response_sha256": entry["response_sha256"],
                        "reason_count": len(errors),
                        "reasons": " | ".join(errors),
                    }
                )
                continue
            selected = (entry, normalized, derived, normalization, envelope)
            break
        if selected is None:
            raise RuntimeError(f"No valid response found for {packet_id}")

        entry, normalized, derived, normalization, envelope = selected
        (scores_dir / f"{packet_id}.json").write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        provenance.append(
            {
                "packet_id": packet_id,
                "selected_response": str(entry["response_path"]),
                "response_sha256": entry["response_sha256"],
                "attempt": entry["attempt"],
                "started_utc": entry["started_utc"],
                "returned_model": envelope.get("model"),
                "input_tokens": envelope.get("usage", {}).get("input_tokens"),
                "output_tokens": envelope.get("usage", {}).get("output_tokens"),
                "normalization": normalization,
            }
        )
        score_by_alias = {row["alias"]: row for row in normalized["candidate_scores"]}
        derived_by_alias = {row["alias"]: row for row in derived}
        for alias in sorted(score_by_alias):
            score = score_by_alias[alias]
            derived_score = derived_by_alias[alias]
            base = {
                "packet_id": packet_id,
                "alias": alias,
                **{field: score[field] for field in IHQ_FIELDS + VALIDITY_FIELDS},
                **{field: derived_score[field] for field in DERIVED_FIELDS},
                **{f"flag_{field}": score["flags"][field] for field in sorted(MAIN_FLAG_FIELDS)},
            }
            blinded_rows.append(base)
            key = key_lookup[(packet_id, alias)]
            unblinded_rows.append(
                {
                    "case_id": int(key["case_id"]),
                    "replicate_id": int(key["replicate_id"]),
                    "condition": key["condition"],
                    "source_kind": key["source_kind"],
                    **base,
                }
            )

    write_csv(output / "selection_provenance.csv", provenance)
    write_csv(output / "pass1_scores_blinded.csv", blinded_rows)
    write_csv(output / "pass1_scores_unblinded.csv", unblinded_rows)
    write_csv(output / "rejected_attempts.csv", rejected_attempts)

    metrics = IHQ_FIELDS + VALIDITY_FIELDS + DERIVED_FIELDS
    summary_rows: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        subset = [row for row in unblinded_rows if row["condition"] == condition]
        for metric in metrics:
            values = [float(row[metric]) for row in subset]
            summary_rows.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n": len(values),
                    "mean": round(statistics.mean(values), 6),
                    "sd": round(statistics.stdev(values), 6),
                    "median": round(statistics.median(values), 6),
                    "min": min(values),
                    "max": max(values),
                }
            )
    write_csv(output / "condition_summary.csv", summary_rows)

    flag_rows: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        subset = [row for row in unblinded_rows if row["condition"] == condition]
        for field in sorted(MAIN_FLAG_FIELDS):
            values = [row[f"flag_{field}"] for row in subset]
            flag_rows.append(
                {
                    "condition": condition,
                    "flag": field,
                    "n": len(values),
                    "yes": values.count("yes"),
                    "uncertain": values.count("uncertain"),
                    "no": values.count("no"),
                }
            )
    write_csv(output / "condition_flag_summary.csv", flag_rows)

    manifest = {
        "status": "PASS",
        "packets": len(expected_packets),
        "candidate_rows": len(unblinded_rows),
        "conditions": list(CONDITION_ORDER),
        "rows_per_condition": {condition: sum(row["condition"] == condition for row in unblinded_rows) for condition in CONDITION_ORDER},
        "selection_rule": "Earliest HTTP-200 response passing strict validation after deterministic schema projection",
        "required_values_modified": False,
        "blind_key": str(blind_key_path),
        "attempt_roots": [str(path) for path in roots],
        "rejected_attempts": len(rejected_attempts),
        "selected_attempts_after_first": sum(int(row["attempt"]) > 1 for row in provenance),
        "total_selected_input_tokens": sum(int(row["input_tokens"] or 0) for row in provenance),
        "total_selected_output_tokens": sum(int(row["output_tokens"] or 0) for row in provenance),
    }
    (output / "assembly_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
