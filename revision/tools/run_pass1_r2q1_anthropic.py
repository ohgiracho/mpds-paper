from __future__ import annotations

from pathlib import Path
from typing import Any

import run_independent_judge_anthropic_v3 as base
from validate_pass1_r2q1_single import validate_main


base.FIXED_ALIAS_KEYS = {"candidate_a": "Candidate A"}
base.VALIDATOR_PATH = Path(__file__).with_name("validate_pass1_r2q1_single.py")


def build_content(root: Path, mode: str, packet: Path) -> tuple[str, str, dict[str, Path]]:
    if mode != "main":
        raise RuntimeError("The R2 Q1 runner supports Pass 1 main mode only")
    original_ihq = root.parent / "mpds_github_prep" / "github_repo" / "data" / "IHQ rubric" / "IHQ Scoring Rules.txt"
    supplement = root / "evaluation" / "supplementary_evaluation_module_v1.md"
    prompt = root / "evaluation" / "judge_prompt_pass1_r2q1_single_v1.md"
    schema = root / "evaluation" / "independent_judge_main_output_schema_r2q1_single_v1.json"
    files = {"prompt": prompt, "original_ihq": original_ihq, "supplement": supplement, "schema": schema, "packet": packet}
    user = "\n\n".join([
        "# ORIGINAL PUBLIC GITHUB IHQ RUBRIC — VERBATIM\n" + original_ihq.read_text(encoding="utf-8"),
        "# SUPPLEMENTARY REVIEWER-REQUESTED MODULE\n" + supplement.read_text(encoding="utf-8"),
        "# BLINDED REVIEWER-2-Q1 PACKET\n" + packet.read_text(encoding="utf-8"),
        "Submit the complete result by calling the required tool exactly once. Do not return scores as ordinary prose.",
    ])
    return prompt.read_text(encoding="utf-8"), user, files


def validate(mode: str, data: dict[str, Any], filename: str) -> tuple[list[str], list[dict[str, Any]]]:
    if mode != "main":
        return ["The R2 Q1 runner supports Pass 1 main mode only"], []
    return validate_main(data, Path(filename))


base.build_content = build_content
base.validate = validate


if __name__ == "__main__":
    raise SystemExit(base.main())
