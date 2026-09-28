from __future__ import annotations

import argparse
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from corpus_size_common import (
    append_jsonl,
    atomic_write_json,
    case_map,
    environment_value,
    load_config,
    normalize_work,
    pool_dir,
    render_knowledge,
    sha256_file,
    write_jsonl,
)


SELECT_FIELDS = (
    "id,title,display_name,publication_year,type,cited_by_count,doi,"
    "authorships,primary_location,abstract_inverted_index,relevance_score"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build one ranked OpenAlex top-1000 master per pool and exact nested top-N snapshots")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--execute", action="store_true", help="Call OpenAlex and write frozen corpus artifacts; default is dry-run")
    parser.add_argument("--case", type=int, action="append")
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--request-retries", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    return parser.parse_args()


def get_page(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any],
    *,
    retries: int,
    timeout: float,
    log_path: Path,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        started = time.perf_counter()
        try:
            response = session.get(endpoint, params=params, timeout=timeout)
            elapsed = round(time.perf_counter() - started, 6)
            append_jsonl(
                log_path,
                {
                    "event": "openalex_request",
                    "attempt": attempt,
                    "timestamp_utc": utc_now(),
                    "status_code": response.status_code,
                    "elapsed_seconds": elapsed,
                    "result_count": len((response.json() or {}).get("results", [])) if response.status_code == 200 else None,
                    "rate_limit_remaining": response.headers.get("X-RateLimit-Remaining"),
                    "rate_limit_credits_used": response.headers.get("X-RateLimit-Credits-Used"),
                },
            )
            if response.status_code == 200:
                return response
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
            last_error = RuntimeError(f"OpenAlex HTTP {response.status_code}: {response.text[:500]}")
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            append_jsonl(
                log_path,
                {
                    "event": "openalex_request_error",
                    "attempt": attempt,
                    "timestamp_utc": utc_now(),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:1000],
                },
            )
        if attempt < retries:
            time.sleep(min(30.0, 2.0**attempt))
    raise RuntimeError(f"OpenAlex request failed after {retries} attempts: {last_error}")


def fetch_master(
    *,
    session: requests.Session,
    endpoint: str,
    query: dict[str, Any],
    master_size: int,
    per_page: int,
    retries: int,
    timeout: float,
    sleep_seconds: float,
    log_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cursor = "*"
    papers: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    pages = 0
    received = 0
    skipped_no_abstract = 0
    duplicate_ids = 0
    meta_count: int | None = None
    filter_value = (
        "has_abstract:true,"
        f"from_publication_date:{int(query['start_year'])}-01-01,"
        f"to_publication_date:{int(query['end_year'])}-12-31"
    )

    while len(papers) < master_size:
        params: dict[str, Any] = {
            "search": query["keyword"],
            "filter": filter_value,
            "per_page": per_page,
            "cursor": cursor,
            "select": SELECT_FIELDS,
        }
        api_key = environment_value("OPENALEX_API_KEY")
        mailto = environment_value("OPENALEX_MAILTO")
        if api_key:
            params["api_key"] = api_key
        if mailto:
            params["mailto"] = mailto
        response = get_page(
            session,
            endpoint,
            params,
            retries=retries,
            timeout=timeout,
            log_path=log_path,
        )
        payload = response.json()
        pages += 1
        meta = payload.get("meta") or {}
        if meta_count is None and isinstance(meta.get("count"), int):
            meta_count = int(meta["count"])
        results = payload.get("results") or []
        if not results:
            break
        for item in results:
            received += 1
            openalex_id = str(item.get("id") or "").strip()
            if not openalex_id:
                continue
            if openalex_id in seen_ids:
                duplicate_ids += 1
                continue
            normalized = normalize_work(item, rank=len(papers) + 1)
            if normalized is None:
                skipped_no_abstract += 1
                continue
            seen_ids.add(openalex_id)
            papers.append(normalized)
            if len(papers) >= master_size:
                break
        cursor = meta.get("next_cursor")
        if not cursor:
            break
        if sleep_seconds:
            time.sleep(sleep_seconds)

    if len(papers) != master_size:
        raise RuntimeError(
            f"Query '{query['keyword']}' yielded only {len(papers)} usable unique papers; required {master_size}. "
            f"OpenAlex meta count was {meta_count}."
        )
    return papers, {
        "openalex_meta_count": meta_count,
        "pages_fetched": pages,
        "records_received": received,
        "skipped_no_abstract": skipped_no_abstract,
        "duplicate_openalex_ids_skipped": duplicate_ids,
    }


def build_pool(
    *,
    input_root: Path,
    case_id: int,
    pool: str,
    query: dict[str, Any],
    corpus_sizes: list[int],
    retrieval_config: dict[str, Any],
    session: requests.Session,
    retries: int,
    timeout: float,
    sleep_seconds: float,
) -> dict[str, Any]:
    target = pool_dir(input_root, case_id, pool)
    if target.exists():
        manifest_path = target / "pool_manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("status") == "PASS":
                return existing
        raise RuntimeError(f"Refusing to replace existing incomplete pool directory: {target}")

    staging = target.with_name(target.name + f"_staging_{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True, exist_ok=False)
    retrieval_log = staging / "retrieval_log.jsonl"
    retrieved_at = utc_now()
    retrieval_id = f"case_{case_id:02d}_pool_{pool}_{retrieved_at}"
    try:
        papers, retrieval_stats = fetch_master(
            session=session,
            endpoint=retrieval_config["endpoint"],
            query=query,
            master_size=int(retrieval_config["master_size_per_pool"]),
            per_page=int(retrieval_config["per_page"]),
            retries=retries,
            timeout=timeout,
            sleep_seconds=sleep_seconds,
            log_path=retrieval_log,
        )
        master_jsonl = staging / "master_top_1000.jsonl"
        write_jsonl(master_jsonl, papers)
        artifacts: dict[str, Any] = {
            "master_jsonl": {
                "path": master_jsonl.name,
                "sha256": sha256_file(master_jsonl),
                "bytes": master_jsonl.stat().st_size,
                "records": len(papers),
            }
        }
        for size in corpus_sizes:
            selected = papers[:size]
            text = render_knowledge(
                selected,
                keyword=str(query["keyword"]),
                start_year=int(query["start_year"]),
                end_year=int(query["end_year"]),
                master_size=len(papers),
                selected_size=size,
                retrieved_at=retrieved_at,
                retrieval_id=retrieval_id,
            )
            path = staging / f"knowledge_top_{size:04d}.txt"
            path.write_text(text, encoding="utf-8")
            artifacts[f"top_{size}"] = {
                "path": path.name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "characters": len(text),
                "records": size,
                "first_openalex_id": selected[0]["openalex_id"],
                "last_openalex_id": selected[-1]["openalex_id"],
            }
        manifest = {
            "status": "PASS",
            "retrieval_id": retrieval_id,
            "retrieved_at_utc": retrieved_at,
            "case_id": case_id,
            "pool": pool,
            "query": query,
            "endpoint": retrieval_config["endpoint"],
            "filter": "has_abstract:true plus query start/end date",
            "ranking": retrieval_config["ranking"],
            "pagination": retrieval_config["pagination"],
            "per_page": retrieval_config["per_page"],
            "api_key_used": bool(environment_value("OPENALEX_API_KEY")),
            "api_key_recorded": False,
            "mailto_used": bool(environment_value("OPENALEX_MAILTO")),
            "nested_prefix_rule": retrieval_config["nested_rule"],
            "retrieval_stats": retrieval_stats,
            "artifacts": artifacts,
        }
        atomic_write_json(staging / "pool_manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(target)
        return manifest
    except Exception:
        failure = {
            "status": "FAILED",
            "failed_at_utc": utc_now(),
            "case_id": case_id,
            "pool": pool,
            "query": query,
        }
        atomic_write_json(staging / "failure_manifest.json", failure)
        raise


def main() -> int:
    args = parse_args()
    if not 0 <= args.sleep_seconds <= 10:
        raise SystemExit("--sleep-seconds must be between 0 and 10")
    if args.request_retries < 1:
        raise SystemExit("--request-retries must be positive")
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    cases = case_map(config)
    selected_ids = list(config["design"]["selected_case_ids"])
    if args.case:
        requested = set(args.case)
        unknown = requested - set(selected_ids)
        if unknown:
            raise SystemExit(f"Cases not in frozen design: {sorted(unknown)}")
        selected_ids = [case_id for case_id in selected_ids if case_id in requested]
    corpus_sizes = [int(value) for value in config["design"]["corpus_sizes"]]
    retrieval = config["retrieval"]
    input_root = revision_root / retrieval["input_root"]
    query_rows = []
    for case_id in selected_ids:
        for pool in ("A", "B"):
            query_rows.append({"case_id": case_id, "pool": pool, **cases[case_id][f"pool_{pool.lower()}"]})
    plan = {
        "dry_run": not args.execute,
        "config": str(config_path),
        "config_id": config["config_id"],
        "input_root": str(input_root),
        "selected_case_ids": selected_ids,
        "queries": query_rows,
        "master_size_per_pool": retrieval["master_size_per_pool"],
        "corpus_sizes": corpus_sizes,
        "expected_openalex_requests_at_full_pages": len(query_rows)
        * ((int(retrieval["master_size_per_pool"]) + int(retrieval["per_page"]) - 1) // int(retrieval["per_page"])),
        "openalex_api_key_configured": bool(environment_value("OPENALEX_API_KEY")),
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    input_root.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": "mpds-corpus-size-sensitivity/1.0"})
    manifests = []
    for row in query_rows:
        manifests.append(
            build_pool(
                input_root=input_root,
                case_id=int(row["case_id"]),
                pool=str(row["pool"]),
                query={key: row[key] for key in ("keyword", "start_year", "end_year")},
                corpus_sizes=corpus_sizes,
                retrieval_config=retrieval,
                session=session,
                retries=args.request_retries,
                timeout=args.timeout_seconds,
                sleep_seconds=args.sleep_seconds,
            )
        )
    root_manifest = {
        "status": "PASS",
        "created_utc": utc_now(),
        "config": str(config_path),
        "config_sha256": sha256_file(config_path),
        "selected_case_ids": selected_ids,
        "pool_count": len(manifests),
        "all_nested_prefixes_require_validation": True,
        "pool_manifests": [
            {
                "case_id": item["case_id"],
                "pool": item["pool"],
                "retrieval_id": item["retrieval_id"],
                "path": str(pool_dir(input_root, int(item["case_id"]), str(item["pool"])) / "pool_manifest.json"),
            }
            for item in manifests
        ],
    }
    atomic_write_json(input_root / "retrieval_manifest.json", root_manifest)
    print(json.dumps(root_manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
