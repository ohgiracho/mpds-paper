from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_judge_outputs import (
    EVIDENCE_FLAG_FIELDS,
    FLAG_VALUES,
    SUPPORT_VALUES,
    validate_evidence,
)


ENDPOINT = "https://api.anthropic.com/v1/messages"
ALIASES = ["Candidate A", "Candidate B", "Candidate C", "Candidate D", "Candidate E"]
SECTION_RE = re.compile(r"(?m)^## (Candidate [A-E])\s*$")
TOOL_NAME = "submit_single_candidate_evidence_audit"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def split_packet(text: str) -> tuple[str, dict[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    if [match.group(1) for match in matches] != ALIASES:
        raise ValueError("Packet must contain Candidate A-E exactly once and in order")
    header = text[: matches[0].start()].rstrip()
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.start() : end].strip()
    return header, sections


def provider_schema(canonical_schema: dict[str, Any]) -> dict[str, Any]:
    packet_schema = copy.deepcopy(canonical_schema["properties"]["packet_id"])
    candidate_schema = copy.deepcopy(
        canonical_schema["properties"]["candidate_audits"]["items"]
    )

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if (
                value.get("type") == "integer"
                and isinstance(value.get("minimum"), int)
                and isinstance(value.get("maximum"), int)
                and 0 <= value["maximum"] - value["minimum"] <= 20
            ):
                value["enum"] = list(range(value["minimum"], value["maximum"] + 1))
            if value.get("type") == "array" and value.get("minItems", 0) not in (0, 1):
                value["minItems"] = 1
            if value.get("type") == "array":
                value.pop("maxItems", None)
            for unsupported in (
                "minimum",
                "maximum",
                "minLength",
                "maxLength",
                "uniqueItems",
            ):
                value.pop(unsupported, None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(packet_schema)
    visit(candidate_schema)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["packet_id", "candidate_audit"],
        "properties": {
            "packet_id": packet_schema,
            "candidate_audit": candidate_schema,
        },
    }


def extract_tool_input(envelope: dict[str, Any]) -> dict[str, Any]:
    calls = [
        block
        for block in envelope.get("content", [])
        if isinstance(block, dict)
        and block.get("type") == "tool_use"
        and block.get("name") == TOOL_NAME
    ]
    if len(calls) != 1 or not isinstance(calls[0].get("input"), dict):
        raise ValueError(f"Expected exactly one valid {TOOL_NAME} call")
    return calls[0]["input"]


def normalize_candidate_audit(audit: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Apply only lossless set-semantic normalization unsupported by strict tools."""
    normalized = copy.deepcopy(audit)
    actions: list[str] = []
    claims = normalized.get("central_claims")
    if not isinstance(claims, list):
        return normalized, actions
    for claim_index, claim in enumerate(claims, start=1):
        if not isinstance(claim, dict):
            continue
        labels = claim.get("cited_evidence_labels")
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            continue
        deduplicated = list(dict.fromkeys(labels))
        if deduplicated != labels:
            claim["cited_evidence_labels"] = deduplicated
            actions.append(
                f"central_claims[{claim_index}].cited_evidence_labels:ordered_deduplication"
            )
    return normalized, actions


def validate_single_candidate(alias: str, audit: Any) -> list[str]:
    errors: list[str] = []
    expected = {
        "alias",
        "evidence_support",
        "citation_traceability",
        "central_claims",
        "flags",
        "audit_rationale",
        "uncertainty_notes",
    }
    claim_expected = {
        "claim_id",
        "claim_text",
        "cited_evidence_labels",
        "support_status",
        "rationale",
    }
    if not isinstance(audit, dict):
        return ["candidate_audit must be an object"]
    if set(audit) != expected:
        errors.append("candidate_audit keys do not match the canonical schema")
    if audit.get("alias") != alias:
        errors.append(f"alias must be {alias}")
    for field in ("evidence_support", "citation_traceability"):
        value = audit.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 5:
            errors.append(f"{field} must be an integer from 0 to 5")
    flags = audit.get("flags")
    if not isinstance(flags, dict) or set(flags) != EVIDENCE_FLAG_FIELDS:
        errors.append("flags do not match the canonical schema")
    elif any(value not in FLAG_VALUES for value in flags.values()):
        errors.append("flags contain an invalid value")
    if not isinstance(audit.get("audit_rationale"), str) or not audit[
        "audit_rationale"
    ].strip():
        errors.append("audit_rationale must be nonempty")
    if not isinstance(audit.get("uncertainty_notes"), str):
        errors.append("uncertainty_notes must be a string")
    claims = audit.get("central_claims")
    if not isinstance(claims, list) or not 1 <= len(claims) <= 5:
        errors.append("central_claims must contain one to five claims")
        return errors
    expected_ids = [f"C{number}" for number in range(1, len(claims) + 1)]
    actual_ids: list[Any] = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("each central claim must be an object")
            continue
        if set(claim) != claim_expected:
            errors.append("central claim keys do not match the canonical schema")
        actual_ids.append(claim.get("claim_id"))
        for field in ("claim_text", "rationale"):
            if not isinstance(claim.get(field), str) or not claim[field].strip():
                errors.append(f"{field} must be nonempty")
        labels = claim.get("cited_evidence_labels")
        if (
            not isinstance(labels, list)
            or any(not isinstance(label, str) for label in labels)
            or len(labels) != len(set(labels))
        ):
            errors.append("cited_evidence_labels must be a unique string array")
        if claim.get("support_status") not in SUPPORT_VALUES:
            errors.append("support_status is invalid")
    if actual_ids != expected_ids:
        errors.append("claim IDs must be sequential from C1")
    return errors


def run_packet(
    *,
    packet: Path,
    output_root: Path,
    api_key: str,
    model: str,
    max_output_tokens: int,
    system_prompt: str,
    supplement_text: str,
    tool_schema: dict[str, Any],
    source_hashes: dict[str, Any],
    validator_sha: str,
) -> dict[str, Any]:
    packet_id = packet.stem
    packet_output = output_root / packet_id
    packet_output.mkdir(parents=True, exist_ok=True)
    header, sections = split_packet(packet.read_text(encoding="utf-8"))
    started = datetime.now(timezone.utc)
    candidate_results: list[dict[str, Any]] = []
    request_records: list[dict[str, Any]] = []

    for alias in ALIASES:
        alias_slug = alias.lower().replace(" ", "_")
        prior_response_files = []
        base_response = packet_output / f"{alias_slug}_response.json"
        if base_response.exists():
            prior_response_files.append(base_response)
        prior_response_files.extend(
            sorted(packet_output.glob(f"{alias_slug}_attempt_*_response.json"))
        )
        reused_prior = False
        for prior_response in prior_response_files:
            try:
                envelope = json.loads(prior_response.read_text(encoding="utf-8"))
                tool_input = extract_tool_input(envelope)
                audit = tool_input.get("candidate_audit")
                if tool_input.get("packet_id") != packet_id:
                    continue
                if not isinstance(audit, dict) or audit.get("alias") != alias:
                    continue
                audit, normalization_actions = normalize_candidate_audit(audit)
                if validate_single_candidate(alias, audit):
                    continue
                usage = envelope.get("usage", {})
                candidate_results.append(audit)
                request_records.append(
                    {
                        "alias": alias,
                        "status": "REUSED_VALID_PRIOR_RESPONSE",
                        "response_path": str(prior_response),
                        "response_sha256": sha256_file(prior_response),
                        "returned_model": envelope.get("model"),
                        "stop_reason": envelope.get("stop_reason"),
                        "usage": usage,
                        "normalization_actions": normalization_actions,
                    }
                )
                reused_prior = True
                break
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        if reused_prior:
            continue

        attempt_number = len(prior_response_files) + 1
        artifact_stem = (
            alias_slug
            if attempt_number == 1
            else f"{alias_slug}_attempt_{attempt_number:02d}"
        )
        candidate_packet = f"{header}\n\n{sections[alias]}\n"
        candidate_tool_schema = copy.deepcopy(tool_schema)
        candidate_tool_schema["properties"]["candidate_audit"]["properties"][
            "alias"
        ] = {"enum": [alias]}
        user_blocks = [
            {
                "type": "text",
                "text": "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement_text,
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": "# SINGLE-CANDIDATE BLINDED EVIDENCE-AUDIT PACKET\n"
                + candidate_packet,
            },
            {
                "type": "text",
                "text": (
                    "Submit this candidate's complete audit by calling the required tool exactly once. "
                    "Do not return the audit as ordinary prose. Every claim_text, claim rationale, "
                    "and audit_rationale must contain substantive nonempty text; never submit an empty placeholder."
                ),
            },
        ]
        payload = {
            "model": model,
            "max_tokens": max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_blocks}],
            "tools": [
                {
                    "name": TOOL_NAME,
                    "description": "Submit one complete blinded Pass 2 candidate evidence audit.",
                    "strict": True,
                    "input_schema": candidate_tool_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": TOOL_NAME},
        }
        request_bytes = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        (packet_output / f"{artifact_stem}_request_payload.json").write_bytes(request_bytes)
        request = urllib.request.Request(
            ENDPOINT,
            data=request_bytes,
            method="POST",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "User-Agent": "mpds-pass2-audit/1.0",
            },
        )
        call_started = time.perf_counter()
        record: dict[str, Any] = {
            "alias": alias,
            "attempt": attempt_number,
            "request_bytes": len(request_bytes),
            "request_sha256": sha256_bytes(request_bytes),
            "provider_tool_schema_sha256": sha256_bytes(
                json.dumps(
                    candidate_tool_schema,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8")
            ),
        }
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                response_bytes = response.read()
                record["http_status"] = response.status
            (packet_output / f"{artifact_stem}_response.json").write_bytes(response_bytes)
            envelope = json.loads(response_bytes.decode("utf-8"))
            tool_input = extract_tool_input(envelope)
            returned_packet = tool_input.get("packet_id")
            audit = tool_input.get("candidate_audit")
            if returned_packet != packet_id:
                raise ValueError(
                    f"Packet mismatch for {alias}: expected {packet_id}, got {returned_packet}"
                )
            if not isinstance(audit, dict) or audit.get("alias") != alias:
                raise ValueError(f"Alias mismatch or invalid candidate audit for {alias}")
            audit, normalization_actions = normalize_candidate_audit(audit)
            candidate_errors = validate_single_candidate(alias, audit)
            if candidate_errors:
                raise ValueError(
                    f"Candidate audit validation failed for {alias}: {candidate_errors}"
                )
            usage = envelope.get("usage", {})
            record.update(
                {
                    "elapsed_seconds": round(time.perf_counter() - call_started, 3),
                    "response_sha256": sha256_bytes(response_bytes),
                    "returned_model": envelope.get("model"),
                    "stop_reason": envelope.get("stop_reason"),
                    "usage": usage,
                    "normalization_actions": normalization_actions,
                    "status": "ACCEPTED_FOR_PACKET_ASSEMBLY",
                }
            )
            candidate_results.append(audit)
            request_records.append(record)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            (packet_output / f"{artifact_stem}_error_body.txt").write_bytes(body)
            record.update(
                {
                    "http_status": exc.code,
                    "elapsed_seconds": round(time.perf_counter() - call_started, 3),
                    "error_type": "HTTPError",
                    "error_body_sha256": sha256_bytes(body),
                    "status": "FAILED",
                }
            )
            request_records.append(record)
            break
        except Exception as exc:
            record.update(
                {
                    "elapsed_seconds": round(time.perf_counter() - call_started, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                    "status": "FAILED",
                }
            )
            request_records.append(record)
            break

    assembled = {"packet_id": packet_id, "candidate_audits": candidate_results}
    errors, derived_rows = validate_evidence(assembled, Path(f"{packet_id}.json"))
    status = "COMPLETE" if not errors else "FAILED"
    if status == "COMPLETE":
        (packet_output / "accepted_scores.json").write_text(
            json.dumps(assembled, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        write_csv(packet_output / "derived_alias_scores.csv", derived_rows)

    finished = datetime.now(timezone.utc)
    manifest = {
        "status": status,
        "purpose": "OFFICIAL_BLINDED_PASS2",
        "mode": "evidence",
        "execution_unit": "single_candidate_requests_assembled_to_original_packet",
        "packet_id": packet_id,
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "transport": "Official Anthropic Messages API",
        "endpoint": ENDPOINT,
        "api_key_env": "ANTHROPIC_API_KEY",
        "api_key_recorded": False,
        "requested_model": model,
        "max_output_tokens_per_candidate": max_output_tokens,
        "provider_strict_tool_schema": True,
        "thinking_parameter": "omitted",
        "temperature_override": None,
        "external_tools": "disabled_except_required_score_submission_tool",
        "packet_source": {
            "path": str(packet),
            "sha256": sha256_file(packet),
            "bytes": packet.stat().st_size,
        },
        "fixed_sources": source_hashes,
        "provider_tool_schema_base_sha256": sha256_bytes(
            json.dumps(tool_schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ),
        "validator_sha256": validator_sha,
        "runner_sha256": sha256_file(Path(__file__)),
        "candidate_requests": request_records,
        "validation_errors": errors,
        "derived_rows": len(derived_rows),
    }
    (packet_output / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    totals = {
        key: sum(
            int(record.get("usage", {}).get(key) or 0) for record in request_records
        )
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
        )
    }
    summary = {
        "packet_id": packet_id,
        "status": status,
        "candidate_calls": len(request_records),
        **totals,
        "derived_rows": len(derived_rows),
        "validation_errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Pass 2 as five independent strict candidate audits per packet"
    )
    parser.add_argument("--packet", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    parser.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    parser.add_argument("--max-workers", type=int, default=1)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    api_key = resolve_environment(args.api_key_env)
    prompt = root / "evaluation" / "judge_prompt_pass2_single_candidate_v1.md"
    supplement = root / "evaluation" / "supplementary_evaluation_module_v1.md"
    schema_path = root / "evaluation" / "evidence_audit_output_schema_v1.json"
    validator = Path(__file__).with_name("validate_judge_outputs.py")
    canonical_schema = json.loads(schema_path.read_text(encoding="utf-8"))
    tool_schema = provider_schema(canonical_schema)
    source_hashes = {
        name: {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
        for name, path in {
            "prompt": prompt,
            "supplement": supplement,
            "canonical_schema": schema_path,
        }.items()
    }
    common = {
        "output_root": output_root,
        "api_key": api_key,
        "model": args.model,
        "max_output_tokens": args.max_output_tokens,
        "system_prompt": prompt.read_text(encoding="utf-8"),
        "supplement_text": supplement.read_text(encoding="utf-8"),
        "tool_schema": tool_schema,
        "source_hashes": source_hashes,
        "validator_sha": sha256_file(validator),
    }
    packets = [packet.resolve() for packet in args.packet]
    summaries: list[dict[str, Any]] = []
    if args.max_workers == 1:
        for packet in packets:
            summary = run_packet(packet=packet, **common)
            summaries.append(summary)
            if summary["status"] != "COMPLETE":
                break
    else:
        with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            future_map = {
                executor.submit(run_packet, packet=packet, **common): packet
                for packet in packets
            }
            for future in as_completed(future_map):
                summaries.append(future.result())
    summaries.sort(key=lambda row: row["packet_id"])
    (output_root / "run_summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0 if len(summaries) == len(packets) and all(
        row["status"] == "COMPLETE" for row in summaries
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
