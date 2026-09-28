from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ALIASES = {f"Candidate {letter}" for letter in "ABCDE"}
SCORE_FIELDS_MAIN = {
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
}
MAIN_FLAG_FIELDS = {
    "scientifically_consequential_error",
    "temporal_cutoff_violation",
    "fixed_task_constraint_violation",
    "infeasible_primary_process",
}
EVIDENCE_FLAG_FIELDS = {
    "consequential_unsupported_or_contradicted_claim",
    "fabricated_or_invalid_citation_identifier",
}
FLAG_VALUES = {"yes", "no", "uncertain"}
SUPPORT_VALUES = {"supported", "partially_supported", "unsupported", "contradicted", "unverifiable"}
PACKET_PATTERN = re.compile(r"^case_[0-9]{2}__rep_[0-9]{2}$")


def exact_keys(value: dict[str, Any], expected: set[str], context: str, errors: list[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        errors.append(f"{context}: key mismatch; missing={missing}, extra={extra}")


def validate_score(value: Any, context: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        errors.append(f"{context}: expected integer 0-5, got {value!r}")


def validate_flags(value: Any, fields: set[str], context: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{context}: flags must be an object")
        return
    exact_keys(value, fields, context, errors)
    for key in fields:
        if key in value and value[key] not in FLAG_VALUES:
            errors.append(f"{context}.{key}: invalid value {value[key]!r}")


def validate_aliases(items: Any, context: str, errors: list[str]) -> bool:
    expected_count = len(ALIASES)
    if not isinstance(items, list) or len(items) != expected_count:
        errors.append(f"{context}: expected exactly {expected_count} candidates")
        return False
    aliases = [item.get("alias") if isinstance(item, dict) else None for item in items]
    if set(aliases) != ALIASES or len(set(aliases)) != expected_count:
        errors.append(
            f"{context}: {sorted(ALIASES)} must each occur exactly once; got {aliases}"
        )
    return True


def validate_common(data: Any, path: Path, list_key: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        errors.append(f"{path.name}: top level must be an object")
        return []
    exact_keys(data, {"packet_id", list_key}, path.name, errors)
    packet_id = data.get("packet_id")
    if not isinstance(packet_id, str) or not PACKET_PATTERN.fullmatch(packet_id):
        errors.append(f"{path.name}: invalid packet_id {packet_id!r}")
    if path.stem != packet_id:
        errors.append(f"{path.name}: filename must match packet_id {packet_id!r}")
    items = data.get(list_key)
    validate_aliases(items, path.name, errors)
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def validate_main(data: Any, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    derived: list[dict[str, Any]] = []
    items = validate_common(data, path, "candidate_scores", errors)
    expected = {
        "alias",
        *SCORE_FIELDS_MAIN,
        "flags",
        "ihq_rationale",
        "validity_rationale",
        "uncertainty_notes",
    }
    for index, item in enumerate(items):
        context = f"{path.name}.candidate_scores[{index}]"
        exact_keys(item, expected, context, errors)
        for field in SCORE_FIELDS_MAIN:
            if field in item:
                validate_score(item[field], f"{context}.{field}", errors)
        validate_flags(item.get("flags"), MAIN_FLAG_FIELDS, f"{context}.flags", errors)
        for field in ("ihq_rationale", "validity_rationale"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{context}.{field}: must be a nonempty string")
        if not isinstance(item.get("uncertainty_notes"), str):
            errors.append(f"{context}.uncertainty_notes: must be a string")
        if all(isinstance(item.get(field), int) and not isinstance(item.get(field), bool) for field in SCORE_FIELDS_MAIN):
            full_ihq = sum(item[field] for field in (
                "idea_novelty", "mechanistic_originality", "tradeoff_reframing", "cross_perspective_integration"
            ))
            ihq_without_cpi = sum(item[field] for field in (
                "idea_novelty", "mechanistic_originality", "tradeoff_reframing"
            ))
            validity = sum(item[field] for field in (
                "scientific_correctness", "physical_plausibility", "constraint_adherence", "falsifiability_actionability"
            ))
            derived.append({
                "packet_id": data.get("packet_id", ""),
                "alias": item.get("alias", ""),
                **{field: item[field] for field in sorted(SCORE_FIELDS_MAIN)},
                "full_ihq": full_ihq,
                "ihq_without_cpi": ihq_without_cpi,
                "validity_composite_descriptive": validity,
            })
    return errors, derived


def validate_evidence(data: Any, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    derived: list[dict[str, Any]] = []
    items = validate_common(data, path, "candidate_audits", errors)
    expected = {
        "alias",
        "evidence_support",
        "citation_traceability",
        "central_claims",
        "flags",
        "audit_rationale",
        "uncertainty_notes",
    }
    claim_expected = {"claim_id", "claim_text", "cited_evidence_labels", "support_status", "rationale"}
    for index, item in enumerate(items):
        context = f"{path.name}.candidate_audits[{index}]"
        exact_keys(item, expected, context, errors)
        validate_score(item.get("evidence_support"), f"{context}.evidence_support", errors)
        validate_score(item.get("citation_traceability"), f"{context}.citation_traceability", errors)
        validate_flags(item.get("flags"), EVIDENCE_FLAG_FIELDS, f"{context}.flags", errors)
        for field in ("audit_rationale",):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{context}.{field}: must be a nonempty string")
        if not isinstance(item.get("uncertainty_notes"), str):
            errors.append(f"{context}.uncertainty_notes: must be a string")

        claims = item.get("central_claims")
        statuses: list[str] = []
        if not isinstance(claims, list) or not 1 <= len(claims) <= 5:
            errors.append(f"{context}.central_claims: expected one to five claims")
            claims = []
        expected_claim_ids = [f"C{claim_index}" for claim_index in range(1, len(claims) + 1)]
        actual_claim_ids = []
        for claim_index, claim in enumerate(claims):
            claim_context = f"{context}.central_claims[{claim_index}]"
            if not isinstance(claim, dict):
                errors.append(f"{claim_context}: must be an object")
                continue
            exact_keys(claim, claim_expected, claim_context, errors)
            actual_claim_ids.append(claim.get("claim_id"))
            for field in ("claim_text", "rationale"):
                if not isinstance(claim.get(field), str) or not claim[field].strip():
                    errors.append(f"{claim_context}.{field}: must be a nonempty string")
            labels = claim.get("cited_evidence_labels")
            if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels) or len(labels) != len(set(labels)):
                errors.append(f"{claim_context}.cited_evidence_labels: must be a unique string array")
            status = claim.get("support_status")
            if status not in SUPPORT_VALUES:
                errors.append(f"{claim_context}.support_status: invalid value {status!r}")
            else:
                statuses.append(status)
        if actual_claim_ids != expected_claim_ids:
            errors.append(f"{context}.central_claims: claim IDs must be sequential {expected_claim_ids}; got {actual_claim_ids}")
        derived.append({
            "packet_id": data.get("packet_id", ""),
            "alias": item.get("alias", ""),
            "evidence_support": item.get("evidence_support"),
            "citation_traceability": item.get("citation_traceability"),
            "claims": len(statuses),
            **{f"claims_{status}": statuses.count(status) for status in sorted(SUPPORT_VALUES)},
        })
    return errors, derived


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly validate blinded judge JSON and calculate derived totals")
    parser.add_argument("--mode", choices=("main", "evidence"), required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--expected-packets", type=int, default=30)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--derived-csv", type=Path)
    args = parser.parse_args()

    files = sorted(args.input_dir.resolve().glob("case_*__rep_*.json"))
    all_errors: dict[str, list[str]] = {}
    derived_rows: list[dict[str, Any]] = []
    validator = validate_main if args.mode == "main" else validate_evidence
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            all_errors[path.name] = [f"invalid JSON: {exc}"]
            continue
        errors, derived = validator(data, path)
        if errors:
            all_errors[path.name] = errors
        else:
            derived_rows.extend(derived)

    if len(files) != args.expected_packets:
        all_errors["_packet_count"] = [f"expected {args.expected_packets}, found {len(files)}"]
    summary = {
        "status": "PASS" if not all_errors else "FAIL",
        "mode": args.mode,
        "expected_packets": args.expected_packets,
        "json_files": len(files),
        "valid_packets": len(files) - sum(1 for key in all_errors if not key.startswith("_")),
        "derived_rows": len(derived_rows),
        "errors": all_errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.summary:
        args.summary.resolve().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.derived_csv and derived_rows:
        write_csv(args.derived_csv.resolve(), derived_rows)
    if all_errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
