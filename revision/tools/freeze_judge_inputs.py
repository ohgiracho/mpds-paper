from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    fixed = [
        root / "evaluation" / "evaluation_rubric_v3.md",
        root / "evaluation" / "judge_prompt_pass1_v1.md",
        root / "evaluation" / "independent_judge_main_output_schema_v3.json",
        root / "evaluation" / "judge_prompt_pass2_evidence_v1.md",
        root / "evaluation" / "evidence_audit_output_schema_v1.json",
        root / "config" / "independent_judge_sonnet5_v1.json",
        root / "tools" / "validate_judge_outputs.py",
    ]
    pass1 = sorted((root / "evaluation" / "blind_packets_core10_n3_v2").glob("case_*__rep_*.md"))
    pass2 = sorted((root / "evaluation" / "evidence_audit_packets_core10_n3_v1").glob("case_*__rep_*.md"))
    if len(pass1) != 30 or len(pass2) != 30:
        raise RuntimeError(f"Expected 30 packets per pass; found pass1={len(pass1)}, pass2={len(pass2)}")

    records = []
    for group, paths in (("fixed", fixed), ("pass1_packet", pass1), ("pass2_packet", pass2)):
        for path in paths:
            if not path.exists():
                raise FileNotFoundError(path)
            records.append(
                {
                    "group": group,
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )

    aggregate_text = "\n".join(f"{item['path']}\t{item['sha256']}" for item in records)
    payload = {
        "manifest_id": "judge_input_integrity_manifest_v1",
        "status": "INPUTS_FROZEN_TRANSPORT_PENDING",
        "frozen_date": "2026-09-13",
        "requested_judge_model": "claude-sonnet-5",
        "pass1_packet_count": len(pass1),
        "pass2_packet_count": len(pass2),
        "file_count": len(records),
        "aggregate_sha256": hashlib.sha256(aggregate_text.encode("utf-8")).hexdigest(),
        "files": records,
    }
    output = root / "evaluation" / "judge_input_integrity_manifest_v1.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "files"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

