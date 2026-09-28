from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_judge_outputs import (
    EVIDENCE_FLAG_FIELDS,
    MAIN_FLAG_FIELDS,
    SCORE_FIELDS_MAIN,
    validate_evidence,
    validate_main,
)


EXPECTED_ENDPOINT = "https://factchat-cloud.mindlogic.ai/v1/gateway/claude/v1/messages/"
OFFICIAL_ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ALLOWED_ENDPOINTS = {EXPECTED_ENDPOINT, OFFICIAL_ANTHROPIC_ENDPOINT}
TOOL_NAMES = {
    "main": "submit_blinded_scores",
    "evidence": "submit_evidence_audit",
}
FIXED_ALIAS_KEYS = {
    "candidate_a": "Candidate A",
    "candidate_b": "Candidate B",
    "candidate_c": "Candidate C",
    "candidate_d": "Candidate D",
    "candidate_e": "Candidate E",
}
VALIDATOR_PATH = Path(__file__).with_name("validate_judge_outputs.py")
PASS2_ONLY_FLAG_FIELDS = {
    "consequential_unsupported_or_contradicted_claim",
    "fabricated_or_invalid_citation_identifier",
}
MAIN_ALLOWED_CANDIDATE_FIELDS = {
    "alias",
    *SCORE_FIELDS_MAIN,
    "flags",
    "ihq_rationale",
    "validity_rationale",
    "uncertainty_notes",
}
EVIDENCE_ALLOWED_CANDIDATE_FIELDS = {
    "alias",
    "evidence_support",
    "citation_traceability",
    "central_claims",
    "flags",
    "audit_rationale",
    "uncertainty_notes",
}
EVIDENCE_ALLOWED_CLAIM_FIELDS = {
    "claim_id",
    "claim_text",
    "cited_evidence_labels",
    "support_status",
    "rationale",
}
MAIN_SCORE_ORDER = (
    "idea_novelty",
    "mechanistic_originality",
    "tradeoff_reframing",
    "cross_perspective_integration",
    "scientific_correctness",
    "physical_plausibility",
    "constraint_adherence",
    "falsifiability_actionability",
)
MAIN_FLAG_ORDER = (
    "scientifically_consequential_error",
    "temporal_cutoff_violation",
    "fixed_task_constraint_violation",
    "infeasible_primary_process",
)


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


def provider_tool_schema(
    source_schema: dict[str, Any],
    mode: str,
    *,
    compact_fixed_candidates: bool = False,
    canonical_candidate_array: bool = False,
    direct_compact_main: bool = False,
) -> dict[str, Any]:
    """Adapt the strict local schema to FactChat/Anthropic's accepted subset.

    Exact candidate count, score ranges, patterns, lengths, and uniqueness are
    still enforced immediately after receipt by validate_judge_outputs.py.
    """
    adapted = copy.deepcopy(source_schema)
    adapted.pop("$schema", None)
    adapted.pop("title", None)

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "array" and isinstance(value.get("minItems"), int) and value["minItems"] > 1:
                value["minItems"] = 1
            if value.get("type") == "array":
                value.pop("maxItems", None)
            for unsupported in ("minimum", "maximum", "minLength", "maxLength", "pattern", "uniqueItems"):
                value.pop(unsupported, None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(adapted)
    if direct_compact_main:
        if mode != "main":
            raise RuntimeError("The compact direct schema is available only for Pass 1 main scoring")
        # Anthropic's strict-schema compiler accepts this small fixed-alias
        # envelope. The compact arrays are expanded and strictly validated
        # locally before a result can be accepted.
        candidate = {
            "type": "object",
            "additionalProperties": False,
            "required": ["s", "f", "r"],
            "properties": {
                "s": {"type": "array", "items": {"type": "integer"}},
                "f": {"type": "array", "items": {"type": "string"}},
                "r": {"type": "array", "items": {"type": "string"}},
            },
        }
        alias_keys = [key.removeprefix("candidate_") for key in FIXED_ALIAS_KEYS]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["p", *alias_keys],
            "properties": {
                "p": {"type": "string"},
                **{key: copy.deepcopy(candidate) for key in alias_keys},
            },
        }
    if canonical_candidate_array:
        return adapted
    if compact_fixed_candidates:
        packet_schema = copy.deepcopy(adapted["properties"]["packet_id"])
        canonical_key = "candidate_scores" if mode == "main" else "candidate_audits"
        fixed_key = "candidate_scores_by_alias" if mode == "main" else "candidate_audits_by_alias"
        candidate_schema = copy.deepcopy(adapted["properties"][canonical_key]["items"])
        fixed_candidates: dict[str, Any] = {}
        for key, alias in FIXED_ALIAS_KEYS.items():
            one_candidate = copy.deepcopy(candidate_schema)
            one_candidate["properties"]["alias"] = {"enum": [alias]}
            fixed_candidates[key] = one_candidate
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["packet_id", fixed_key],
            "properties": {
                "packet_id": packet_schema,
                fixed_key: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(FIXED_ALIAS_KEYS),
                    "properties": fixed_candidates,
                },
            },
        }
    if mode == "main":
        packet_schema = copy.deepcopy(adapted["properties"]["packet_id"])
        candidate_schema = copy.deepcopy(adapted["properties"]["candidate_scores"]["items"])
        fixed_candidates: dict[str, Any] = {}
        for key, alias in FIXED_ALIAS_KEYS.items():
            one_candidate = copy.deepcopy(candidate_schema)
            one_candidate["properties"]["alias"] = {"enum": [alias]}
            fixed_candidates[key] = one_candidate
        adapted = {
            "type": "object",
            "additionalProperties": False,
            "required": ["packet_id", "candidate_scores_by_alias"],
            "properties": {
                "packet_id": packet_schema,
                "candidate_scores_by_alias": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(FIXED_ALIAS_KEYS),
                    "properties": fixed_candidates,
                },
            },
        }
    else:
        packet_schema = copy.deepcopy(adapted["properties"]["packet_id"])
        candidate_schema = copy.deepcopy(adapted["properties"]["candidate_audits"]["items"])
        claim_schema = copy.deepcopy(candidate_schema["properties"]["central_claims"]["items"])
        claim_properties: dict[str, Any] = {}
        for number in range(1, 6):
            one_claim = copy.deepcopy(claim_schema)
            one_claim["properties"]["claim_id"] = {"enum": [f"C{number}"]}
            claim_properties[f"claim_{number}"] = one_claim
        candidate_schema["properties"].pop("central_claims")
        candidate_schema["properties"]["central_claims_by_id"] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["claim_1"],
            "properties": claim_properties,
        }
        candidate_schema["required"] = [
            "central_claims_by_id" if field == "central_claims" else field
            for field in candidate_schema["required"]
        ]
        fixed_candidates: dict[str, Any] = {}
        for key, alias in FIXED_ALIAS_KEYS.items():
            one_candidate = copy.deepcopy(candidate_schema)
            one_candidate["properties"]["alias"] = {"enum": [alias]}
            fixed_candidates[key] = one_candidate
        adapted = {
            "type": "object",
            "additionalProperties": False,
            "required": ["packet_id", "candidate_audits_by_alias"],
            "properties": {
                "packet_id": packet_schema,
                "candidate_audits_by_alias": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(FIXED_ALIAS_KEYS),
                    "properties": fixed_candidates,
                },
            },
        }
    return adapted


def normalize_direct_compact_main(data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Expand Anthropic's compact fixed-alias Pass 1 tool envelope."""
    candidates: list[dict[str, Any]] = []
    alias_keys = [(key.removeprefix("candidate_"), alias) for key, alias in FIXED_ALIAS_KEYS.items()]
    for short_key, alias in alias_keys:
        source = data.get(short_key)
        candidate: dict[str, Any] = {"alias": alias}
        errors: list[str] = []
        if not isinstance(source, dict):
            errors.append("candidate must be an object")
            source = {}
        scores = source.get("s")
        flags = source.get("f")
        rationales = source.get("r")
        if not isinstance(scores, list) or len(scores) != len(MAIN_SCORE_ORDER):
            errors.append(f"s must contain {len(MAIN_SCORE_ORDER)} values")
        else:
            candidate.update(dict(zip(MAIN_SCORE_ORDER, scores, strict=True)))
        if not isinstance(flags, list) or len(flags) != len(MAIN_FLAG_ORDER):
            errors.append(f"f must contain {len(MAIN_FLAG_ORDER)} values")
        else:
            candidate["flags"] = dict(zip(MAIN_FLAG_ORDER, flags, strict=True))
        if not isinstance(rationales, list) or len(rationales) != 3:
            errors.append("r must contain ihq, validity, and uncertainty strings")
        else:
            candidate.update(
                {
                    "ihq_rationale": rationales[0],
                    "validity_rationale": rationales[1],
                    "uncertainty_notes": rationales[2],
                }
            )
        if errors:
            candidate["__compact_format_error"] = "; ".join(errors)
        candidates.append(candidate)
    return {
        "packet_id": data.get("p"),
        "candidate_scores": candidates,
    }, "direct_compact_fixed_alias_envelope;strict_local_validation"


def normalize_tool_input(mode: str, data: dict[str, Any]) -> tuple[dict[str, Any], str]:
    if mode == "main" and "p" in data and all(
        key.removeprefix("candidate_") in data for key in FIXED_ALIAS_KEYS
    ):
        return normalize_direct_compact_main(data)
    canonical_key = "candidate_scores" if mode == "main" else "candidate_audits"
    if isinstance(data.get(canonical_key), list):
        return data, "provider_canonical_arrays;strict_local_validation"
    fixed_key = "candidate_scores_by_alias" if mode == "main" else "candidate_audits_by_alias"
    fixed = data.get(fixed_key)
    if not isinstance(fixed, dict):
        return data, "fixed_alias_object_missing"
    candidates = [copy.deepcopy(fixed.get(key)) for key in FIXED_ALIAS_KEYS]
    discarded_fields: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        alias = str(candidate.get("alias", "unknown"))
        if mode == "evidence":
            claim_object = candidate.pop("central_claims_by_id", None)
            if isinstance(claim_object, dict):
                claims = []
                for number in range(1, 6):
                    claim = claim_object.get(f"claim_{number}")
                    if claim is None:
                        continue
                    if isinstance(claim, dict):
                        for field in sorted(set(claim) - EVIDENCE_ALLOWED_CLAIM_FIELDS):
                            claim.pop(field)
                            discarded_fields.append(f"{alias}.claim_{number}.{field}")
                    claims.append(claim)
                candidate["central_claims"] = claims
            allowed_candidate_fields = EVIDENCE_ALLOWED_CANDIDATE_FIELDS
            allowed_flag_fields = EVIDENCE_FLAG_FIELDS
        else:
            allowed_candidate_fields = MAIN_ALLOWED_CANDIDATE_FIELDS
            allowed_flag_fields = MAIN_FLAG_FIELDS
        for field in sorted(set(candidate) - allowed_candidate_fields):
            candidate.pop(field)
            discarded_fields.append(f"{alias}.{field}")
        if not isinstance(candidate.get("flags"), dict):
            continue
        for field in sorted(set(candidate["flags"]) - allowed_flag_fields):
            candidate["flags"].pop(field)
            discarded_fields.append(f"{alias}.flags.{field}")
    normalized = {
        "packet_id": data.get("packet_id"),
        "candidate_scores" if mode == "main" else "candidate_audits": candidates,
    }
    suffix = ",".join(discarded_fields) if discarded_fields else "none"
    return normalized, f"fixed_alias_and_claim_objects_to_canonical_arrays;schema_projection_discarded_fields={suffix}"


def build_content(root: Path, mode: str, packet: Path) -> tuple[str, str, dict[str, Path]]:
    supplement = root / "evaluation" / "supplementary_evaluation_module_v1.md"
    if mode == "main":
        original_ihq = root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt"
        prompt = root / "evaluation" / "judge_prompt_pass1_v2.md"
        schema = root / "evaluation" / "independent_judge_main_output_schema_v3.json"
        files = {
            "prompt": prompt,
            "original_ihq": original_ihq,
            "supplement": supplement,
            "schema": schema,
            "packet": packet,
        }
        user = "\n\n".join(
            [
                "# ORIGINAL PUBLIC GITHUB IHQ RUBRIC — VERBATIM\n" + original_ihq.read_text(encoding="utf-8"),
                "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement.read_text(encoding="utf-8"),
                "# BLINDED PACKET\n" + packet.read_text(encoding="utf-8"),
                "Submit the complete result by calling the required tool exactly once. Do not return scores as ordinary prose.",
            ]
        )
    else:
        prompt = root / "evaluation" / "judge_prompt_pass2_evidence_v2.md"
        schema = root / "evaluation" / "evidence_audit_output_schema_v1.json"
        files = {"prompt": prompt, "supplement": supplement, "schema": schema, "packet": packet}
        user = "\n\n".join(
            [
                "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement.read_text(encoding="utf-8"),
                "# BLINDED EVIDENCE-AUDIT PACKET\n" + packet.read_text(encoding="utf-8"),
                "Submit the complete result by calling the required tool exactly once. Do not return scores as ordinary prose.",
            ]
        )
    return prompt.read_text(encoding="utf-8"), user, files


def extract_tool_input(envelope: dict[str, Any], expected_name: str) -> tuple[dict[str, Any], list[str]]:
    content = envelope.get("content")
    if not isinstance(content, list):
        raise ValueError("Claude response has no content array")
    content_types = [str(block.get("type")) for block in content if isinstance(block, dict)]
    calls = [
        block
        for block in content
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == expected_name
    ]
    if len(calls) != 1:
        raise ValueError(f"Expected exactly one {expected_name!r} tool call; found {len(calls)}")
    tool_input = calls[0].get("input")
    if not isinstance(tool_input, dict):
        raise ValueError("Tool input is not a JSON object")
    return tool_input, content_types


def validate(mode: str, data: dict[str, Any], filename: str) -> tuple[list[str], list[dict[str, Any]]]:
    virtual_path = Path(filename)
    return validate_main(data, virtual_path) if mode == "main" else validate_evidence(data, virtual_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run blinded packets through FactChat's native Claude Messages API")
    parser.add_argument("--mode", choices=("main", "evidence"), required=True)
    parser.add_argument("--packet", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--max-output-tokens", type=int, default=6000)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--api-key-env", default="AJOU_LLM_API_KEY")
    parser.add_argument("--endpoint", default=EXPECTED_ENDPOINT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.endpoint not in ALLOWED_ENDPOINTS:
        raise RuntimeError(f"Unexpected endpoint: {args.endpoint}")

    root = Path(__file__).resolve().parents[1]
    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    api_key = "" if args.dry_run else resolve_environment(args.api_key_env)
    validator_sha = sha256_file(VALIDATOR_PATH)
    run_summary: list[dict[str, Any]] = []

    for packet_arg in args.packet:
        packet = packet_arg.resolve()
        packet_id = packet.stem
        packet_output = output_root / packet_id
        packet_output.mkdir(parents=True, exist_ok=True)
        official_transport = args.endpoint == OFFICIAL_ANTHROPIC_ENDPOINT
        system_prompt, user_content, source_files = build_content(root, args.mode, packet)
        strict_schema = json.loads(source_files["schema"].read_text(encoding="utf-8"))
        direct_compact_main = official_transport and args.mode == "main"
        if direct_compact_main:
            compact_aliases = [
                (key.removeprefix("candidate_"), alias)
                for key, alias in FIXED_ALIAS_KEYS.items()
            ]
            compact_alias_description = ", ".join(
                f"`{short}` is {alias}" for short, alias in compact_aliases
            )
            user_content += f"""

# DIRECT ANTHROPIC COMPACT TOOL FORMAT — REQUIRED
Use the required tool's compact object exactly. `p` is the packet ID. {compact_alias_description}, and all {len(compact_aliases)} candidates must be supplied.
For every candidate: `s` is exactly eight integer scores in this order: idea_novelty, mechanistic_originality, tradeoff_reframing, cross_perspective_integration, scientific_correctness, physical_plausibility, constraint_adherence, falsifiability_actionability. `f` is exactly four flag values in this order: scientifically_consequential_error, temporal_cutoff_violation, fixed_task_constraint_violation, infeasible_primary_process. `r` is exactly three strings in this order: ihq_rationale, validity_rationale, uncertainty_notes. Do not use placeholders or omit any candidate.
"""
        tool_schema = provider_tool_schema(
            strict_schema,
            args.mode,
            # Anthropic strict-mode grammar compilation becomes too large when
            # the full nested candidate object is duplicated once per alias.
            # Keep the canonical array here and enforce exactly A-D (or A-E)
            # immediately with the local validator after tool submission.
            compact_fixed_candidates=False,
            canonical_candidate_array=official_transport,
            direct_compact_main=direct_compact_main,
        )
        tool_name = TOOL_NAMES[args.mode]
        (packet_output / "provider_tool_schema.json").write_text(
            json.dumps(tool_schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        tool_definition = {
            "name": tool_name,
            "description": "Submit the complete blinded evaluation in the required machine-readable structure.",
            "input_schema": tool_schema,
        }
        if official_transport:
            tool_definition["strict"] = True

        request_payload = {
            "model": args.model,
            "max_tokens": args.max_output_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}],
            "tools": [tool_definition],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        request_bytes = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (packet_output / "request_payload.json").write_bytes(request_bytes)
        source_hashes = {
            name: {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}
            for name, path in source_files.items()
        }
        started = datetime.now(timezone.utc)
        attempts: list[dict[str, Any]] = []
        accepted: dict[str, Any] | None = None
        derived_rows: list[dict[str, Any]] = []
        final_envelope: dict[str, Any] | None = None

        if args.dry_run:
            run_summary.append({"packet_id": packet_id, "status": "DRY_RUN", "request_bytes": len(request_bytes)})
            continue

        for attempt in range(1, args.max_attempts + 1):
            attempt_started = time.perf_counter()
            request = urllib.request.Request(
                args.endpoint,
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
                with urllib.request.urlopen(request, timeout=300) as response:
                    response_bytes = response.read()
                    record["http_status"] = response.status
                (packet_output / f"attempt_{attempt:02d}_response.json").write_bytes(response_bytes)
                envelope = json.loads(response_bytes.decode("utf-8"))
                raw_tool_input, content_types = extract_tool_input(envelope, tool_name)
                parsed, normalization = normalize_tool_input(args.mode, raw_tool_input)
                errors, derived = validate(args.mode, parsed, f"{packet_id}.json")
                record.update(
                    {
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "response_sha256": sha256_bytes(response_bytes),
                        "raw_tool_input_sha256": sha256_bytes(json.dumps(raw_tool_input, ensure_ascii=False, sort_keys=True).encode("utf-8")),
                        "normalized_tool_input_sha256": sha256_bytes(json.dumps(parsed, ensure_ascii=False, sort_keys=True).encode("utf-8")),
                        "normalization": normalization,
                        "usage": envelope.get("usage", {}),
                        "returned_model": envelope.get("model"),
                        "stop_reason": envelope.get("stop_reason"),
                        "content_types": content_types,
                        "validation_errors": errors,
                    }
                )
                attempts.append(record)
                if not errors:
                    accepted = parsed
                    derived_rows = derived
                    final_envelope = envelope
                    break
            except urllib.error.HTTPError as exc:
                body = exc.read()
                (packet_output / f"attempt_{attempt:02d}_error_body.txt").write_bytes(body)
                record.update(
                    {
                        "http_status": exc.code,
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "error_type": "HTTPError",
                        "error_body_sha256": sha256_bytes(body),
                    }
                )
                attempts.append(record)
                # Paid batch policy: an HTTP/API failure stops the run. Only a
                # structurally invalid HTTP-200 result may receive one retry.
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
            if attempt < args.max_attempts:
                time.sleep(10 * attempt)

        finished = datetime.now(timezone.utc)
        status = "COMPLETE" if accepted is not None else "FAILED"
        if accepted is not None:
            (packet_output / "accepted_scores.json").write_text(
                json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            write_csv(packet_output / "derived_alias_scores.csv", derived_rows)
        fixed_aliases = list(FIXED_ALIAS_KEYS.values())
        alias_span = (
            fixed_aliases[0]
            if len(fixed_aliases) == 1
            else f"{fixed_aliases[0]}-{fixed_aliases[-1].removeprefix('Candidate ')}"
        )
        manifest = {
            "status": status,
            "purpose": "FORMAT_PILOT_NOT_UNBLINDED" if len(args.packet) == 1 else "OFFICIAL_BLINDED_JUDGING",
            "mode": args.mode,
            "packet_id": packet_id,
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "transport": (
                "Official Anthropic Messages API"
                if official_transport
                else "FactChat native Claude Messages API"
            ),
            "endpoint": args.endpoint,
            "api_key_env": args.api_key_env,
            "api_key_recorded": False,
            "requested_model": args.model,
            "returned_model": final_envelope.get("model") if final_envelope else None,
            "max_output_tokens": args.max_output_tokens,
            "thinking_parameter": "omitted",
            "temperature_override": None,
            "top_p_override": None,
            "external_tools": "disabled_except_required_score_submission_tool",
            "response_format": "forced_single_tool_call_with_fixed_candidate_objects_plus_strict_local_validation",
            "provider_strict_tool_schema": official_transport,
            "provider_schema_adapter": (
                f"compact fixed-alias envelope for {alias_span}; each candidate's score/flag/rationale arrays are expanded and exact candidate count, aliases, ranges, patterns, lengths, and uniqueness are enforced by the strict local validator"
                if direct_compact_main
                else f"canonical candidate array for {alias_span}; provider-unsupported constraints removed and exact candidate count, aliases, ranges, patterns, lengths, and uniqueness enforced by the strict local validator"
                if official_transport
                else f"{alias_span} encoded as {len(fixed_aliases)} required object properties, then losslessly normalized to the canonical array; score ranges/patterns/lengths remain enforced locally"
            ),
            "provider_tool_schema_sha256": sha256_file(packet_output / "provider_tool_schema.json"),
            "request_payload_sha256": sha256_bytes(request_bytes),
            "request_bytes": len(request_bytes),
            "source_files": source_hashes,
            "validator_sha256": validator_sha,
            "attempts": attempts,
        }
        (packet_output / "run_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        usage = final_envelope.get("usage", {}) if final_envelope else {}
        run_summary.append(
            {
                "packet_id": packet_id,
                "status": status,
                "attempts": len(attempts),
                "returned_model": manifest["returned_model"],
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens"),
                "derived_rows": len(derived_rows),
            }
        )
        print(json.dumps(run_summary[-1], ensure_ascii=False))
        if accepted is None:
            raise SystemExit(2)

    (output_root / "run_summary.json").write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
