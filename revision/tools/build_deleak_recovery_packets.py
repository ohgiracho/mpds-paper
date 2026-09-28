from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any

from build_deleak_pass1_packets import packet_body, read_json, resolve, sha256_text, write_csv


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = read_json(root / "config" / "independent_judge_sonnet5_pass1_deleak_pair_v1.json")
    pair_dir = resolve(root, config["packets"])
    pair_key_dir = resolve(root, config["blind_key_dir"])
    output_dir = resolve(root, config["target_recovery_packets"])
    key_dir = resolve(root, config["target_recovery_key_dir"])
    for directory in (output_dir, key_dir):
        if directory.exists():
            raise RuntimeError(f"Refusing to overwrite existing directory: {directory}")
    summary = read_json(pair_key_dir / "build_summary.json")
    if summary.get("status") != "PASS" or summary.get("candidates") != 18:
        raise RuntimeError("Paired Pass 1 packet integrity has not passed")
    with (pair_key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv").open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 18:
        raise RuntimeError("Expected exactly 18 blinded source rows")
    for row in rows:
        pair = (pair_dir / f"{row['packet_id']}.md").read_text(encoding="utf-8")
        body = packet_body(pair, row["alias"], "Candidate B" if row["alias"] == "Candidate A" else None)
        if sha256_text(body) != row["cleaned_body_sha256"]:
            raise RuntimeError(f"Pair-to-audit body mismatch: {row['packet_id']} {row['alias']}")
        row["body"] = body
    rng = random.Random(int(config["seed"]) + 1)
    rng.shuffle(rows)
    output_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)
    key_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        audit_id = f"audit_{index:03d}"
        packet = output_dir / f"{audit_id}.md"
        packet.write_text(f"# Blinded output {audit_id}\n\nCase ID: {row['case_id']}\n\n## Final answer\n\n{row['body']}\n", encoding="utf-8")
        copied_body = packet.read_text(encoding="utf-8").split("\n## Final answer\n\n", 1)[1].strip()
        matches = sha256_text(copied_body) == row["cleaned_body_sha256"]
        key_rows.append({
            "audit_id": audit_id, "case_id": row["case_id"], "replicate_id": row["replicate_id"],
            "pair_packet_id": row["packet_id"], "pair_alias": row["alias"],
            "condition": row["condition"], "cleaned_body_sha256": row["cleaned_body_sha256"],
            "audit_body_sha256": sha256_text(copied_body), "hash_match": matches,
        })
    write_csv(key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv", key_rows)
    result = {
        "status": "PASS" if len(key_rows) == 18 and all(row["hash_match"] for row in key_rows) else "FAIL",
        "audit_packets": len(key_rows), "body_hash_matches": sum(row["hash_match"] for row in key_rows),
        "scoring_unit": "one cleaned final answer with case identifier only",
        "rubric": "protocol/prompt_deleaking_target_recovery_rubric_v1.md",
        "api_calls_made": 0,
    }
    (key_dir / "build_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
