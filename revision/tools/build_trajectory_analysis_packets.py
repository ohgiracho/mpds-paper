from __future__ import annotations

import argparse
import csv
import difflib
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openpyxl

from trajectory_common import ALIASES, CONDITIONS, load_config, normalize_space, resolve_from_root, sha256_bytes, sha256_file, write_csv, write_json


@dataclass(frozen=True)
class TrajectorySource:
    condition: str
    case_id: int
    replicate: int
    source_kind: str
    source_files: tuple[Path, ...]
    manifest_path: Path | None
    text: str
    stage_count: int
    integrity_note: str


DEBATE_HEADER = re.compile(
    r"^\[(?P<label>(?:[^\]\r\n]*Round\s+[123])|FINAL SYNTHESIS)\]\s*$",
    flags=re.MULTILINE | re.IGNORECASE,
)
EVIDENCE_APPENDIX = re.compile(r"\n--- Evidence Appendix[^\n]*---.*\Z", flags=re.DOTALL | re.IGNORECASE)


def verify_generated_manifest(path: Path, *, case_id: int, condition: str, replicate: int) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "status": "COMPLETE",
        "case_id": case_id,
        "condition": condition,
        "replicate_id": replicate,
    }
    for field, value in expected.items():
        observed = data.get(field)
        if field in {"case_id", "replicate_id"}:
            observed = int(observed)
        if field == "condition":
            observed = str(observed).lower()
        if observed != value:
            raise RuntimeError(f"Manifest mismatch {field}: {path}")
    return data


def remove_evidence_appendix(value: str) -> str:
    cleaned = EVIDENCE_APPENDIX.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    cleaned = re.sub(r"\n={20,}\s*\Z", "", cleaned)
    return cleaned.strip()


def clean_final_file(value: str) -> str:
    cleaned = remove_evidence_appendix(value).lstrip("\ufeff")
    return re.sub(r"^\[FINAL SYNTHESIS\]\s*", "", cleaned, flags=re.IGNORECASE).strip()


def compare_final(final_body: str, final_file_text: str, *, allow_legacy_encoding_damage: bool) -> str:
    left = normalize_space(final_body)
    right = normalize_space(final_file_text)
    if left == right:
        return "final_section_exactly_matches_final_file_after_deterministic_cleaning"
    ratio = difflib.SequenceMatcher(a=left, b=right, autojunk=False).ratio()
    if allow_legacy_encoding_damage and ratio >= 0.995:
        return f"legacy_final_file_near_match_after_apparent_encoding_damage;sequence_similarity={ratio:.6f}"
    raise RuntimeError(f"Final-section mismatch; normalized sequence similarity={ratio:.6f}")


def extract_debate_trajectory(text: str) -> tuple[str, int, str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(DEBATE_HEADER.finditer(normalized))
    if len(matches) != 7:
        raise RuntimeError(f"Expected six debate turns plus final synthesis; found {len(matches)} sections")
    sections: list[str] = []
    final_body = ""
    for index, match in enumerate(matches):
        label = match.group("label").strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = remove_evidence_appendix(normalized[match.end():end])
        if not body:
            raise RuntimeError(f"Empty debate section: {label}")
        sections.extend([f"### Stage {index + 1}: {label}", "", body])
        if label.upper() == "FINAL SYNTHESIS":
            final_body = body
    if not final_body:
        raise RuntimeError("Final synthesis section was not found")
    return "\n\n".join(sections).strip() + "\n", len(matches), final_body


def read_eligibility(path: Path) -> dict[tuple[int, str], dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {(int(row["case_id"]), row["condition"]): row for row in csv.DictReader(handle)}


def core_source(
    root: Path,
    repo: Path,
    run_set: Path,
    eligibility: dict[tuple[int, str], dict[str, str]],
    case_id: int,
    condition: str,
    replicate: int,
) -> TrajectorySource:
    if replicate == 1:
        row = eligibility.get((case_id, condition))
        if row is None or row.get("practical_eligible_as_replicate_1", "").lower() != "true":
            raise RuntimeError(f"Legacy replicate 1 is not eligible: case {case_id}, {condition}")
        final_path = (repo / row["output_file"]).resolve()
        if sha256_file(final_path) != row["output_sha256"].lower():
            raise RuntimeError(f"Legacy final hash mismatch: {final_path}")
        log_name = f"DS_Debate_Log({case_id}).txt" if condition == "ds" else f"Debate_Log({case_id}).txt"
        log_path = final_path.parent / log_name
        if not log_path.exists():
            raise RuntimeError(f"Legacy debate log missing: {log_path}")
        trajectory, stages, final_body = extract_debate_trajectory(log_path.read_text(encoding="utf-8", errors="replace"))
        final_text = clean_final_file(final_path.read_text(encoding="utf-8", errors="replace"))
        try:
            integrity_note = compare_final(final_body, final_text, allow_legacy_encoding_damage=True)
        except RuntimeError as exc:
            raise RuntimeError(f"Legacy final does not match final section in debate log: {log_path}; {exc}") from exc
        return TrajectorySource(condition, case_id, replicate, "legacy_public_debate_log", (log_path, final_path), None, trajectory, stages, integrity_note)

    run_dir = run_set / f"case_{case_id:02d}" / condition / f"replicate_{replicate:02d}"
    full_output = run_dir / "full_output.txt"
    final_path = run_dir / "final.txt"
    manifest_path = run_dir / "run_manifest.json"
    if not all(path.exists() for path in (full_output, final_path, manifest_path)):
        raise RuntimeError(f"Generated core trajectory is incomplete: {run_dir}")
    manifest = verify_generated_manifest(
        manifest_path, case_id=case_id, condition=condition, replicate=replicate
    )
    if sha256_file(full_output) != str(manifest.get("full_output_sha256", "")).lower():
        raise RuntimeError(f"Generated full output hash mismatch: {full_output}")
    if sha256_file(final_path) != str(manifest.get("final_sha256", "")).lower():
        raise RuntimeError(f"Generated final hash mismatch: {final_path}")
    trajectory, stages, final_body = extract_debate_trajectory(full_output.read_text(encoding="utf-8", errors="replace"))
    final_text = clean_final_file(final_path.read_text(encoding="utf-8", errors="replace"))
    try:
        integrity_note = compare_final(final_body, final_text, allow_legacy_encoding_damage=False)
    except RuntimeError as exc:
        raise RuntimeError(f"Generated final does not match final section: {full_output}; {exc}") from exc
    return TrajectorySource(condition, case_id, replicate, "generated_core", (full_output, final_path, manifest_path), manifest_path, trajectory, stages, integrity_note)


def component_source(run_set: Path, case_id: int, condition: str, replicate: int) -> TrajectorySource:
    run_dir = run_set / f"case_{case_id:02d}" / condition / f"replicate_{replicate:02d}"
    manifest_path = run_dir / "run_manifest.json"
    final_path = run_dir / "final.txt"
    if not manifest_path.exists() or not final_path.exists():
        raise RuntimeError(f"Component-control trajectory is incomplete: {run_dir}")
    manifest = verify_generated_manifest(
        manifest_path, case_id=case_id, condition=condition, replicate=replicate
    )
    if sha256_file(final_path) != str(manifest.get("final_sha256", "")).lower():
        raise RuntimeError(f"Component-control final hash mismatch: {final_path}")

    sections: list[str] = []
    if condition == "sair":
        trajectory_path = run_dir / "trajectory.json"
        stages_data = json.loads(trajectory_path.read_text(encoding="utf-8"))
        expected = ["initial", "critique_1", "revision_1", "critique_2", "revision_2", "critique_3", "revision_3"]
        observed = [str(item.get("stage")) for item in stages_data]
        if observed != expected:
            raise RuntimeError(f"Unexpected SAIR stage order: {trajectory_path}")
        for index, item in enumerate(stages_data, start=1):
            body = str(item.get("text", "")).strip()
            if not body:
                raise RuntimeError(f"Empty SAIR stage: {trajectory_path}")
            sections.extend([f"### Stage {index}: {item['stage']}", "", body])
        if normalize_space(stages_data[-1]["text"]) != normalize_space(final_path.read_text(encoding="utf-8", errors="replace")):
            raise RuntimeError(f"SAIR revision_3 does not match final.txt: {run_dir}")
        source_files = (trajectory_path, final_path, manifest_path)
        stage_count = 7
    elif condition == "ses":
        independent_path = run_dir / "independent_answers.json"
        independent = json.loads(independent_path.read_text(encoding="utf-8"))
        for index, key in enumerate(("scientist_a", "scientist_b"), start=1):
            body = str(independent.get(key, {}).get("text", "")).strip()
            if not body:
                raise RuntimeError(f"Empty SES independent answer: {independent_path}")
            label = "Independent Scientist A answer" if key == "scientist_a" else "Independent Scientist B answer"
            sections.extend([f"### Stage {index}: {label}", "", body])
        final_text = final_path.read_text(encoding="utf-8", errors="replace").strip()
        if not final_text:
            raise RuntimeError(f"Empty SES final: {final_path}")
        sections.extend(["### Stage 3: Final synthesis", "", final_text])
        source_files = (independent_path, final_path, manifest_path)
        stage_count = 3
    else:
        raise ValueError(condition)
    trajectory = "\n\n".join(sections).strip() + "\n"
    return TrajectorySource(
        condition,
        case_id,
        replicate,
        "generated_component",
        source_files,
        manifest_path,
        trajectory,
        stage_count,
        "component_final_matches_its_required_terminal_stage",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build label-masked trajectory-analysis packets without model calls")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--rebuild-before-freeze", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(root, args.config)
    if tuple(config["conditions"]) != CONDITIONS:
        raise RuntimeError(f"Condition order must remain {CONDITIONS}")
    cases = [int(value) for value in config["selected_case_ids"]]
    replicates = [int(value) for value in config["replicates"]]
    expected = len(cases) * len(replicates) * len(CONDITIONS)
    if expected != int(config["expected_trajectories"]):
        raise RuntimeError("Frozen expected trajectory count is inconsistent")

    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    packet_dir = resolve_from_root(root, config["packet_directory"])
    packet_dir.mkdir(parents=True, exist_ok=True)
    core_runs = resolve_from_root(root, config["core_run_set"])
    component_runs = resolve_from_root(root, config["component_run_set"])
    repo = resolve_from_root(root, config["legacy_repository"])
    eligibility_path = resolve_from_root(root, config["replicate1_eligibility"])
    eligibility = read_eligibility(eligibility_path)

    workbook = openpyxl.load_workbook(
        repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx",
        read_only=True,
        data_only=True,
    )
    values = list(workbook["BenchmarkCases"].iter_rows(values_only=True))
    records = {int(row[0]): dict(zip(values[0], row)) for row in values[1:] if row[0] is not None}

    base_order = list(CONDITIONS)
    random.Random(int(config["blinding"]["seed"])).shuffle(base_order)
    manifest_rows: list[dict[str, Any]] = []
    packet_records: list[tuple[Path, str]] = []
    source_counts: dict[str, int] = {}
    alias_condition_counts = {alias: {condition: 0 for condition in CONDITIONS} for alias in ALIASES}
    packet_index = 0

    for case_id in cases:
        record = records.get(case_id)
        if record is None:
            raise RuntimeError(f"Benchmark case is missing: {case_id}")
        for replicate in replicates:
            sources: dict[str, TrajectorySource] = {}
            for condition in CONDITIONS:
                if condition in {"ds", "mpds"}:
                    source = core_source(root, repo, core_runs, eligibility, case_id, condition, replicate)
                else:
                    source = component_source(component_runs, case_id, condition, replicate)
                sources[condition] = source
                source_counts[source.source_kind] = source_counts.get(source.source_kind, 0) + 1

            shift = packet_index % len(CONDITIONS)
            order = base_order[shift:] + base_order[:shift]
            packet_id = f"case_{case_id:02d}__rep_{replicate:02d}"
            parts = [
                f"# Label-masked trajectory packet {packet_id}",
                "",
                f"Simulation date: {record['cutoff_year']}",
                "",
                f"Scientific task: {record['debate_topic']}",
                "",
                "Evaluate each trajectory independently. Stage count, length, persona labels, and explicit disagreement do not by themselves merit a higher score.",
            ]
            pending_rows: list[dict[str, Any]] = []
            for alias, condition in zip(ALIASES, order, strict=True):
                source = sources[condition]
                parts.extend(["", f"## {alias}", "", source.text.rstrip()])
                trajectory_hash = sha256_bytes(source.text.encode("utf-8"))
                source_paths = [str(path.resolve()) for path in source.source_files]
                source_hashes = [sha256_file(path) for path in source.source_files]
                pending_rows.append(
                    {
                        "trajectory_id": f"{packet_id}__{alias.lower().replace(' ', '_')}",
                        "packet_id": packet_id,
                        "case_id": case_id,
                        "replicate": replicate,
                        "blind_condition_label": alias,
                        "condition": condition,
                        "source_kind": source.source_kind,
                        "source_paths_json": json.dumps(source_paths, ensure_ascii=False),
                        "source_hashes_json": json.dumps(source_hashes),
                        "source_manifest": str(source.manifest_path.resolve()) if source.manifest_path else "",
                        "source_integrity_note": source.integrity_note,
                        "stage_count": source.stage_count,
                        "trajectory_characters": len(source.text),
                        "trajectory_sha256": trajectory_hash,
                    }
                )
                alias_condition_counts[alias][condition] += 1
            packet_text = "\n".join(parts).rstrip() + "\n"
            packet_path = packet_dir / f"{packet_id}.md"
            packet_bytes = packet_text.encode("utf-8")
            if packet_path.exists():
                if packet_path.read_bytes() != packet_bytes:
                    integrity = analysis_dir / "trajectory_input_integrity_manifest.json"
                    if not args.rebuild_before_freeze or integrity.exists():
                        raise RuntimeError(f"Refusing to overwrite a non-identical packet: {packet_path}")
                    packet_path.write_bytes(packet_bytes)
            else:
                packet_path.write_bytes(packet_bytes)
            packet_hash = sha256_file(packet_path)
            for row in pending_rows:
                row["evaluation_packet"] = str(packet_path.resolve())
                row["evaluation_packet_sha256"] = packet_hash
                manifest_rows.append(row)
            packet_records.append((packet_path, packet_hash))
            packet_index += 1

    lower = int(config["expected_packets"]) // len(CONDITIONS)
    upper = lower + (1 if int(config["expected_packets"]) % len(CONDITIONS) else 0)
    alias_balance = all(lower <= count <= upper for values in alias_condition_counts.values() for count in values.values())
    unique_trajectories = len({row["trajectory_sha256"] for row in manifest_rows})
    passed = (
        len(packet_records) == int(config["expected_packets"])
        and len(manifest_rows) == int(config["expected_trajectories"])
        and unique_trajectories == len(manifest_rows)
        and alias_balance
    )
    manifest_path = analysis_dir / "trajectory_input_manifest.csv"
    write_csv(manifest_path, manifest_rows)
    summary = {
        "status": "PASS" if passed else "FAIL",
        "config": str(config_path),
        "packets": len(packet_records),
        "trajectories": len(manifest_rows),
        "unique_trajectory_hashes": unique_trajectories,
        "source_counts": source_counts,
        "stage_counts": {
            condition: sorted({int(row["stage_count"]) for row in manifest_rows if row["condition"] == condition})
            for condition in CONDITIONS
        },
        "aliasing_method": config["blinding"]["method"],
        "balanced_base_conditions": base_order,
        "alias_condition_counts": alias_condition_counts,
        "alias_balance_passed": alias_balance,
        "packet_bytes": {
            "minimum": min(path.stat().st_size for path, _ in packet_records),
            "maximum": max(path.stat().st_size for path, _ in packet_records),
            "total": sum(path.stat().st_size for path, _ in packet_records),
        },
        "substantive_text_truncation": False,
        "api_calls_made": 0,
    }
    write_json(analysis_dir / "trajectory_packet_build_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
