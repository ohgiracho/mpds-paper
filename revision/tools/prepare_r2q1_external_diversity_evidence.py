from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

from corpus_size_common import atomic_write_json
from prepare_q4_system_integration_evidence import build_pool


REVISION_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REVISION_ROOT / "config" / "r2q1_external_diversity_v1.json"


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("config_id") != "r2q1_external_diversity_v1":
        raise RuntimeError("Unexpected config_id")
    if data.get("status") not in {
        "INPUTS_FROZEN_EVIDENCE_PENDING",
        "INPUTS_AND_EVIDENCE_FROZEN_READY_FOR_PREFLIGHT",
    }:
        raise RuntimeError("Unexpected R2 Q1 configuration status")
    # The Q4 retrieval implementation is intentionally reused unchanged.
    data["breadth_cases"] = data["cases"]
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare target-excluded OpenAlex evidence for Reviewer 2 Q1")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--case", type=int, action="append")
    parser.add_argument("--sleep-seconds", type=float, default=0.3)
    parser.add_argument("--request-retries", type=int, default=6)
    parser.add_argument("--timeout-seconds", type=float, default=45.0)
    args = parser.parse_args()
    config = load_config(args.config.resolve())
    case_ids = sorted(int(key) for key in config["cases"])
    if args.case:
        requested = set(args.case)
        unknown = requested - set(case_ids)
        if unknown:
            raise SystemExit(f"Unknown case ids: {sorted(unknown)}")
        case_ids = [case_id for case_id in case_ids if case_id in requested]
    plan = {
        "config_id": config["config_id"],
        "dry_run": not args.execute,
        "selected_cases": case_ids,
        "planned_pools": len(case_ids) * 2,
        "raw_records_per_pool": config["retrieval"]["master_fetch_size_before_exclusion"],
        "selected_records_per_pool": config["retrieval"]["selected_top_n_after_exclusion"],
        "api_calls_made": 0,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    manifests = []
    with requests.Session() as session:
        session.headers.update({"User-Agent": "mpds-revision-r2q1-evidence/1.0"})
        for case_id in case_ids:
            for pool in ("A", "B"):
                manifests.append(
                    build_pool(
                        revision_root=REVISION_ROOT,
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
    summary_path = REVISION_ROOT / "r2q1_external_diversity_inputs_v1" / "evidence" / "retrieval_summary.json"
    atomic_write_json(
        summary_path,
        {
            "status": "PASS",
            "config_id": config["config_id"],
            "pool_count": len(manifests),
            "target_matches_excluded": sum(int(x["target_exclusion"]["excluded_count"]) for x in manifests),
            "api_key_recorded": False,
            "pools": [
                {
                    "case_id": x["case_id"],
                    "pool": x["pool"],
                    "selected_records": x["selected_records"],
                    "knowledge_sha256": x["artifacts"]["knowledge"]["sha256"],
                }
                for x in manifests
            ],
        },
    )
    print(json.dumps({"status": "PASS", "pool_count": len(manifests), "summary": str(summary_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
