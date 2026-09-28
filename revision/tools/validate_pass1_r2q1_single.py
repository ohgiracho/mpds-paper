from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import validate_pass1_litm as frozen


PACKET_PATTERN = re.compile(r"^r2q1_[0-9a-f]{10}$")


def validate_main(data: Any, path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Single-candidate adapter around the frozen official Pass 1 validator."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{path.name}: top level must be an object"], []
    frozen.exact_keys(data, {"packet_id", "candidate_scores"}, path.name, errors)
    packet_id = data.get("packet_id")
    if not isinstance(packet_id, str) or not PACKET_PATTERN.fullmatch(packet_id):
        errors.append(f"{path.name}: invalid packet_id {packet_id!r}")
    if path.stem != packet_id:
        errors.append(f"{path.name}: filename must match packet_id {packet_id!r}")
    items = data.get("candidate_scores")
    if not isinstance(items, list) or len(items) != 1:
        errors.append(f"{path.name}: expected exactly one candidate")
        return errors, []
    if not isinstance(items[0], dict) or items[0].get("alias") != "Candidate A":
        errors.append(f"{path.name}: Candidate A must occur exactly once")
        return errors, []
    synthetic = frozen.valid_synthetic("case_01__rep_01")
    expanded = {"packet_id": "case_01__rep_01", "candidate_scores": [items[0], *synthetic["candidate_scores"][1:]]}
    frozen_errors, frozen_rows = frozen.validate_main(expanded, Path("case_01__rep_01.json"))
    errors.extend(frozen_errors)
    rows = []
    for row in frozen_rows:
        if row.get("alias") == "Candidate A":
            item = dict(row); item["packet_id"] = packet_id; rows.append(item)
    return errors, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate R2 Q1 single-candidate Pass 1 output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        raise SystemExit("Only --self-test is supported")
    sample = frozen.valid_synthetic()["candidate_scores"][0]
    good, rows = validate_main({"packet_id": "r2q1_0123456789", "candidate_scores": [sample]}, Path("r2q1_0123456789.json"))
    bad, _ = validate_main({"packet_id": "r2q1_0123456789", "candidate_scores": []}, Path("r2q1_0123456789.json"))
    passed = not good and len(rows) == 1 and bool(bad)
    print(json.dumps({"status": "PASS" if passed else "FAIL", "self_test": True}))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
