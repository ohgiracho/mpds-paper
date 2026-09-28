from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SECTION_RE = re.compile(r"(?m)^## (Candidate [A-D])\s*$")
TARGET_CONDITIONS = {"sair", "ses"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def split_packet(text: str) -> tuple[str, dict[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    aliases = [match.group(1) for match in matches]
    expected = [f"Candidate {letter}" for letter in "ABCD"]
    if aliases != expected:
        raise RuntimeError(f"Expected Candidate A-D in order, got {aliases}")
    header = text[: matches[0].start()].rstrip()
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.start() : end].strip()
    return header, sections


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    source_dir = (
        root / "evaluation" / "evidence_audit_packets_component_controls_core10_n3_4condition_v1"
    )
    blind_key_path = (
        root
        / "evaluation"
        / "blind_packets_component_controls_core10_n3_4condition_v1"
        / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv"
    )
    output_dir = root / "evaluation" / "evidence_audit_packets_component_controls_sair_ses_v1"
    output_dir.mkdir(parents=True, exist_ok=False)

    with blind_key_path.open(encoding="utf-8-sig", newline="") as handle:
        key_rows = list(csv.DictReader(handle))
    by_packet: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in key_rows:
        if row["condition"] in TARGET_CONDITIONS:
            by_packet[row["packet_id"]].append(row)

    if len(by_packet) != 30 or sum(len(rows) for rows in by_packet.values()) != 60:
        raise RuntimeError("Expected 30 packets and 60 SAIR/SES candidates")

    selection_rows: list[dict[str, Any]] = []
    alias_condition_counts: Counter[tuple[str, str]] = Counter()
    packet_hashes: dict[str, str] = {}
    for packet_id in sorted(by_packet):
        rows = sorted(by_packet[packet_id], key=lambda row: row["alias"])
        if {row["condition"] for row in rows} != TARGET_CONDITIONS:
            raise RuntimeError(f"{packet_id}: SAIR/SES pair is incomplete")
        source_packet = source_dir / f"{packet_id}.md"
        header, sections = split_packet(source_packet.read_text(encoding="utf-8"))
        selected_aliases = [row["alias"] for row in rows]
        filtered_text = "\n\n".join([header, *(sections[alias] for alias in selected_aliases)]) + "\n"
        output_packet = output_dir / source_packet.name
        output_packet.write_text(filtered_text, encoding="utf-8")
        packet_hashes[packet_id] = sha256(output_packet)
        for row in rows:
            alias_condition_counts[(row["alias"], row["condition"])] += 1
            selection_rows.append(
                {
                    "packet_id": packet_id,
                    "case_id": row["case_id"],
                    "replicate_id": row["replicate_id"],
                    "alias": row["alias"],
                    "condition": row["condition"],
                    "source_file_sha256": row["source_file_sha256"],
                    "full_evidence_packet_sha256": sha256(source_packet),
                    "filtered_packet_sha256": packet_hashes[packet_id],
                }
            )

    write_csv(output_dir / "selection_key_DO_NOT_SHARE_WITH_RATERS.csv", selection_rows)
    summary = {
        "status": "PASS",
        "purpose": "SAIR_SES_ONLY_INPUT_ADAPTER_FOR_FROZEN_SPLIT_CANDIDATE_PASS2",
        "source_evidence_packet_dir": str(source_dir),
        "source_blind_key": str(blind_key_path),
        "packets": len(packet_hashes),
        "candidates": len(selection_rows),
        "conditions": sorted(TARGET_CONDITIONS),
        "alias_condition_counts": {
            f"{alias}|{condition}": count
            for (alias, condition), count in sorted(alias_condition_counts.items())
        },
        "packet_sha256": packet_hashes,
        "note": (
            "Only the two target candidate sections were retained. Candidate text and supplied evidence "
            "records are byte-for-byte slices of the full four-condition evidence packets."
        ),
    }
    (output_dir / "build_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
