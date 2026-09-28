from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def record(root: Path, path: Path) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"Missing recovery input: {path}")
    return {
        "path": os.path.relpath(path.resolve(), root).replace("\\", "/"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "evaluation" / "deleak_target_recovery_input_integrity_manifest_v1.json"
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite frozen recovery manifest: {output}")
    result_root = root / "results" / "deleak_target_recovery_sonnet5_v1"
    if result_root.exists() and list(result_root.glob("*/run_manifest.json")):
        raise RuntimeError("Recovery API calls already exist")
    packet_dir = root / "evaluation" / "blind_packets_deleak_target_recovery_v1"
    packets = sorted(packet_dir.glob("audit_*.md"))
    if len(packets) != 18:
        raise RuntimeError(f"Expected 18 recovery packets, found {len(packets)}")
    key_dir = root / "evaluation" / "deleak_recovery_blind_key_v1_DO_NOT_SHARE"
    summary = json.loads((key_dir / "build_summary.json").read_text(encoding="utf-8"))
    if summary.get("status") != "PASS" or summary.get("body_hash_matches") != 18:
        raise RuntimeError("Recovery packet build has not passed integrity checks")
    fixed = [
        root / "protocol" / "prompt_deleaking_target_recovery_rubric_v1.md",
        root / "protocol" / "deleak_target_recovery_anthropic_v1.md",
        root / "evaluation" / "deleak_target_recovery_prompt_v1.md",
        root / "evaluation" / "deleak_target_recovery_schema_v1.json",
        root / "evaluation" / "deleak_pass1_input_integrity_manifest_v1.json",
        root / "tools" / "run_deleak_target_recovery_anthropic.py",
        root / "tools" / "run_independent_judge_anthropic_v3.py",
        root / "tools" / "freeze_deleak_recovery_inputs.py",
        key_dir / "build_summary.json",
        key_dir / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv",
    ]
    manifest = {
        "status": "FROZEN_BEFORE_ANY_DELEAK_RECOVERY_API_CALL",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "packet_count": 18,
        "model": "claude-sonnet-5",
        "api_calls_made_during_preparation": 0,
        "api_key_recorded": False,
        "fixed_files": [record(root, path) for path in fixed],
        "packets": [record(root, path) for path in packets],
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "packets": len(packets), "api_calls_made": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
