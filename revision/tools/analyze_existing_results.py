from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any

import openpyxl


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_final(text: str) -> str:
    markers = ("[FINAL SYNTHESIS]", "[Final Synthesis]", "[EOP Answer]", "[EO Answer]", "[Raw LLM Answer]")
    found = [(text.rfind(marker), marker) for marker in markers if marker in text]
    if not found:
        return text.strip()
    position, marker = max(found)
    return text[position + len(marker) :].strip()


def citation_ids(text: str) -> list[int]:
    ids: list[int] = []
    for body in re.findall(r"\[ID:\s*([^\]]+)\]", text, flags=re.I):
        ids.extend(int(value) for value in re.findall(r"\d+", body))
    return ids


def parse_entries(text: str) -> list[dict[str, str]]:
    blocks = re.split(r"(?m)(?=^ID:\s*\d+\s*$)", text)
    entries = []
    for block in blocks:
        if not re.match(r"(?m)^ID:\s*\d+\s*$", block):
            continue
        record = {}
        for key in ("ID", "Title", "Year", "DOI", "OpenAlexID"):
            match = re.search(rf"(?m)^{key}:\s*(.*)$", block)
            record[key] = match.group(1).strip() if match else ""
        entries.append(record)
    return entries


def dedup_key(entry: dict[str, str]) -> tuple[str, str]:
    doi = entry["DOI"].lower().strip()
    if doi and doi != "n/a":
        return "doi", doi
    openalex = entry["OpenAlexID"].lower().strip()
    if openalex and openalex != "n/a":
        return "openalex", openalex
    normalized = re.sub(r"[^0-9a-z]+", " ", entry["Title"].lower()).strip()
    return "title_year", f"{normalized}|{entry['Year']}"


def merged_count(path_a: Path, path_b: Path) -> int:
    seen = set()
    for path in (path_a, path_b):
        for entry in parse_entries(read_text(path)):
            seen.add(dedup_key(entry))
    return len(seen)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def quartile(citation_id: int, denominator: int) -> str:
    return f"Q{min(4, max(1, math.ceil(4 * citation_id / denominator)))}"


def main() -> None:
    parser = argparse.ArgumentParser()
    default_root = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo", type=Path, default=default_root.parent / "mpds_github_prep" / "github_repo")
    parser.add_argument("--audit-dir", type=Path, default=default_root / "audit")
    parser.add_argument("--output-dir", type=Path, default=default_root / "analysis")
    args = parser.parse_args()
    repo, audit_dir, output_dir = args.repo.resolve(), args.audit_dir.resolve(), args.output_dir.resolve()

    manifest: dict[int, dict[str, Path]] = {}
    with (audit_dir / "knowledge_snapshot_manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            manifest.setdefault(int(row["case_id"]), {})[row["pool"]] = Path(row["local_path"])

    workbook = openpyxl.load_workbook(
        repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx",
        read_only=True,
        data_only=True,
    )
    values = list(workbook["BenchmarkCases"].iter_rows(values_only=True))
    cases = [dict(zip(values[0], row)) for row in values[1:] if row[0] is not None]
    output_columns = {
        "raw": "public_raw_llm_output",
        "eo": "public_eo_output",
        "eop": "public_eop_output",
        "ds": "public_ds_output",
        "mpds": "public_mpds_output",
    }

    rows: list[dict[str, Any]] = []
    for case in cases:
        case_id = int(case["case_id"])
        merged_denominator = merged_count(manifest[case_id]["A"], manifest[case_id]["B"])
        for condition in CONDITIONS:
            path = repo / str(case[output_columns[condition]])
            final = extract_final(read_text(path))
            citations = citation_ids(final)
            denominator = merged_denominator if condition in {"eo", "eop"} else 500
            counts = Counter(quartile(value, denominator) for value in citations if 1 <= value <= denominator)
            invalid = sorted({value for value in citations if value < 1 or value > denominator})
            rows.append(
                {
                    "case_id": case_id,
                    "repo_case_slug": case["case_slug"],
                    "case_name": case["case_name"],
                    "condition": condition,
                    "output_file": str(case[output_columns[condition]]),
                    "characters": len(final),
                    "words": len(re.findall(r"\b\w+\b", final)),
                    "approx_tokens_chars_div_4": round(len(final) / 4),
                    "citation_occurrences": len(citations),
                    "unique_citation_ids": len(set(citations)),
                    "evidence_entry_count": 0 if condition == "raw" else denominator,
                    "valid_citation_occurrences": sum(counts.values()),
                    "invalid_citation_ids": ";".join(map(str, invalid)),
                    "q1_citations": counts["Q1"],
                    "q2_citations": counts["Q2"],
                    "q3_citations": counts["Q3"],
                    "q4_citations": counts["Q4"],
                }
            )
    write_csv(output_dir / "existing_output_metrics.csv", rows)

    summary: dict[str, Any] = {}
    for condition in CONDITIONS:
        subset = [row for row in rows if row["condition"] == condition]
        chars = [int(row["characters"]) for row in subset]
        citations = [int(row["citation_occurrences"]) for row in subset]
        quartiles = {f"Q{index}": sum(int(row[f"q{index}_citations"]) for row in subset) for index in range(1, 5)}
        valid_total = sum(quartiles.values())
        summary[condition] = {
            "cases": len(subset),
            "final_characters_mean": round(mean(chars), 2),
            "final_characters_sd": round(stdev(chars), 2),
            "final_characters_median": median(chars),
            "citation_occurrences_mean": round(mean(citations), 2),
            "citation_position_counts": quartiles,
            "citation_position_percent": {
                key: round(100 * value / valid_total, 2) if valid_total else None for key, value in quartiles.items()
            },
            "invalid_citation_case_count": sum(bool(row["invalid_citation_ids"]) for row in subset),
        }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "existing_output_metrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"rows": len(rows), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
