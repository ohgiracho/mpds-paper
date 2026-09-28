from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

from validate_pass1_component_controls import validate_main


CONDITIONS = ("ds", "mpds", "sair", "ses")
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
FLAG_FIELDS = (
    "scientifically_consequential_error",
    "temporal_cutoff_violation",
    "fixed_task_constraint_violation",
    "infeasible_primary_process",
)
DERIVED_FIELDS = ("full_ihq", "ihq_without_cpi", "validity_composite_descriptive")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble official four-condition Pass 1 scores")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing output directory: {output}")
    key_rows = read_csv(args.blind_key.resolve())
    expected_packets = sorted({row["packet_id"] for row in key_rows})
    if len(expected_packets) != 30 or len(key_rows) != 120:
        raise RuntimeError("Expected a 30-packet / 120-candidate blind key")
    key_lookup = {(row["packet_id"], row["alias"]): row for row in key_rows}

    output.mkdir(parents=True)
    blinded_rows: list[dict[str, Any]] = []
    unblinded_rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []

    for packet_id in expected_packets:
        packet_dir = run_root / packet_id
        manifest_path = packet_dir / "run_manifest.json"
        score_path = packet_dir / "accepted_scores.json"
        if not manifest_path.exists() or not score_path.exists():
            raise RuntimeError(f"Missing official output for {packet_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            raise RuntimeError(f"Non-complete manifest for {packet_id}")
        if manifest.get("transport") != "Official Anthropic Messages API":
            raise RuntimeError(f"Non-direct transport for {packet_id}")
        if manifest.get("endpoint") != "https://api.anthropic.com/v1/messages":
            raise RuntimeError(f"Unexpected endpoint for {packet_id}")
        if manifest.get("returned_model") != "claude-sonnet-5":
            raise RuntimeError(f"Unexpected model for {packet_id}")
        if manifest.get("provider_strict_tool_schema") is not True:
            raise RuntimeError(f"Strict schema was not active for {packet_id}")

        score = json.loads(score_path.read_text(encoding="utf-8"))
        errors, derived = validate_main(score, Path(f"{packet_id}.json"))
        if errors:
            raise RuntimeError(f"Invalid accepted score for {packet_id}: {errors}")
        score_by_alias = {row["alias"]: row for row in score["candidate_scores"]}
        derived_by_alias = {row["alias"]: row for row in derived}
        if set(score_by_alias) != {"Candidate A", "Candidate B", "Candidate C", "Candidate D"}:
            raise RuntimeError(f"Wrong aliases in {packet_id}")

        usage = manifest["attempts"][-1].get("usage", {})
        provenance.append(
            {
                "packet_id": packet_id,
                "selected_score": str(score_path),
                "attempts": len(manifest["attempts"]),
                "returned_model": manifest["returned_model"],
                "transport": manifest["transport"],
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
            }
        )
        for alias in sorted(score_by_alias):
            raw = score_by_alias[alias]
            derived_score = derived_by_alias[alias]
            base = {
                "packet_id": packet_id,
                "alias": alias,
                **{field: raw[field] for field in IHQ_FIELDS + VALIDITY_FIELDS},
                **{field: derived_score[field] for field in DERIVED_FIELDS},
                **{f"flag_{field}": raw["flags"][field] for field in FLAG_FIELDS},
            }
            blinded_rows.append(base)
            key = key_lookup[(packet_id, alias)]
            unblinded_rows.append(
                {
                    "case_id": int(key["case_id"]),
                    "replicate_id": int(key["replicate_id"]),
                    "condition": key["condition"],
                    "source_kind": key["source_kind"],
                    "output_characters": int(key["output_characters"]),
                    **base,
                }
            )

    write_csv(output / "selection_provenance.csv", provenance)
    write_csv(output / "pass1_scores_blinded.csv", blinded_rows)
    write_csv(output / "pass1_scores_unblinded.csv", unblinded_rows)

    metrics = IHQ_FIELDS + VALIDITY_FIELDS + DERIVED_FIELDS
    summary_rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in unblinded_rows if row["condition"] == condition]
        if len(subset) != 30:
            raise RuntimeError(f"Expected 30 rows for {condition}, found {len(subset)}")
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
    for condition in CONDITIONS:
        subset = [row for row in unblinded_rows if row["condition"] == condition]
        for field in FLAG_FIELDS:
            counts = Counter(row[f"flag_{field}"] for row in subset)
            flag_rows.append(
                {
                    "condition": condition,
                    "flag": field,
                    "n": len(subset),
                    "yes": counts["yes"],
                    "uncertain": counts["uncertain"],
                    "no": counts["no"],
                }
            )
    write_csv(output / "condition_flag_summary.csv", flag_rows)

    attempts = [row["attempts"] for row in provenance]
    manifest = {
        "status": "PASS",
        "packets": len(expected_packets),
        "candidate_rows": len(unblinded_rows),
        "conditions": list(CONDITIONS),
        "rows_per_condition": {condition: sum(row["condition"] == condition for row in unblinded_rows) for condition in CONDITIONS},
        "selection_rule": "Accepted score written only after strict local validation of Anthropic direct compact-format tool output",
        "required_values_modified": False,
        "run_root": str(run_root),
        "blind_key": str(args.blind_key.resolve()),
        "attempt_count_histogram": dict(sorted(Counter(attempts).items())),
        "total_selected_input_tokens": sum(int(row["input_tokens"] or 0) for row in provenance),
        "total_selected_output_tokens": sum(int(row["output_tokens"] or 0) for row in provenance),
    }
    (output / "assembly_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
