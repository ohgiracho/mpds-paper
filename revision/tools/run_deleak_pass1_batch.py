from __future__ import annotations

from pathlib import Path

import run_litm_pass1_batch as frozen_batch


frozen_batch.CONFIG_ID = "independent_judge_sonnet5_pass1_deleak_pair_v1"


def verify_frozen_inputs(root: Path) -> None:
    manifest_path = root / "evaluation" / "deleak_pass1_input_integrity_manifest_v1.json"
    manifest = frozen_batch.read_json(manifest_path)
    if manifest.get("status") != "FROZEN_BEFORE_ANY_DELEAK_PASS1_API_CALL":
        raise RuntimeError("De-leaking Pass 1 input manifest is not frozen")
    for group in ("fixed_files", "generation_sources", "packets", "recovery_packets", "transport_dry_run_files"):
        for record in manifest[group]:
            path = (root / str(record["path"])).resolve()
            if not path.is_file() or frozen_batch.sha256_file(path) != record["sha256"]:
                raise RuntimeError(f"Frozen de-leaking Pass 1 input mismatch: {path}")


frozen_batch.verify_frozen_inputs = verify_frozen_inputs


if __name__ == "__main__":
    raise SystemExit(frozen_batch.main())
