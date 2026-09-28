from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


ALIASES = {"Candidate A", "Candidate B", "Candidate C"}
SCORE_FIELDS = {
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
}
FLAG_FIELDS = {
    "scientifically_consequential_error",
    "temporal_cutoff_violation",
    "fixed_task_constraint_violation",
    "infeasible_primary_process",
}
FLAG_VALUES = {"yes", "no", "uncertain"}
PACKET_PATTERN = re.compile(r"^case_[0-9]{2}__rep_[0-9]{2}$")


def exact_keys(value: dict[str, Any], expected: set[str], context: str, errors: list[str]) -> None:
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{context}: key mismatch; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def validate_score(value: Any, context: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
        errors.append(f"{context}: expected integer 0-5, got {value!r}")


def validate_main(data: Any, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    derived: list[dict[str, Any]] = []
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be an object"], []
    exact_keys(data, {"packet_id", "candidate_scores"}, path.name, errors)
    packet_id = data.get("packet_id")
    if not isinstance(packet_id, str) or not PACKET_PATTERN.fullmatch(packet_id):
        errors.append(f"{path.name}: invalid packet_id {packet_id!r}")
    if path.stem != packet_id:
        errors.append(f"{path.name}: filename must match packet_id {packet_id!r}")

    items = data.get("candidate_scores")
    if not isinstance(items, list) or len(items) != 3:
        errors.append(f"{path.name}: expected exactly three candidates")
        return errors, []
    aliases = [item.get("alias") if isinstance(item, dict) else None for item in items]
    if set(aliases) != ALIASES or len(set(aliases)) != 3:
        errors.append(f"{path.name}: Candidate A-C must each occur exactly once; got {aliases}")

    expected = {
        "alias",
        *SCORE_FIELDS,
        "flags",
        "ihq_rationale",
        "validity_rationale",
        "uncertainty_notes",
    }
    for index, item in enumerate(items):
        context = f"{path.name}.candidate_scores[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{context}: must be an object")
            continue
        exact_keys(item, expected, context, errors)
        for field in SCORE_FIELDS:
            if field in item:
                validate_score(item[field], f"{context}.{field}", errors)
        flags = item.get("flags")
        if not isinstance(flags, dict):
            errors.append(f"{context}.flags: must be an object")
        else:
            exact_keys(flags, FLAG_FIELDS, f"{context}.flags", errors)
            for field in FLAG_FIELDS:
                if field in flags and flags[field] not in FLAG_VALUES:
                    errors.append(f"{context}.flags.{field}: invalid value {flags[field]!r}")
        for field in ("ihq_rationale", "validity_rationale"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"{context}.{field}: must be a nonempty string")
        if not isinstance(item.get("uncertainty_notes"), str):
            errors.append(f"{context}.uncertainty_notes: must be a string")

        if all(isinstance(item.get(field), int) and not isinstance(item.get(field), bool) for field in SCORE_FIELDS):
            full_ihq = sum(
                item[field]
                for field in (
                    "idea_novelty",
                    "mechanistic_originality",
                    "tradeoff_reframing",
                    "cross_perspective_integration",
                )
            )
            ihq_without_cpi = sum(
                item[field]
                for field in ("idea_novelty", "mechanistic_originality", "tradeoff_reframing")
            )
            validity = sum(
                item[field]
                for field in (
                    "scientific_correctness",
                    "physical_plausibility",
                    "constraint_adherence",
                    "falsifiability_actionability",
                )
            )
            derived.append(
                {
                    "packet_id": packet_id,
                    "alias": item.get("alias", ""),
                    **{field: item[field] for field in sorted(SCORE_FIELDS)},
                    "full_ihq": full_ihq,
                    "ihq_without_cpi": ihq_without_cpi,
                    "validity_composite_descriptive": validity,
                }
            )
    return errors, derived


def valid_synthetic(packet_id: str = "case_01__rep_01") -> dict[str, Any]:
    return {
        "packet_id": packet_id,
        "candidate_scores": [
            {
                "alias": alias,
                **{field: 3 for field in SCORE_FIELDS},
                "flags": {field: "no" for field in FLAG_FIELDS},
                "ihq_rationale": "Synthetic validator self-test.",
                "validity_rationale": "Synthetic validator self-test.",
                "uncertainty_notes": "",
            }
            for alias in ("Candidate A", "Candidate B", "Candidate C")
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate three-ordering LITM Pass 1 outputs")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--expected-packets", type=int, default=12)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--derived-csv", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sample = valid_synthetic()
        errors, derived = validate_main(sample, Path("case_01__rep_01.json"))
        wrong = dict(sample)
        wrong["candidate_scores"] = sample["candidate_scores"][:2]
        wrong_errors, _ = validate_main(wrong, Path("case_01__rep_01.json"))
        passed = not errors and len(derived) == 3 and bool(wrong_errors)
        print(json.dumps({"status": "PASS" if passed else "FAIL", "self_test": True}, ensure_ascii=False))
        raise SystemExit(0 if passed else 2)
    if args.input_dir is None:
        raise SystemExit("--input-dir is required unless --self-test is used")

    files = sorted(args.input_dir.resolve().glob("case_*__rep_*.json"))
    all_errors: dict[str, list[str]] = {}
    derived_rows: list[dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            all_errors[path.name] = [f"invalid JSON: {exc}"]
            continue
        errors, derived = validate_main(data, path)
        if errors:
            all_errors[path.name] = errors
        else:
            derived_rows.extend(derived)
    if len(files) != args.expected_packets:
        all_errors["_packet_count"] = [f"expected {args.expected_packets}, found {len(files)}"]

    summary = {
        "status": "PASS" if not all_errors else "FAIL",
        "mode": "main_litm_3ordering",
        "expected_packets": args.expected_packets,
        "json_files": len(files),
        "valid_packets": len(files) - sum(1 for key in all_errors if not key.startswith("_")),
        "derived_rows": len(derived_rows),
        "errors": all_errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.summary:
        args.summary.resolve().write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.derived_csv:
        write_csv(args.derived_csv.resolve(), derived_rows)
    if all_errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
