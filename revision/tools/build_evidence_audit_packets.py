from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build_blind_packets import clean_final, sha256_file


FIELD_ORDER = ("ID", "Type", "Title", "Year", "FirstAuthor", "Venue", "Citations", "DOI", "OpenAlexID", "Abstract")
CITATION_PATTERN = re.compile(r"\[\s*IDs?\s*:\s*([^\]]+)\]", re.IGNORECASE)
ALIASES = tuple(f"Candidate {letter}" for letter in "ABCDE")


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_knowledge_text(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("ID:"):
            if current:
                entries.append(current)
            current = {key: "" for key in FIELD_ORDER}
            current["ID"] = stripped.split(":", 1)[1].strip()
            continue
        if current is None:
            continue
        matched = False
        for key in FIELD_ORDER[1:]:
            prefix = f"{key}:"
            if stripped.startswith(prefix):
                current[key] = stripped.split(":", 1)[1].strip()
                matched = True
                break
        if matched:
            continue
        if stripped and set(stripped) == {"-"}:
            entries.append(current)
            current = None
        elif stripped:
            current["Abstract"] = f"{current.get('Abstract', '')} {stripped}".strip()
    if current:
        entries.append(current)
    return entries


def normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", (text or "").lower())).strip()


def dedupe_key(entry: dict[str, str]) -> tuple[str, str]:
    doi = entry.get("DOI", "").strip()
    if doi and doi.upper() != "N/A":
        return "doi", doi.lower()
    openalex = entry.get("OpenAlexID", "").strip()
    if openalex and openalex.upper() != "N/A":
        return "openalex", openalex.lower()
    return "title_year", f"{normalize_title(entry.get('Title', ''))}||{entry.get('Year', '').strip()}"


def merge_entries(entries_a: list[dict[str, str]], entries_b: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries_a + entries_b:
        key = dedupe_key(entry)
        if key in seen:
            continue
        seen.add(key)
        copied = dict(entry)
        copied["ID"] = str(len(merged) + 1)
        merged.append(copied)
    return merged


def index_entries(entries: list[dict[str, str]]) -> dict[int, dict[str, str]]:
    indexed: dict[int, dict[str, str]] = {}
    for entry in entries:
        try:
            identifier = int(entry["ID"])
        except (KeyError, TypeError, ValueError):
            continue
        if identifier in indexed:
            raise RuntimeError(f"Duplicate evidence ID {identifier}")
        indexed[identifier] = entry
    return indexed


def extract_citation_ids(text: str) -> list[int]:
    identifiers: list[int] = []
    seen: set[int] = set()
    for match in CITATION_PATTERN.finditer(text):
        for token in re.findall(r"\d+", match.group(1)):
            identifier = int(token)
            if identifier not in seen:
                seen.add(identifier)
                identifiers.append(identifier)
    return identifiers


def extract_citation_occurrences(text: str) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    hint_pattern = re.compile(r"(?:scientist|debater|expert|evidence\s+pool|source\s+pool)\s*([AB])\b", re.IGNORECASE)
    for bracket_index, match in enumerate(CITATION_PATTERN.finditer(text), start=1):
        # Keep the attribution test deliberately local. A distant mention of a
        # scientist must not silently resolve an otherwise ambiguous citation.
        context = text[max(0, match.start() - 96):match.start()]
        hints = list(hint_pattern.finditer(context))
        pool_hint = hints[-1].group(1).upper() if hints else ""
        for token in re.findall(r"\d+", match.group(1)):
            occurrences.append(
                {
                    "bracket_index": bracket_index,
                    "cited_id": int(token),
                    "explicit_pool_hint": pool_hint,
                }
            )
    return occurrences


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def canonical_knowledge_manifest(run_set: Path, case_id: int) -> dict[str, Any]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted((run_set / f"case_{case_id:02d}").glob("**/run_manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("status") != "COMPLETE":
            continue
        if not manifest.get("knowledge_a") or not manifest.get("knowledge_b"):
            continue
        candidates.append((path, manifest))
    if not candidates:
        raise RuntimeError(f"No COMPLETE manifest with knowledge paths for case {case_id}")

    signatures = {
        (
            str(manifest["knowledge_a"]),
            str(manifest["knowledge_b"]),
            str(manifest.get("knowledge_sha256", {}).get("A", "")),
            str(manifest.get("knowledge_sha256", {}).get("B", "")),
        )
        for _, manifest in candidates
    }
    if len(signatures) != 1:
        raise RuntimeError(f"Knowledge snapshot mismatch across COMPLETE manifests for case {case_id}")
    return candidates[0][1]


def load_case_evidence(run_set: Path, case_id: int) -> dict[str, Any]:
    manifest = canonical_knowledge_manifest(run_set, case_id)
    path_a = Path(manifest["knowledge_a"])
    path_b = Path(manifest["knowledge_b"])
    if not path_a.exists() or not path_b.exists():
        raise FileNotFoundError(f"Missing knowledge snapshot for case {case_id}")
    expected = manifest.get("knowledge_sha256", {})
    if expected.get("A") and sha256_file(path_a) != str(expected["A"]).lower():
        raise RuntimeError(f"Knowledge A hash mismatch for case {case_id}")
    if expected.get("B") and sha256_file(path_b) != str(expected["B"]).lower():
        raise RuntimeError(f"Knowledge B hash mismatch for case {case_id}")

    entries_a = parse_knowledge_text(read_text(path_a))
    entries_b = parse_knowledge_text(read_text(path_b))
    merged = merge_entries(entries_a, entries_b)
    return {
        "A": index_entries(entries_a),
        "B": index_entries(entries_b),
        "M": index_entries(merged),
        "hash_a": sha256_file(path_a),
        "hash_b": sha256_file(path_b),
        "count_a": len(entries_a),
        "count_b": len(entries_b),
        "count_merged": len(merged),
    }


def format_record(label: str, citation_id: int, pool: str, entry: dict[str, str]) -> list[str]:
    return [
        f"#### {label}",
        "",
        f"Cited token: `[ID: {citation_id}]`",
        f"Evidence pool: {pool}",
        f"Title: {entry.get('Title', '') or 'N/A'}",
        f"Year: {entry.get('Year', '') or 'N/A'}",
        f"DOI: {entry.get('DOI', '') or 'N/A'}",
        f"OpenAlexID: {entry.get('OpenAlexID', '') or 'N/A'}",
        f"Abstract: {entry.get('Abstract', '') or 'N/A'}",
    ]


def same_record(first: dict[str, str], second: dict[str, str]) -> bool:
    return dedupe_key(first) == dedupe_key(second)


def make_candidate_evidence(
    packet_id: str,
    row: dict[str, str],
    final: str,
    evidence: dict[str, Any],
) -> tuple[list[str], list[dict[str, Any]], dict[str, int]]:
    alias = row["alias"]
    letter = alias.rsplit(" ", 1)[-1]
    condition = row["condition"].lower()
    citation_ids = extract_citation_ids(final)
    occurrences = extract_citation_occurrences(final)
    hints_by_id: dict[int, list[str]] = defaultdict(list)
    for occurrence in occurrences:
        hints_by_id[occurrence["cited_id"]].append(occurrence["explicit_pool_hint"])
    audit_rows: list[dict[str, Any]] = []
    blocks: list[str] = []
    counters = Counter(
        unique_cited_ids=len(citation_ids),
        resolved_unique_ids=0,
        context_or_namespace_single_record_ids=0,
        ambiguous_multiple_record_ids=0,
        unresolved_unique_ids=0,
        supplied_records=0,
    )

    if condition == "raw":
        namespace = "none"
    elif condition in {"eo", "eop"}:
        namespace = "merged"
    elif condition in {"ds", "mpds", "sair", "ses"}:
        namespace = "dual_pool"
    else:
        raise RuntimeError(f"Unsupported condition in blind key: {condition}")

    if not citation_ids:
        blocks.extend(["No bracketed evidence identifiers were present in this candidate; no abstract records are supplied."])
        audit_rows.append(
            {
                "packet_id": packet_id,
                "case_id": row["case_id"],
                "replicate_id": row["replicate_id"],
                "alias": alias,
                "condition": condition,
                "citation_namespace": namespace,
                "cited_id": "",
                "evidence_label": "",
                "source_pool": "",
                "source_original_id": "",
                "resolution_status": "no_citation",
                "title": "",
                "doi": "",
                "openalex_id": "",
            }
        )
        return blocks, audit_rows, dict(counters)

    for ordinal, citation_id in enumerate(citation_ids, start=1):
        matches: list[tuple[str, dict[str, str]]] = []
        if namespace == "merged":
            entry = evidence["M"].get(citation_id)
            if entry:
                matches.append(("merged", entry))
        elif namespace == "dual_pool":
            entry_a = evidence["A"].get(citation_id)
            entry_b = evidence["B"].get(citation_id)
            local_hints = hints_by_id.get(citation_id, [])
            all_explicit_a = bool(local_hints) and all(hint == "A" for hint in local_hints)
            all_explicit_b = bool(local_hints) and all(hint == "B" for hint in local_hints)
            if all_explicit_a and entry_a:
                matches.append(("A", entry_a))
            elif all_explicit_b and entry_b:
                matches.append(("B", entry_b))
            elif entry_a and entry_b and same_record(entry_a, entry_b):
                matches.append(("A and B (same record)", entry_a))
            else:
                if entry_a:
                    matches.append(("A", entry_a))
                if entry_b:
                    matches.append(("B", entry_b))

        if not matches:
            counters["unresolved_unique_ids"] += 1
            blocks.extend([f"#### {letter}-U{ordinal:02d}", "", f"Cited token `[ID: {citation_id}]` did not resolve to a supplied evidence record."])
            audit_rows.append(
                {
                    "packet_id": packet_id,
                    "case_id": row["case_id"],
                    "replicate_id": row["replicate_id"],
                    "alias": alias,
                    "condition": condition,
                    "citation_namespace": namespace,
                    "cited_id": citation_id,
                    "evidence_label": "",
                    "source_pool": "",
                    "source_original_id": "",
                    "resolution_status": "unresolved",
                    "title": "",
                    "doi": "",
                    "openalex_id": "",
                }
            )
            continue

        counters["resolved_unique_ids"] += 1
        if len(matches) == 1:
            counters["context_or_namespace_single_record_ids"] += 1
        else:
            counters["ambiguous_multiple_record_ids"] += 1

        for match_index, (pool, entry) in enumerate(matches):
            suffix = "" if len(matches) == 1 else chr(ord("a") + match_index)
            label = f"{letter}-R{ordinal:02d}{suffix}"
            blocks.extend(format_record(label, citation_id, pool, entry))
            counters["supplied_records"] += 1
            audit_rows.append(
                {
                    "packet_id": packet_id,
                    "case_id": row["case_id"],
                    "replicate_id": row["replicate_id"],
                    "alias": alias,
                    "condition": condition,
                    "citation_namespace": namespace,
                    "cited_id": citation_id,
                    "evidence_label": label,
                    "source_pool": pool,
                    "source_original_id": entry.get("ID", ""),
                    "resolution_status": "resolved_unique" if len(matches) == 1 else "resolved_ambiguous",
                    "title": entry.get("Title", ""),
                    "doi": entry.get("DOI", ""),
                    "openalex_id": entry.get("OpenAlexID", ""),
                }
            )
    return blocks, audit_rows, dict(counters)


def make_occurrence_audit_rows(
    packet_id: str,
    row: dict[str, str],
    final: str,
    evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], Counter]:
    condition = row["condition"].lower()
    if condition == "raw":
        namespace = "none"
    elif condition in {"eo", "eop"}:
        namespace = "merged"
    else:
        namespace = "dual_pool"

    rows: list[dict[str, Any]] = []
    counters = Counter(
        citation_occurrences=0,
        resolved_occurrences=0,
        attributable_occurrences=0,
        ambiguous_occurrences=0,
        unresolved_occurrences=0,
    )
    for occurrence_index, occurrence in enumerate(extract_citation_occurrences(final), start=1):
        citation_id = occurrence["cited_id"]
        pool_hint = occurrence["explicit_pool_hint"]
        records_a = evidence["A"].get(citation_id)
        records_b = evidence["B"].get(citation_id)
        record_m = evidence["M"].get(citation_id)
        resolution = "unresolved"
        attributed_pool = ""

        if namespace == "merged" and record_m:
            resolution = "attributable_merged"
            attributed_pool = "merged"
        elif namespace == "dual_pool":
            if pool_hint == "A" and records_a:
                resolution = "attributable_explicit_pool"
                attributed_pool = "A"
            elif pool_hint == "B" and records_b:
                resolution = "attributable_explicit_pool"
                attributed_pool = "B"
            elif records_a and records_b and same_record(records_a, records_b):
                resolution = "attributable_same_record_in_both_pools"
                attributed_pool = "A_and_B"
            elif bool(records_a) ^ bool(records_b):
                resolution = "attributable_single_available_record"
                attributed_pool = "A" if records_a else "B"
            elif records_a and records_b:
                resolution = "ambiguous_two_records"

        counters["citation_occurrences"] += 1
        if resolution != "unresolved":
            counters["resolved_occurrences"] += 1
        if resolution.startswith("attributable_"):
            counters["attributable_occurrences"] += 1
        elif resolution.startswith("ambiguous_"):
            counters["ambiguous_occurrences"] += 1
        else:
            counters["unresolved_occurrences"] += 1
        rows.append(
            {
                "packet_id": packet_id,
                "case_id": row["case_id"],
                "replicate_id": row["replicate_id"],
                "alias": row["alias"],
                "condition": condition,
                "citation_namespace": namespace,
                "occurrence_index": occurrence_index,
                "bracket_index": occurrence["bracket_index"],
                "cited_id": citation_id,
                "explicit_pool_hint": pool_hint,
                "resolution_status": resolution,
                "attributed_pool": attributed_pool,
            }
        )
    return rows, counters


def main() -> None:
    parser = argparse.ArgumentParser(description="Build blinded evidence-audit packets from frozen main packets")
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--blind-dir", type=Path, required=True)
    parser.add_argument("--run-set", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=root / "evaluation" / "evidence_audit_packets")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    blind_dir = args.blind_dir.resolve()
    run_set = args.run_set.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    key_path = blind_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv"
    rows = load_rows(key_path)
    by_packet: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_packet[row["packet_id"]].append(row)

    case_evidence: dict[int, dict[str, Any]] = {}
    audit_key_rows: list[dict[str, Any]] = []
    occurrence_audit_rows: list[dict[str, Any]] = []
    aggregate = Counter()
    occurrence_aggregate = Counter()
    packet_sizes: dict[str, dict[str, int]] = {}
    errors: list[str] = []

    for packet_id in sorted(by_packet):
        packet_rows = by_packet[packet_id]
        aliases = [row["alias"] for row in packet_rows]
        if sorted(aliases) != sorted(ALIASES):
            errors.append(
                f"{packet_id}: expected exactly {', '.join(ALIASES)}; got {sorted(aliases)}"
            )
            continue
        case_id = int(packet_rows[0]["case_id"])
        replicate_id = int(packet_rows[0]["replicate_id"])
        if any(int(row["case_id"]) != case_id or int(row["replicate_id"]) != replicate_id for row in packet_rows):
            errors.append(f"{packet_id}: inconsistent case/replicate in blind key")
            continue
        if case_id not in case_evidence:
            case_evidence[case_id] = load_case_evidence(run_set, case_id)
        evidence = case_evidence[case_id]

        source_packet = (blind_dir / f"{packet_id}.md").read_text(encoding="utf-8")
        cutoff_match = re.search(r"^Simulation date:\s*(.+)$", source_packet, re.MULTILINE)
        task_match = re.search(r"^Task:\s*(.+)$", source_packet, re.MULTILINE)
        if not cutoff_match or not task_match:
            errors.append(f"{packet_id}: missing cutoff or task")
            continue

        parts = [
            f"# Blinded evidence-audit packet {packet_id}",
            "",
            f"Simulation date: {cutoff_match.group(1).strip()}",
            "",
            f"Task: {task_match.group(1).strip()}",
            "",
            "Use Pass 2 of supplementary_evaluation_module_v1.md. Audit each candidate independently and return raw evidence scores and claim-level findings only; do not rank candidates.",
            "",
            "The records below are limited to identifiers cited in each candidate. If two records are shown for one numeric token, the token is not uniquely attributable unless the candidate text itself clearly identifies the intended evidence pool.",
        ]

        packet_counter = Counter()
        for row in sorted(packet_rows, key=lambda item: item["alias"]):
            source_path = Path(row["source_file"])
            if sha256_file(source_path) != row["source_file_sha256"].lower():
                raise RuntimeError(f"Source hash mismatch: {source_path}")
            # Match build_blind_packets.py exactly so legacy UTF-8 BOM handling
            # cannot change the frozen cleaned-output hash.
            final = clean_final(source_path.read_text(encoding="utf-8", errors="replace"))
            output_hash = hashlib.sha256(final.encode("utf-8")).hexdigest()
            if output_hash != row["output_sha256"].lower():
                raise RuntimeError(f"Cleaned output hash mismatch: {source_path}")

            blocks, candidate_audit_rows, counters = make_candidate_evidence(packet_id, row, final, evidence)
            audit_key_rows.extend(candidate_audit_rows)
            packet_counter.update(counters)
            aggregate.update(counters)
            candidate_occurrence_rows, occurrence_counters = make_occurrence_audit_rows(packet_id, row, final, evidence)
            occurrence_audit_rows.extend(candidate_occurrence_rows)
            packet_counter.update(occurrence_counters)
            occurrence_aggregate.update(occurrence_counters)
            parts.extend(["", f"## {row['alias']}", "", "### Candidate answer", "", final, "", "### Supplied evidence records", ""])
            parts.extend(blocks)

        packet_text = "\n".join(parts).rstrip() + "\n"
        packet_path = output_dir / f"{packet_id}.md"
        packet_path.write_text(packet_text, encoding="utf-8")
        packet_sizes[packet_id] = {
            "characters": len(packet_text),
            "approx_tokens_chars_div_4": (len(packet_text) + 3) // 4,
            **dict(packet_counter),
        }

    write_csv(output_dir / "evidence_audit_key_DO_NOT_SHARE_WITH_RATERS.csv", audit_key_rows)
    write_csv(output_dir / "citation_occurrence_audit_DO_NOT_SHARE_WITH_RATERS.csv", occurrence_audit_rows)
    expected_packets = 30
    expected_candidates = expected_packets * len(ALIASES)
    packet_files = sorted(output_dir.glob("case_*__rep_*.md"))
    passed = len(packet_files) == expected_packets and len(rows) == expected_candidates and not errors
    summary = {
        "status": "PASS" if passed else "FAIL",
        "rubric": "supplementary_evaluation_module_v1.md Pass 2",
        "source_blind_dir": str(blind_dir),
        "run_set": str(run_set),
        "expected_packets": expected_packets,
        "packets": len(packet_files),
        "expected_candidates": expected_candidates,
        "candidates": len(rows),
        "case_evidence": {
            str(case_id): {
                "knowledge_a_sha256": evidence["hash_a"],
                "knowledge_b_sha256": evidence["hash_b"],
                "knowledge_a_records": evidence["count_a"],
                "knowledge_b_records": evidence["count_b"],
                "merged_records": evidence["count_merged"],
            }
            for case_id, evidence in sorted(case_evidence.items())
        },
        "citation_summary": dict(aggregate),
        "citation_occurrence_summary": dict(occurrence_aggregate),
        "packet_size_summary": {
            "min_characters": min((item["characters"] for item in packet_sizes.values()), default=0),
            "max_characters": max((item["characters"] for item in packet_sizes.values()), default=0),
            "mean_characters": round(sum(item["characters"] for item in packet_sizes.values()) / len(packet_sizes), 1) if packet_sizes else 0,
            "max_approx_tokens_chars_div_4": max((item["approx_tokens_chars_div_4"] for item in packet_sizes.values()), default=0),
        },
        "packet_details": packet_sizes,
        "errors": errors,
    }
    (output_dir / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
