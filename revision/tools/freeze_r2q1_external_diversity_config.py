from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from corpus_size_common import atomic_write_json, sha256_file


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "r2q1_external_diversity_v1.json"


def main() -> int:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    if data.get("config_id") != "r2q1_external_diversity_v1":
        raise RuntimeError("Unexpected config_id")
    summary = ROOT / "r2q1_external_diversity_inputs_v1" / "evidence" / "retrieval_summary.json"
    if not summary.is_file() or json.loads(summary.read_text(encoding="utf-8")).get("status") != "PASS":
        raise RuntimeError("Evidence retrieval summary is not PASS")
    for case in data["cases"].values():
        for path_key, hash_key in (
            ("source_pdf", "source_pdf_sha256"),
            ("situation", "situation_sha256"),
            ("user_context", "user_context_sha256"),
            ("pool_a", "pool_a_sha256"),
            ("pool_b", "pool_b_sha256"),
        ):
            path = ROOT / case[path_key]
            if not path.is_file():
                raise RuntimeError(f"Missing artifact: {path}")
            actual = sha256_file(path)
            expected = case.get(hash_key)
            if expected not in (None, actual):
                raise RuntimeError(f"Refusing to replace mismatched frozen hash for {path_key}: {path}")
            case[hash_key] = actual
    data["status"] = "INPUTS_AND_EVIDENCE_FROZEN_READY_FOR_PREFLIGHT"
    data["frozen_date"] = date.today().isoformat()
    atomic_write_json(CONFIG, data)
    print(json.dumps({"status": "FROZEN", "config": str(CONFIG), "cases": len(data["cases"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
