from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import validate_pass1_litm as frozen


ALIASES = {"Candidate A", "Candidate B"}


def validate_main(data: Any, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Keep the frozen Pass 1 field/range/derived-score logic; change only cardinality."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be an object"], []
    frozen.exact_keys(data, {"packet_id", "candidate_scores"}, path.name, errors)
    packet_id = data.get("packet_id")
    if not isinstance(packet_id, str) or not frozen.PACKET_PATTERN.fullmatch(packet_id):
        errors.append(f"{path.name}: invalid packet_id {packet_id!r}")
    if path.stem != packet_id:
        errors.append(f"{path.name}: filename must match packet_id {packet_id!r}")

    items = data.get("candidate_scores")
    if not isinstance(items, list) or len(items) != 2:
        errors.append(f"{path.name}: expected exactly two candidates")
        return errors, []
    aliases = [item.get("alias") if isinstance(item, dict) else None for item in items]
    if set(aliases) != ALIASES or len(set(aliases)) != 2:
        errors.append(f"{path.name}: Candidate A-B must each occur exactly once; got {aliases}")

    # The frozen validator performs all original field checks and calculations.
    # Add a synthetic third record solely inside local validation and discard it.
    # This adapter never enters the provider request or accepted score output.
    synthetic = frozen.valid_synthetic(packet_id if isinstance(packet_id, str) else "case_01__rep_01")
    candidate_c = synthetic["candidate_scores"][2]
    expanded = {"packet_id": packet_id, "candidate_scores": [*items, candidate_c]}
    frozen_errors, frozen_derived = frozen.validate_main(expanded, path)
    errors.extend(frozen_errors)
    return errors, [row for row in frozen_derived if row.get("alias") in ALIASES]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate two-candidate de-leaking Pass 1 scores")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--expected-packets", type=int, default=9)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        sample = frozen.valid_synthetic()
        sample["candidate_scores"] = sample["candidate_scores"][:2]
        good, derived = validate_main(sample, Path("case_01__rep_01.json"))
        bad = dict(sample)
        bad["candidate_scores"] = sample["candidate_scores"][:1]
        bad_errors, _ = validate_main(bad, Path("case_01__rep_01.json"))
        passed = not good and len(derived) == 2 and bool(bad_errors)
        print(json.dumps({"status": "PASS" if passed else "FAIL", "self_test": True}, ensure_ascii=False))
        raise SystemExit(0 if passed else 2)
    if args.input_dir is None:
        raise SystemExit("--input-dir is required unless --self-test is used")
    files = sorted(args.input_dir.resolve().glob("case_*__rep_*.json"))
    errors_by_file: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            errors, derived = validate_main(data, path)
        except Exception as exc:
            errors, derived = [f"invalid JSON or validation error: {exc}"], []
        if errors:
            errors_by_file[path.name] = errors
        else:
            rows.extend(derived)
    if len(files) != args.expected_packets:
        errors_by_file["_packet_count"] = [f"expected {args.expected_packets}, found {len(files)}"]
    result = {
        "status": "PASS" if not errors_by_file else "FAIL",
        "expected_packets": args.expected_packets,
        "valid_packets": len(files) - sum(not k.startswith("_") for k in errors_by_file),
        "derived_rows": len(rows),
        "errors": errors_by_file,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors_by_file:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
