from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from litm_common import (
    atomic_write_json,
    decode_bytes,
    input_pool_dir,
    load_config,
    optimal_three_way_contiguous_split,
    read_csv,
    sha256_bytes,
    sha256_file,
    split_knowledge_bytes,
    write_csv,
)


CORE_CONFIG = "config/core_replication_subset_v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build frozen position-control evidence rotations")
    parser.add_argument("--config", type=Path)
    return parser.parse_args()


def selection_rows(revision_root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    core = json.loads((revision_root / CORE_CONFIG).read_text(encoding="utf-8"))
    core_ids = {int(value) for value in core["selected_case_ids"]}
    audit_path = revision_root / str(config["inputs"]["audit_manifest"])
    audit = [row for row in read_csv(audit_path) if int(row["case_id"]) in core_ids]
    grouped: dict[int, list[dict[str, str]]] = {}
    for row in audit:
        grouped.setdefault(int(row["case_id"]), []).append(row)
    rows: list[dict[str, Any]] = []
    for case_id in sorted(core_ids):
        group = grouped.get(case_id, [])
        by_pool = {row["pool"]: row for row in group}
        if set(by_pool) != {"A", "B"}:
            raise RuntimeError(f"Incomplete frozen evidence audit for case {case_id}")
        eligible = all(
            row["exists"].lower() == "true" and int(row["safe_release_record_count"]) == 500
            for row in by_pool.values()
        )
        rows.append(
            {
                "case_id": case_id,
                "case_name": by_pool["A"]["case_name"],
                "pool_a_characters": int(by_pool["A"]["characters"]),
                "pool_b_characters": int(by_pool["B"]["characters"]),
                "combined_characters": int(by_pool["A"]["characters"])
                + int(by_pool["B"]["characters"]),
                "pool_a_records": int(by_pool["A"]["safe_release_record_count"]),
                "pool_b_records": int(by_pool["B"]["safe_release_record_count"]),
                "eligible": eligible,
                "pool_a_path": by_pool["A"]["local_path"],
                "pool_b_path": by_pool["B"]["local_path"],
                "pool_a_sha256": by_pool["A"]["sha256"],
                "pool_b_sha256": by_pool["B"]["sha256"],
            }
        )
    eligible_rows = sorted(
        (row for row in rows if row["eligible"]),
        key=lambda row: (-row["combined_characters"], row["case_id"]),
    )
    for rank, row in enumerate(eligible_rows, start=1):
        row["eligible_rank"] = rank
    ineligible = [row for row in rows if not row["eligible"]]
    for row in ineligible:
        row["eligible_rank"] = ""
    return sorted(rows, key=lambda row: (not row["eligible"], row.get("eligible_rank") or 999))


def build_pool(
    *,
    revision_root: Path,
    config: dict[str, Any],
    case_id: int,
    pool: str,
    source_path: Path,
    expected_source_hash: str,
) -> dict[str, Any]:
    payload = source_path.read_bytes()
    if sha256_bytes(payload) != expected_source_hash:
        raise RuntimeError(f"Source hash mismatch for case {case_id}, pool {pool}")
    header, records = split_knowledge_bytes(payload)
    if len(records) != 500:
        raise RuntimeError(f"Expected 500 records for case {case_id}, pool {pool}; found {len(records)}")
    first, second = optimal_three_way_contiguous_split(records)
    block_records = {
        "X": records[:first],
        "Y": records[first:second],
        "Z": records[second:],
    }
    out_dir = input_pool_dir(revision_root, config, case_id, pool)
    out_dir.mkdir(parents=True, exist_ok=False)
    block_rows: list[dict[str, Any]] = []
    block_summary: dict[str, Any] = {}
    for block, members in block_records.items():
        block_bytes = b"".join(record["bytes"] for record in members)
        block_summary[block] = {
            "record_count": len(members),
            "character_count": sum(int(record["character_count"]) for record in members),
            "byte_count": len(block_bytes),
            "content_sha256": sha256_bytes(block_bytes),
            "first_canonical_index": members[0]["canonical_index"],
            "last_canonical_index": members[-1]["canonical_index"],
            "first_id": members[0]["paper_id"],
            "last_id": members[-1]["paper_id"],
        }
        for record in members:
            block_rows.append(
                {
                    "case_id": case_id,
                    "pool": pool,
                    "block": block,
                    "canonical_index": record["canonical_index"],
                    "paper_id": record["paper_id"],
                    "record_characters": record["character_count"],
                    "record_bytes": record["byte_count"],
                    "record_sha256": record["sha256"],
                }
            )
    write_csv(
        out_dir / "block_membership.csv",
        block_rows,
        [
            "case_id",
            "pool",
            "block",
            "canonical_index",
            "paper_id",
            "record_characters",
            "record_bytes",
            "record_sha256",
        ],
    )

    rotations = config["position_manipulation"]["rotations"]
    ordering_artifacts: dict[str, Any] = {}
    for ordering in config["design"]["orderings"]:
        labels = list(ordering)
        ordered_records = [record for label in labels for record in block_records[label]]
        ordered_payload = header + b"".join(record["bytes"] for record in ordered_records)
        path = out_dir / f"knowledge_order_{ordering}.txt"
        path.write_bytes(ordered_payload)
        ordering_artifacts[ordering] = {
            "path": str(path.relative_to(revision_root)).replace("\\", "/"),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "characters": len(decode_bytes(ordered_payload)),
            "record_count": len(ordered_records),
            "record_id_order_sha256": sha256_bytes(
                "|".join(str(record["paper_id"]) for record in ordered_records).encode("ascii")
            ),
            "positions": rotations[ordering],
        }

    manifest = {
        "status": "FROZEN_POSITION_CONTROL_INPUT",
        "case_id": case_id,
        "pool": pool,
        "source_path": str(source_path),
        "source_sha256": expected_source_hash,
        "source_bytes": len(payload),
        "source_characters": len(decode_bytes(payload)),
        "header_bytes": len(header),
        "header_sha256": sha256_bytes(header),
        "records": len(records),
        "canonical_record_id_order_sha256": sha256_bytes(
            "|".join(str(record["paper_id"]) for record in records).encode("ascii")
        ),
        "record_multiset_sha256": sha256_bytes(
            "|".join(sorted(record["sha256"] for record in records)).encode("ascii")
        ),
        "partition_cut_after_canonical_indices": [first, second],
        "partition_objective": "minimum squared character imbalance; deterministic tie breaks",
        "blocks": block_summary,
        "orderings": ordering_artifacts,
        "persona_source": str(source_path),
        "persona_source_sha256": expected_source_hash,
    }
    atomic_write_json(out_dir / "block_manifest.json", manifest)
    return manifest


def main() -> int:
    args = parse_args()
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    input_root = revision_root / str(config["inputs"]["input_root"])
    if input_root.exists():
        raise SystemExit(f"Refusing to overwrite existing frozen input root: {input_root}")

    rows = selection_rows(revision_root, config)
    selected_expected = [int(value) for value in config["design"]["selected_case_ids"]]
    selected_actual = [int(row["case_id"]) for row in rows if row["eligible"]][:4]
    if selected_actual != selected_expected:
        raise RuntimeError(
            f"Outcome-independent case selection mismatch: expected {selected_expected}, got {selected_actual}"
        )
    input_root.mkdir(parents=True)
    public_selection_rows = [
        {key: value for key, value in row.items() if not key.endswith("_path")}
        for row in rows
    ]
    write_csv(
        input_root / "case_selection_audit.csv",
        public_selection_rows,
        [
            "case_id",
            "case_name",
            "pool_a_characters",
            "pool_b_characters",
            "combined_characters",
            "pool_a_records",
            "pool_b_records",
            "eligible",
            "pool_a_sha256",
            "pool_b_sha256",
            "eligible_rank",
        ],
    )

    manifests: list[dict[str, Any]] = []
    row_lookup = {int(row["case_id"]): row for row in rows}
    for case_id in selected_expected:
        row = row_lookup[case_id]
        for pool in ("A", "B"):
            manifests.append(
                build_pool(
                    revision_root=revision_root,
                    config=config,
                    case_id=case_id,
                    pool=pool,
                    source_path=Path(row[f"pool_{pool.lower()}_path"]),
                    expected_source_hash=str(row[f"pool_{pool.lower()}_sha256"]),
                )
            )
    summary = {
        "status": "PASS",
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "selected_cases": selected_expected,
        "pool_manifests": len(manifests),
        "ordered_knowledge_files": sum(len(item["orderings"]) for item in manifests),
        "total_unique_source_records": sum(int(item["records"]) for item in manifests),
        "expected_outputs": int(config["design"]["expected_outputs"]),
        "api_calls_made": 0,
    }
    atomic_write_json(input_root / "build_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
