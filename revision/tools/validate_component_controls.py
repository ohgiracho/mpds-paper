from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ROOT / "conditions"
if str(CONDITIONS) not in sys.path:
    sys.path.insert(0, str(CONDITIONS))

from baseline_common import citation_check, pool_with_prefix, read_text, valid_ids  # noqa: E402
from run_condition import EXPECTED_CALLS, knowledge_paths, load_case  # noqa: E402
import run_sair  # noqa: E402
import run_ses  # noqa: E402


RUBRIC_LEAK_TERMS = (
    "integrative hypothesis quality",
    "ihq",
    "idea novelty",
    "mechanistic originality",
    "cross-perspective integration",
    "scientific correctness",
    "physical plausibility",
    "falsifiability",
    "actionability",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="No-API fairness preflight for SAIR and SES")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "component_controls_core10_v2.json",
    )
    return parser.parse_args()


def assert_no_rubric_leak(prompt: str, label: str) -> None:
    lowered = prompt.lower()
    found = [term for term in RUBRIC_LEAK_TERMS if term in lowered]
    if found:
        raise AssertionError(f"{label} contains judge-rubric coaching terms: {found}")


def main() -> int:
    args = parse_args()
    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    repo = ROOT.parent / "mpds_github_prep" / "github_repo"
    selected_cases = config["selected_case_ids"]

    sentinel_args = SimpleNamespace(
        simulation_date="2019",
        debate_topic="SENTINEL_TOPIC",
    )
    sentinel_context = "SENTINEL_CONTEXT"
    sentinel_evidence = "SENTINEL_EVIDENCE"
    sentinel_answer = (
        "Draft Scientist A [ID: 1], Scientist A [ID: 2], and Scientist B [ID: 3]."
    )
    sentinel_critique = "SENTINEL_CRITIQUE"

    sair_prompts = {
        "initial": run_sair.initial_prompt(sentinel_args, sentinel_context, sentinel_evidence),
        "critique_1": run_sair.critique_prompt(sentinel_args, sentinel_context, sentinel_answer, 1),
        "revision_1": run_sair.revision_prompt(
            sentinel_args, sentinel_context, sentinel_answer, sentinel_critique, 1, sentinel_evidence
        ),
        "critique_2": run_sair.critique_prompt(sentinel_args, sentinel_context, sentinel_answer, 2),
        "revision_2": run_sair.revision_prompt(
            sentinel_args, sentinel_context, sentinel_answer, sentinel_critique, 2, sentinel_evidence
        ),
        "critique_3": run_sair.critique_prompt(sentinel_args, sentinel_context, sentinel_answer, 3),
        "revision_3": run_sair.revision_prompt(
            sentinel_args, sentinel_context, sentinel_answer, sentinel_critique, 3, None
        ),
    }
    expected_sair_evidence_stages = {"initial", "revision_1", "revision_2"}
    observed_sair_evidence_stages = {
        stage for stage, prompt in sair_prompts.items() if sentinel_evidence in prompt
    }
    if observed_sair_evidence_stages != expected_sair_evidence_stages:
        raise AssertionError(
            f"Unexpected SAIR evidence schedule: {sorted(observed_sair_evidence_stages)}"
        )

    ses_prompts = {
        "scientist_a": run_ses.independent_prompt(
            sentinel_args, sentinel_context, sentinel_evidence, "A"
        ),
        "scientist_b": run_ses.independent_prompt(
            sentinel_args, sentinel_context, sentinel_evidence, "B"
        ),
        "synthesis": run_ses.synthesis_prompt(
            sentinel_args, sentinel_context, sentinel_answer, sentinel_answer
        ),
    }
    if sentinel_evidence not in ses_prompts["scientist_a"]:
        raise AssertionError("SES Scientist A prompt is missing its evidence")
    if sentinel_evidence not in ses_prompts["scientist_b"]:
        raise AssertionError("SES Scientist B prompt is missing its evidence")
    if sentinel_evidence in ses_prompts["synthesis"]:
        raise AssertionError("SES synthesis unexpectedly contains raw evidence")

    for label, prompt in {**sair_prompts, **ses_prompts}.items():
        assert_no_rubric_leak(prompt, label)

    validation_fixture = citation_check(
        "Scientist A [ID: 1] and Scientist A [ID: 2] support this; "
        "Scientist B [ID: 3] supports that.",
        {"A:1", "A:2", "B:3"},
        minimum=3,
        required_pools=("A", "B"),
    )
    if not validation_fixture["passed"]:
        raise AssertionError(f"Valid scoped-citation fixture failed: {validation_fixture}")
    invalid_fixtures = (
        "Scientist A [ID: 1], [ID: 2], Scientist B [ID: 3]",
        "Scientist A [ID: 1], Scientist A [ID: 2], Scientist A [ID: 1]",
        "Scientist A [ID: 1], Scientist A [ID: 2], Scientist B [ID: 99]",
        "[A-ID: 1], [A-ID: 2], [B-ID: 3]",
        "Scientist A [ID: 1, 2], Scientist B [ID: 3]",
    )
    for fixture in invalid_fixtures:
        if citation_check(
            fixture,
            {"A:1", "A:2", "B:3"},
            minimum=3,
            required_pools=("A", "B"),
        )["passed"]:
            raise AssertionError(f"Invalid citation fixture passed: {fixture}")

    case_rows = []
    for case_id in selected_cases:
        record = load_case(repo, case_id)
        knowledge_a, knowledge_b, hashes = knowledge_paths(ROOT / "audit", case_id)
        raw_a, raw_b = read_text(knowledge_a), read_text(knowledge_b)
        scoped_a, scoped_b = pool_with_prefix(raw_a, "A"), pool_with_prefix(raw_b, "B")
        if "Scientist A ID:" not in scoped_a or "Scientist B ID:" not in scoped_b:
            raise AssertionError(f"Case {case_id} evidence namespacing failed")
        ids_a, ids_b = valid_ids(raw_a, "A"), valid_ids(raw_b, "B")
        if not ids_a or not ids_b:
            raise AssertionError(f"Case {case_id} has an empty evidence pool")
        source_chars = len(raw_a) + len(raw_b)
        case_rows.append(
            {
                "case_id": case_id,
                "case_name": record["case_name"],
                "records_a": len(ids_a),
                "records_b": len(ids_b),
                "source_characters_a_plus_b": source_chars,
                "old_sair_nominal_source_character_exposure": 7 * source_chars,
                "revised_sair_nominal_source_character_exposure": 3 * source_chars,
                "ds_nominal_source_character_exposure": 3 * source_chars,
                "ses_nominal_source_character_exposure": source_chars,
                "knowledge_hash_a": hashes["A"],
                "knowledge_hash_b": hashes["B"],
            }
        )

    result = {
        "status": "PASS",
        "api_calls_made": 0,
        "config": str(args.config.resolve()),
        "case_count": len(case_rows),
        "replicates_per_case": len(config["target_replicates"]),
        "planned_runs": len(case_rows) * len(config["target_replicates"]) * 2,
        "planned_nominal_calls": {
            "sair": len(case_rows) * len(config["target_replicates"]) * EXPECTED_CALLS["sair"],
            "ses": len(case_rows) * len(config["target_replicates"]) * EXPECTED_CALLS["ses"],
        },
        "sair_evidence_stages": sorted(observed_sair_evidence_stages),
        "ses_raw_evidence_stages": ["scientist_a", "scientist_b"],
        "rubric_coaching_terms_found": [],
        "citation_validation_fixtures": "PASS",
        "case_checks": case_rows,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
