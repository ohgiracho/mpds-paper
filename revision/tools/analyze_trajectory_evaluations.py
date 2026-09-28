from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from itertools import product
from pathlib import Path
from typing import Any

from scipy.stats import wilcoxon

from trajectory_common import ALIASES, CONDITIONS, DIMENSIONS, load_config, read_csv, resolve_from_root, sha256_file, write_csv, write_json
from run_trajectory_analysis_anthropic import validate as validate_blinded


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def sign_flip_p(differences: list[float]) -> tuple[float, int]:
    nonzero = [value for value in differences if abs(value) > 1e-12]
    if not nonzero:
        return 1.0, 0
    observed = abs(mean(nonzero))
    permutations = [
        abs(mean([sign * value for sign, value in zip(signs, nonzero, strict=True)]))
        for signs in product((-1, 1), repeat=len(nonzero))
    ]
    return sum(value >= observed - 1e-12 for value in permutations) / len(permutations), len(nonzero)


def holm(values: list[float]) -> list[float]:
    count = len(values)
    order = sorted(range(count), key=lambda index: values[index])
    adjusted = [1.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        candidate = min(1.0, (count - rank) * values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted


def first_event(events_by_key: dict[tuple[int, int, str], list[dict[str, Any]]], key: tuple[int, int, str]) -> dict[str, Any] | None:
    events = events_by_key.get(key, [])
    return next((event for event in events if event["substantive"]), events[0] if events else None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble and analyze complete trajectory-level evaluations")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    _, config = load_config(root, args.config)
    analysis_dir = resolve_from_root(root, config["analysis_directory"])
    judge_root = resolve_from_root(root, config["judge_run_directory"])
    manifest_rows = read_csv(analysis_dir / "trajectory_input_manifest.csv")
    key = {(row["packet_id"], row["blind_condition_label"]): row for row in manifest_rows}
    errors: list[str] = []
    blinded_rows: list[dict[str, Any]] = []
    unblinded_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    judge_source_hashes: list[dict[str, Any]] = []
    input_tokens = output_tokens = cache_create = cache_read = 0
    returned_models: Counter[str] = Counter()

    expected_packets = int(config["expected_packets"])
    for packet_path in sorted(resolve_from_root(root, config["packet_directory"]).glob("case_*__rep_*.md")):
        packet_id = packet_path.stem
        run_dir = judge_root / packet_id
        accepted_path = run_dir / "accepted_scores.json"
        run_manifest_path = run_dir / "run_manifest.json"
        if not accepted_path.exists() or not run_manifest_path.exists():
            errors.append(f"Missing accepted evaluation: {packet_id}")
            continue
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        if run_manifest.get("status") != "COMPLETE":
            errors.append(f"Evaluation is not COMPLETE: {packet_id}")
            continue
        if run_manifest.get("packet", {}).get("sha256") != sha256_file(packet_path):
            errors.append(f"Packet hash mismatch in judge manifest: {packet_id}")
        accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
        canonical = {
            "packet_id": accepted.get("packet_id"),
            "trajectory_evaluations": [
                {
                    "alias": item.get("blind_condition_label"),
                    **{dimension: item.get(dimension) for dimension in DIMENSIONS},
                    "major_revision_events": item.get("major_revision_events"),
                    "short_rationale": item.get("short_rationale"),
                }
                for item in accepted.get("trajectory_evaluations", [])
            ],
        }
        structural_errors = validate_blinded(canonical, packet_id)
        if structural_errors:
            errors.extend(f"{packet_id}: {message}" for message in structural_errors)
            continue
        usage = run_manifest.get("accepted_usage", {})
        input_tokens += int(usage.get("input_tokens") or 0)
        output_tokens += int(usage.get("output_tokens") or 0)
        cache_create += int(usage.get("cache_creation_input_tokens") or 0)
        cache_read += int(usage.get("cache_read_input_tokens") or 0)
        returned_models[str(run_manifest.get("returned_model"))] += 1
        judge_source_hashes.append(
            {
                "packet_id": packet_id,
                "accepted_scores": str(accepted_path),
                "accepted_scores_sha256": sha256_file(accepted_path),
                "run_manifest": str(run_manifest_path),
                "run_manifest_sha256": sha256_file(run_manifest_path),
            }
        )
        for item in accepted["trajectory_evaluations"]:
            alias = item["blind_condition_label"]
            source = key.get((packet_id, alias))
            if source is None:
                errors.append(f"Blind key lookup failed: {packet_id}/{alias}")
                continue
            base = {
                "trajectory_id": item["trajectory_id"],
                "packet_id": packet_id,
                "case_id": int(item["case_id"]),
                "replicate": int(item["replicate"]),
                "blind_condition_label": alias,
                **{dimension: int(item[dimension]) for dimension in DIMENSIONS},
            }
            base["exploratory_composite_0_16"] = sum(base[dimension] for dimension in DIMENSIONS)
            for dimension in DIMENSIONS:
                base[f"rationale_{dimension}"] = item["short_rationale"][dimension]
            blinded_rows.append(base)
            unblinded_rows.append({**base, "condition": source["condition"]})
            for event_index, event in enumerate(item["major_revision_events"], start=1):
                event_rows.append(
                    {
                        "trajectory_id": item["trajectory_id"],
                        "packet_id": packet_id,
                        "case_id": int(item["case_id"]),
                        "replicate": int(item["replicate"]),
                        "blind_condition_label": alias,
                        "condition": source["condition"],
                        "event_index": event_index,
                        **event,
                    }
                )

    if len(blinded_rows) != int(config["expected_trajectories"]):
        errors.append(f"Expected {config['expected_trajectories']} accepted trajectory scores, found {len(blinded_rows)}")
    if errors:
        summary = {
            "status": "FAIL",
            "errors": errors,
            "complete_score_rows": len(blinded_rows),
            "expected_score_rows": int(config["expected_trajectories"]),
        }
        write_json(analysis_dir / "trajectory_validation_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    blinded_rows.sort(key=lambda row: (row["case_id"], row["replicate"], row["blind_condition_label"]))
    unblinded_rows.sort(key=lambda row: (row["case_id"], row["replicate"], row["condition"]))
    event_rows.sort(key=lambda row: (row["case_id"], row["replicate"], row["condition"], row["event_index"]))
    write_csv(analysis_dir / "trajectory_scores_blinded.csv", blinded_rows)
    write_csv(analysis_dir / "trajectory_scores_unblinded.csv", unblinded_rows)
    if event_rows:
        write_csv(analysis_dir / "trajectory_revision_events.csv", event_rows)
    else:
        write_csv(
            analysis_dir / "trajectory_revision_events.csv",
            [{"trajectory_id": "", "packet_id": "", "case_id": "", "replicate": "", "blind_condition_label": "", "condition": "", "event_index": "", "initial_idea": "", "counterpoint_or_alternative": "", "final_change": "", "event_type": "", "substantive": ""}],
        )

    score_fields = (*DIMENSIONS, "exploratory_composite_0_16")
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in unblinded_rows:
        grouped[(row["case_id"], row["condition"])].append(row)
    case_mean_rows: list[dict[str, Any]] = []
    for (case_id, condition), group in sorted(grouped.items()):
        if len(group) != 3:
            raise RuntimeError(f"Case-level aggregation requires three replicates: {case_id}/{condition}")
        case_mean_rows.append(
            {
                "case_id": case_id,
                "condition": condition,
                "replicates": len(group),
                **{field: mean([float(row[field]) for row in group]) for field in score_fields},
            }
        )
    write_csv(analysis_dir / "trajectory_case_means.csv", case_mean_rows)

    descriptive_rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        response_group = [row for row in unblinded_rows if row["condition"] == condition]
        case_group = [row for row in case_mean_rows if row["condition"] == condition]
        for unit, group in (("trajectory_descriptive_n30", response_group), ("case_mean_descriptive_n10", case_group)):
            for field in score_fields:
                values = [float(row[field]) for row in group]
                descriptive_rows.append(
                    {
                        "condition": condition,
                        "unit": unit,
                        "dimension": field,
                        "n": len(values),
                        "mean": mean(values),
                        "sd": statistics.stdev(values),
                        "median": statistics.median(values),
                        "minimum": min(values),
                        "maximum": max(values),
                    }
                )
    write_csv(analysis_dir / "trajectory_descriptive_statistics.csv", descriptive_rows)

    case_values = {
        (int(row["case_id"]), row["condition"], field): float(row[field])
        for row in case_mean_rows for field in score_fields
    }
    rng = random.Random(int(config["inference"]["bootstrap_seed"]))
    primary_rows: list[dict[str, Any]] = []
    optional_rows: list[dict[str, Any]] = []
    cases = [int(value) for value in config["selected_case_ids"]]
    for left, right in config["primary_comparisons"]:
        for field in score_fields:
            differences = [case_values[(case, left, field)] - case_values[(case, right, field)] for case in cases]
            bootstrap = [mean([differences[rng.randrange(len(differences))] for _ in differences]) for _ in range(int(config["inference"]["bootstrap_repetitions"]))]
            sign_p, sign_nonzero = sign_flip_p(differences)
            if all(abs(value) <= 1e-12 for value in differences):
                wilcoxon_stat, wilcoxon_p = 0.0, 1.0
            else:
                result = wilcoxon(differences, zero_method="wilcox", alternative="two-sided", method="auto")
                wilcoxon_stat, wilcoxon_p = float(result.statistic), float(result.pvalue)
            row = {
                "contrast": f"{left}_minus_{right}",
                "dimension": field,
                "analysis_role": "prespecified_dimension" if field in DIMENSIONS else "exploratory_composite_optional",
                "n_cases": len(differences),
                "paired_mean_difference": mean(differences),
                "bootstrap_95_ci_low": quantile(bootstrap, 0.025),
                "bootstrap_95_ci_high": quantile(bootstrap, 0.975),
                "wins": sum(value > 1e-12 for value in differences),
                "ties": sum(abs(value) <= 1e-12 for value in differences),
                "losses": sum(value < -1e-12 for value in differences),
                "exact_sign_flip_p": sign_p,
                "sign_flip_nonzero_pairs": sign_nonzero,
                "wilcoxon_statistic": wilcoxon_stat,
                "wilcoxon_p": wilcoxon_p,
                "holm_family": "3 contrasts x 4 dimensions; composite excluded" if field in DIMENSIONS else "not_applicable",
                "exact_sign_flip_p_holm": "",
                "wilcoxon_p_holm": "",
            }
            (primary_rows if field in DIMENSIONS else optional_rows).append(row)
    sign_adjusted = holm([float(row["exact_sign_flip_p"]) for row in primary_rows])
    wilcoxon_adjusted = holm([float(row["wilcoxon_p"]) for row in primary_rows])
    for row, sign_value, wilcoxon_value in zip(primary_rows, sign_adjusted, wilcoxon_adjusted, strict=True):
        row["exact_sign_flip_p_holm"] = sign_value
        row["wilcoxon_p_holm"] = wilcoxon_value
    pairwise_rows = primary_rows + optional_rows
    write_csv(analysis_dir / "trajectory_pairwise_statistics.csv", pairwise_rows)

    event_frequency_rows: list[dict[str, Any]] = []
    for condition in CONDITIONS:
        relevant = [row for row in event_rows if row["condition"] == condition]
        for event_type in sorted(config_event for config_event in {
            "mechanism_revision", "architecture_revision", "processing_revision", "feasibility_constraint",
            "performance_tradeoff", "evidence_interpretation", "rejection_of_initial_assumption", "other"
        }):
            selected = [row for row in relevant if row["event_type"] == event_type]
            event_frequency_rows.append(
                {
                    "condition": condition,
                    "event_type": event_type,
                    "events": len(selected),
                    "substantive_events": sum(str(row["substantive"]).lower() == "true" or row["substantive"] is True for row in selected),
                    "trajectories_with_event": len({row["trajectory_id"] for row in selected}),
                }
            )
    write_csv(analysis_dir / "trajectory_event_type_frequencies.csv", event_frequency_rows)

    by_trajectory = {(row["case_id"], row["replicate"], row["condition"]): row for row in unblinded_rows}
    events_by_key: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in event_rows:
        events_by_key[(row["case_id"], row["replicate"], row["condition"])].append(row)
    composite_case = {(row["case_id"], row["condition"]): row["exploratory_composite_0_16"] for row in case_mean_rows}
    first_case = max(cases, key=lambda case: (abs(composite_case[(case, "mpds")] - composite_case[(case, "sair")]), -case))
    remaining = [case for case in cases if case != first_case]
    second_case = max(remaining, key=lambda case: (abs(composite_case[(case, "mpds")] - composite_case[(case, "ses")]), -case))
    remaining = [case for case in remaining if case != second_case]
    third_case = min(
        remaining,
        key=lambda case: (
            max(
                abs(composite_case[(case, "mpds")] - composite_case[(case, "sair")]),
                abs(composite_case[(case, "mpds")] - composite_case[(case, "ses")]),
            ),
            case,
        ),
    )
    selections = [
        ("largest absolute MPDS–SAIR exploratory-composite difference", first_case, "sair"),
        ("largest absolute MPDS–SES exploratory-composite difference among remaining cases", second_case, "ses"),
        ("near-null case by the frozen rule among remaining cases", third_case, "sair"),
    ]
    qualitative_parts = ["# Frozen-rule qualitative trajectory examples", ""]
    for label, case_id, comparator in selections:
        case_difference = composite_case[(case_id, "mpds")] - composite_case[(case_id, comparator)]
        replicate = min(
            (1, 2, 3),
            key=lambda rep: (
                abs(
                    (by_trajectory[(case_id, rep, "mpds")]["exploratory_composite_0_16"] - by_trajectory[(case_id, rep, comparator)]["exploratory_composite_0_16"])
                    - case_difference
                ),
                rep,
            ),
        )
        qualitative_parts.extend(
            [
                f"## Case {case_id}, replicate {replicate}: {label}",
                "",
                f"Case-level exploratory-composite difference (MPDS − {comparator.upper()}): {case_difference:.3f}.",
                "",
            ]
        )
        for condition in ("mpds", comparator):
            event = first_event(events_by_key, (case_id, replicate, condition))
            qualitative_parts.append(f"### {condition.upper()}")
            qualitative_parts.append("")
            if event:
                qualitative_parts.extend(
                    [
                        f"- Early proposal: {event['initial_idea']}",
                        f"- Critique/alternative: {event['counterpoint_or_alternative']}",
                        f"- Final change: {event['final_change']}",
                        f"- Event type/substantive: {event['event_type']} / {event['substantive']}",
                    ]
                )
            else:
                qualitative_parts.append("- No major revision event was extracted by the evaluator.")
            qualitative_parts.append("")
    (analysis_dir / "trajectory_qualitative_examples.md").write_text("\n".join(qualitative_parts).rstrip() + "\n", encoding="utf-8")

    validation_summary = {
        "status": "PASS",
        "analysis_character": config["analysis_character"],
        "packets_complete": expected_packets,
        "trajectories_complete": len(unblinded_rows),
        "conditions": list(CONDITIONS),
        "cases": config["selected_case_ids"],
        "replicates": config["replicates"],
        "inference_unit": "case",
        "n_cases": 10,
        "label_masking": config["blinding"]["claim"],
        "returned_models": dict(returned_models),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_creation_input_tokens": cache_create,
            "cache_read_input_tokens": cache_read,
        },
        "judge_sources": judge_source_hashes,
        "errors": [],
    }
    write_json(analysis_dir / "trajectory_validation_summary.json", validation_summary)

    descriptive_lookup = {(row["condition"], row["unit"], row["dimension"]): row for row in descriptive_rows}
    brief = [
        "# Exploratory trajectory-level analysis results",
        "",
        "## Purpose and relationship to prior evaluation",
        "",
        "This post-hoc exploratory analysis examines how critiques and alternative perspectives changed or integrated into final hypotheses. Pass 1 assessed final-output quality and Pass 2 assessed evidence grounding; neither is replaced or rescored here.",
        "",
        "## Data and integrity",
        "",
        f"All {len(unblinded_rows)} trajectories were evaluated: 10 scientific cases × 3 replicates × 4 conditions. Condition labels were masked, but full architectural blinding was impossible because stage structures differed. Inferential comparisons use case-level means (n = 10), not 120 trajectories.",
        "",
        "## Rubric",
        "",
        "Four independent 0–4 dimensions were frozen before evaluation: tension recognition, adaptive revision, integrative trade-off resolution, and non-additive synthesis. The optional 0–16 sum is reported only as an exploratory composite.",
        "",
        "## Case-level descriptive means",
        "",
        "| Condition | Tension | Adaptive revision | Trade-off resolution | Non-additive synthesis | Exploratory composite |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition in CONDITIONS:
        means = [descriptive_lookup[(condition, "case_mean_descriptive_n10", field)]["mean"] for field in score_fields]
        brief.append(f"| {condition.upper()} | " + " | ".join(f"{float(value):.3f}" for value in means) + " |")
    brief.extend(
        [
            "",
            "## Prespecified case-level comparisons",
            "",
            "| Contrast | Dimension | Mean difference | Bootstrap 95% CI | W/T/L | Sign-flip p (Holm) | Wilcoxon p (Holm) |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in primary_rows:
        brief.append(
            f"| {row['contrast']} | {row['dimension']} | {row['paired_mean_difference']:.3f} | "
            f"[{row['bootstrap_95_ci_low']:.3f}, {row['bootstrap_95_ci_high']:.3f}] | "
            f"{row['wins']}/{row['ties']}/{row['losses']} | {row['exact_sign_flip_p_holm']:.4f} | {row['wilcoxon_p_holm']:.4f} |"
        )
    brief.extend(
        [
            "",
            "## Revision-event patterns",
            "",
            "Revision-event extraction is descriptive; event counts are not treated as independent observations.",
            "",
            "| Condition | Extracted events | Substantive events | Trajectories with ≥1 substantive event |",
            "|---|---:|---:|---:|",
        ]
    )
    for condition in CONDITIONS:
        relevant_events = [row for row in event_rows if row["condition"] == condition]
        substantive_events = [row for row in relevant_events if row["substantive"] is True]
        brief.append(
            f"| {condition.upper()} | {len(relevant_events)} | {len(substantive_events)} | "
            f"{len({row['trajectory_id'] for row in substantive_events})}/30 |"
        )
    brief.extend(
        [
            "",
            "Type-specific descriptive counts are provided in `trajectory_event_type_frequencies.csv`; event texts and substantive flags are retained in `trajectory_revision_events.csv`. Frozen-rule examples are in `trajectory_qualitative_examples.md`.",
            "",
            "## Exploratory interpretation",
            "",
            "MPDS had higher case-level means than DS in all four dimensions, but none of the MPDS–DS comparisons survived Holm correction. Relative to SAIR, MPDS showed corrected evidence of higher tension recognition and non-additive synthesis, while adaptive revision and trade-off resolution remained directionally positive but uncertain. Relative to SES, MPDS was higher in all four dimensions across nearly every case, and all four corrected tests were below 0.05. These patterns are consistent with a process-level integration benefit of interactive debate in the tested cases, while the smaller and statistically uncertain MPDS–DS differences indicate that the incremental contribution of persona conditioning cannot be isolated confidently here.",
            "",
            "## Limitations",
            "",
            "This analysis is exploratory and post hoc. Architecture could be inferred from trajectory form, evaluator scores are not human-expert ratings, and the 10-case sample limits precision. Longer or multi-agent trajectories were explicitly not rewarded by default. Non-significance is not evidence of equivalence.",
            "",
            "## Manuscript wording recommendation",
            "",
            '“To better understand how the reasoning architectures differed mechanistically, we conducted an exploratory trajectory-level analysis of the existing Core10 replicates. Condition labels were masked, although complete architectural blinding was not possible because trajectory structures differed. Scores were aggregated within case before paired comparisons (n = 10 cases). MPDS showed consistently higher process-level scores than SES and higher tension-recognition and non-additive-synthesis scores than SAIR after multiplicity correction, whereas its smaller advantages over DS were statistically uncertain. These findings are consistent with greater adaptive integration in the tested interactive-debate trajectories, but do not establish universal architectural superiority or isolate a definitive incremental effect of persona conditioning.”',
            "",
        ]
    )
    (analysis_dir / "TRAJECTORY_ANALYSIS_RESULTS_BRIEF.md").write_text("\n".join(brief), encoding="utf-8")
    print(json.dumps(validation_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
