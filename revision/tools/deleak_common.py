from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from litm_common import atomic_write_json, read_json, sha256_file


DEFAULT_CONFIG_NAME = "prompt_deleaking_targeted_v2.json"


def load_deleak_config(revision_root: Path, config_path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    path = (config_path or revision_root / "config" / DEFAULT_CONFIG_NAME).resolve()
    return path, read_json(path)


def frozen_schedule(config: dict[str, Any]) -> list[dict[str, int]]:
    return [
        {"case_id": int(item["case_id"]), "replicate_id": int(item["replicate_id"])}
        for item in config["design"]["execution_order"]
    ]


def output_directory(revision_root: Path, config: dict[str, Any], case_id: int, replicate_id: int) -> Path:
    return (
        revision_root
        / str(config["output"]["run_set"])
        / f"case_{case_id:02d}"
        / "deleaked"
        / f"replicate_{replicate_id:02d}"
    )


def manifest_status(directory: Path) -> str:
    path = directory / "run_manifest.json"
    if not path.exists():
        return "MISSING"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status") or "UNKNOWN")
    except (OSError, json.JSONDecodeError):
        return "INVALID"


def litm_gate_status(revision_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    gate = config["execution_gate"]
    status_path = (revision_root / str(gate["dependency"])).resolve()
    required = int(gate["required_complete"])
    complete = 0
    if status_path.exists():
        payload = read_json(status_path)
        complete = int((payload.get("status_counts") or {}).get("COMPLETE") or 0)
    return {
        "status_file": str(status_path),
        "complete": complete,
        "required": required,
        "open": complete >= required,
    }


def assert_litm_gate_open(revision_root: Path, config: dict[str, Any]) -> None:
    gate = litm_gate_status(revision_root, config)
    if not gate["open"]:
        raise SystemExit(
            "Execution blocked: lost-in-the-middle generation must finish first "
            f"({gate['complete']}/{gate['required']} COMPLETE)."
        )


def assert_hash(path: Path, expected: str, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"Frozen file missing ({label}): {path}")
    actual = sha256_file(path)
    if actual.lower() != str(expected).lower():
        raise SystemExit(f"Frozen file hash mismatch ({label}): {path}")


__all__ = [
    "assert_hash",
    "assert_litm_gate_open",
    "atomic_write_json",
    "frozen_schedule",
    "litm_gate_status",
    "load_deleak_config",
    "manifest_status",
    "output_directory",
    "sha256_file",
]
