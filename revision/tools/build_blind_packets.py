from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds", "sair", "ses")
TRUNCATE_SECTION_TITLES = (
    "evidence map",
    "evidence appendix",
    "appendix",
    "appendices",
    "supporting evidence",
    "evidence table",
    "references",
    "reference list",
    "bibliography",
)


@dataclass(frozen=True)
class ResultSource:
    path: Path
    source_kind: str
    manifest_path: Path | None


def extract_final(text: str) -> str:
    markers = ("[FINAL SYNTHESIS]", "[Final Synthesis]", "[EOP Answer]", "[EO Answer]", "[Raw LLM Answer]")
    found = [(text.rfind(marker), marker) for marker in markers if marker in text]
    if not found:
        return text.strip()
    position, marker = max(found)
    return text[position + len(marker) :].strip()


def normalize_section_header(line: str) -> str:
    header = line.strip()
    header = re.sub(r"^\s{0,3}#{1,6}\s*", "", header)
    header = re.sub(r"^[=\-_*`~]+\s*", "", header)
    header = re.sub(r"\s*[=\-_*`~]+$", "", header)
    header = header.strip().rstrip(":").strip()
    header = re.sub(r"^(?:section\s+)?\d+(?:\.\d+)*[.)\-:]?\s+", "", header, flags=re.I)
    return re.sub(r"\s+", " ", header).lower()


def strip_appendix_sections(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        normalized = normalize_section_header(line)
        if not normalized or len(normalized) > 120:
            continue
        for title in TRUNCATE_SECTION_TITLES:
            if normalized == title or normalized.startswith(f"{title} "):
                return "\n".join(lines[:index]).rstrip()
    return text.strip()


def clean_final(text: str) -> str:
    return strip_appendix_sections(extract_final(text)).strip()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def legacy_path(repo: Path, record: dict[str, Any], condition: str) -> Path | None:
    columns = {
        "raw": "public_raw_llm_output",
        "eo": "public_eo_output",
        "eop": "public_eop_output",
        "ds": "public_ds_output",
        "mpds": "public_mpds_output",
    }
    return repo / str(record[columns[condition]]) if condition in columns else None


def load_eligibility(path: Path) -> dict[tuple[int, str], dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (int(row["case_id"]), row["condition"]): row
            for row in csv.DictReader(handle)
        }


def generated_result(run_set: Path, case_id: int, condition: str, replicate: int) -> ResultSource | None:
    run_dir = run_set / f"case_{case_id:02d}" / condition / f"replicate_{replicate:02d}"
    final_path = run_dir / "final.txt"
    if not final_path.exists():
        return None

    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        raise RuntimeError(f"Generated output has no manifest: {final_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "COMPLETE":
        raise RuntimeError(f"Generated output is not COMPLETE: {manifest_path}")
    if int(manifest.get("case_id", -1)) != case_id:
        raise RuntimeError(f"Case mismatch in manifest: {manifest_path}")
    if str(manifest.get("condition", "")).lower() != condition:
        raise RuntimeError(f"Condition mismatch in manifest: {manifest_path}")
    if int(manifest.get("replicate_id", -1)) != replicate:
        raise RuntimeError(f"Replicate mismatch in manifest: {manifest_path}")
    expected_hash = str(manifest.get("final_sha256", "")).lower()
    if not expected_hash or sha256_file(final_path) != expected_hash:
        raise RuntimeError(f"Final-file hash mismatch: {final_path}")
    return ResultSource(final_path, "generated", manifest_path)


def result_source(
    run_set: Path,
    repo: Path,
    record: dict[str, Any],
    condition: str,
    replicate: int,
    allow_legacy: bool,
    eligibility: dict[tuple[int, str], dict[str, str]],
) -> ResultSource | None:
    case_id = int(record["case_id"])
    generated = generated_result(run_set, case_id, condition, replicate)
    if generated is not None:
        return generated

    if replicate != 1 or not allow_legacy:
        return None

    eligibility_row = eligibility.get((case_id, condition))
    if eligibility_row is None or not truthy(eligibility_row.get("practical_eligible_as_replicate_1")):
        return None
    candidate = repo / eligibility_row["output_file"]
    if not candidate.exists():
        return None
    expected_hash = str(eligibility_row.get("output_sha256", "")).lower()
    if not expected_hash or sha256_file(candidate) != expected_hash:
        raise RuntimeError(f"Legacy output hash mismatch: {candidate}")
    return ResultSource(candidate, "legacy_replicate_1", None)


def alias_set(count: int) -> list[str]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    if count > len(alphabet):
        raise ValueError(count)
    return [f"Candidate {alphabet[index]}" for index in range(count)]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create blinded multi-candidate packets without API calls")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--case", type=int, action="append", choices=range(1, 31))
    parser.add_argument("--replicate", type=int, action="append", choices=(1, 2, 3))
    parser.add_argument("--condition", action="append", choices=CONDITIONS)
    parser.add_argument("--allow-legacy-replicate1", action="store_true")
    parser.add_argument("--case-config", type=Path, help="Frozen subset configuration JSON.")
    parser.add_argument("--run-set", type=Path, default=root / "runs", help="Accepted generated-run directory.")
    parser.add_argument(
        "--eligibility-file",
        type=Path,
        default=root / "audit" / "replicate1_eligibility.csv",
        help="Audited practical-eligibility table for legacy Replicate 1.",
    )
    parser.add_argument("--seed", type=int, default=7346298)
    parser.add_argument("--output-dir", type=Path, default=root / "evaluation" / "blind_packets")
    parser.add_argument("--strict", action="store_true", help="Fail unless every requested packet is complete and unique.")
    args = parser.parse_args()

    config: dict[str, Any] = {}
    if args.case_config:
        config = json.loads(args.case_config.resolve().read_text(encoding="utf-8"))
    run_set = args.run_set.resolve()
    eligibility_file = args.eligibility_file.resolve()
    eligibility = load_eligibility(eligibility_file)

    repo = root.parent / "mpds_github_prep" / "github_repo"
    workbook = openpyxl.load_workbook(
        repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx",
        read_only=True,
        data_only=True,
    )
    values = list(workbook["BenchmarkCases"].iter_rows(values_only=True))
    cases = [dict(zip(values[0], row)) for row in values[1:] if row[0] is not None]
    selected_cases = set(args.case or config.get("selected_case_ids") or range(1, 31))
    selected_replicates = args.replicate or config.get("target_replicates") or [1, 2, 3]
    selected_conditions = tuple(args.condition or config.get("conditions") or CONDITIONS)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    key_rows: list[dict[str, Any]] = []
    packet_count = 0
    missing: list[str] = []
    packet_sizes: dict[str, int] = {}
    duplicate_packets: list[str] = []
    source_counts = {"legacy_replicate_1": 0, "generated": 0}
    found_cases: set[int] = set()
    balanced_base_conditions = list(selected_conditions)
    random.Random(args.seed).shuffle(balanced_base_conditions)
    packet_index = 0

    for record in cases:
        case_id = int(record["case_id"])
        if case_id not in selected_cases:
            continue
        found_cases.add(case_id)
        for replicate in selected_replicates:
            available = []
            for condition in selected_conditions:
                source = result_source(
                    run_set,
                    repo,
                    record,
                    condition,
                    replicate,
                    args.allow_legacy_replicate1,
                    eligibility,
                )
                if source is None:
                    missing.append(f"case_{case_id:02d}/{condition}/replicate_{replicate:02d}")
                    continue
                final = clean_final(source.path.read_text(encoding="utf-8", errors="replace"))
                if not final:
                    raise RuntimeError(f"Empty candidate body after cleaning: {source.path}")
                available.append((condition, source, final))
            if not available:
                continue

            available_by_condition = {item[0]: item for item in available}
            shift = packet_index % len(balanced_base_conditions)
            balanced_order = balanced_base_conditions[shift:] + balanced_base_conditions[:shift]
            available = [available_by_condition[condition] for condition in balanced_order if condition in available_by_condition]
            aliases = alias_set(len(available))
            packet_id = f"case_{case_id:02d}__rep_{replicate:02d}"
            packet_sizes[packet_id] = len(available)
            body_hashes = [hashlib.sha256(final.encode("utf-8")).hexdigest() for _, _, final in available]
            if len(set(body_hashes)) != len(body_hashes):
                duplicate_packets.append(packet_id)
            parts = [
                f"# Blinded evaluation packet {packet_id}",
                "",
                f"Simulation date: {record['cutoff_year']}",
                "",
                f"Task: {record['debate_topic']}",
                "",
                "Score each candidate independently using the verbatim public IHQ Scoring Rules plus Pass 1 of supplementary_evaluation_module_v1.md. Return raw dimension scores only; do not rank candidates.",
            ]
            for alias, (condition, source, final) in zip(aliases, available):
                parts.extend(["", f"## {alias}", "", final])
                source_counts[source.source_kind] += 1
                key_rows.append(
                    {
                        "packet_id": packet_id,
                        "case_id": case_id,
                        "replicate_id": replicate,
                        "alias": alias,
                        "condition": condition,
                        "source_kind": source.source_kind,
                        "source_file": str(source.path.resolve()),
                        "source_manifest": str(source.manifest_path.resolve()) if source.manifest_path else "",
                        "source_file_sha256": sha256_file(source.path),
                        "output_sha256": hashlib.sha256(final.encode("utf-8")).hexdigest(),
                        "output_characters": len(final),
                    }
                )
            packet_text = "\n".join(parts) + "\n"
            (output_dir / f"{packet_id}.md").write_bytes(packet_text.encode("utf-8"))
            packet_count += 1
            packet_index += 1

    for case_id in sorted(selected_cases - found_cases):
        missing.append(f"case_{case_id:02d}/benchmark_record")

    if key_rows:
        write_csv(output_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv", key_rows)
    expected_packets = len(selected_cases) * len(selected_replicates)
    expected_candidates = expected_packets * len(selected_conditions)
    alias_condition_counts = {
        alias: {
            condition: sum(
                row["alias"] == alias and row["condition"] == condition
                for row in key_rows
            )
            for condition in selected_conditions
        }
        for alias in alias_set(len(selected_conditions))
    }
    expected_alias_count = expected_packets // len(selected_conditions) if expected_packets % len(selected_conditions) == 0 else None
    alias_balance_passed = expected_alias_count is not None and all(
        count == expected_alias_count
        for condition_counts in alias_condition_counts.values()
        for count in condition_counts.values()
    )
    wrong_size_packets = sorted(
        packet_id for packet_id, size in packet_sizes.items() if size != len(selected_conditions)
    )
    passed = (
        packet_count == expected_packets
        and len(key_rows) == expected_candidates
        and not missing
        and not wrong_size_packets
        and not duplicate_packets
        and alias_balance_passed
    )
    summary = {
        "status": "PASS" if passed else "FAIL",
        "case_config": str(args.case_config.resolve()) if args.case_config else "",
        "run_set": str(run_set),
        "eligibility_file": str(eligibility_file),
        "seed": args.seed,
        "aliasing_method": "seeded balanced cyclic rotation",
        "balanced_base_conditions": balanced_base_conditions,
        "selected_cases": sorted(selected_cases),
        "selected_replicates": list(selected_replicates),
        "selected_conditions": list(selected_conditions),
        "expected_packets": expected_packets,
        "packets": packet_count,
        "expected_candidates": expected_candidates,
        "candidates": len(key_rows),
        "source_counts": source_counts,
        "expected_count_per_alias_condition": expected_alias_count,
        "alias_condition_counts": alias_condition_counts,
        "alias_balance_passed": alias_balance_passed,
        "wrong_size_packets": wrong_size_packets,
        "duplicate_candidate_packets": sorted(duplicate_packets),
        "missing_count": len(missing),
        "missing": missing,
    }
    (output_dir / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
