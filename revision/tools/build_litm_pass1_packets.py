from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import openpyxl

import build_blind_packets as common


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def resolve_from_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_benchmark_records(root: Path) -> dict[int, dict[str, Any]]:
    repo = root.parent / "mpds_github_prep" / "github_repo"
    workbook = openpyxl.load_workbook(
        repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx",
        read_only=True,
        data_only=True,
    )
    values = list(workbook["BenchmarkCases"].iter_rows(values_only=True))
    return {
        int(row[0]): dict(zip(values[0], row))
        for row in values[1:]
        if row[0] is not None
    }


def source_record(run_set: Path, config_id: str, case_id: int, ordering: str, replicate_id: int) -> dict[str, Any] | None:
    run_dir = run_set / f"case_{case_id:02d}" / f"order_{ordering}" / f"replicate_{replicate_id:02d}"
    final_path = run_dir / "final.txt"
    manifest_path = run_dir / "run_manifest.json"
    if not final_path.exists() or not manifest_path.exists():
        return None
    manifest = read_json(manifest_path)
    checks = {
        "status": manifest.get("status") == "COMPLETE",
        "config_id": manifest.get("config_id") == config_id,
        "case_id": int(manifest.get("case_id", -1)) == case_id,
        "ordering": manifest.get("ordering") == ordering,
        "replicate_id": int(manifest.get("replicate_id", -1)) == replicate_id,
        "model": manifest.get("model") == "gemini-2.5-pro",
        "temperature": float(manifest.get("temperature", -1)) == 0.5,
        "final_hash": common.sha256_file(final_path) == str(manifest.get("final_sha256", "")).lower(),
    }
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise RuntimeError(f"Source validation failed for {run_dir}: {failed}")
    source_text = final_path.read_text(encoding="utf-8", errors="replace")
    candidate_body = common.clean_final(source_text)
    if not candidate_body:
        raise RuntimeError(f"Empty candidate body after frozen clean_final: {final_path}")
    return {
        "final_path": final_path.resolve(),
        "manifest_path": manifest_path.resolve(),
        "manifest": manifest,
        "candidate_body": candidate_body,
        "source_file_sha256": common.sha256_file(final_path),
        "candidate_body_sha256": sha256_text(candidate_body),
    }


def packet_body_from_text(packet_text: str, alias: str, next_alias: str | None) -> str:
    marker = f"\n## {alias}\n\n"
    start = packet_text.index(marker) + len(marker)
    end = len(packet_text) if next_alias is None else packet_text.index(f"\n## {next_alias}\n\n", start)
    return packet_text[start:end].strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Build LITM blind Pass 1 packets while reusing the frozen official evaluation implementation"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "independent_judge_sonnet5_pass1_litm_v1.json",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = read_json(config_path)
    source_config_path = resolve_from_root(root, config["source_generation_config"])
    source_config = read_json(source_config_path)
    case_ids = [int(value) for value in config["selected_case_ids"]]
    orderings = [str(value) for value in config["orderings"]]
    replicates = [int(value) for value in config["target_replicates"]]
    if case_ids != [int(value) for value in source_config["design"]["selected_case_ids"]]:
        raise RuntimeError("Evaluation cases do not match the frozen generation design")
    if orderings != [str(value) for value in source_config["design"]["orderings"]]:
        raise RuntimeError("Evaluation orderings do not match the frozen generation design")
    if replicates != [int(value) for value in source_config["design"]["replicates"]]:
        raise RuntimeError("Evaluation replicates do not match the frozen generation design")

    run_set = resolve_from_root(root, config["generation_run_set"])
    output_dir = args.output_dir.resolve() if args.output_dir else resolve_from_root(root, config["packets"])
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite nonempty packet directory: {output_dir}")

    records = load_benchmark_records(root)
    sources: dict[tuple[int, str, int], dict[str, Any]] = {}
    missing: list[str] = []
    for case_id in case_ids:
        if case_id not in records:
            missing.append(f"case_{case_id:02d}/benchmark_record")
            continue
        for replicate_id in replicates:
            for ordering in orderings:
                source = source_record(
                    run_set,
                    source_config["config_id"],
                    case_id,
                    ordering,
                    replicate_id,
                )
                if source is None:
                    missing.append(f"case_{case_id:02d}/order_{ordering}/replicate_{replicate_id:02d}")
                else:
                    sources[(case_id, ordering, replicate_id)] = source
    if missing:
        result = {
            "status": "NOT_READY",
            "expected_sources": len(case_ids) * len(orderings) * len(replicates),
            "validated_sources": len(sources),
            "missing": missing,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2 if args.strict else 0

    output_dir.mkdir(parents=True, exist_ok=False)
    base_order = list(orderings)
    random.Random(int(config["seed"])).shuffle(base_order)
    aliases = common.alias_set(len(orderings))
    key_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []
    packet_hashes: dict[str, str] = {}
    duplicate_packets: list[str] = []

    packet_index = 0
    for case_id in case_ids:
        record = records[case_id]
        for replicate_id in replicates:
            packet_id = f"case_{case_id:02d}__rep_{replicate_id:02d}"
            shift = packet_index % len(base_order)
            ordered_conditions = base_order[shift:] + base_order[:shift]
            ordered_sources = [sources[(case_id, ordering, replicate_id)] for ordering in ordered_conditions]
            body_hashes = [source["candidate_body_sha256"] for source in ordered_sources]
            if len(body_hashes) != len(set(body_hashes)):
                duplicate_packets.append(packet_id)

            parts = [
                f"# Blinded lost-in-the-middle evaluation packet {packet_id}",
                "",
                f"Simulation date: {record['cutoff_year']}",
                "",
                f"Task: {record['debate_topic']}",
                "",
                "Score each candidate independently using the verbatim public IHQ Scoring Rules plus Pass 1 of supplementary_evaluation_module_v1.md. Return raw dimension scores only; do not rank or compare candidates.",
            ]
            for alias, source in zip(aliases, ordered_sources, strict=True):
                parts.extend(["", f"## {alias}", "", source["candidate_body"]])
            packet_text = "\n".join(parts) + "\n"
            packet_path = output_dir / f"{packet_id}.md"
            packet_path.write_bytes(packet_text.encode("utf-8"))
            reread = packet_path.read_text(encoding="utf-8")
            packet_hashes[packet_id] = common.sha256_file(packet_path)

            for index, (alias, ordering, source) in enumerate(
                zip(aliases, ordered_conditions, ordered_sources, strict=True)
            ):
                next_alias = aliases[index + 1] if index + 1 < len(aliases) else None
                packet_body = packet_body_from_text(reread, alias, next_alias)
                packet_body_sha256 = sha256_text(packet_body)
                body_match = packet_body_sha256 == source["candidate_body_sha256"]
                row = {
                    "packet_id": packet_id,
                    "case_id": case_id,
                    "replicate_id": replicate_id,
                    "alias": alias,
                    "ordering": ordering,
                    "source_file": str(source["final_path"]),
                    "source_manifest": str(source["manifest_path"]),
                    "source_file_sha256": source["source_file_sha256"],
                    "manifest_final_sha256": source["manifest"]["final_sha256"],
                    "candidate_body_sha256": source["candidate_body_sha256"],
                    "packet_body_sha256": packet_body_sha256,
                    "candidate_body_hash_match": body_match,
                    "source_file_equals_packet_body": source["source_file_sha256"] == packet_body_sha256,
                    "candidate_body_policy": "frozen build_blind_packets.clean_final",
                    "output_characters": len(source["candidate_body"]),
                }
                key_rows.append(row)
                hash_rows.append(
                    {
                        "packet_id": packet_id,
                        "candidate": alias,
                        "source_file_sha256": source["source_file_sha256"],
                        "cleaned_source_body_sha256": source["candidate_body_sha256"],
                        "packet_body_sha256": packet_body_sha256,
                        "hash_match": body_match,
                    }
                )
            packet_index += 1

    write_csv(output_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv", key_rows)
    write_csv(output_dir / "hash_validation.csv", hash_rows)
    alias_ordering_counts = {
        alias: {
            ordering: sum(row["alias"] == alias and row["ordering"] == ordering for row in key_rows)
            for ordering in orderings
        }
        for alias in aliases
    }
    expected_per_position = len(key_rows) // (len(aliases) * len(orderings))
    alias_balance_passed = all(
        count == expected_per_position for counts in alias_ordering_counts.values() for count in counts.values()
    )
    passed = (
        packet_index == int(config["expected_packets"])
        and len(key_rows) == int(config["expected_candidates"])
        and all(row["candidate_body_hash_match"] for row in key_rows)
        and alias_balance_passed
        and not duplicate_packets
    )
    summary = {
        "status": "PASS" if passed else "FAIL",
        "config": str(config_path),
        "source_generation_config": str(source_config_path),
        "generation_run_set": str(run_set),
        "seed": int(config["seed"]),
        "aliasing_method": config["aliasing_method"],
        "balanced_base_orderings": base_order,
        "selected_cases": case_ids,
        "selected_replicates": replicates,
        "orderings": orderings,
        "packets": packet_index,
        "candidates": len(key_rows),
        "candidate_body_hash_matches": sum(row["candidate_body_hash_match"] for row in key_rows),
        "source_file_equals_packet_body": sum(row["source_file_equals_packet_body"] for row in key_rows),
        "source_to_packet_note": "The frozen clean_final transformation removes evidence-map/appendix sections before judging; the required equality is cleaned source body versus packet body.",
        "expected_count_per_alias_ordering": expected_per_position,
        "alias_ordering_counts": alias_ordering_counts,
        "alias_balance_passed": alias_balance_passed,
        "duplicate_candidate_packets": duplicate_packets,
        "packet_sha256": packet_hashes,
        "frozen_evaluator_files": {
            "runner": config["runner"],
            "base_runner": config["base_runner"],
            "prompt": config["prompt"],
            "schema": config["schema"],
            "validator": config["validator"],
        },
        "api_calls_made": 0,
    }
    (output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed or not args.strict else 2


if __name__ == "__main__":
    raise SystemExit(main())
