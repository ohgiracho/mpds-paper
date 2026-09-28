from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


DEFAULT_CONFIG_NAME = "corpus_size_sensitivity_v1.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def load_config(revision_root: Path, config_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    resolved = (config_path or revision_root / "config" / DEFAULT_CONFIG_NAME).resolve()
    return resolved, read_json(resolved)


def case_map(config: dict[str, Any]) -> dict[int, dict[str, Any]]:
    selected = config["case_selection_rule"]["selected_cases"]
    return {int(item["case_id"]): item for item in selected}


def pool_dir(input_root: Path, case_id: int, pool: str) -> Path:
    return input_root / f"case_{case_id:02d}" / f"pool_{pool.upper()}"


def selected_knowledge_path(input_root: Path, case_id: int, pool: str, corpus_size: int) -> Path:
    return pool_dir(input_root, case_id, pool) / f"knowledge_top_{corpus_size:04d}.txt"


def pool_manifest_path(input_root: Path, case_id: int, pool: str) -> Path:
    return pool_dir(input_root, case_id, pool) / "pool_manifest.json"


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    populated = [indices for indices in inverted_index.values() if indices]
    if not populated:
        return None
    try:
        words = [""] * (max(max(indices) for indices in populated) + 1)
        for word, indices in inverted_index.items():
            for index in indices:
                words[index] = word
        text = " ".join(words).strip()
        return text if len(text) >= 10 else None
    except (TypeError, ValueError, IndexError):
        return None


def classify_paper_type(item: dict[str, Any]) -> str:
    title = (item.get("title") or item.get("display_name") or "").lower()
    item_type = (item.get("type") or "").lower()
    review_tokens = ("review", "perspective", "roadmap", "outlook", "status", "future", "challenge")
    if item_type == "review" or any(token in title for token in review_tokens):
        return "[REVIEW/PERSPECTIVE]"
    return "[RESEARCH ARTICLE]"


def extract_first_author(item: dict[str, Any]) -> str:
    authorships = item.get("authorships") or []
    if authorships:
        author = (authorships[0].get("author") or {}).get("display_name")
        if author:
            return str(author)
    return "N/A"


def extract_venue(item: dict[str, Any]) -> str:
    primary_source = ((item.get("primary_location") or {}).get("source") or {}).get("display_name")
    return str(primary_source or "N/A")


def normalize_work(item: dict[str, Any], rank: int) -> dict[str, Any] | None:
    abstract = reconstruct_abstract(item.get("abstract_inverted_index"))
    openalex_id = str(item.get("id") or "").strip()
    if not abstract or not openalex_id:
        return None
    return {
        "rank": rank,
        "type": classify_paper_type(item),
        "title": item.get("title") or item.get("display_name") or "N/A",
        "year": item.get("publication_year") or "N/A",
        "first_author": extract_first_author(item),
        "venue": extract_venue(item),
        "citations": item.get("cited_by_count") or 0,
        "doi": item.get("doi") or "N/A",
        "openalex_id": openalex_id,
        "relevance_score": item.get("relevance_score"),
        "abstract": abstract,
    }


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError(f"Invalid JSONL object at {path}:{line_number}")
            rows.append(item)
    return rows


def render_knowledge(
    papers: list[dict[str, Any]],
    *,
    keyword: str,
    start_year: int,
    end_year: int,
    master_size: int,
    selected_size: int,
    retrieved_at: str,
    retrieval_id: str,
) -> str:
    lines = [
        f"SYSTEM_PROMPT_CONTEXT: This knowledge base contains {len(papers)} papers on '{keyword}'.",
        f"Period: {start_year} to {end_year}",
        "REPRODUCIBILITY:",
        "provider: OpenAlex Works API",
        f"keyword: {keyword}",
        f"start_year: {start_year}",
        f"end_year: {end_year}",
        f"master_size: {master_size}",
        f"selected_top_n: {selected_size}",
        "ranking: default search relevance_score descending",
        "pagination: cursor",
        f"retrieved_at: {retrieved_at}",
        f"retrieval_id: {retrieval_id}",
        "=" * 60,
        "",
    ]
    for paper_id, paper in enumerate(papers, start=1):
        lines.extend(
            [
                f"ID: {paper_id}",
                f"Type: {paper['type']}",
                f"Title: {paper['title']}",
                f"Year: {paper['year']}",
                f"FirstAuthor: {paper['first_author']}",
                f"Venue: {paper['venue']}",
                f"Citations: {paper['citations']}",
                f"DOI: {paper['doi']}",
                f"OpenAlexID: {paper['openalex_id']}",
                f"Abstract: {paper['abstract']}",
                "-" * 50,
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def count_knowledge_records(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("ID:") and line[3:].strip().isdigit():
                count += 1
    return count


def read_knowledge_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def environment_value(name: str) -> str:
    value = (os.getenv(name) or "").strip().strip("\"'")
    if value or os.name != "nt":
        return value
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            stored, _ = winreg.QueryValueEx(key, name)
        return str(stored or "").strip().strip("\"'")
    except (FileNotFoundError, OSError, ImportError):
        return ""


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
