from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def option_value(arguments: list[str], option: str) -> str:
    try:
        index = arguments.index(option)
    except ValueError as exc:
        raise RuntimeError(f"Required forwarded option is missing: {option}") from exc
    if index + 1 >= len(arguments):
        raise RuntimeError(f"Forwarded option has no value: {option}")
    return arguments[index + 1]


def load_source(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("litm_frozen_source_mpds", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import frozen source script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--source-script", type=Path, required=True)
    parser.add_argument("--expected-source-sha256", required=True)
    parser.add_argument("--canonical-persona-a", type=Path, required=True)
    parser.add_argument("--canonical-persona-b", type=Path, required=True)
    parser.add_argument("--self-test", action="store_true")
    args, forwarded = parser.parse_known_args()

    source = args.source_script.resolve()
    if sha256_file(source) != args.expected_source_sha256:
        raise RuntimeError("Frozen MPDS source-script hash mismatch")
    module = load_source(source)
    for name in ("main", "read_text", "build_persona_prompt"):
        if not callable(getattr(module, name, None)):
            raise RuntimeError(f"Frozen source script lacks required callable: {name}")

    debate_a_path = Path(option_value(forwarded, "--knowledge-a")).resolve()
    debate_b_path = Path(option_value(forwarded, "--knowledge-b")).resolve()
    canonical_a_path = args.canonical_persona_a.resolve()
    canonical_b_path = args.canonical_persona_b.resolve()
    for path in (debate_a_path, debate_b_path, canonical_a_path, canonical_b_path):
        if not path.exists():
            raise RuntimeError(f"Required position-control input is missing: {path}")

    debate_a = module.read_text(debate_a_path)
    debate_b = module.read_text(debate_b_path)
    canonical_a = module.read_text(canonical_a_path)
    canonical_b = module.read_text(canonical_b_path)
    original_builder = module.build_persona_prompt
    calls = {"A": 0, "B": 0}

    def controlled_persona_prompt(simulation_date: str, knowledge: str) -> str:
        if knowledge == debate_a:
            calls["A"] += 1
            canonical = canonical_a
        elif knowledge == debate_b:
            calls["B"] += 1
            canonical = canonical_b
        else:
            raise RuntimeError("Persona builder received an unrecognized debate knowledge snapshot")
        return original_builder(simulation_date, canonical)

    module.build_persona_prompt = controlled_persona_prompt
    if args.self_test:
        simulation_date = option_value(forwarded, "--simulation-date")
        prompt_a = controlled_persona_prompt(simulation_date, debate_a)
        prompt_b = controlled_persona_prompt(simulation_date, debate_b)
        if prompt_a != original_builder(simulation_date, canonical_a):
            raise RuntimeError("Persona A prompt is not canonical and invariant")
        if prompt_b != original_builder(simulation_date, canonical_b):
            raise RuntimeError("Persona B prompt is not canonical and invariant")
        if calls != {"A": 1, "B": 1}:
            raise RuntimeError(f"Persona-control self-test call counts are wrong: {calls}")
        print(json.dumps({"status": "PASS", "persona_control": "canonical", "api_calls_made": 0}))
        return 0
    sys.argv = [str(source), *forwarded]
    result = int(module.main())
    if result == 0 and calls != {"A": 1, "B": 1}:
        raise RuntimeError(f"Canonical persona control was not applied exactly once per pool: {calls}")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
