from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl

import build_blind_packets as common


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


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


def source_record(
    run_set: Path,
    case_id: int,
    corpus_size: int,
    replicate_id: int,
) -> dict[str, Any] | None:
    run_dir = (
        run_set
        / f"case_{case_id:02d}"
        / f"corpus_{corpus_size:04d}"
        / f"replicate_{replicate_id:02d}"
    )
    final_path = run_dir / "final.txt"
    manifest_path = run_dir / "run_manifest.json"
    if not final_path.exists() or not manifest_path.exists():
        return None
    manifest = read_json(manifest_path)
    checks = {
        "status": manifest.get("status") == "COMPLETE",
        "case_id": int(manifest.get("case_id", -1)) == case_id,
        "corpus_size": int(manifest.get("corpus_size_per_pool", -1)) == corpus_size,
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
        "source_text": source_text,
        "candidate_body": candidate_body,
        "source_file_sha256": common.sha256_file(final_path),
        "candidate_body_sha256": sha256_text(candidate_body),
    }


def packet_body_from_text(packet_text: str, alias: str, next_alias: str | None) -> str:
    marker = f"\n## {alias}\n\n"
    start = packet_text.index(marker) + len(marker)
    if next_alias is None:
        end = len(packet_text)
    else:
        end = packet_text.index(f"\n## {next_alias}\n\n", start)
    return packet_text[start:end].strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Build corpus-size blind Pass 1 packets while reusing the frozen official four-candidate evaluation implementation"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "independent_judge_sonnet5_pass1_corpus_size_v1.json",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = read_json(config_path)
    source_config_path = resolve_from_root(root, config["source_generation_config"])
    source_config = read_json(source_config_path)
    case_ids = [int(value) for value in config["selected_case_ids"]]
    corpus_sizes = [int(value) for value in config["corpus_sizes"]]
    replicates = [int(value) for value in config["target_replicates"]]
    if case_ids != [int(value) for value in source_config["design"]["selected_case_ids"]]:
        raise RuntimeError("Evaluation cases do not match the frozen generation design")
    if corpus_sizes != [int(value) for value in source_config["design"]["corpus_sizes"]]:
        raise RuntimeError("Evaluation corpus sizes do not match the frozen generation design")
    if replicates != [int(value) for value in source_config["design"]["replicates"]]:
        raise RuntimeError("Evaluation replicates do not match the frozen generation design")

    run_set = resolve_from_root(root, config["generation_run_set"])
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else resolve_from_root(root, config["packets"])
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite nonempty packet directory: {output_dir}")

    records = load_benchmark_records(root)
    sources: dict[tuple[int, int, int], dict[str, Any]] = {}
    missing: list[str] = []
    for case_id in case_ids:
        if case_id not in records:
            missing.append(f"case_{case_id:02d}/benchmark_record")
            continue
        for replicate_id in replicates:
            for corpus_size in corpus_sizes:
                source = source_record(run_set, case_id, corpus_size, replicate_id)
                if source is None:
                    missing.append(
                        f"case_{case_id:02d}/corpus_{corpus_size:04d}/replicate_{replicate_id:02d}"
                    )
                else:
                    sources[(case_id, corpus_size, replicate_id)] = source
    if missing:
        result = {
            "status": "NOT_READY",
            "expected_sources": len(case_ids) * len(corpus_sizes) * len(replicates),
            "validated_sources": len(sources),
            "missing": missing,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.strict:
            return 2
        return 0

    output_dir.mkdir(parents=True, exist_ok=False)
    base_order = list(corpus_sizes)
    random.Random(int(config["seed"])).shuffle(base_order)
    aliases = common.alias_set(len(corpus_sizes))
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
            ordered_sizes = base_order[shift:] + base_order[:shift]
            ordered_sources = [sources[(case_id, size, replicate_id)] for size in ordered_sizes]
            body_hashes = [source["candidate_body_sha256"] for source in ordered_sources]
            if len(body_hashes) != len(set(body_hashes)):
                duplicate_packets.append(packet_id)

            parts = [
                f"# Blinded component-control evaluation packet {packet_id}",
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

            for index, (alias, corpus_size, source) in enumerate(
                zip(aliases, ordered_sizes, ordered_sources, strict=True)
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
                    "corpus_size": corpus_size,
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
    alias_size_counts = {
        alias: {
            str(size): sum(row["alias"] == alias and row["corpus_size"] == size for row in key_rows)
            for size in corpus_sizes
        }
        for alias in aliases
    }
    expected_per_position = len(key_rows) // (len(aliases) * len(corpus_sizes))
    passed = (
        packet_index == int(config["expected_packets"])
        and len(key_rows) == int(config["expected_candidates"])
        and all(row["candidate_body_hash_match"] for row in key_rows)
        and all(count == expected_per_position for counts in alias_size_counts.values() for count in counts.values())
        and not duplicate_packets
    )
    summary = {
        "status": "PASS" if passed else "FAIL",
        "config": str(config_path),
        "source_generation_config": str(source_config_path),
        "generation_run_set": str(run_set),
        "seed": int(config["seed"]),
        "aliasing_method": config["aliasing_method"],
        "balanced_base_corpus_sizes": base_order,
        "selected_cases": case_ids,
        "selected_replicates": replicates,
        "corpus_sizes": corpus_sizes,
        "packets": packet_index,
        "candidates": len(key_rows),
        "candidate_body_hash_matches": sum(row["candidate_body_hash_match"] for row in key_rows),
        "source_file_equals_packet_body": sum(row["source_file_equals_packet_body"] for row in key_rows),
        "source_to_packet_note": "The frozen clean_final transformation removes evidence-map/appendix sections before judging, so raw final.txt hashes are recorded separately; the required equality is cleaned source body versus packet body.",
        "expected_count_per_alias_corpus_size": expected_per_position,
        "alias_corpus_size_counts": alias_size_counts,
        "alias_balance_passed": all(
            count == expected_per_position for counts in alias_size_counts.values() for count in counts.values()
        ),
        "duplicate_candidate_packets": duplicate_packets,
        "packet_sha256": packet_hashes,
        "frozen_evaluator_files": {
            "runner": config["runner"],
            "base_runner": config["base_runner"],
            "prompt": config["prompt"],
            "schema": config["schema"],
            "validator": config["validator"],
        },
    }
    (output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
