from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import validate_judge_outputs as validator


EVIDENCE_FLAG_FIELDS = validator.EVIDENCE_FLAG_FIELDS
SUPPORT_VALUES = validator.SUPPORT_VALUES


CONDITIONS = ("ds", "mpds", "sair", "ses")


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_sd(values: list[float]) -> tuple[float, float]:
    return statistics.mean(values), statistics.stdev(values) if len(values) > 1 else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Assemble four-condition component-control Pass 2 results"
    )
    parser.add_argument("--legacy-results", type=Path, required=True)
    parser.add_argument("--new-run-root", type=Path, required=True)
    parser.add_argument("--new-blind-key", type=Path, required=True)
    parser.add_argument("--integrity-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    legacy = args.legacy_results.resolve()
    new_root = args.new_run_root.resolve()
    key_path = args.new_blind_key.resolve()
    integrity_path = args.integrity_manifest.resolve()
    output = args.output_dir.resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite existing output directory: {output}")

    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    reuse = integrity.get("ds_mpds_reuse_audit", {})
    if reuse.get("decision") != "REUSE_EXISTING_OFFICIAL_DS_MPDS_PASS2_RESULTS":
        raise RuntimeError("DS/MPDS reuse was not frozen as approved")
    if (
        reuse.get("source_output_sha256_matches") != 60
        or reuse.get("evidence_record_group_matches") != 60
        or reuse.get("case_knowledge_snapshot_matches") != 10
    ):
        raise RuntimeError("DS/MPDS reuse integrity counts are incomplete")

    legacy_scores_path = legacy / "pass2_scores_unblinded.csv"
    legacy_claims_path = legacy / "pass2_claims_unblinded.csv"
    legacy_manifest_path = legacy / "assembly_manifest.json"
    legacy_manifest = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
    if legacy_manifest.get("status") != "PASS" or legacy_manifest.get("strict_validation_errors") != 0:
        raise RuntimeError("Legacy official Pass 2 results are not strictly validated")

    score_rows: list[dict[str, Any]] = [
        dict(row)
        for row in read_csv(legacy_scores_path)
        if row["condition"] in {"ds", "mpds"}
    ]
    claim_rows: list[dict[str, Any]] = [
        dict(row)
        for row in read_csv(legacy_claims_path)
        if row["condition"] in {"ds", "mpds"}
    ]
    if len(score_rows) != 60:
        raise RuntimeError(f"Expected 60 reused DS/MPDS rows, found {len(score_rows)}")

    key_rows = read_csv(key_path)
    if len(key_rows) != 60:
        raise RuntimeError(f"Expected 60 SAIR/SES key rows, found {len(key_rows)}")
    if {row["condition"] for row in key_rows} != {"sair", "ses"}:
        raise RuntimeError("New key contains conditions other than SAIR/SES")
    key_lookup = {(row["packet_id"], row["alias"]): row for row in key_rows}
    packet_ids = sorted({row["packet_id"] for row in key_rows})
    if len(packet_ids) != 30:
        raise RuntimeError(f"Expected 30 packets, found {len(packet_ids)}")

    provenance: list[dict[str, Any]] = []
    selected_usage: Counter[str] = Counter()
    for packet_id in packet_ids:
        packet_dir = new_root / packet_id
        score_path = packet_dir / "accepted_scores.json"
        manifest_path = packet_dir / "run_manifest.json"
        if not score_path.exists() or not manifest_path.exists():
            raise RuntimeError(f"Missing accepted output for {packet_id}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            raise RuntimeError(f"Non-complete run manifest for {packet_id}")
        if manifest.get("transport") != "Official Anthropic Messages API":
            raise RuntimeError(f"Unexpected transport for {packet_id}")
        if manifest.get("requested_model") != "claude-sonnet-5":
            raise RuntimeError(f"Unexpected model for {packet_id}")
        if manifest.get("provider_strict_tool_schema") is not True:
            raise RuntimeError(f"Strict provider schema not active for {packet_id}")

        scores = json.loads(score_path.read_text(encoding="utf-8"))
        validator.ALIASES = expected_aliases = {
            row["alias"] for row in key_rows if row["packet_id"] == packet_id
        }
        errors, derived = validator.validate_evidence(scores, Path(f"{packet_id}.json"))
        if errors:
            raise RuntimeError(f"Invalid accepted output for {packet_id}: {errors}")
        derived_by_alias = {row["alias"]: row for row in derived}
        audits = scores["candidate_audits"]
        if {audit["alias"] for audit in audits} != expected_aliases:
            raise RuntimeError(f"Alias mismatch in accepted output for {packet_id}")

        for request in manifest.get("candidate_requests", []):
            usage = request.get("usage", {})
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                selected_usage[field] += int(usage.get(field) or 0)

        provenance.append(
            {
                "packet_id": packet_id,
                "selection": "NEW_OFFICIAL_SAIR_SES_PASS2",
                "accepted_scores": str(score_path),
                "accepted_scores_sha256": sha256_file(score_path),
                "run_manifest": str(manifest_path),
                "run_manifest_sha256": sha256_file(manifest_path),
            }
        )
        for audit in audits:
            alias = audit["alias"]
            key = key_lookup[(packet_id, alias)]
            base = {
                "case_id": int(key["case_id"]),
                "replicate_id": int(key["replicate_id"]),
                "condition": key["condition"],
                "source_kind": "dual_pool_component_control",
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
            score_rows.append(base)
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

    counts = Counter(row["condition"] for row in score_rows)
    if counts != Counter({condition: 30 for condition in CONDITIONS}):
        raise RuntimeError(f"Unbalanced four-condition rows: {dict(counts)}")
    output.mkdir(parents=True)
    score_rows.sort(key=lambda row: (int(row["case_id"]), int(row["replicate_id"]), row["condition"]))
    claim_rows.sort(
        key=lambda row: (
            int(row["case_id"]),
            int(row["replicate_id"]),
            row["condition"],
            row["claim_id"],
        )
    )
    write_csv(output / "pass2_scores_unblinded.csv", score_rows)
    write_csv(output / "pass2_claims_unblinded.csv", claim_rows)
    write_csv(output / "selection_provenance_new_sair_ses.csv", provenance)

    condition_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in score_rows if row["condition"] == condition]
        for metric in ("evidence_support", "citation_traceability", "claims"):
            values = [float(row[metric]) for row in subset]
            mean, sd = mean_sd(values)
            condition_summary.append(
                {
                    "condition": condition,
                    "metric": metric,
                    "n": len(values),
                    "mean": round(mean, 6),
                    "sd": round(sd, 6),
                    "median": statistics.median(values),
                    "min": min(values),
                    "max": max(values),
                }
            )
    write_csv(output / "condition_summary.csv", condition_summary)

    claim_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in claim_rows if row["condition"] == condition]
        status_counts = Counter(row["support_status"] for row in subset)
        total = len(subset)
        claim_summary.append(
            {
                "condition": condition,
                "claims": total,
                **{status: status_counts[status] for status in sorted(SUPPORT_VALUES)},
                "strict_supported_rate": round(status_counts["supported"] / total, 6),
                "supported_or_partial_rate": round(
                    (status_counts["supported"] + status_counts["partially_supported"]) / total,
                    6,
                ),
                "unsupported_or_contradicted_rate": round(
                    (status_counts["unsupported"] + status_counts["contradicted"]) / total,
                    6,
                ),
                "unverifiable_rate": round(status_counts["unverifiable"] / total, 6),
            }
        )
    write_csv(output / "claim_status_summary.csv", claim_summary)

    flag_summary: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        subset = [row for row in score_rows if row["condition"] == condition]
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

    manifest = {
        "status": "PASS",
        "packets": len(packet_ids),
        "candidate_rows": len(score_rows),
        "claim_rows": len(claim_rows),
        "conditions": list(CONDITIONS),
        "rows_per_condition": dict(counts),
        "strict_validation_errors": 0,
        "ds_mpds_source": "reused from prior official Pass 2 after exact source/evidence integrity audit",
        "sair_ses_source": "new official Anthropic single-candidate Pass 2 calls",
        "selected_new_sair_ses_usage": dict(selected_usage),
        "legacy_results": str(legacy),
        "legacy_scores_sha256": sha256_file(legacy_scores_path),
        "legacy_claims_sha256": sha256_file(legacy_claims_path),
        "new_run_root": str(new_root),
        "new_blind_key": str(key_path),
        "new_blind_key_sha256": sha256_file(key_path),
        "integrity_manifest": str(integrity_path),
        "integrity_manifest_sha256": sha256_file(integrity_path),
    }
    (output / "assembly_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
