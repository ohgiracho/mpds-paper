from __future__ import annotations

import argparse
import re
from pathlib import Path


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def normalize_title(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z]+", " ", (text or "").lower())).strip()


def parse_knowledge_text(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    field_order = ["ID", "Type", "Title", "Year", "FirstAuthor", "Venue", "Citations", "DOI", "OpenAlexID", "Abstract"]
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("ID:"):
            if current:
                entries.append(current)
            current = {key: "" for key in field_order}
            current["ID"] = stripped.split(":", 1)[1].strip()
            continue
        if current is None:
            continue
        matched = False
        for key in field_order[1:]:
            prefix = f"{{key}}:"
            if stripped.startswith(prefix):
                current[key] = stripped.split(":", 1)[1].strip()
                matched = True
                break
        if matched:
            continue
        if stripped and set(stripped) == {{"-"}}:
            entries.append(current)
            current = None
            continue
        if current is not None and stripped:
            current["Abstract"] = (current.get("Abstract", "") + " " + stripped).strip()
    if current:
        entries.append(current)
    return entries


def dedupe_key(entry: dict[str, str]) -> tuple[str, str]:
    doi = entry.get("DOI", "").strip()
    if doi and doi.upper() != "N/A":
        return ("doi", doi.lower())
    openalex = entry.get("OpenAlexID", "").strip()
    if openalex and openalex.upper() != "N/A":
        return ("openalex", openalex.lower())
    return ("title_year", f"{{normalize_title(entry.get('Title', ''))}}||{{entry.get('Year', '').strip()}}")


def merge_knowledge_texts(source_a_name: str, source_b_name: str, text_a: str, text_b: str) -> str:
    entries_a = parse_knowledge_text(text_a)
    entries_b = parse_knowledge_text(text_b)
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries_a + entries_b:
        key = dedupe_key(entry)
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    lines = [
        f"SYSTEM_PROMPT_CONTEXT: This merged knowledge base contains {{len(merged)}} deduplicated papers from two source snapshots.",
        "MERGE_REPRODUCIBILITY:",
        f"source_a_file: {{source_a_name}}",
        f"source_b_file: {{source_b_name}}",
        "merge_rule: doi_then_openalex_then_title_year",
        "============================================================",
        "",
    ]
    field_order = ["Type", "Title", "Year", "FirstAuthor", "Venue", "Citations", "DOI", "OpenAlexID", "Abstract"]
    for i, entry in enumerate(merged, start=1):
        lines.append(f"ID: {{i}}")
        for key in field_order:
            lines.append(f"{{key}}: {{entry.get(key, '').strip() or 'N/A'}}")
        lines.append("--------------------------------------------------")
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--knowledge-a", required=True)
    parser.add_argument("--knowledge-b", required=True)
    parser.add_argument("--output-file", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path_a = Path(args.knowledge_a)
    path_b = Path(args.knowledge_b)
    text_a = read_text(path_a)
    text_b = read_text(path_b)
    merged = merge_knowledge_texts(path_a.name, path_b.name, text_a, text_b)
    Path(args.output_file).write_text(merged, encoding="utf-8")
    print(f"[DONE] {{args.output_file}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
