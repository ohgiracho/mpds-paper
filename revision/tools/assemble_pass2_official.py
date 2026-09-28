from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from validate_judge_outputs import EVIDENCE_FLAG_FIELDS, SUPPORT_VALUES, validate_evidence


CONDITION_ORDER = ("raw", "eo", "eop", "ds", "mpds")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def mean_sd(values: list[float]) -> tuple[float, float]:
    return (
        round(statistics.mean(values), 6),
        round(statistics.stdev(values), 6) if len(values) > 1 else 0.0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble and unblind official Pass 2 results")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--blind-key", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    blind_key = args.blind_key.resolve()
    output = args.output_dir.resolve()
    blinded_dir = output / "blinded_scores"
    blinded_dir.mkdir(parents=True, exist_ok=False)

    key_rows = read_csv(blind_key)
    if len(key_rows) != 150:
        raise RuntimeError(f"Expected 150 blind-key rows, found {len(key_rows)}")
    key_lookup = {(row["packet_id"], row["alias"]): row for row in key_rows}
    expected_packets = sorted({row["packet_id"] for row in key_rows})
    if len(expected_packets) != 30:
        raise RuntimeError(f"Expected 30 packets in blind key, found {len(expected_packets)}")

    candidate_rows: list[dict[str, Any]] = []
    claim_rows: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    all_errors: dict[str, list[str]] = {}
    selected_usage = Counter()
    normalization_events: list[dict[str, Any]] = []

    for packet_id in expected_packets:
        packet_dir = run_root / packet_id
        score_path = packet_dir / "accepted_scores.json"
        manifest_path = packet_dir / "run_manifest.json"
        if not score_path.exists() or not manifest_path.exists():
            all_errors[packet_id] = ["missing accepted_scores.json or run_manifest.json"]
            continue
        scores = json.loads(score_path.read_text(encoding="utf-8"))
        errors, derived = validate_evidence(scores, Path(f"{packet_id}.json"))
        if errors:
            all_errors[packet_id] = errors
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            all_errors[packet_id] = ["run manifest is not COMPLETE"]
            continue
        (blinded_dir / f"{packet_id}.json").write_text(
            json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        provenance.append(
            {
                "packet_id": packet_id,
                "accepted_scores": str(score_path),
                "accepted_scores_sha256": sha256_file(score_path),
                "run_manifest": str(manifest_path),
                "run_manifest_sha256": sha256_file(manifest_path),
                "candidate_calls": len(manifest.get("candidate_requests", [])),
            }
        )
        for request in manifest.get("candidate_requests", []):
            usage = request.get("usage", {})
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                selected_usage[field] += int(usage.get(field) or 0)
            for action in request.get("normalization_actions", []):
                normalization_events.append(
                    {"packet_id": packet_id, "alias": request.get("alias"), "action": action}
                )

        derived_by_alias = {row["alias"]: row for row in derived}
        for audit in scores["candidate_audits"]:
            alias = audit["alias"]
            key = key_lookup[(packet_id, alias)]
            base = {
                "case_id": int(key["case_id"]),
                "replicate_id": int(key["replicate_id"]),
                "condition": key["condition"],
                "source_kind": key["source_kind"],
                "packet_id": packet_id,
                "alias": alias,
                "evidence_support": audit["evidence_support"],
                "citation_traceability": audit["citation_traceability"],
                "claims": derived_by_alias[alias]["claims"],
                **{
                    f"flag_{field}": audit["flags"][field]
                    for field in sorted(EVIDENCE_FLAG_FIELDS)
                },
                "audit_rationale": audit["audit_rationale"],
                "uncertainty_notes": audit["uncertainty_notes"],
            }
            candidate_rows.append(base)
            for claim in audit["central_claims"]:
                claim_rows.append(
                    {
                        "case_id": base["case_id"],
                        "replicate_id": base["replicate_id"],
                        "condition": base["condition"],
                        "packet_id": packet_id,
                        "alias": alias,
                        "claim_id": claim["claim_id"],
                        "support_status": claim["support_status"],
                        "cited_evidence_count": len(claim["cited_evidence_labels"]),
                        "cited_evidence_labels": "|".join(claim["cited_evidence_labels"]),
                        "claim_text": claim["claim_text"],
                        "rationale": claim["rationale"],
                    }
                )

    if all_errors:
        raise RuntimeError(json.dumps(all_errors, ensure_ascii=False, indent=2))
    if len(candidate_rows) != 150:
        raise RuntimeError(f"Expected 150 candidate rows, found {len(candidate_rows)}")

    candidate_rows.sort(key=lambda row: (row["case_id"], row["replicate_id"], row["alias"]))
    claim_rows.sort(
        key=lambda row: (row["case_id"], row["replicate_id"], row["alias"], row["claim_id"])
    )
    write_csv(output / "pass2_scores_unblinded.csv", candidate_rows)
    write_csv(output / "pass2_claims_unblinded.csv", claim_rows)
    write_csv(output / "selection_provenance.csv", provenance)
    write_csv(output / "normalization_events.csv", normalization_events)

    condition_summary: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        subset = [row for row in candidate_rows if row["condition"] == condition]
        for metric in ("evidence_support", "citation_traceability", "claims"):
            values = [float(row[metric]) for row in subset]
            mean, sd = mean_sd(values)
            condition_summary.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n": len(values),
                    "mean": mean,
                    "sd": sd,
                    "median": statistics.median(values),
                    "min": min(values),
                    "max": max(values),
                }
            )
    write_csv(output / "condition_summary.csv", condition_summary)

    claim_summary: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        subset = [row for row in claim_rows if row["condition"] == condition]
        counts = Counter(row["support_status"] for row in subset)
        total = len(subset)
        claim_summary.append(
            {
                "condition": condition,
                "claims": total,
                **{status: counts[status] for status in sorted(SUPPORT_VALUES)},
                "strict_supported_rate": round(counts["supported"] / total, 6),
                "supported_or_partial_rate": round(
                    (counts["supported"] + counts["partially_supported"]) / total, 6
                ),
                "unsupported_or_contradicted_rate": round(
                    (counts["unsupported"] + counts["contradicted"]) / total, 6
                ),
                "unverifiable_rate": round(counts["unverifiable"] / total, 6),
            }
        )
    write_csv(output / "claim_status_summary.csv", claim_summary)

    flag_summary: list[dict[str, Any]] = []
    for condition in CONDITION_ORDER:
        subset = [row for row in candidate_rows if row["condition"] == condition]
        for field in sorted(EVIDENCE_FLAG_FIELDS):
            values = [row[f"flag_{field}"] for row in subset]
            flag_summary.append(
                {
                    "condition": condition,
                    "flag": field,
                    "n": len(values),
                    "yes": values.count("yes"),
                    "uncertain": values.count("uncertain"),
                    "no": values.count("no"),
                }
            )
    write_csv(output / "flag_summary.csv", flag_summary)

    case_means: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
    for case_id in sorted({row["case_id"] for row in candidate_rows}):
        for condition in CONDITION_ORDER:
            subset = [
                row
                for row in candidate_rows
                if row["case_id"] == case_id and row["condition"] == condition
            ]
            for metric in ("evidence_support", "citation_traceability"):
                case_means[(case_id, condition)][metric] = statistics.mean(
                    float(row[metric]) for row in subset
                )
    paired_rows: list[dict[str, Any]] = []
    for metric in ("evidence_support", "citation_traceability"):
        deltas = []
        for case_id in sorted({row["case_id"] for row in candidate_rows}):
            mpds = case_means[(case_id, "mpds")][metric]
            ds = case_means[(case_id, "ds")][metric]
            delta = mpds - ds
            deltas.append(delta)
            paired_rows.append(
                {
                    "row_type": "case",
                    "metric": metric,
                    "case_id": case_id,
                    "mpds_mean": round(mpds, 6),
                    "ds_mean": round(ds, 6),
                    "mpds_minus_ds": round(delta, 6),
                    "mean_delta": "",
                    "wins": "",
                    "ties": "",
                    "losses": "",
                }
            )
        paired_rows.append(
            {
                "row_type": "summary",
                "metric": metric,
                "case_id": "",
                "mpds_mean": "",
                "ds_mean": "",
                "mpds_minus_ds": "",
                "mean_delta": round(statistics.mean(deltas), 6),
                "wins": sum(delta > 0 for delta in deltas),
                "ties": sum(delta == 0 for delta in deltas),
                "losses": sum(delta < 0 for delta in deltas),
            }
        )
    write_csv(output / "mpds_vs_ds_case_means.csv", paired_rows)

    manifest = {
        "status": "PASS",
        "packets": len(expected_packets),
        "candidate_rows": len(candidate_rows),
        "claim_rows": len(claim_rows),
        "rows_per_condition": {
            condition: sum(row["condition"] == condition for row in candidate_rows)
            for condition in CONDITION_ORDER
        },
        "strict_validation_errors": 0,
        "normalization_events": len(normalization_events),
        "selected_usage": dict(selected_usage),
        "run_root": str(run_root),
        "blind_key": str(blind_key),
        "blind_key_sha256": sha256_file(blind_key),
    }
    (output / "assembly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
