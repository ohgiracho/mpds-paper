from __future__ import annotations

import argparse
import csv
import copy
import hashlib
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

from validate_judge_outputs import validate_evidence, validate_main


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


def parse_json_content(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        candidate = fence.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise ValueError("Response contains no JSON object")
        candidate = candidate[start : end + 1]
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Top-level response is not an object")
    return parsed


def response_text(envelope: dict[str, Any]) -> str:
    try:
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("OpenAI-compatible response has no choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                fragments.append(item["text"])
        return "".join(fragments)
    raise ValueError("Unsupported message content type")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def factchat_response_schema(source_schema: dict[str, Any]) -> dict[str, Any]:
    """Remove validation keywords unsupported by Anthropic structured output.

    Required fields, object closure, and enums remain provider-enforced. Exact
    cardinality, numeric ranges, patterns, lengths, and uniqueness remain
    enforced by validate_judge_outputs.py immediately after receipt.
    """
    adapted = copy.deepcopy(source_schema)

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
    return adapted


def build_messages(root: Path, mode: str, packet: Path) -> tuple[list[dict[str, str]], dict[str, Path]]:
    supplement = root / "evaluation" / "supplementary_evaluation_module_v1.md"
    if mode == "main":
        original_ihq = root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt"
        prompt = root / "evaluation" / "judge_prompt_pass1_v2.md"
        schema = root / "evaluation" / "independent_judge_main_output_schema_v3.json"
        files = {"prompt": prompt, "original_ihq": original_ihq, "supplement": supplement, "schema": schema, "packet": packet}
        user = "\n\n".join(
            [
                "# ORIGINAL PUBLIC GITHUB IHQ RUBRIC — VERBATIM\n" + original_ihq.read_text(encoding="utf-8"),
                "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement.read_text(encoding="utf-8"),
                "# REQUIRED OUTPUT JSON SCHEMA\n" + schema.read_text(encoding="utf-8"),
                "# BLINDED PACKET\n" + packet.read_text(encoding="utf-8"),
            ]
        )
    else:
        prompt = root / "evaluation" / "judge_prompt_pass2_evidence_v2.md"
        schema = root / "evaluation" / "evidence_audit_output_schema_v1.json"
        files = {"prompt": prompt, "supplement": supplement, "schema": schema, "packet": packet}
        user = "\n\n".join(
            [
                "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement.read_text(encoding="utf-8"),
                "# REQUIRED OUTPUT JSON SCHEMA\n" + schema.read_text(encoding="utf-8"),
                "# BLINDED EVIDENCE-AUDIT PACKET\n" + packet.read_text(encoding="utf-8"),
            ]
        )
    return [
        {"role": "system", "content": prompt.read_text(encoding="utf-8")},
        {"role": "user", "content": user},
    ], files


def validate(mode: str, data: dict[str, Any], filename: str) -> tuple[list[str], list[dict[str, Any]]]:
    virtual_path = Path(filename)
    return validate_main(data, virtual_path) if mode == "main" else validate_evidence(data, virtual_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one or more blinded independent-judge packets through Ajou LLM")
    parser.add_argument("--mode", choices=("main", "evidence"), required=True)
    parser.add_argument("--packet", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--max-output-tokens", type=int, default=8000)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--api-key-env", default="AJOU_LLM_API_KEY")
    parser.add_argument("--endpoint-env", default="AJOU_LLM_CHAT_COMPLETIONS_URL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    endpoint = resolve_environment(args.endpoint_env)
    if endpoint != "https://factchat-cloud.mindlogic.ai/v1/gateway/chat/completions/":
        raise RuntimeError(f"Unexpected endpoint in {args.endpoint_env}: {endpoint}")
    api_key = "" if args.dry_run else resolve_environment(args.api_key_env)
    validator_sha = sha256_file(Path(__file__).with_name("validate_judge_outputs.py"))
    run_summary: list[dict[str, Any]] = []

    for packet_arg in args.packet:
        packet = packet_arg.resolve()
        packet_id = packet.stem
        packet_output = output_root / packet_id
        packet_output.mkdir(parents=True, exist_ok=True)
        messages, source_files = build_messages(root, args.mode, packet)
        schema = json.loads(source_files["schema"].read_text(encoding="utf-8"))
        response_format_schema = factchat_response_schema(schema)
        (packet_output / "response_format_schema.json").write_text(
            json.dumps(response_format_schema, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        request_payload = {
            "model": args.model,
            "messages": messages,
            "max_tokens": args.max_output_tokens,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "mpds_pass1_v3" if args.mode == "main" else "mpds_evidence_pass2_v1",
                    "strict": True,
                    "schema": response_format_schema,
                },
            },
        }
        request_bytes = json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        (packet_output / "request_payload.json").write_bytes(request_bytes)
        source_hashes = {name: {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size} for name, path in source_files.items()}
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
                endpoint,
                data=request_bytes,
                method="POST",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    # FactChat rejects Python's default urllib user agent with
                    # HTTP 403 even when the same key/model succeeds otherwise.
                    "User-Agent": "OpenAI/Python 2.0.0",
                },
            )
            record: dict[str, Any] = {"attempt": attempt}
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    response_bytes = response.read()
                    record["http_status"] = response.status
                envelope = json.loads(response_bytes.decode("utf-8"))
                content = response_text(envelope)
                record.update(
                    {
                        "elapsed_seconds": round(time.perf_counter() - attempt_started, 3),
                        "response_sha256": sha256_bytes(response_bytes),
                        "content_sha256": sha256_bytes(content.encode("utf-8")),
                        "usage": envelope.get("usage", {}),
                        "returned_model": envelope.get("model"),
                        "finish_reason": envelope.get("choices", [{}])[0].get("finish_reason"),
                    }
                )
                (packet_output / f"attempt_{attempt:02d}_response.json").write_bytes(response_bytes)
                (packet_output / f"attempt_{attempt:02d}_content.txt").write_text(content, encoding="utf-8")
                parsed = parse_json_content(content)
                errors, derived = validate(args.mode, parsed, f"{packet_id}.json")
                record["validation_errors"] = errors
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
                if exc.code != 429 and not 500 <= exc.code <= 599:
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
            if attempt < args.max_attempts:
                time.sleep(10 * attempt)

        finished = datetime.now(timezone.utc)
        status = "COMPLETE" if accepted is not None else "FAILED"
        if accepted is not None:
            (packet_output / "accepted_scores.json").write_text(json.dumps(accepted, ensure_ascii=False, indent=2), encoding="utf-8")
            write_csv(packet_output / "derived_alias_scores.csv", derived_rows)
        manifest = {
            "status": status,
            "purpose": "FORMAT_PILOT_NOT_UNBLINDED" if len(args.packet) == 1 else "OFFICIAL_BLINDED_JUDGING",
            "mode": args.mode,
            "packet_id": packet_id,
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "endpoint": endpoint,
            "api_key_env": args.api_key_env,
            "api_key_recorded": False,
            "requested_model": args.model,
            "returned_model": final_envelope.get("model") if final_envelope else None,
            "max_output_tokens": args.max_output_tokens,
            "temperature_override": None,
            "top_p_override": None,
            "external_tools": "disabled",
            "http_user_agent": "OpenAI/Python 2.0.0",
            "response_format": "strict_json_schema",
            "response_format_adapter": "unsupported cardinality/range/pattern/length/uniqueness keywords removed; all retained in strict local validator",
            "response_format_schema_sha256": sha256_file(packet_output / "response_format_schema.json"),
            "request_payload_sha256": sha256_bytes(request_bytes),
            "request_bytes": len(request_bytes),
            "source_files": source_hashes,
            "validator_sha256": validator_sha,
            "attempts": attempts,
        }
        (packet_output / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        usage = final_envelope.get("usage", {}) if final_envelope else {}
        run_summary.append(
            {
                "packet_id": packet_id,
                "status": status,
                "attempts": len(attempts),
                "returned_model": manifest["returned_model"],
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "derived_rows": len(derived_rows),
            }
        )
        print(json.dumps(run_summary[-1], ensure_ascii=False))
        if accepted is None:
            raise SystemExit(2)

    (output_root / "run_summary.json").write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
