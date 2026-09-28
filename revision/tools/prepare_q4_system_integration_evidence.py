from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from corpus_size_common import atomic_write_json, render_knowledge, sha256_file, write_jsonl
from prepare_corpus_size_corpora import fetch_master


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_doi(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    return text.rstrip("/.")


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("config_id") != "q4_system_integration_v1":
        raise RuntimeError("Unexpected config_id")
    return data


def build_pool(
    *,
    revision_root: Path,
    config: dict[str, Any],
    case_id: int,
    pool: str,
    session: requests.Session,
    retries: int,
    timeout: float,
    sleep_seconds: float,
) -> dict[str, Any]:
    case = config["breadth_cases"][str(case_id)]
    pool_key = f"pool_{pool.lower()}"
    query = case[f"{pool_key}_query"]
    target = (revision_root / case[pool_key]).resolve().parent
    manifest_path = target / "pool_manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "PASS":
            return existing
        raise RuntimeError(f"Incomplete existing evidence pool requires review: {target}")
    if target.exists():
        raise RuntimeError(f"Refusing to replace existing evidence directory: {target}")

    staging = target.with_name(target.name + f"_staging_{uuid.uuid4().hex[:8]}")
    staging.mkdir(parents=True, exist_ok=False)
    log_path = staging / "retrieval_log.jsonl"
    retrieved_at = utc_now()
    retrieval_id = f"q4_case_{case_id:02d}_pool_{pool}_{retrieved_at}"
    try:
        raw, stats = fetch_master(
            session=session,
            endpoint=str(config["retrieval"]["endpoint"]),
            query=query,
            master_size=int(config["retrieval"]["master_fetch_size_before_exclusion"]),
            per_page=int(config["retrieval"]["per_page"]),
            retries=retries,
            timeout=timeout,
            sleep_seconds=sleep_seconds,
            log_path=log_path,
        )
        target_doi = normalize_doi(case["target_doi"])
        target_title = normalize_title(case["target_title"])
        retained: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for row in raw:
            doi_match = bool(target_doi and normalize_doi(row.get("doi", "")) == target_doi)
            title_match = bool(target_title and normalize_title(row.get("title", "")) == target_title)
            if doi_match or title_match:
                excluded.append(
                    {
                        "openalex_id": row.get("openalex_id"),
                        "doi_match": doi_match,
                        "title_match": title_match,
                    }
                )
            else:
                retained.append(row)

        selected_n = int(config["retrieval"]["selected_top_n_after_exclusion"])
        if len(retained) < selected_n:
            raise RuntimeError(
                f"Only {len(retained)} records remain after target exclusion for case {case_id} pool {pool}; "
                f"required {selected_n}."
            )
        selected = retained[:selected_n]
        for rank, row in enumerate(selected, start=1):
            row["rank"] = rank

        filtered_master = staging / "master_after_target_exclusion.jsonl"
        selected_jsonl = staging / "selected_top_0500.jsonl"
        write_jsonl(filtered_master, retained)
        write_jsonl(selected_jsonl, selected)
        knowledge = render_knowledge(
            selected,
            keyword=str(query["keyword"]),
            start_year=int(query["start_year"]),
            end_year=int(query["end_year"]),
            master_size=len(raw),
            selected_size=selected_n,
            retrieved_at=retrieved_at,
            retrieval_id=retrieval_id,
        )
        knowledge_path = staging / "knowledge_top_0500.txt"
        knowledge_path.write_text(knowledge, encoding="utf-8")
        manifest = {
            "status": "PASS",
            "case_id": case_id,
            "pool": pool,
            "retrieval_id": retrieval_id,
            "retrieved_at_utc": retrieved_at,
            "query": query,
            "target_exclusion": {
                "normalized_doi": target_doi,
                "normalized_title_sha256_only": True,
                "target_title_sha256": __import__("hashlib").sha256(target_title.encode("utf-8")).hexdigest(),
                "excluded_count": len(excluded),
                "excluded_matches": excluded,
                "target_present_after_exclusion": False,
            },
            "retrieval_stats": stats,
            "raw_usable_records": len(raw),
            "retained_after_exclusion": len(retained),
            "selected_records": len(selected),
            "artifacts": {
                "knowledge": {
                    "path": knowledge_path.name,
                    "records": selected_n,
                    "bytes": knowledge_path.stat().st_size,
                    "characters": len(knowledge),
                    "sha256": sha256_file(knowledge_path),
                },
                "filtered_master": {
                    "path": filtered_master.name,
                    "records": len(retained),
                    "sha256": sha256_file(filtered_master),
                },
                "selected_jsonl": {
                    "path": selected_jsonl.name,
                    "records": len(selected),
                    "sha256": sha256_file(selected_jsonl),
                },
            },
            "api_key_recorded": False,
        }
        atomic_write_json(staging / "pool_manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(target)
        return manifest
    except Exception as exc:
        atomic_write_json(
            staging / "failure_manifest.json",
            {
                "status": "FAILED",
                "failed_at_utc": utc_now(),
                "case_id": case_id,
                "pool": pool,
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
            },
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare target-excluded OpenAlex evidence for Reviewer 1 Q4")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case", type=int, action="append")
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    parser.add_argument("--request-retries", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()

    revision_root = Path(__file__).resolve().parents[1]
    config_path = (args.config or revision_root / "config" / "q4_system_integration_v1.json").resolve()
    config = load_config(config_path)
    selected_ids = sorted(int(value) for value in config["breadth_cases"])
    if args.case:
        requested = set(args.case)
        unknown = sorted(requested - set(selected_ids))
        if unknown:
            raise SystemExit(f"Unknown case ids: {unknown}")
        selected_ids = [case_id for case_id in selected_ids if case_id in requested]

    plan = {
        "config_id": config["config_id"],
        "dry_run": not args.execute,
        "selected_cases": selected_ids,
        "planned_pools": len(selected_ids) * 2,
        "raw_records_per_pool": config["retrieval"]["master_fetch_size_before_exclusion"],
        "selected_records_per_pool": config["retrieval"]["selected_top_n_after_exclusion"],
        "api_calls_made": 0,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    manifests: list[dict[str, Any]] = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "mpds-revision-q4-evidence/1.0"})
        for case_id in selected_ids:
            for pool in ("A", "B"):
                manifests.append(
                    build_pool(
                        revision_root=revision_root,
                        config=config,
                        case_id=case_id,
                        pool=pool,
                        session=session,
                        retries=args.request_retries,
                        timeout=args.timeout_seconds,
                        sleep_seconds=args.sleep_seconds,
                    )
                )
                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)

    summary_path = revision_root / "q4_system_integration_inputs_v1" / "evidence" / "retrieval_summary.json"
    atomic_write_json(
        summary_path,
        {
            "status": "PASS",
            "config_id": config["config_id"],
            "completed_utc": utc_now(),
            "pool_count": len(manifests),
            "target_matches_excluded": sum(
                int(item["target_exclusion"]["excluded_count"]) for item in manifests
            ),
            "api_key_recorded": False,
            "pools": [
                {
                    "case_id": item["case_id"],
                    "pool": item["pool"],
                    "selected_records": item["selected_records"],
                    "knowledge_sha256": item["artifacts"]["knowledge"]["sha256"],
                }
                for item in manifests
            ],
        },
    )
    print(
        json.dumps(
            {
                "status": "PASS",
                "prepared_pools": len(manifests),
                "summary": str(summary_path),
                "target_matches_excluded": sum(
                    int(item["target_exclusion"]["excluded_count"]) for item in manifests
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
