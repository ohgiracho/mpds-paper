from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_KEYWORD = ""  # TODO: set keyword
DEFAULT_END_YEAR = 2025  # TODO: set end year
DEFAULT_START_YEAR = DEFAULT_END_YEAR - 9  # rolling 10-year window
DEFAULT_MAX_PAPERS = 500


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    try:
        max_idx = max(max(indices) for indices in inverted_index.values() if indices)
        words = [""] * (max_idx + 1)
        for word, indices in inverted_index.items():
            for idx in indices:
                words[idx] = word
        text = " ".join(words).strip()
        return text if len(text) >= 10 else None
    except Exception:
        return None


def classify_paper_type(item: dict[str, Any]) -> str:
    title = (item.get("title") or "").lower()
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
            return author
    return "N/A"


def extract_venue(item: dict[str, Any]) -> str:
    primary_source = ((item.get("primary_location") or {}).get("source") or {}).get("display_name")
    if primary_source:
        return primary_source
    host_venue = (item.get("host_venue") or {}).get("display_name")
    if host_venue:
        return host_venue
    return "N/A"


def fetch_papers(
    keyword: str,
    start_year: int,
    end_year: int,
    max_papers: int,
    sort_by: str,
    per_page: int,
    sleep_sec: float,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    papers: list[dict[str, Any]] = []
    page = 1
    pages_fetched = 0
    total_seen = 0
    skipped_no_abstract = 0
    works_url = "https://api.openalex.org/works"
    filter_param = (
        "has_abstract:true,"
        f"from_publication_date:{start_year}-01-01,"
        f"to_publication_date:{end_year}-12-31"
    )

    print("[START] OpenAlex download started.")
    print(
        f"[CONFIG] keyword='{keyword}', years={start_year}-{end_year}, "
        f"target={max_papers}, sort='{sort_by}', per_page={per_page}"
    )

    while len(papers) < max_papers:
        print(f"[PAGE {page}] Requesting records... collected={len(papers)}/{max_papers}")
        params = {
            "search": keyword,
            "filter": filter_param,
            "per_page": per_page,
            "page": page,
        }
        if sort_by and sort_by != "relevance":
            params["sort"] = sort_by

        response = requests.get(works_url, params=params, timeout=30)
        if response.status_code != 200:
            raise RuntimeError(f"OpenAlex request failed: {response.status_code}")

        payload = response.json()
        pages_fetched += 1
        results = payload.get("results", [])
        if not results:
            print(f"[PAGE {page}] No more results from API. Stopping.")
            break

        accepted_this_page = 0
        skipped_this_page = 0
        for item in results:
            if len(papers) >= max_papers:
                break
            total_seen += 1
            abstract = reconstruct_abstract(item.get("abstract_inverted_index"))
            if not abstract:
                skipped_no_abstract += 1
                skipped_this_page += 1
                continue
            papers.append(
                {
                    "type": classify_paper_type(item),
                    "title": item.get("title") or "N/A",
                    "year": item.get("publication_year") or "N/A",
                    "first_author": extract_first_author(item),
                    "venue": extract_venue(item),
                    "citations": item.get("cited_by_count") or 0,
                    "doi": item.get("doi") or "N/A",
                    "openalex_id": item.get("id") or "N/A",
                    "abstract": abstract,
                }
            )
            accepted_this_page += 1

        print(
            f"[PAGE {page}] received={len(results)}, accepted={accepted_this_page}, "
            f"skipped_no_abstract={skipped_this_page}, collected={len(papers)}/{max_papers}"
        )
        page += 1
        time.sleep(sleep_sec)

    stats = {
        "pages_fetched": pages_fetched,
        "total_seen": total_seen,
        "skipped_no_abstract": skipped_no_abstract,
    }
    print(
        f"[SUMMARY] pages={pages_fetched}, seen={total_seen}, "
        f"skipped_no_abstract={skipped_no_abstract}, final_count={len(papers)}"
    )
    return papers, stats


def safe_name(text: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text).strip("_")


def write_output(
    output_dir: Path,
    keyword: str,
    start_year: int,
    end_year: int,
    max_papers: int,
    sort_by: str,
    per_page: int,
    retrieved_at: str,
    papers: list[dict[str, Any]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"Topic_{safe_name(keyword)}_{start_year}-{end_year}_Knowledge.txt"
    output_path = output_dir / filename
    with output_path.open("w", encoding="utf-8") as f:
        f.write(
            f"SYSTEM_PROMPT_CONTEXT: This knowledge base contains {len(papers)} papers on '{keyword}'.\n"
            f"Period: {start_year} to {end_year}\n"
            "REPRODUCIBILITY:\n"
            f"keyword: {keyword}\n"
            f"start_year: {start_year}\n"
            f"end_year: {end_year}\n"
            f"max_papers: {max_papers}\n"
            f"sort_by: {sort_by}\n"
            f"per_page: {per_page}\n"
            f"retrieved_at: {retrieved_at}\n"
            "============================================================\n\n"
        )
        for idx, paper in enumerate(papers, start=1):
            f.write(f"ID: {idx}\n")
            f.write(f"Type: {paper['type']}\n")
            f.write(f"Title: {paper['title']}\n")
            f.write(f"Year: {paper['year']}\n")
            f.write(f"FirstAuthor: {paper['first_author']}\n")
            f.write(f"Venue: {paper['venue']}\n")
            f.write(f"Citations: {paper['citations']}\n")
            f.write(f"DOI: {paper['doi']}\n")
            f.write(f"OpenAlexID: {paper['openalex_id']}\n")
            f.write(f"Abstract: {paper['abstract']}\n")
            f.write("-" * 50 + "\n")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keyword", default=DEFAULT_KEYWORD)
    parser.add_argument("--start-year", type=int, default=None)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--max-papers", type=int, default=DEFAULT_MAX_PAPERS)
    parser.add_argument("--sort-by", default="relevance")
    parser.add_argument("--per-page", type=int, default=100)
    parser.add_argument("--sleep-sec", type=float, default=0.4)
    parser.add_argument("--output-dir", default=".")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keyword = args.keyword.strip()
    if not keyword:
        raise SystemExit("Set --keyword or edit DEFAULT_KEYWORD.")
    start_year = args.start_year if args.start_year is not None else args.end_year - 9
    if start_year > args.end_year:
        raise SystemExit("start_year must be <= end_year.")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    papers, stats = fetch_papers(
        keyword=keyword,
        start_year=start_year,
        end_year=args.end_year,
        max_papers=args.max_papers,
        sort_by=args.sort_by,
        per_page=args.per_page,
        sleep_sec=args.sleep_sec,
    )
    output = write_output(
        output_dir=Path(args.output_dir),
        keyword=keyword,
        start_year=start_year,
        end_year=args.end_year,
        max_papers=args.max_papers,
        sort_by=args.sort_by,
        per_page=args.per_page,
        retrieved_at=retrieved_at,
        papers=papers,
    )
    print(f"[DONE] {output}")
    print(f"[COUNT] {len(papers)}")
    print(
        f"[STATS] pages={stats['pages_fetched']}, seen={stats['total_seen']}, "
        f"skipped_no_abstract={stats['skipped_no_abstract']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


