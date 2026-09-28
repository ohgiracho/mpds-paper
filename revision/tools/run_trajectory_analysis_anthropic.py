from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trajectory_common import ALIASES, DIMENSIONS, EVENT_TYPES, load_config, read_csv, resolve_from_root, sha256_bytes, sha256_file, write_json


TOOL_NAME = "submit_trajectory_evaluations"
ALIAS_SHORT = {"a": "Trajectory A", "b": "Trajectory B", "c": "Trajectory C", "d": "Trajectory D"}
EVENT_SHORT = {
    "i": "initial_idea",
    "c": "counterpoint_or_alternative",
    "f": "final_change",
    "t": "event_type",
    "u": "substantive",
}


def resolve_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
            if str(value).strip():
                return str(value).strip()
        except (FileNotFoundError, OSError):
            pass
    raise RuntimeError(f"Required environment variable is not configured: {name}")


def provider_schema() -> dict[str, Any]:
    event = {
        "type": "object",
        "additionalProperties": False,
        "required": ["i", "c", "f", "t", "u"],
        "properties": {
            "i": {"type": "string"},
            "c": {"type": "string"},
            "f": {"type": "string"},
            "t": {"type": "string", "enum": sorted(EVENT_TYPES)},
            "u": {"type": "boolean"},
        },
    }
    evaluation = {
        "type": "object",
        "additionalProperties": False,
        "required": ["s", "e", "r"],
        "properties": {
            "s": {"type": "array", "items": {"type": "integer"}},
            "e": {"type": "array", "items": event},
            "r": {"type": "array", "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["p", "a", "b", "c", "d"],
        "properties": {
            "p": {"type": "string"},
            **{key: evaluation for key in ALIAS_SHORT},
        },
    }


def extract_tool_input(envelope: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    content = envelope.get("content")
    if not isinstance(content, list):
        raise ValueError("Claude response has no content array")
    calls = [
        block for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == TOOL_NAME
    ]
    if len(calls) != 1 or not isinstance(calls[0].get("input"), dict):
        raise ValueError(f"Expected exactly one valid {TOOL_NAME} call")
    return calls[0]["input"], [str(block.get("type")) for block in content if isinstance(block, dict)]


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    evaluations: list[dict[str, Any]] = []
    for short, alias in ALIAS_SHORT.items():
        source = raw.get(short)
        if not isinstance(source, dict):
            source = {}
        scores = source.get("s")
        rationales = source.get("r")
        events = source.get("e")
        item: dict[str, Any] = {"alias": alias}
        if isinstance(scores, list) and len(scores) == len(DIMENSIONS):
            item.update(dict(zip(DIMENSIONS, scores, strict=True)))
        else:
            item["__score_format_error"] = "s must contain four values"
        item["major_revision_events"] = []
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict):
                    item["major_revision_events"].append(
                        {long: event.get(short_key) for short_key, long in EVENT_SHORT.items()}
                    )
                else:
                    item["major_revision_events"].append(event)
        else:
            item["__event_format_error"] = "e must be an array"
        if isinstance(rationales, list) and len(rationales) == len(DIMENSIONS):
            item["short_rationale"] = dict(zip(DIMENSIONS, rationales, strict=True))
        else:
            item["short_rationale"] = {}
            item["__rationale_format_error"] = "r must contain four values"
        evaluations.append(item)
    return {"packet_id": raw.get("p"), "trajectory_evaluations": evaluations}


def validate(data: dict[str, Any], packet_id: str) -> list[str]:
    errors: list[str] = []
    if data.get("packet_id") != packet_id:
        errors.append(f"packet_id must be {packet_id}")
    evaluations = data.get("trajectory_evaluations")
    if not isinstance(evaluations, list) or len(evaluations) != len(ALIASES):
        return errors + ["Exactly four trajectory evaluations are required"]
    if [item.get("alias") for item in evaluations if isinstance(item, dict)] != list(ALIASES):
        errors.append("Aliases must be Trajectory A-D in order")
    for item in evaluations:
        if not isinstance(item, dict):
            errors.append("Each evaluation must be an object")
            continue
        alias = str(item.get("alias"))
        for dimension in DIMENSIONS:
            score = item.get(dimension)
            if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
                errors.append(f"{alias}.{dimension} must be an integer from 0 to 4")
        events = item.get("major_revision_events")
        if not isinstance(events, list) or len(events) > 3:
            errors.append(f"{alias}.major_revision_events must contain zero to three events")
        else:
            for index, event in enumerate(events, start=1):
                if not isinstance(event, dict):
                    errors.append(f"{alias}.event_{index} must be an object")
                    continue
                if set(event) != set(EVENT_SHORT.values()):
                    errors.append(f"{alias}.event_{index} fields are incomplete")
                for field in ("initial_idea", "counterpoint_or_alternative", "final_change"):
                    value = event.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"{alias}.event_{index}.{field} must be nonempty")
                if event.get("event_type") not in EVENT_TYPES:
                    errors.append(f"{alias}.event_{index}.event_type is invalid")
                if not isinstance(event.get("substantive"), bool):
                    errors.append(f"{alias}.event_{index}.substantive must be boolean")
        rationales = item.get("short_rationale")
        if not isinstance(rationales, dict) or set(rationales) != set(DIMENSIONS):
            errors.append(f"{alias}.short_rationale must contain all four dimensions")
        else:
            for dimension, rationale in rationales.items():
                if not isinstance(rationale, str) or len(rationale.strip()) < 20:
                    errors.append(f"{alias}.{dimension} rationale is too short")
        for internal in ("__score_format_error", "__event_format_error", "__rationale_format_error"):
            if internal in item:
                errors.append(f"{alias}: {item[internal]}")
    return errors


def verify_integrity(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    integrity_path = analysis_dir / "trajectory_input_integrity_manifest.json"
    if not integrity_path.exists():
        raise RuntimeError("Frozen trajectory input integrity manifest is missing")
    integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
    if integrity.get("status") != "FROZEN_BEFORE_ANY_TRAJECTORY_EVALUATION_CALL":
        raise RuntimeError("Trajectory input integrity manifest has an unexpected status")
    for group in ("fixed_files", "packets", "source_files"):
        for item in integrity.get(group, []):
            path = Path(item["path"])
            if not path.is_absolute():
                path = (root / path).resolve()
            if not path.exists() or sha256_file(path) != item["sha256"]:
                raise RuntimeError(f"Frozen integrity check failed: {path}")
    return integrity


def packet_identity(packet_id: str) -> tuple[int, int]:
    match = re.fullmatch(r"case_(\d{2})__rep_(\d{2})", packet_id)
    if not match:
        raise ValueError(packet_id)
    return int(match.group(1)), int(match.group(2))


def enriched_scores(data: dict[str, Any]) -> dict[str, Any]:
    case_id, replicate = packet_identity(data["packet_id"])
    enriched: list[dict[str, Any]] = []
    for item in data["trajectory_evaluations"]:
        alias = item["alias"]
        enriched.append(
            {
                "trajectory_id": f"{data['packet_id']}__{alias.lower().replace(' ', '_')}",
                "case_id": case_id,
                "replicate": replicate,
                "blind_condition_label": alias,
                **{key: value for key, value in item.items() if key != "alias"},
            }
        )
    return {"packet_id": data["packet_id"], "trajectory_evaluations": enriched}


def summarize_runs(output_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(output_root.glob("case_*__rep_*/run_manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        accepted = manifest_path.parent / "accepted_scores.json"
        usage = manifest.get("accepted_usage") or {}
        rows.append(
            {
                "packet_id": manifest.get("packet_id"),
                "status": manifest.get("status"),
                "attempts": len(manifest.get("attempts", [])),
                "returned_model": manifest.get("returned_model"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "accepted_scores_sha256": sha256_file(accepted) if accepted.exists() else None,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen trajectory packets through official Anthropic Messages API")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--packet", type=Path, action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--max-packets", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if bool(args.packet) == bool(args.all):
        raise SystemExit("Use exactly one of --packet or --all")
    root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(root, args.config)
    integrity = verify_integrity(root, config)
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    prompt_path = analysis_dir / "trajectory_evaluation_prompt_frozen.txt"
    rubric_path = analysis_dir / "trajectory_rubric_frozen.json"
    schema_path = analysis_dir / "trajectory_output_schema_frozen.json"
    packet_dir = resolve_from_root(root, config["packet_directory"])
    output_root = resolve_from_root(root, config["judge_run_directory"])
    output_root.mkdir(parents=True, exist_ok=True)
    packets = sorted(packet_dir.glob("case_*__rep_*.md")) if args.all else [path.resolve() for path in args.packet]
    if args.max_packets is not None:
        if args.max_packets < 1:
            raise SystemExit("--max-packets must be positive")
        packets = packets[: args.max_packets]
    api_key = "" if args.dry_run else resolve_environment(config["evaluator"]["api_key_env"])
    endpoint = config["evaluator"]["endpoint"]
    if endpoint != "https://api.anthropic.com/v1/messages":
        raise RuntimeError(f"Unexpected endpoint: {endpoint}")
    prompt = prompt_path.read_text(encoding="utf-8")
    rubric = rubric_path.read_text(encoding="utf-8")
    canonical_schema_sha = sha256_file(schema_path)
    tool_schema = provider_schema()

    for packet in packets:
        packet_id = packet.stem
        run_dir = output_root / packet_id
        manifest_path = run_dir / "run_manifest.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("status") == "COMPLETE":
                print(json.dumps({"packet_id": packet_id, "status": "SKIPPED_COMPLETE"}))
                continue
        run_dir.mkdir(parents=True, exist_ok=True)
        user = "\n\n".join(
            [
                "# FROZEN TRAJECTORY RUBRIC\n" + rubric,
                "# LABEL-MASKED TRAJECTORY PACKET\n" + packet.read_text(encoding="utf-8"),
                """# COMPACT TOOL FORMAT — REQUIRED
`p` is the packet ID. `a`, `b`, `c`, and `d` correspond to Trajectory A-D.
For each trajectory, `s` contains exactly four integer scores in this order: tension_recognition, adaptive_revision, tradeoff_resolution, nonadditive_synthesis.
`e` contains zero to three revision events. In every event, `i` is initial_idea, `c` is counterpoint_or_alternative, `f` is final_change, `t` is event_type, and `u` is substantive.
`r` contains exactly four rationale strings in the same order as `s`.
Supply all four trajectories. Do not add fields or return ordinary prose.""",
            ]
        )
        tool_definition = {
            "name": TOOL_NAME,
            "description": "Submit all four independent trajectory evaluations in the frozen compact format.",
            "input_schema": tool_schema,
            "strict": True,
        }
        request_payload = {
            "model": config["evaluator"]["requested_model"],
            "max_tokens": int(config["evaluator"]["max_output_tokens"]),
            "system": prompt,
            "messages": [{"role": "user", "content": user}],
            "tools": [tool_definition],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        request_bytes = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request_path = run_dir / "request_payload.json"
        schema_output = run_dir / "provider_tool_schema.json"
        if request_path.exists() and request_path.read_bytes() != request_bytes:
            raise RuntimeError(f"Refusing to change an existing request: {request_path}")
        request_path.write_bytes(request_bytes)
        schema_bytes = json.dumps(tool_schema, ensure_ascii=False, indent=2).encode("utf-8")
        if schema_output.exists() and schema_output.read_bytes() != schema_bytes:
            raise RuntimeError(f"Refusing to change an existing provider schema: {schema_output}")
        schema_output.write_bytes(schema_bytes)
        if args.dry_run:
            print(json.dumps({"packet_id": packet_id, "status": "DRY_RUN", "request_bytes": len(request_bytes)}))
            continue

        started = datetime.now(timezone.utc)
        attempts: list[dict[str, Any]] = []
        accepted: dict[str, Any] | None = None
        accepted_envelope: dict[str, Any] | None = None
        for attempt in range(1, int(config["evaluator"]["max_attempts"]) + 1):
            attempt_started = time.perf_counter()
            request = urllib.request.Request(
                endpoint,
                data=request_bytes,
                method="POST",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                    "User-Agent": "anthropic-sdk-python/0.70.0",
                },
            )
            record: dict[str, Any] = {"attempt": attempt}
            try:
                with urllib.request.urlopen(request, timeout=600) as response:
                    response_bytes = response.read()
                    record["http_status"] = response.status
                response_path = run_dir / f"attempt_{attempt:02d}_response.json"
                response_path.write_bytes(response_bytes)
                envelope = json.loads(response_bytes.decode("utf-8"))
                raw, content_types = extract_tool_input(envelope)
                normalized = normalize(raw)
                errors = validate(normalized, packet_id)
                record.update(
                    {
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "response_sha256": sha256_bytes(response_bytes),
                        "raw_tool_input_sha256": sha256_bytes(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")),
                        "normalized_tool_input_sha256": sha256_bytes(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")),
                        "returned_model": envelope.get("model"),
                        "stop_reason": envelope.get("stop_reason"),
                        "content_types": content_types,
                        "usage": envelope.get("usage", {}),
                        "validation_errors": errors,
                    }
                )
                attempts.append(record)
                if not errors:
                    accepted = enriched_scores(normalized)
                    accepted_envelope = envelope
                    break
            except urllib.error.HTTPError as exc:
                body = exc.read()
                (run_dir / f"attempt_{attempt:02d}_error_body.txt").write_bytes(body)
                record.update(
                    {
                        "http_status": exc.code,
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "error_type": "HTTPError",
                        "error_body_sha256": sha256_bytes(body),
                    }
                )
                attempts.append(record)
                break
            except Exception as exc:
                record.update(
                    {
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                )
                attempts.append(record)
                break
            if attempt < int(config["evaluator"]["max_attempts"]):
                time.sleep(10)

        status = "COMPLETE" if accepted is not None else "FAILED"
        if accepted is not None:
            write_json(run_dir / "accepted_scores.json", accepted)
        usage = accepted_envelope.get("usage", {}) if accepted_envelope else {}
        manifest = {
            "status": status,
            "purpose": "OFFICIAL_EXPLORATORY_TRAJECTORY_EVALUATION",
            "packet_id": packet_id,
            "started_utc": started.isoformat(),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "transport": config["evaluator"]["provider"],
            "endpoint": endpoint,
            "api_key_env": config["evaluator"]["api_key_env"],
            "api_key_recorded": False,
            "requested_model": config["evaluator"]["requested_model"],
            "returned_model": accepted_envelope.get("model") if accepted_envelope else None,
            "max_output_tokens": config["evaluator"]["max_output_tokens"],
            "temperature_override": None,
            "thinking_parameter": "omitted",
            "external_tools": config["evaluator"]["external_tools"],
            "blinding_claim": config["blinding"]["claim"],
            "packet": {"path": str(packet), "sha256": sha256_file(packet), "bytes": packet.stat().st_size},
            "prompt_sha256": sha256_file(prompt_path),
            "rubric_sha256": sha256_file(rubric_path),
            "canonical_schema_sha256": canonical_schema_sha,
            "provider_tool_schema_sha256": sha256_file(schema_output),
            "request_payload_sha256": sha256_bytes(request_bytes),
            "request_bytes": len(request_bytes),
            "integrity_manifest_sha256": sha256_file(analysis_dir / "trajectory_input_integrity_manifest.json"),
            "attempts": attempts,
            "accepted_usage": usage,
        }
        write_json(manifest_path, manifest)
        write_json(output_root / "run_summary.json", summarize_runs(output_root))
        print(json.dumps({"packet_id": packet_id, "status": status, "usage": usage}, ensure_ascii=False))
        if accepted is None:
            return 2
    if not args.dry_run:
        write_json(output_root / "run_summary.json", summarize_runs(output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
