from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import build_blind_packets as frozen


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def read_controls(path: Path) -> dict[tuple[int, int], dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    controls = {(int(row["case_id"]), int(row["replicate_id"])): row for row in rows}
    if len(controls) != len(rows):
        raise RuntimeError("Duplicate original control case/replicate rows")
    return controls


def validated_original(row: dict[str, str], case: dict[str, Any]) -> dict[str, Any]:
    path = Path(row["source_file"]).resolve()
    if row["condition"] != "original_prompt_mpds" or not path.is_file():
        raise RuntimeError(f"Missing or mismatched original source: {path}")
    if frozen.sha256_file(path) != row["source_file_sha256"].lower():
        raise RuntimeError(f"Original source hash changed: {path}")
    manifest_path = Path(row["source_manifest"]).resolve() if row["source_manifest"] else None
    if manifest_path:
        manifest = read_json(manifest_path)
        checks = {
            "status": manifest.get("status") == "COMPLETE",
            "final_hash": manifest.get("final_sha256") == row["source_file_sha256"],
            "model": manifest.get("model") == "gemini-2.5-pro",
            "temperature": manifest.get("temperature") == 0.5,
            "case": manifest.get("case_id") == int(row["case_id"]),
            "replicate": manifest.get("replicate_id") == int(row["replicate_id"]),
            "evidence_a": manifest.get("knowledge_sha256", {}).get("A") == case["knowledge_a_sha256"],
            "evidence_b": manifest.get("knowledge_sha256", {}).get("B") == case["knowledge_b_sha256"],
        }
        if not all(checks.values()):
            raise RuntimeError(f"Original run manifest mismatch: {manifest_path}")
    body = frozen.clean_final(path.read_text(encoding="utf-8", errors="replace"))
    if not body or sha256_text(body) != row["cleaned_output_sha256"] or len(body) != int(row["output_characters"]):
        raise RuntimeError(f"Original cleaned output mismatch: {path}")
    return {"path": path, "manifest_path": manifest_path, "body": body, "source_sha256": row["source_file_sha256"], "body_sha256": sha256_text(body)}


def validated_deleaked(root: Path, generation: dict[str, Any], case_id: int, replicate_id: int) -> dict[str, Any]:
    run_dir = root / generation["output"]["run_set"] / f"case_{case_id:02d}" / "deleaked" / f"replicate_{replicate_id:02d}"
    path = run_dir / "final.txt"
    manifest_path = run_dir / "run_manifest.json"
    if not path.is_file() or not manifest_path.is_file():
        raise RuntimeError(f"Missing de-leaked source: {run_dir}")
    manifest = read_json(manifest_path)
    case = generation["cases"][str(case_id)]
    checks = {
        "status": manifest.get("status") == "COMPLETE",
        "config": manifest.get("config_id") == generation["config_id"],
        "case": manifest.get("case_id") == case_id,
        "replicate": manifest.get("replicate_id") == replicate_id,
        "condition": manifest.get("condition") == "mpds_deleaked",
        "model": manifest.get("model") == "gemini-2.5-pro",
        "temperature": manifest.get("temperature") == 0.5,
        "date": str(manifest.get("simulation_date")) == str(case["simulation_date"]),
        "task": manifest.get("debate_topic") == case["debate_topic"],
        "input_situation": manifest.get("deleaked_inputs", {}).get("situation_sha256") == case["deleaked_situation_sha256"],
        "input_context": manifest.get("deleaked_inputs", {}).get("user_context_sha256") == case["deleaked_user_context_sha256"],
        "evidence_a": manifest.get("evidence", {}).get("A", {}).get("sha256") == case["knowledge_a_sha256"],
        "evidence_b": manifest.get("evidence", {}).get("B", {}).get("sha256") == case["knowledge_b_sha256"],
        "citation_validation": manifest.get("citation_validation_completed") is True,
        "final_hash": frozen.sha256_file(path) == manifest.get("final_sha256"),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"De-leaked source failed checks {failed}: {run_dir}")
    body = frozen.clean_final(path.read_text(encoding="utf-8", errors="replace"))
    if not body:
        raise RuntimeError(f"Empty de-leaked cleaned output: {path}")
    return {"path": path.resolve(), "manifest_path": manifest_path.resolve(), "body": body, "source_sha256": frozen.sha256_file(path), "body_sha256": sha256_text(body)}


def packet_body(packet_text: str, alias: str, next_alias: str | None) -> str:
    marker = f"\n## {alias}\n\n"
    start = packet_text.index(marker) + len(marker)
    end = len(packet_text) if next_alias is None else packet_text.index(f"\n## {next_alias}\n\n", start)
    return packet_text[start:end].strip()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build condition-blind original/de-leaked Pass 1 pairs")
    parser.add_argument("--config", type=Path, default=root / "config" / "independent_judge_sonnet5_pass1_deleak_pair_v1.json")
    args = parser.parse_args()
    config_path = args.config.resolve()
    config = read_json(config_path)
    generation = read_json(resolve(root, config["source_generation_config"]))
    if config["selected_case_ids"] != generation["selection"]["selected_case_ids"]:
        raise RuntimeError("Case IDs differ from frozen generation config")
    if config["target_replicates"] != generation["design"]["replicates"]:
        raise RuntimeError("Replicates differ from frozen generation config")
    controls = read_controls(resolve(root, config["original_control_manifest"]))
    expected = {(case_id, rep) for case_id in config["selected_case_ids"] for rep in config["target_replicates"]}
    if set(controls) != expected:
        raise RuntimeError("Original control manifest does not contain exactly the nine frozen pairs")
    packet_dir = resolve(root, config["packets"])
    key_dir = resolve(root, config["blind_key_dir"])
    for directory in (packet_dir, key_dir):
        if directory.exists():
            raise RuntimeError(f"Refusing to overwrite existing directory: {directory}")

    sources: dict[tuple[int, int, str], dict[str, Any]] = {}
    for case_id, rep in sorted(expected):
        sources[(case_id, rep, "original_prompt_mpds")] = validated_original(controls[(case_id, rep)], generation["cases"][str(case_id)])
        sources[(case_id, rep, "mpds_deleaked")] = validated_deleaked(root, generation, case_id, rep)

    packet_dir.mkdir(parents=True)
    key_dir.mkdir(parents=True)
    base_order = list(config["conditions"])
    random.Random(int(config["seed"])).shuffle(base_order)
    aliases = ("Candidate A", "Candidate B")
    key_rows: list[dict[str, Any]] = []
    hash_rows: list[dict[str, Any]] = []
    packet_hashes: dict[str, str] = {}
    duplicates: list[str] = []
    for index, (case_id, rep) in enumerate((case, replicate) for case in config["selected_case_ids"] for replicate in config["target_replicates"]):
        packet_id = f"case_{case_id:02d}__rep_{rep:02d}"
        condition_order = base_order[index % 2:] + base_order[:index % 2]
        selected = [sources[(case_id, rep, condition)] for condition in condition_order]
        if selected[0]["body_sha256"] == selected[1]["body_sha256"]:
            duplicates.append(packet_id)
        case = generation["cases"][str(case_id)]
        parts = [
            f"# Blinded battery hypothesis evaluation packet {packet_id}",
            "",
            f"Simulation date: {case['simulation_date']}",
            "",
            f"Task: {case['debate_topic']}",
            "",
            "Score each anonymous final answer independently using the verbatim public IHQ Scoring Rules and Pass 1 of the supplementary module. Apply only the task constraints stated above; do not infer undisclosed target design features. Return raw dimensions, not rankings.",
        ]
        for alias, source in zip(aliases, selected, strict=True):
            parts.extend(["", f"## {alias}", "", source["body"]])
        packet_path = packet_dir / f"{packet_id}.md"
        packet_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
        reread = packet_path.read_text(encoding="utf-8")
        packet_hashes[packet_id] = frozen.sha256_file(packet_path)
        for position, (alias, condition, source) in enumerate(zip(aliases, condition_order, selected, strict=True)):
            read_body = packet_body(reread, alias, aliases[position + 1] if position + 1 < len(aliases) else None)
            matches = sha256_text(read_body) == source["body_sha256"]
            key_rows.append({
                "packet_id": packet_id, "case_id": case_id, "replicate_id": rep,
                "alias": alias, "condition": condition, "source_file": str(source["path"]),
                "source_manifest": str(source["manifest_path"] or ""),
                "source_file_sha256": source["source_sha256"],
                "cleaned_body_sha256": source["body_sha256"],
                "packet_body_sha256": sha256_text(read_body), "hash_match": matches,
                "output_characters": len(read_body),
            })
            hash_rows.append({"packet_id": packet_id, "alias": alias, "cleaned_source_body_sha256": source["body_sha256"], "packet_body_sha256": sha256_text(read_body), "hash_match": matches})

    write_csv(key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv", key_rows)
    write_csv(key_dir / "hash_validation.csv", hash_rows)
    counts = {alias: {condition: sum(row["alias"] == alias and row["condition"] == condition for row in key_rows) for condition in config["conditions"]} for alias in aliases}
    passed = (
        len(packet_hashes) == config["expected_packets"]
        and len(key_rows) == config["expected_candidates"]
        and all(row["hash_match"] for row in key_rows)
        and not duplicates
        and all(abs(values[base_order[0]] - values[base_order[1]]) == 1 for values in counts.values())
    )
    summary = {
        "status": "PASS" if passed else "FAIL", "config": str(config_path),
        "packets": len(packet_hashes), "candidates": len(key_rows),
        "candidate_body_hash_matches": sum(row["hash_match"] for row in key_rows),
        "alias_condition_counts": counts, "duplicate_candidate_packets": duplicates,
        "packet_sha256": packet_hashes, "blind_key_dir": str(key_dir), "api_calls_made": 0,
    }
    (key_dir / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"blind_key_dir", "packet_sha256"}}, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
