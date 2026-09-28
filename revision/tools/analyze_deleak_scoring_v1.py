from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from validate_pass1_deleak_pair import validate_main


METRICS = (
    "ihq_without_cpi", "full_ihq", "scientific_correctness", "physical_plausibility",
    "constraint_adherence", "falsifiability_actionability", "validity_composite_descriptive",
    "output_characters",
)
CASES = (1, 8, 22)
CONDITIONS = ("original_prompt_mpds", "mpds_deleaked")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float) -> str:
    return f"{value:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate blinded de-leaking scores at the case level")
    parser.add_argument("--recovery-adjudication", default="analysis/deleak_recovery_blind_format_adjudication_v2.json")
    parser.add_argument("--output-version", default="v1")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pass1_root = root / "results" / "pass1_sonnet5_deleak_pair_v1"
    recovery_root = root / "results" / "deleak_target_recovery_sonnet5_v1"
    pair_key = read_csv(root / "evaluation" / "deleak_pair_blind_key_v1_DO_NOT_SHARE" / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv")
    recovery_key = read_csv(root / "evaluation" / "deleak_recovery_blind_key_v1_DO_NOT_SHARE" / "blind_key_DO_NOT_SHARE_WITH_RATERS.csv")
    recovery_blind = read_json(root / args.recovery_adjudication)
    if len(pair_key) != 18 or len(recovery_key) != 18 or recovery_blind.get("status") not in {"PASS", "PASS_POST_UNBLIND_KEY_INDEPENDENT_CONSISTENCY_CORRECTION"} or len(recovery_blind["rows"]) != 18:
        raise RuntimeError("Incomplete paired keys or blind recovery adjudication")
    pair_map = {(row["packet_id"], row["alias"]): row for row in pair_key}
    if len(pair_map) != 18:
        raise RuntimeError("Duplicate pair key aliases")
    score_rows: list[dict[str, Any]] = []
    pass1_attempts = 0
    pass1_input = pass1_output = 0
    for packet_path in sorted((root / "evaluation" / "blind_packets_deleak_pair_v1").glob("case_*__rep_*.md")):
        packet_id = packet_path.stem
        run_dir = pass1_root / packet_id
        manifest = read_json(run_dir / "run_manifest.json")
        accepted = read_json(run_dir / "accepted_scores.json")
        errors, derived = validate_main(accepted, Path(f"{packet_id}.json"))
        if errors or len(derived) != 2 or manifest.get("status") != "COMPLETE" or manifest.get("requested_model") != "claude-sonnet-5" or manifest.get("returned_model") != "claude-sonnet-5":
            raise RuntimeError(f"Invalid Pass 1 accepted result: {packet_id}: {errors}")
        if manifest["source_files"]["packet"]["sha256"] != pair_key_sha(packet_path):
            raise RuntimeError(f"Pass 1 packet hash mismatch: {packet_id}")
        if manifest["attempts"][-1].get("validation_errors"):
            raise RuntimeError(f"Accepted Pass 1 packet contains validation errors: {packet_id}")
        for attempt in manifest["attempts"]:
            pass1_attempts += 1
            usage = attempt.get("usage", {})
            pass1_input += int(usage.get("input_tokens") or 0)
            pass1_output += int(usage.get("output_tokens") or 0)
        for row in derived:
            key = pair_map[(packet_id, row["alias"])]
            score_rows.append({
                "case_id": int(key["case_id"]), "replicate_id": int(key["replicate_id"]),
                "condition": key["condition"], "packet_id": packet_id, "alias": row["alias"],
                **{field: row[field] for field in row if field not in {"packet_id", "alias"}},
                "output_characters": int(key["output_characters"]),
            })
    if len(score_rows) != 18 or {(r["case_id"], r["replicate_id"], r["condition"]) for r in score_rows} != {(c, rep, cond) for c in CASES for rep in (1, 2, 3) for cond in CONDITIONS}:
        raise RuntimeError("Pass 1 scores are not a complete paired 3-case × 3-replicate × 2-condition design")
    score_rows.sort(key=lambda row: (row["case_id"], row["replicate_id"], row["condition"]))

    recovery_map = {row["audit_id"]: row for row in recovery_key}
    recovery_rows: list[dict[str, Any]] = []
    recovery_calls = recovery_input = recovery_output = 0
    for row in recovery_blind["rows"]:
        audit_id = row["audit_id"]
        key = recovery_map[audit_id]
        if int(key["case_id"]) != row["case_id"] or key["condition"] not in CONDITIONS:
            raise RuntimeError(f"Recovery key mismatch: {audit_id}")
        pair = pair_map[(key["pair_packet_id"], key["pair_alias"])]
        if pair["condition"] != key["condition"] or pair["cleaned_body_sha256"] != key["cleaned_body_sha256"]:
            raise RuntimeError(f"Recovery packet/source mismatch: {audit_id}")
        manifest = read_json(recovery_root / audit_id / "run_manifest.json")
        if len(manifest["attempts"]) != row["source_attempt"]:
            raise RuntimeError(f"Recovery source attempt mismatch: {audit_id}")
        for attempt in manifest["attempts"]:
            recovery_calls += 1
            usage = attempt.get("usage", {})
            recovery_input += int(usage.get("input_tokens") or 0)
            recovery_output += int(usage.get("output_tokens") or 0)
        recovery_rows.append({
            "case_id": int(key["case_id"]), "replicate_id": int(key["replicate_id"]),
            "condition": key["condition"], "audit_id": audit_id,
            "overall_recovery": row["rubric_derived_overall_recovery"],
            "strict_original_status": row["strict_original_status"],
            "overall_was_corrected": row["overall_was_corrected"],
            "feature_labels_json": json.dumps({f["feature_id"]: f["label"] for f in row["features"]}, ensure_ascii=False, sort_keys=True),
        })
    if len(recovery_rows) != 18 or {(r["case_id"], r["replicate_id"], r["condition"]) for r in recovery_rows} != {(c, rep, cond) for c in CASES for rep in (1, 2, 3) for cond in CONDITIONS}:
        raise RuntimeError("Recovery audit is not a complete paired design")
    recovery_rows.sort(key=lambda row: (row["case_id"], row["replicate_id"], row["condition"]))

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        grouped[(row["case_id"], row["condition"])].append(row)
    recovery_grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in recovery_rows:
        recovery_grouped[(row["case_id"], row["condition"])].append(row)
    comparisons: list[dict[str, Any]] = []
    for case_id in CASES:
        original = grouped[(case_id, CONDITIONS[0])]
        deleaked = grouped[(case_id, CONDITIONS[1])]
        result: dict[str, Any] = {"case_id": case_id, "n_replicates_per_condition": 3}
        for metric in METRICS:
            original_values = [float(row[metric]) for row in original]
            deleaked_values = [float(row[metric]) for row in deleaked]
            result[f"original_{metric}_mean"] = round(mean(original_values), 4)
            result[f"deleaked_{metric}_mean"] = round(mean(deleaked_values), 4)
            result[f"delta_deleaked_minus_original_{metric}"] = round(mean(deleaked_values) - mean(original_values), 4)
            result[f"original_{metric}_range"] = f"{min(original_values):g}–{max(original_values):g}"
            result[f"deleaked_{metric}_range"] = f"{min(deleaked_values):g}–{max(deleaked_values):g}"
        for condition in CONDITIONS:
            labels = [row["overall_recovery"] for row in recovery_grouped[(case_id, condition)]]
            counts = Counter(labels)
            prefix = "original" if condition == CONDITIONS[0] else "deleaked"
            for label in ("absent", "partial_general", "explicit_target_like"):
                result[f"{prefix}_recovery_{label}_of_3"] = counts[label]
        comparisons.append(result)

    output_paths = [
        root / "analysis" / f"deleak_pass1_scores_by_replicate_{args.output_version}.csv",
        root / "analysis" / f"deleak_target_recovery_by_replicate_{args.output_version}.csv",
        root / "analysis" / f"deleak_case_comparison_{args.output_version}.csv",
        root / "analysis" / f"deleak_scoring_results_{args.output_version}.md",
    ]
    if any(path.exists() for path in output_paths):
        raise RuntimeError("Refusing to overwrite existing analysis files")
    write_csv(output_paths[0], score_rows)
    write_csv(output_paths[1], recovery_rows)
    write_csv(output_paths[2], comparisons)
    lines = [
        f"# Targeted de-leaking blind scoring results {args.output_version}", "",
        "Scope: Cases 1, 8, 22; three paired original/de-leaked replicates each. Pass 1 uses official direct-Anthropic Claude Sonnet 5, unchanged IHQ and supplementary Pass 1 rubrics. All original and de-leaked final answers were freshly rescored in nine A/B packets. The target-recovery audit was a separate single-answer blind evaluation.", "",
        "## Case-level results", "",
        "| Case | IHQ w/o CPI original → de-leaked (Δ) | Full IHQ original → de-leaked (Δ) | Validity sum original → de-leaked (Δ) | Explicit target recovery original → de-leaked |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in comparisons:
        def cell(metric: str) -> str:
            return f"{fmt(row[f'original_{metric}_mean'])} → {fmt(row[f'deleaked_{metric}_mean'])} ({row[f'delta_deleaked_minus_original_{metric}']:+.2f})"
        lines.append(f"| {row['case_id']} | {cell('ihq_without_cpi')} | {cell('full_ihq')} | {cell('validity_composite_descriptive')} | {row['original_recovery_explicit_target_like_of_3']}/3 → {row['deleaked_recovery_explicit_target_like_of_3']}/3 |")
    lines.extend(["", "Deltas are de-leaked minus original. The IHQ-without-CPI scale is 0–15, Full IHQ 0–20, and the descriptive four-dimension validity sum 0–20. The validity sum does not contribute to IHQ. Replicate-level scores, ranges, output lengths and four validity dimensions are in the companion CSVs.", "", "## Interpretation and audit status", ""])
    for metric in ("ihq_without_cpi", "full_ihq", "validity_composite_descriptive"):
        signs = Counter("higher" if row[f"delta_deleaked_minus_original_{metric}"] > 0 else "lower" if row[f"delta_deleaked_minus_original_{metric}"] < 0 else "equal" for row in comparisons)
        lines.append(f"- {metric}: de-leaked case means higher in {signs['higher']}/3, lower in {signs['lower']}/3, equal in {signs['equal']}/3 cases.")
    lines.extend([
        f"- Pass 1: 9/9 packets COMPLETE; {pass1_attempts} actual API attempts; {pass1_input:,} input and {pass1_output:,} output tokens.",
        f"- Target-recovery audit: 18/18 packets received model responses in {recovery_calls} API attempts; {recovery_input:,} input and {recovery_output:,} output tokens. Original strict validation accepted 7/18. A condition-blind, uniformly applied format adjudication accepted 18/18 without changing feature labels; it corrected {recovery_blind['overall_corrections']} model overall labels by the frozen case-specific rule. Nine quoted excerpts required ellipsis/Markdown/literal-fragment normalization. This is a disclosed post-format repair, not 18/18 strict original success.",
        "- After unblinding and the initial aggregate, a Case 8 consistency review found one response whose combined-feature label was explicit while its porous/permeable-wall feature was only partial. Full recovery requires all constituent features in the frozen definition; a key-independent but post-unblinding v3 correction changed this response's overall label to partial without changing any feature label. The earlier v1 aggregate is superseded by this version. Because this extra correction was noticed after unblinding, treat the target-recovery result as exploratory pending independent human review.",
        "- Three original replicate-1 controls are public legacy outputs verified by file/body hashes but lack full run manifests. Replicates 2–3 have checked Gemini 2.5 Pro, temperature 0.5, and evidence hashes.",
        "- This is a targeted sensitivity analysis of the three very-high-risk cases in Core10, not proof of robustness across all 30 cases. The revised prompt broadened some design choices as well as removing target cues; a fixed evidence corpus may still contain target-associated concepts. No p-values are reported for n=3 cases.",
        "", "## Reproducibility files", "",
        f"- `analysis/deleak_pass1_scores_by_replicate_{args.output_version}.csv`", f"- `analysis/deleak_target_recovery_by_replicate_{args.output_version}.csv`", f"- `analysis/deleak_case_comparison_{args.output_version}.csv`", f"- `{args.recovery_adjudication}`", "",
    ])
    output_paths[3].write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "PASS", "pass1_packets": 9, "pass1_candidates": 18, "recovery_audits": 18, "pass1_api_attempts": pass1_attempts, "recovery_api_attempts": recovery_calls, "case_comparisons": [{"case_id": row["case_id"], "ihq_without_cpi_delta": row["delta_deleaked_minus_original_ihq_without_cpi"], "full_ihq_delta": row["delta_deleaked_minus_original_full_ihq"], "original_target_explicit": row["original_recovery_explicit_target_like_of_3"], "deleaked_target_explicit": row["deleaked_recovery_explicit_target_like_of_3"]} for row in comparisons]}, ensure_ascii=False, indent=2))


def pair_key_sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
