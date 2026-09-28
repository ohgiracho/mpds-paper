from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from scipy import stats

from litm_common import load_config, pool_manifest_path, read_json, write_csv


CITATION_RE = re.compile(r"\[ID\s*:\s*(\d+)\]", flags=re.IGNORECASE)
SCOPED_FINAL_RE = re.compile(r"Scientist\s*([AB])\s*\[ID\s*:\s*(\d+)\]", flags=re.IGNORECASE)
CITATION_GROUP_RE = re.compile(r"\[ID\s*:\s*([^\]]+)\]", flags=re.IGNORECASE)
SCOPED_FINAL_GROUP_RE = re.compile(r"Scientist\s*([AB])\s*\[ID\s*:\s*([^\]]+)\]", flags=re.IGNORECASE)
ANY_ID_BRACKET_RE = re.compile(r"\[ID[^\]]+\]", flags=re.IGNORECASE)
TURN_HEADER_RE = re.compile(r"(?m)^\[(.+?) - Round (\d+)\]\s*$")
POSITIONS = ("front", "middle", "rear")
METRICS = (
    "debate_citation_occurrences",
    "debate_unique_cited_papers",
    "debate_citation_share",
    "debate_block_coverage",
    "final_citation_occurrences",
    "final_unique_cited_papers",
    "final_citation_share",
    "final_block_coverage",
)
COMPARISONS = (
    ("primary", "front_minus_middle", "front", "middle"),
    ("primary", "rear_minus_middle", "rear", "middle"),
    ("secondary", "front_minus_rear", "front", "rear"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze deterministic block-level citation utilization")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--unscoped-policy",
        choices=("fail", "position-only"),
        default="fail",
        help="Default fail-closed v1 behavior, or versioned position-only attribution for bare final citations",
    )
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def extract_final(text: str) -> str:
    marker = "[FINAL SYNTHESIS]"
    if marker not in text:
        raise ValueError("Missing FINAL SYNTHESIS marker")
    final = text.rsplit(marker, 1)[1]
    return final.split("--- Evidence Appendix (Scientist A snapshot) ---", 1)[0].strip()


def extract_debate_turns(text: str) -> dict[str, list[str]]:
    debate_text = text.split("[FINAL SYNTHESIS]", 1)[0]
    matches = list(TURN_HEADER_RE.finditer(debate_text))
    by_round: dict[int, list[str]] = defaultdict(list)
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(debate_text)
        body = debate_text[start:end].split("--- Evidence Appendix", 1)[0]
        by_round[int(match.group(2))].append(body)
    if sorted(by_round) != [1, 2, 3] or any(len(items) != 2 for items in by_round.values()):
        raise ValueError(f"Expected two turns in each of three rounds; found {dict((k, len(v)) for k, v in by_round.items())}")
    return {
        "A": [by_round[round_id][0] for round_id in (1, 2, 3)],
        "B": [by_round[round_id][1] for round_id in (1, 2, 3)],
    }


def membership_lookup(path: Path) -> tuple[dict[int, str], Counter[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    lookup = {int(row["paper_id"]): row["block"] for row in rows}
    if len(rows) != 500 or len(lookup) != 500:
        raise ValueError(f"Expected 500 unique membership rows: {path}")
    return lookup, Counter(row["block"] for row in rows)


def unscoped_position(
    paper_id: int,
    memberships: dict[str, tuple[dict[int, str], Counter[str]]],
    position_by_block: dict[str, str],
) -> str | None:
    positions = []
    for pool in ("A", "B"):
        block = memberships[pool][0].get(paper_id)
        if block is None:
            return None
        positions.append(position_by_block[block])
    return positions[0] if positions[0] == positions[1] else None


def parse_citation_group(content: str) -> tuple[list[int], bool]:
    """Parse the observed numeric-list syntax; never guess at an unknown annotation."""
    cross_pool = bool(re.search(r"\b(?:your ref|opponent's data|in your data)\b", content, re.IGNORECASE))
    cleaned = re.sub(r"\(\s*(?:your ref|opponent's data)\s*\)", "", content, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+in your data\s*$", "", cleaned, flags=re.IGNORECASE)
    ids: list[int] = []
    for item in cleaned.split(","):
        match = re.fullmatch(r"\s*(?:ID\s*:?\s*)?(\d+)\s*", item, flags=re.IGNORECASE)
        if match is None:
            raise ValueError(f"Unrecognized citation-list item: {item!r} in {content!r}")
        ids.append(int(match.group(1)))
    if not ids:
        raise ValueError(f"Empty citation list: {content!r}")
    return ids, cross_pool


def assert_all_id_brackets_parseable(body: str) -> None:
    parsed_spans = {match.span() for match in CITATION_GROUP_RE.finditer(body)}
    for match in ANY_ID_BRACKET_RE.finditer(body):
        if match.span() not in parsed_spans:
            raise ValueError(f"Unrecognized citation bracket: {match.group()!r}")


def exact_sign_flip(values: list[float]) -> float:
    observed = abs(statistics.mean(values))
    outcomes = [
        abs(statistics.mean(sign * value for sign, value in zip(signs, values)))
        for signs in itertools.product((-1, 1), repeat=len(values))
    ]
    return sum(value >= observed - 1e-12 for value in outcomes) / len(outcomes)


def bootstrap_ci(values: list[float], seed: int, draws: int = 20_000) -> tuple[float, float]:
    rng = random.Random(seed)
    estimates = sorted(statistics.mean(rng.choice(values) for _ in values) for _ in range(draws))
    low_index = int(0.025 * (draws - 1))
    high_index = int(0.975 * (draws - 1))
    return estimates[low_index], estimates[high_index]


def holm_adjust(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    adjusted = [0.0] * len(values)
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(values) - rank) * values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def run_self_test() -> int:
    synthetic = """[RUN CONFIG]\n\n[Alpha - Round 1]\nUses [ID: 1] and [ID: 2].\n--- Evidence Appendix ---\n- [ID: 1 | x]\n[Beta - Round 1]\nUses [ID: 3].\n[Alpha - Round 2]\nUses [ID: 2].\n[Beta - Round 2]\nUses [ID: 4].\n[Alpha - Round 3]\nUses [ID: 5].\n[Beta - Round 3]\nUses [ID: 6].\n============================================================\n[FINAL SYNTHESIS]\nScientist A [ID: 2] and Scientist B [ID: 6].\n--- Evidence Appendix (Scientist A snapshot) ---\n"""
    turns = extract_debate_turns(synthetic)
    final = extract_final(synthetic)
    assert [int(value) for body in turns["A"] for value in CITATION_RE.findall(body)] == [1, 2, 2, 5]
    assert [int(value) for body in turns["B"] for value in CITATION_RE.findall(body)] == [3, 4, 6]
    assert [(pool.upper(), int(value)) for pool, value in SCOPED_FINAL_RE.findall(final)] == [("A", 2), ("B", 6)]
    assert parse_citation_group("5, 157") == ([5, 157], False)
    assert parse_citation_group("6, ID: 14, ID: 28, ID 55") == ([6, 14, 28, 55], False)
    assert parse_citation_group("101, 224 in your data") == ([101, 224], True)
    assert parse_citation_group("11 (opponent's data)") == ([11], True)
    assert_all_id_brackets_parseable("Use [ID: 5, 157] and [ID: 2].")
    synthetic_memberships = {"A": ({1: "X"}, Counter(X=1)), "B": ({1: "Y"}, Counter(Y=1))}
    assert unscoped_position(1, synthetic_memberships, {"X": "front", "Y": "front"}) == "front"
    assert unscoped_position(1, synthetic_memberships, {"X": "front", "Y": "middle"}) is None
    print(json.dumps({"status": "PASS", "self_test": True, "api_calls_made": 0}))
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()
    revision_root = Path(__file__).resolve().parents[1]
    config_path, config = load_config(revision_root, args.config)
    run_root = (args.run_root or revision_root / str(config["output"]["run_set"])).resolve()
    output = (args.output_dir or revision_root / "results" / "lost_in_middle_position_control_v1").resolve()
    if output.exists():
        raise SystemExit(f"Refusing to overwrite existing analysis output: {output}")

    raw_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    unscoped_rows: list[dict[str, Any]] = []
    final_position_rows: list[dict[str, Any]] = []
    run_provenance: list[dict[str, Any]] = []
    for case_id in config["design"]["selected_case_ids"]:
        memberships: dict[str, tuple[dict[int, str], Counter[str]]] = {}
        for pool in ("A", "B"):
            manifest_path = pool_manifest_path(revision_root, config, int(case_id), pool)
            memberships[pool] = membership_lookup(manifest_path.parent / "block_membership.csv")
        for ordering in config["design"]["orderings"]:
            position_by_block = {
                block: position
                for position, block in config["position_manipulation"]["rotations"][ordering].items()
            }
            for replicate in config["design"]["replicates"]:
                run_dir = (
                    run_root
                    / f"case_{int(case_id):02d}"
                    / f"order_{ordering}"
                    / f"replicate_{int(replicate):02d}"
                )
                manifest_path = run_dir / "run_manifest.json"
                full_output_path = run_dir / "full_output.txt"
                if not manifest_path.exists() or not full_output_path.exists():
                    raise RuntimeError(f"Missing completed run artifacts: {run_dir}")
                manifest = read_json(manifest_path)
                if manifest.get("status") != "COMPLETE":
                    raise RuntimeError(f"Non-complete run: {run_dir}")
                text = full_output_path.read_text(encoding="utf-8", errors="replace")
                turns = extract_debate_turns(text)
                final = extract_final(text)
                debate_ids: dict[str, list[int]] = {"A": [], "B": []}
                final_ids: dict[str, list[int]] = {"A": [], "B": []}
                unscoped_ids: list[int] = []
                scoped_spans: list[tuple[int, int]] = []
                if args.unscoped_policy == "position-only":
                    for speaker in ("A", "B"):
                        for body in turns[speaker]:
                            assert_all_id_brackets_parseable(body)
                            for match in CITATION_GROUP_RE.finditer(body):
                                ids, cross_pool = parse_citation_group(match.group(1))
                                source_pool = ({"A": "B", "B": "A"}[speaker] if cross_pool else speaker)
                                debate_ids[source_pool].extend(ids)
                    assert_all_id_brackets_parseable(final)
                    for match in SCOPED_FINAL_GROUP_RE.finditer(final):
                        ids, cross_pool = parse_citation_group(match.group(2))
                        if cross_pool:
                            raise RuntimeError(f"Conflicting explicit and cross-pool final citation: {run_dir}")
                        final_ids[match.group(1).upper()].extend(ids)
                        scoped_spans.append(match.span())
                    final_matches = CITATION_GROUP_RE.finditer(final)
                else:
                    debate_ids = {
                        pool: [int(value) for body in turns[pool] for value in CITATION_RE.findall(body)]
                        for pool in ("A", "B")
                    }
                    for match in SCOPED_FINAL_RE.finditer(final):
                        final_ids[match.group(1).upper()].append(int(match.group(2)))
                        scoped_spans.append(match.span())
                    final_matches = CITATION_RE.finditer(final)
                for match in final_matches:
                    if not any(match.start() >= start and match.end() <= end for start, end in scoped_spans):
                        if args.unscoped_policy == "position-only":
                            ids, cross_pool = parse_citation_group(match.group(1))
                            if cross_pool:
                                raise RuntimeError(f"Unscoped final citation with cross-pool annotation: {run_dir}")
                        else:
                            ids = [int(match.group(1))]
                        for paper_id in ids:
                            issue = {
                                "case_id": case_id,
                                "ordering": ordering,
                                "replicate_id": replicate,
                                "stage": "final",
                                "pool": "UNSCOPED",
                                "paper_id": paper_id,
                                "reason": "unscoped_final_citation",
                            }
                            if args.unscoped_policy == "fail":
                                invalid_rows.append(issue)
                            else:
                                position = unscoped_position(paper_id, memberships, position_by_block)
                                if position is None:
                                    invalid_rows.append({**issue, "reason": "unscoped_position_not_unique"})
                                else:
                                    unscoped_ids.append(paper_id)
                                    unscoped_rows.append({
                                        **issue,
                                        "position": position,
                                        "pool_a_block": memberships["A"][0][paper_id],
                                        "pool_b_block": memberships["B"][0][paper_id],
                                        "attribution": "position_only_pool_and_paper_unknown",
                                    })

                for pool in ("A", "B"):
                    lookup, block_sizes = memberships[pool]
                    for stage, ids in (("debate", debate_ids[pool]), ("final", final_ids[pool])):
                        for paper_id in ids:
                            if paper_id not in lookup:
                                invalid_rows.append(
                                    {
                                        "case_id": case_id,
                                        "ordering": ordering,
                                        "replicate_id": replicate,
                                        "stage": stage,
                                        "pool": pool,
                                        "paper_id": paper_id,
                                        "reason": "id_not_in_frozen_pool",
                                    }
                                )
                    valid_debate = [paper_id for paper_id in debate_ids[pool] if paper_id in lookup]
                    valid_final = [paper_id for paper_id in final_ids[pool] if paper_id in lookup]
                    debate_total = len(valid_debate)
                    final_total = len(valid_final)
                    for block in config["design"]["block_labels"]:
                        debate_block = [paper_id for paper_id in valid_debate if lookup[paper_id] == block]
                        final_block = [paper_id for paper_id in valid_final if lookup[paper_id] == block]
                        raw_rows.append(
                            {
                                "case_id": case_id,
                                "ordering": ordering,
                                "replicate_id": replicate,
                                "pool": pool,
                                "block": block,
                                "position": position_by_block[block],
                                "block_records": block_sizes[block],
                                "debate_citation_occurrences": len(debate_block),
                                "debate_unique_cited_papers": len(set(debate_block)),
                                "debate_citation_share": len(debate_block) / debate_total if debate_total else 0.0,
                                "debate_block_coverage": len(set(debate_block)) / block_sizes[block],
                                "final_citation_occurrences": len(final_block),
                                "final_unique_cited_papers": len(set(final_block)),
                                "final_citation_share": len(final_block) / final_total if final_total else 0.0,
                                "final_block_coverage": len(set(final_block)) / block_sizes[block],
                            }
                        )
                if args.unscoped_policy == "position-only":
                    scoped_by_position: dict[str, list[tuple[str, int]]] = {position: [] for position in POSITIONS}
                    bare_by_position: dict[str, list[int]] = {position: [] for position in POSITIONS}
                    for pool in ("A", "B"):
                        lookup = memberships[pool][0]
                        for paper_id in final_ids[pool]:
                            if paper_id in lookup:
                                scoped_by_position[position_by_block[lookup[paper_id]]].append((pool, paper_id))
                    for paper_id in unscoped_ids:
                        position = unscoped_position(paper_id, memberships, position_by_block)
                        if position is not None:
                            bare_by_position[position].append(paper_id)
                    denominator = sum(len(items) for items in scoped_by_position.values()) + len(unscoped_ids)
                    for position in POSITIONS:
                        scoped = scoped_by_position[position]
                        bare = bare_by_position[position]
                        known_papers = set(scoped)
                        unique_counts = [
                            len(known_papers | set(zip(pool_assignment, bare)))
                            for pool_assignment in itertools.product(("A", "B"), repeat=len(bare))
                        ]
                        occurrences = len(scoped) + len(bare)
                        final_position_rows.append({
                            "case_id": case_id,
                            "ordering": ordering,
                            "replicate_id": replicate,
                            "position": position,
                            "final_pooled_citation_occurrences": occurrences,
                            "final_pooled_citation_share": occurrences / denominator if denominator else 0.0,
                            "final_pooled_unique_numeric_ids": len({paper_id for _, paper_id in scoped} | set(bare)),
                            "final_pooled_unique_papers_min": min(unique_counts),
                            "final_pooled_unique_papers_max": max(unique_counts),
                            "scoped_occurrences": len(scoped),
                            "unscoped_position_only_occurrences": len(bare),
                            "total_final_citation_occurrences": denominator,
                        })
                run_provenance.append(
                    {
                        "case_id": case_id,
                        "ordering": ordering,
                        "replicate_id": replicate,
                        "run_id": manifest["run_id"],
                        "full_output_sha256": manifest["full_output_sha256"],
                        "final_sha256": manifest["final_sha256"],
                        "successful_api_calls": manifest["actual_successful_api_calls"],
                        "unscoped_final_citation_occurrences": len(unscoped_ids),
                    }
                )

    if invalid_rows:
        output.mkdir(parents=True)
        write_csv(output / "invalid_or_unscoped_citations.csv", invalid_rows, list(invalid_rows[0]))
        raise RuntimeError(f"Citation mapping validation failed with {len(invalid_rows)} invalid/unscoped citations")
    if len(raw_rows) != 216:
        raise RuntimeError(f"Expected 216 case-order-replicate-pool-block rows, found {len(raw_rows)}")

    output.mkdir(parents=True)
    if args.unscoped_policy == "position-only":
        if not unscoped_rows:
            raise RuntimeError("Position-only policy requested but no bare final citations were found")
        write_csv(output / "position_only_attribution_audit.csv", unscoped_rows, list(unscoped_rows[0]))
        write_csv(output / "final_pooled_position_by_output.csv", final_position_rows, list(final_position_rows[0]))
    write_csv(output / "block_utilization_by_output.csv", raw_rows, list(raw_rows[0]))
    write_csv(output / "run_provenance.csv", run_provenance, list(run_provenance[0]))

    fixed_groups: dict[tuple[int, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in raw_rows:
        fixed_groups[(int(row["case_id"]), row["pool"], row["block"], row["position"])].append(row)
    fixed_rows: list[dict[str, Any]] = []
    for (case_id, pool, block, position), rows in sorted(fixed_groups.items()):
        if len(rows) != 3:
            raise RuntimeError(f"Expected 3 replicates for fixed block cell {(case_id, pool, block, position)}")
        fixed_rows.append(
            {
                "case_id": case_id,
                "pool": pool,
                "block": block,
                "position": position,
                "replicates": 3,
                **{metric: statistics.mean(float(row[metric]) for row in rows) for metric in METRICS},
            }
        )
    write_csv(output / "fixed_block_position_means.csv", fixed_rows, list(fixed_rows[0]))

    case_groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in fixed_rows:
        case_groups[(int(row["case_id"]), row["position"])].append(row)
    case_rows: list[dict[str, Any]] = []
    for (case_id, position), rows in sorted(case_groups.items()):
        if len(rows) != 6:
            raise RuntimeError(f"Expected 6 pool-block units for case {case_id}, {position}")
        case_rows.append(
            {
                "case_id": case_id,
                "position": position,
                "nested_pool_block_units": 6,
                **{metric: statistics.mean(float(row[metric]) for row in rows) for metric in METRICS},
            }
        )
    write_csv(output / "case_position_means_n4.csv", case_rows, list(case_rows[0]))
    lookup = {(int(row["case_id"]), row["position"]): row for row in case_rows}
    cases = sorted({int(row["case_id"]) for row in case_rows})

    comparison_metrics = METRICS[:4] if args.unscoped_policy == "position-only" else METRICS
    comparison_rows: list[dict[str, Any]] = []
    for metric_index, metric in enumerate(comparison_metrics):
        pending: list[dict[str, Any]] = []
        p_values: list[float] = []
        for comparison_index, (tier, label, left, right) in enumerate(COMPARISONS):
            differences = [
                float(lookup[(case_id, left)][metric]) - float(lookup[(case_id, right)][metric])
                for case_id in cases
            ]
            if all(abs(value) < 1e-12 for value in differences):
                wilcoxon_stat, p_value = 0.0, 1.0
            else:
                result = stats.wilcoxon(differences, zero_method="pratt", alternative="two-sided", method="auto")
                wilcoxon_stat, p_value = float(result.statistic), float(result.pvalue)
            low, high = bootstrap_ci(differences, 20260921 + metric_index * 10 + comparison_index)
            pending.append(
                {
                    "metric": metric,
                    "contrast_tier": tier,
                    "comparison": label,
                    "analysis_unit": "case mean; n=4 paired cases",
                    "n_cases": len(cases),
                    "left_mean": statistics.mean(float(lookup[(case_id, left)][metric]) for case_id in cases),
                    "right_mean": statistics.mean(float(lookup[(case_id, right)][metric]) for case_id in cases),
                    "mean_difference": statistics.mean(differences),
                    "bootstrap_95ci_low": low,
                    "bootstrap_95ci_high": high,
                    "wins": sum(value > 0 for value in differences),
                    "ties": sum(value == 0 for value in differences),
                    "losses": sum(value < 0 for value in differences),
                    "wilcoxon_statistic": wilcoxon_stat,
                    "p_value_raw": p_value,
                    "sign_flip_p_exact": exact_sign_flip(differences),
                }
            )
            p_values.append(p_value)
        for row, adjusted in zip(pending, holm_adjust(p_values), strict=True):
            row["p_value_holm_within_metric"] = adjusted
            comparison_rows.append(row)
    write_csv(output / "position_comparisons_case_level.csv", comparison_rows, list(comparison_rows[0]))

    if args.unscoped_policy == "position-only":
        final_metric_names = (
            "final_pooled_citation_occurrences",
            "final_pooled_citation_share",
            "final_pooled_unique_numeric_ids",
            "final_pooled_unique_papers_min",
            "final_pooled_unique_papers_max",
        )
        final_groups: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for row in final_position_rows:
            final_groups[(int(row["case_id"]), row["position"])].append(row)
        final_case_rows: list[dict[str, Any]] = []
        for (case_id, position), rows in sorted(final_groups.items()):
            if len(rows) != 9:
                raise RuntimeError(f"Expected 9 final runs for case-position {(case_id, position)}")
            final_case_rows.append({
                "case_id": case_id,
                "position": position,
                "runs": len(rows),
                **{metric: statistics.mean(float(row[metric]) for row in rows) for metric in final_metric_names},
                "unscoped_position_only_occurrences": sum(int(row["unscoped_position_only_occurrences"]) for row in rows),
            })
        write_csv(output / "final_pooled_case_position_means_n4.csv", final_case_rows, list(final_case_rows[0]))
        final_lookup = {(int(row["case_id"]), row["position"]): row for row in final_case_rows}
        final_comparisons: list[dict[str, Any]] = []
        for metric_index, metric in enumerate(final_metric_names):
            pending: list[dict[str, Any]] = []
            p_values: list[float] = []
            for comparison_index, (tier, label, left, right) in enumerate(COMPARISONS):
                differences = [
                    float(final_lookup[(case_id, left)][metric]) - float(final_lookup[(case_id, right)][metric])
                    for case_id in cases
                ]
                if all(abs(value) < 1e-12 for value in differences):
                    wilcoxon_stat, p_value = 0.0, 1.0
                else:
                    result = stats.wilcoxon(differences, zero_method="pratt", alternative="two-sided", method="auto")
                    wilcoxon_stat, p_value = float(result.statistic), float(result.pvalue)
                low, high = bootstrap_ci(differences, 20260922 + metric_index * 10 + comparison_index)
                pending.append({
                    "metric": metric,
                    "contrast_tier": tier,
                    "comparison": label,
                    "analysis_unit": "case mean; n=4 paired cases",
                    "n_cases": len(cases),
                    "left_mean": statistics.mean(float(final_lookup[(case_id, left)][metric]) for case_id in cases),
                    "right_mean": statistics.mean(float(final_lookup[(case_id, right)][metric]) for case_id in cases),
                    "mean_difference": statistics.mean(differences),
                    "bootstrap_95ci_low": low,
                    "bootstrap_95ci_high": high,
                    "wins": sum(value > 0 for value in differences),
                    "ties": sum(value == 0 for value in differences),
                    "losses": sum(value < 0 for value in differences),
                    "wilcoxon_statistic": wilcoxon_stat,
                    "p_value_raw": p_value,
                    "sign_flip_p_exact": exact_sign_flip(differences),
                })
                p_values.append(p_value)
            for row, adjusted in zip(pending, holm_adjust(p_values), strict=True):
                row["p_value_holm_within_metric"] = adjusted
                final_comparisons.append(row)
        write_csv(output / "final_pooled_position_comparisons_case_level.csv", final_comparisons, list(final_comparisons[0]))

    manifest = {
        "status": "PASS_WITH_POSITION_ONLY_FINAL_ATTRIBUTION" if args.unscoped_policy == "position-only" else "PASS",
        "analysis_version": "v2_grouped_citations_and_position_only_final" if args.unscoped_policy == "position-only" else "v1_fail_closed_default",
        "attribution_protocol": "protocol/litm_citation_attribution_v2.md" if args.unscoped_policy == "position-only" else None,
        "config": str(config_path),
        "runs": len(run_provenance),
        "raw_block_rows": len(raw_rows),
        "fixed_block_position_rows": len(fixed_rows),
        "case_position_rows": len(case_rows),
        "cases": len(cases),
        "invalid_citations": 0,
        "debate_numeric_citation_pointers": sum(int(row["debate_citation_occurrences"]) for row in raw_rows),
        "final_numeric_citation_pointers": sum(int(row["final_pooled_citation_occurrences"]) for row in final_position_rows) if final_position_rows else sum(int(row["final_citation_occurrences"]) for row in raw_rows),
        "unscoped_final_citation_occurrences": len(unscoped_rows),
        "unscoped_policy": args.unscoped_policy,
        "final_pool_specific_metrics": "scoped citations only; incomplete when unscoped occurrences > 0" if unscoped_rows else "complete",
        "final_pooled_occurrence_and_share_metrics": "exact position for scoped and position-resolvable unscoped citations" if unscoped_rows else "not requested",
        "final_pooled_unique_papers": "lower and upper bounds over A/B assignments of bare citations" if unscoped_rows else "not requested",
        "analysis_unit": "case mean after three-replicate and nested pool/block averaging",
        "metrics": list(comparison_metrics),
        "comparisons": [label for _, label, _, _ in COMPARISONS],
        "inference_warning": "Only four independent cases; emphasize estimates and heterogeneity, and do not interpret non-significance as equivalence.",
        "api_calls_made": 0,
    }
    (output / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
