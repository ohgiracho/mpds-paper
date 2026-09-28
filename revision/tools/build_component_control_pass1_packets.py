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


CONDITIONS = ("ds", "mpds", "sair", "ses")
CORE_CONDITIONS = {"ds", "mpds"}
COMPONENT_CONDITIONS = {"sair", "ses"}


def resolve_from_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def read_reference_hashes(path: Path) -> dict[tuple[str, str], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (row["packet_id"], row["condition"]): row["output_sha256"].lower()
            for row in csv.DictReader(handle)
            if row["condition"] in CORE_CONDITIONS
        }


def source_for(
    *,
    core_run_set: Path,
    component_run_set: Path,
    repo: Path,
    record: dict[str, Any],
    condition: str,
    replicate: int,
    eligibility: dict[tuple[int, str], dict[str, str]],
) -> common.ResultSource | None:
    case_id = int(record["case_id"])
    if condition in COMPONENT_CONDITIONS:
        source = common.generated_result(component_run_set, case_id, condition, replicate)
        if source is None:
            return None
        return common.ResultSource(source.path, "generated_component", source.manifest_path)

    source = common.result_source(
        core_run_set,
        repo,
        record,
        condition,
        replicate,
        True,
        eligibility,
    )
    if source is None:
        return None
    source_kind = "legacy_replicate_1" if source.source_kind == "legacy_replicate_1" else "generated_core"
    return common.ResultSource(source.path, source_kind, source.manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the frozen four-condition DS/MPDS/SAIR/SES Pass 1 packets without API calls"
    )
    root = Path(__file__).resolve().parents[1]
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "independent_judge_sonnet5_pass1_component_controls_v1.json",
    )
    parser.add_argument(
        "--eligibility-file",
        type=Path,
        default=root / "audit" / "replicate1_eligibility.csv",
    )
    parser.add_argument(
        "--reference-blind-key",
        type=Path,
        default=root
        / "evaluation"
        / "blind_packets_core10_n3_v3"
        / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    selected_conditions = tuple(config["conditions"])
    if selected_conditions != CONDITIONS:
        raise RuntimeError(f"Frozen condition order must be {CONDITIONS}; got {selected_conditions}")

    selected_cases = [int(value) for value in config["selected_case_ids"]]
    selected_replicates = [int(value) for value in config["target_replicates"]]
    if len(selected_cases) != len(set(selected_cases)) or len(selected_replicates) != len(set(selected_replicates)):
        raise RuntimeError("Frozen cases and replicates must not contain duplicates")

    core_run_set = resolve_from_root(root, config["core_run_set"])
    component_run_set = resolve_from_root(root, config["component_run_set"])
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else resolve_from_root(root, config["packets"])
    )
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(f"Refusing to overwrite nonempty packet directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    eligibility_file = args.eligibility_file.resolve()
    reference_key = args.reference_blind_key.resolve()
    eligibility = common.load_eligibility(eligibility_file)
    reference_hashes = read_reference_hashes(reference_key)

    repo = root.parent / "mpds_github_prep" / "github_repo"
    workbook = openpyxl.load_workbook(
        repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx",
        read_only=True,
        data_only=True,
    )
    values = list(workbook["BenchmarkCases"].iter_rows(values_only=True))
    records = [dict(zip(values[0], row)) for row in values[1:] if row[0] is not None]
    records_by_case = {int(record["case_id"]): record for record in records}

    seed = int(config["seed"])
    base_order = list(CONDITIONS)
    random.Random(seed).shuffle(base_order)
    aliases = common.alias_set(len(CONDITIONS))
    key_rows: list[dict[str, Any]] = []
    packet_sizes: dict[str, int] = {}
    missing: list[str] = []
    duplicate_packets: list[str] = []
    reference_mismatches: list[str] = []
    source_counts = {
        "legacy_replicate_1": 0,
        "generated_core": 0,
        "generated_component": 0,
    }

    packet_index = 0
    for case_id in selected_cases:
        record = records_by_case.get(case_id)
        if record is None:
            missing.append(f"case_{case_id:02d}/benchmark_record")
            continue
        for replicate in selected_replicates:
            packet_id = f"case_{case_id:02d}__rep_{replicate:02d}"
            available: dict[str, tuple[common.ResultSource, str]] = {}
            for condition in CONDITIONS:
                source = source_for(
                    core_run_set=core_run_set,
                    component_run_set=component_run_set,
                    repo=repo,
                    record=record,
                    condition=condition,
                    replicate=replicate,
                    eligibility=eligibility,
                )
                if source is None:
                    missing.append(f"case_{case_id:02d}/{condition}/replicate_{replicate:02d}")
                    continue
                final = common.clean_final(source.path.read_text(encoding="utf-8", errors="replace"))
                if not final:
                    raise RuntimeError(f"Empty candidate body after cleaning: {source.path}")
                output_hash = hashlib.sha256(final.encode("utf-8")).hexdigest()
                if condition in CORE_CONDITIONS:
                    expected_hash = reference_hashes.get((packet_id, condition))
                    if expected_hash != output_hash:
                        reference_mismatches.append(f"{packet_id}/{condition}")
                available[condition] = (source, final)

            shift = packet_index % len(base_order)
            order = base_order[shift:] + base_order[:shift]
            ordered = [(condition, *available[condition]) for condition in order if condition in available]
            packet_sizes[packet_id] = len(ordered)
            body_hashes = [hashlib.sha256(final.encode("utf-8")).hexdigest() for _, _, final in ordered]
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
            for alias, (condition, source, final) in zip(aliases, ordered):
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
                        "source_run_set": str(
                            component_run_set if condition in COMPONENT_CONDITIONS else core_run_set
                        ),
                        "source_file": str(source.path.resolve()),
                        "source_manifest": str(source.manifest_path.resolve()) if source.manifest_path else "",
                        "source_file_sha256": common.sha256_file(source.path),
                        "output_sha256": hashlib.sha256(final.encode("utf-8")).hexdigest(),
                        "output_characters": len(final),
                    }
                )
            (output_dir / f"{packet_id}.md").write_bytes(("\n".join(parts) + "\n").encode("utf-8"))
            packet_index += 1

    if key_rows:
        common.write_csv(output_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv", key_rows)

    expected_packets = len(selected_cases) * len(selected_replicates)
    expected_candidates = expected_packets * len(CONDITIONS)
    alias_condition_counts = {
        alias: {
            condition: sum(row["alias"] == alias and row["condition"] == condition for row in key_rows)
            for condition in CONDITIONS
        }
        for alias in aliases
    }
    lower = expected_packets // len(CONDITIONS)
    upper = lower + (1 if expected_packets % len(CONDITIONS) else 0)
    alias_balance_passed = all(
        lower <= count <= upper
        for counts in alias_condition_counts.values()
        for count in counts.values()
    )
    wrong_size_packets = sorted(
        packet_id for packet_id, size in packet_sizes.items() if size != len(CONDITIONS)
    )
    passed = (
        packet_index == expected_packets
        and len(key_rows) == expected_candidates
        and not missing
        and not wrong_size_packets
        and not duplicate_packets
        and not reference_mismatches
        and alias_balance_passed
    )
    summary = {
        "status": "PASS" if passed else "FAIL",
        "config": str(config_path),
        "core_run_set": str(core_run_set),
        "component_run_set": str(component_run_set),
        "reference_blind_key": str(reference_key),
        "seed": seed,
        "aliasing_method": "seeded balanced cyclic rotation",
        "balanced_base_conditions": base_order,
        "selected_cases": selected_cases,
        "selected_replicates": selected_replicates,
        "selected_conditions": list(CONDITIONS),
        "expected_packets": expected_packets,
        "packets": packet_index,
        "expected_candidates": expected_candidates,
        "candidates": len(key_rows),
        "source_counts": source_counts,
        "alias_count_lower_bound": lower,
        "alias_count_upper_bound": upper,
        "alias_condition_counts": alias_condition_counts,
        "alias_balance_passed": alias_balance_passed,
        "core_reference_hashes_checked": expected_packets * len(CORE_CONDITIONS),
        "core_reference_hash_mismatches": sorted(reference_mismatches),
        "wrong_size_packets": wrong_size_packets,
        "duplicate_candidate_packets": sorted(duplicate_packets),
        "missing_count": len(missing),
        "missing": missing,
    }
    (output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
