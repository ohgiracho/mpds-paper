from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from build_blind_packets import clean_final, sha256_file
from corpus_size_common import atomic_write_json
from run_r2q1_external_diversity_batch import case_material, output_dir, run_id
from validate_r2q1_setup import DEFAULT_CONFIG, REVISION_ROOT, load_config


PACKET_DIR = REVISION_ROOT / "evaluation" / "blind_packets_r2q1_v1"
KEY_DIR = REVISION_ROOT / "evaluation" / "r2q1_pass1_blind_key_v1_DO_NOT_SHARE"
INTEGRITY_PATH = REVISION_ROOT / "evaluation" / "r2q1_pass1_input_integrity_manifest_v1.json"


def packet_id(identifier: str) -> str:
    return "r2q1_" + hashlib.sha256(("r2q1-pass1-frozen-v1|" + identifier).encode()).hexdigest()[:10]


def packet_text(pid: str, simulation_date: str, task: str, context: str, final: str) -> str:
    return f"""# Blinded battery hypothesis evaluation packet {pid}

Simulation date: {simulation_date}

Task: {task}

Problem context supplied to the generating system:

{context.strip()}

Score the anonymous final answer independently using the verbatim public IHQ Scoring Rules and Pass 1 of the supplementary module. Apply only the task and constraints stated above; do not infer an undisclosed source-paper solution or generating system. Return raw dimensions, not a total or ranking.

## Candidate A

{final.strip()}
"""


def main() -> int:
    config = load_config(DEFAULT_CONFIG)
    run_root = REVISION_ROOT / config["output"]["run_set"]
    if PACKET_DIR.exists() or KEY_DIR.exists():
        raise RuntimeError("R2 Q1 Pass 1 packet or key directory already exists; refusing to overwrite")
    PACKET_DIR.mkdir(parents=True); KEY_DIR.mkdir(parents=True)
    rows: list[dict[str, Any]] = []; keys: list[dict[str, Any]] = []
    try:
        for item in config["design"]["execution_order"]:
            identifier, folder = run_id(item), output_dir(run_root, item)
            manifest_path, final_path = folder / "run_manifest.json", folder / "final.txt"
            if not manifest_path.is_file() or not final_path.is_file():
                raise RuntimeError(f"Missing COMPLETE source for {identifier}")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("status") != "COMPLETE" or manifest.get("final_sha256") != sha256_file(final_path):
                raise RuntimeError(f"Invalid source for {identifier}")
            material = case_material(config, item); context_path = Path(material["context"])
            if manifest.get("user_context_sha256") != sha256_file(context_path):
                raise RuntimeError(f"Context hash mismatch: {identifier}")
            cleaned = clean_final(final_path.read_text(encoding="utf-8", errors="replace"))
            if not cleaned:
                raise RuntimeError(f"Empty cleaned final: {identifier}")
            pid = packet_id(identifier); path = PACKET_DIR / f"{pid}.md"
            path.write_text(packet_text(pid, str(material["simulation_date"]), str(material["debate_topic"]), context_path.read_text(encoding="utf-8"), cleaned), encoding="utf-8")
            rows.append({"packet_id": pid, "packet_sha256": sha256_file(path), "packet_bytes": path.stat().st_size, "simulation_date": str(material["simulation_date"]), "source_final_sha256": manifest["final_sha256"], "source_context_sha256": manifest["user_context_sha256"], "cleaned_final_sha256": hashlib.sha256(cleaned.encode()).hexdigest(), "cleaned_final_characters": len(cleaned)})
            case = config["cases"][str(item["case_id"])]
            keys.append({"packet_id": pid, "run_id": identifier, "case_id": item["case_id"], "replicate_id": item["replicate_id"], "problem_class": case["problem_class"], "group_accounting": case["group_accounting"], "source_final": str(final_path)})
    except Exception:
        shutil.rmtree(PACKET_DIR, ignore_errors=True); shutil.rmtree(KEY_DIR, ignore_errors=True); raise
    rows.sort(key=lambda x: x["packet_id"]); keys.sort(key=lambda x: x["packet_id"])
    atomic_write_json(INTEGRITY_PATH, {"status": "FROZEN_READY_FOR_BLINDED_PASS1", "config_id": "independent_judge_sonnet5_pass1_r2q1_v1", "generation_config_sha256": sha256_file(DEFAULT_CONFIG), "expected_packets": 6, "packet_count": len(rows), "candidate_body_policy": "build_blind_packets.clean_final", "packets": rows})
    atomic_write_json(KEY_DIR / "blind_key.json", {"do_not_send_to_judge": True, "mapping": keys})
    print(json.dumps({"status": "PASS" if len(rows) == 6 else "FAIL", "packets": len(rows), "packet_dir": str(PACKET_DIR), "integrity_manifest": str(INTEGRITY_PATH)}, ensure_ascii=False, indent=2))
    return 0 if len(rows) == 6 else 2


if __name__ == "__main__":
    raise SystemExit(main())
