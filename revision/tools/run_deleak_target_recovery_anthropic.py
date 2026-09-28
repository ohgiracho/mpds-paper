from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from run_independent_judge_anthropic_v3 import extract_tool_input, resolve_environment, sha256_file


CONFIG_ID = "deleak_target_recovery_sonnet5_v1"
ENDPOINT = "https://api.anthropic.com/v1/messages"
LABELS = {"absent", "partial_general", "explicit_target_like"}
FEATURES = {
    1: ("surface_lpscl_contact", "interstitial_lpscl_network", "combined_dual_allocation"),
    8: ("hollow_cube_like_unit", "porous_or_permeable_wall", "graphene_network_integration", "combined_cube_wall_graphene_architecture"),
    22: ("one_dimensional_nio_body", "nested_inner_outer_tubes", "internal_void_as_strain_buffer"),
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_frozen(root: Path) -> None:
    manifest = read_json(root / "evaluation" / "deleak_target_recovery_input_integrity_manifest_v1.json")
    if manifest.get("status") != "FROZEN_BEFORE_ANY_DELEAK_RECOVERY_API_CALL":
        raise RuntimeError("Target-recovery inputs are not frozen")
    for group in ("fixed_files", "packets"):
        for record in manifest[group]:
            path = (root / record["path"]).resolve()
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                raise RuntimeError(f"Frozen recovery input mismatch: {path}")


def packet_content(packet: Path) -> tuple[int, str]:
    text = packet.read_text(encoding="utf-8")
    found = re.search(r"^Case ID: (\d+)$", text, re.MULTILINE)
    if not found or "\n## Final answer\n\n" not in text:
        raise RuntimeError(f"Invalid recovery packet: {packet}")
    case_id = int(found.group(1))
    if case_id not in FEATURES:
        raise RuntimeError(f"Unexpected case ID: {case_id}")
    body = text.split("\n## Final answer\n\n", 1)[1].strip()
    if not body:
        raise RuntimeError(f"Empty final answer: {packet}")
    return case_id, body


def validate(data: Any, audit_id: str, case_id: int, answer: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict) or set(data) != {"audit_id", "features", "overall_recovery", "rationale"}:
        return ["Wrong top-level object fields"]
    if data["audit_id"] != audit_id:
        errors.append("Wrong audit ID")
    rows = data["features"]
    expected = FEATURES[case_id]
    if not isinstance(rows, list) or len(rows) != len(expected):
        return [*errors, f"Expected {len(expected)} case-specific features"]
    labels: dict[str, str] = {}
    normalized_answer = " ".join(answer.split()).casefold()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"feature_id", "label", "excerpt"}:
            errors.append("Feature object fields invalid")
            continue
        feature_id, label, excerpt = row["feature_id"], row["label"], row["excerpt"]
        if feature_id not in expected or feature_id in labels:
            errors.append(f"Invalid or duplicate feature ID: {feature_id}")
            continue
        labels[feature_id] = label
        if label not in LABELS:
            errors.append(f"Invalid label: {feature_id}")
        if not isinstance(excerpt, str):
            errors.append(f"Excerpt is not a string: {feature_id}")
        elif label == "absent" and excerpt.strip().lower() != "none":
            errors.append(f"Absent feature requires excerpt 'none': {feature_id}")
        elif label != "absent" and (not excerpt.strip() or excerpt.strip().lower() == "none" or " ".join(excerpt.split()).casefold() not in normalized_answer):
            errors.append(f"Non-absent feature requires an exact supporting excerpt: {feature_id}")
    if set(labels) != set(expected):
        errors.append("Missing case-specific feature IDs")
    overall = data["overall_recovery"]
    if overall not in LABELS:
        errors.append("Invalid overall label")
    elif set(labels) == set(expected) and all(value in LABELS for value in labels.values()):
        if case_id == 1:
            explicit = labels["combined_dual_allocation"] == "explicit_target_like" and labels["surface_lpscl_contact"] != "absent" and labels["interstitial_lpscl_network"] != "absent"
        elif case_id == 8:
            explicit = labels["combined_cube_wall_graphene_architecture"] == "explicit_target_like"
        else:
            explicit = labels["nested_inner_outer_tubes"] == "explicit_target_like" and labels["internal_void_as_strain_buffer"] != "absent"
        expected_overall = "explicit_target_like" if explicit else "partial_general" if any(value != "absent" for value in labels.values()) else "absent"
        if overall != expected_overall:
            errors.append(f"Overall label contradicts feature-level rule; expected {expected_overall}")
    if not isinstance(data["rationale"], str) or not data["rationale"].strip():
        errors.append("Rationale must be nonempty")
    return errors


def status_of(root: Path, audit_id: str) -> str:
    manifest_path = root / audit_id / "run_manifest.json"
    accepted = root / audit_id / "accepted_audit.json"
    if not manifest_path.exists():
        return "MISSING"
    try:
        manifest = read_json(manifest_path)
    except Exception:
        return "INVALID"
    return "COMPLETE" if manifest.get("status") == "COMPLETE" and accepted.is_file() else str(manifest.get("status", "INVALID"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Condition-blind direct Anthropic target-recovery audit")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-config-id")
    parser.add_argument("--max-packets", type=int, default=1)
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()
    if args.max_packets < 1:
        raise SystemExit("--max-packets must be positive")
    verify_frozen(root)
    packet_dir = root / "evaluation" / "blind_packets_deleak_target_recovery_v1"
    result_root = root / "results" / "deleak_target_recovery_sonnet5_v1"
    packets = sorted(packet_dir.glob("audit_*.md"))
    if len(packets) != 18:
        raise RuntimeError("Expected 18 frozen audit packets")
    pending = [packet for packet in packets if status_of(result_root, packet.stem) != "COMPLETE"]
    plan = {"dry_run": not args.execute, "config_id": CONFIG_ID, "expected_packets": 18, "complete": 18 - len(pending), "pending": len(pending), "first_pending": [packet.stem for packet in pending[:args.max_packets]], "model": "claude-sonnet-5", "api_key_recorded": False}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False))
        return 0
    if args.confirm_config_id != CONFIG_ID:
        raise SystemExit(f"Live execution requires --confirm-config-id {CONFIG_ID}")
    api_key = resolve_environment("ANTHROPIC_API_KEY")
    prompt = root / "evaluation" / "deleak_target_recovery_prompt_v1.md"
    rubric = root / "protocol" / "prompt_deleaking_target_recovery_rubric_v1.md"
    schema = root / "evaluation" / "deleak_target_recovery_schema_v1.json"
    result_root.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    for packet in pending[:args.max_packets]:
        audit_id = packet.stem
        case_id, answer = packet_content(packet)
        output = result_root / audit_id
        if output.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            destination = output.with_name(f"{audit_id}_previous_incomplete_{stamp}")
            if destination.exists():
                raise RuntimeError(f"Preservation destination exists: {destination}")
            output.rename(destination)
        output.mkdir()
        user = "\n\n".join(["# FROZEN TARGET-RECOVERY RUBRIC\n" + rubric.read_text(encoding="utf-8"), "# ANONYMOUS SINGLE-ANSWER PACKET\n" + packet.read_text(encoding="utf-8"), "Submit the complete audit using the required tool exactly once."])
        payload = {"model": "claude-sonnet-5", "max_tokens": 2000, "system": prompt.read_text(encoding="utf-8"), "messages": [{"role": "user", "content": user}], "tools": [{"name": "submit_target_recovery", "description": "Submit one blinded target-feature recovery audit.", "input_schema": read_json(schema), "strict": True}], "tool_choice": {"type": "tool", "name": "submit_target_recovery"}}
        request_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (output / "request_payload.json").write_bytes(request_bytes)
        attempts: list[dict[str, Any]] = []
        accepted: dict[str, Any] | None = None
        started = utc()
        for attempt in (1, 2):
            request = urllib.request.Request(ENDPOINT, data=request_bytes, method="POST", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json", "User-Agent": "anthropic-sdk-python/0.70.0"})
            begin = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    response_bytes = response.read()
                    http_status = response.status
                (output / f"attempt_{attempt:02d}_response.json").write_bytes(response_bytes)
                envelope = json.loads(response_bytes.decode("utf-8"))
                data, _ = extract_tool_input(envelope, "submit_target_recovery")
                errors = validate(data, audit_id, case_id, answer)
                attempts.append({"attempt": attempt, "http_status": http_status, "elapsed_seconds": round(time.perf_counter() - begin, 3), "returned_model": envelope.get("model"), "usage": envelope.get("usage", {}), "validation_errors": errors})
                if not errors and envelope.get("model") == "claude-sonnet-5":
                    accepted = data
                    break
                if not errors:
                    attempts[-1]["validation_errors"] = ["Returned model mismatch"]
            except urllib.error.HTTPError as exc:
                body = exc.read()
                attempts.append({"attempt": attempt, "http_status": exc.code, "elapsed_seconds": round(time.perf_counter() - begin, 3), "error_type": "HTTPError", "error_body_sha256": hashlib.sha256(body).hexdigest()})
                break
            except Exception as exc:
                attempts.append({"attempt": attempt, "elapsed_seconds": round(time.perf_counter() - begin, 3), "error_type": type(exc).__name__, "error_message": str(exc)[:300]})
                break
            if attempt == 1:
                time.sleep(10)
        if accepted is not None:
            (output / "accepted_audit.json").write_text(json.dumps(accepted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = {"status": "COMPLETE" if accepted is not None else "FAILED", "audit_id": audit_id, "case_id": case_id, "started_utc": started, "finished_utc": utc(), "requested_model": "claude-sonnet-5", "endpoint": ENDPOINT, "api_key_env": "ANTHROPIC_API_KEY", "api_key_recorded": False, "packet_sha256": sha256_file(packet), "prompt_sha256": sha256_file(prompt), "rubric_sha256": sha256_file(rubric), "schema_sha256": sha256_file(schema), "request_sha256": hashlib.sha256(request_bytes).hexdigest(), "attempts": attempts}
        (output / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if accepted is None:
            failed.append(audit_id)
        status = {"expected": 18, "complete": sum(status_of(result_root, path.stem) == "COMPLETE" for path in packets), "failed": failed, "last_attempted": audit_id, "updated_utc": utc()}
        (result_root / "batch_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"audit_id": audit_id, "status": manifest["status"], "attempts": len(attempts), "usage": attempts[-1].get("usage", {})}, ensure_ascii=False), flush=True)
        if failed and not args.continue_on_error:
            break
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
