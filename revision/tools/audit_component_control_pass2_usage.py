from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit all recorded component-control Pass 2 calls")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--results-dir", type=Path, required=True)
    args = parser.parse_args()

    run_root = args.run_root.resolve()
    results = args.results_dir.resolve()
    assembly = json.loads((results / "assembly_manifest.json").read_text(encoding="utf-8"))
    selected = Counter(
        {
            field: int(assembly["selected_new_sair_ses_usage"].get(field, 0))
            for field in USAGE_FIELDS
        }
    )

    all_usage: Counter[str] = Counter()
    response_files = sorted(run_root.rglob("candidate_*_response.json"))
    max_token_stops = 0
    approximate_call_seconds = 0.0
    paired_artifact_times = 0
    for response_path in response_files:
        envelope = json.loads(response_path.read_text(encoding="utf-8"))
        usage = envelope.get("usage")
        if not isinstance(usage, dict):
            raise RuntimeError(f"Missing usage object: {response_path}")
        for field in USAGE_FIELDS:
            all_usage[field] += int(usage.get(field) or 0)
        max_token_stops += envelope.get("stop_reason") == "max_tokens"
        request_path = response_path.with_name(
            response_path.name.replace("_response.json", "_request_payload.json")
        )
        if request_path.exists():
            approximate_call_seconds += max(
                0.0, response_path.stat().st_mtime - request_path.stat().st_mtime
            )
            paired_artifact_times += 1

    manifests = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(run_root.rglob("run_manifest.json"))
    ]
    if len(manifests) != 30 or any(item.get("status") != "COMPLETE" for item in manifests):
        raise RuntimeError("Expected 30 COMPLETE manifests")
    validation_errors = sum(len(item.get("validation_errors", [])) for item in manifests)
    recorded_manifest_elapsed = sum(
        float(request.get("elapsed_seconds") or 0.0)
        for manifest in manifests
        for request in manifest.get("candidate_requests", [])
    )

    audit = {
        "status": "PASS",
        "packets_complete": len(manifests),
        "selected_candidate_results": 60,
        "actual_http_200_calls": len(response_files),
        "overhead_calls": len(response_files) - 60,
        "max_token_stops": max_token_stops,
        "final_validation_errors": validation_errors,
        "selected_accepted_usage": dict(selected),
        "all_http_200_usage_including_failed_max_token_attempt": dict(all_usage),
        "overhead_usage": {
            field: all_usage[field] - selected[field] for field in USAGE_FIELDS
        },
        "recorded_elapsed_seconds_in_final_manifests": round(recorded_manifest_elapsed, 3),
        "artifact_timestamp_call_seconds_approx": round(approximate_call_seconds, 3),
        "artifact_timestamp_pairs": paired_artifact_times,
        "runtime_note": (
            "Artifact timestamp duration is an approximate sum from request-payload write to "
            "response write. Final manifests retain selected calls; the discarded max-token "
            "attempt remains as a separate response artifact."
        ),
        "billing_note": "Provider invoice is authoritative; no price assumption is applied here.",
    }
    (results / "api_usage_audit_new_sair_ses.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
