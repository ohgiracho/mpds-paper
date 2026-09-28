from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


CONDITIONS = ("raw", "eo", "eop", "ds", "mpds")
CALLS_PER_RUN = {"raw": 1, "eo": 1, "eop": 2, "ds": 7, "mpds": 9}
EXPECTED_MODEL = "models/gemini-2.5-pro"
EXPECTED_TEMPERATURE = "0.5"
EXPECTED_MAX_OUTPUT_TOKENS = "8192"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def extract_field(text: str, keys: tuple[str, ...]) -> str:
    for key in keys:
        match = re.search(rf"^{re.escape(key)}\s*:\s*(.+)$", text, flags=re.I | re.M)
        if match:
            return match.group(1).strip()
    return ""


def extract_year(value: str) -> str:
    match = re.search(r"(?:19|20)\d{2}", value or "")
    return match.group(0) if match else ""


def to_repo_path(value: str) -> str:
    return value.replace("\\", "/").lstrip("./")


def run_git(repo: Path, *args: str) -> str:
    safe = repo.resolve().as_posix()
    command = ["git", "-c", f"safe.directory={safe}", "-C", str(repo), *args]
    return subprocess.check_output(command, text=True, encoding="utf-8").strip()


def find_case_code(tracked: set[str], case_id: int, condition: str) -> str:
    marker = f"({case_id})/"
    expected_parts = {
        "raw": "/raw_llm/",
        "eo": "/eo/",
        "eop": "/eop/",
        "ds": "/ds/",
        "mpds": "/mpds/",
    }
    matches = []
    for item in tracked:
        low = f"/{item.lower()}"
        if (
            item.startswith("code/02_case_specific_generation_code/")
            and marker in item
            and expected_parts[condition] in low
            and item.lower().endswith(".py")
            and "merge_knowledge.py" not in low
        ):
            matches.append(item)
    if condition == "ds" and not matches and case_id == 6:
        matches = [
            item
            for item in tracked
            if item.startswith("code/02_case_specific_generation_code/VN(6)/")
            and item.lower().endswith("run_ds.py")
        ]
    return sorted(matches)[0] if matches else ""


def output_paths(record: dict[str, object]) -> dict[str, tuple[str, str]]:
    return {
        "raw": (str(record["public_raw_llm_output"]), str(record["public_raw_llm_output"])),
        "eo": (str(record["public_eo_output"]), str(record["public_eo_output"])),
        "eop": (str(record["public_eop_output"]), str(record["public_eop_output"])),
        "ds": (str(record["public_ds_output"]), str(record["public_ds_full_log"])),
        "mpds": (str(record["public_mpds_output"]), str(record["public_mpds_full_log"])),
    }


def knowledge_manifest(
    repo: Path,
    tracked: set[str],
    paper_root: Path,
    cases: list[dict[str, object]],
) -> tuple[list[dict[str, object]], dict[int, bool]]:
    rows: list[dict[str, object]] = []
    per_case_consistency: dict[int, bool] = {}
    for record in cases:
        case_id = int(record["case_id"])
        log_rel = to_repo_path(str(record["public_mpds_full_log"]))
        log_path = repo / log_rel
        text = log_path.read_text(encoding="utf-8", errors="replace")
        hashes: dict[str, str] = {}
        case_ok = True
        config_path = repo / "data" / "snapshots_safe" / f"case_{case_id:02d}" / "retrieval_config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        expected_names = {Path(value).name for value in config["knowledge_files"]}
        context_dir = paper_root / Path(config["canonical_context_dir"])
        for pool, key in (("A", "knowledge_a_file"), ("B", "knowledge_b_file")):
            raw_path = extract_field(text, (key,))
            local_path = Path(raw_path)
            exists = local_path.exists()
            digest = sha256_file(local_path) if exists else ""
            hashes[pool] = digest
            if not exists:
                case_ok = False

            safe_csv = repo / "data" / "snapshots_safe" / f"case_{case_id:02d}" / "openalex_ids.csv"
            with safe_csv.open(encoding="utf-8-sig", newline="") as handle:
                id_rows = list(csv.DictReader(handle))
            safe_count = sum(row["source_file"] == local_path.name for row in id_rows)
            name_match = exists and local_path.name in expected_names
            matching_copies = list(context_dir.rglob(local_path.name)) if context_dir.exists() else []
            copy_hashes = {sha256_file(item) for item in matching_copies}
            copies_match = bool(digest) and copy_hashes == {digest}
            case_ok = case_ok and name_match and copies_match
            rows.append(
                {
                    "case_id": case_id,
                    "repo_case_slug": record["case_slug"],
                    "case_name": record["case_name"],
                    "pool": pool,
                    "local_path": str(local_path),
                    "exists": exists,
                    "filename_matches_release_config": name_match,
                    "matching_local_copy_count": len(matching_copies),
                    "all_local_copies_sha_match": copies_match,
                    "sha256": digest,
                    "bytes": local_path.stat().st_size if exists else 0,
                    "characters": len(local_path.read_text(encoding="utf-8", errors="replace")) if exists else 0,
                    "safe_release_record_count": safe_count,
                    "release_config_tracked": to_repo_path(str(config_path.relative_to(repo))) in tracked,
                    "safe_ids_tracked": to_repo_path(str(safe_csv.relative_to(repo))) in tracked,
                }
            )
        per_case_consistency[case_id] = case_ok and bool(hashes["A"]) and bool(hashes["B"])
    return rows, per_case_consistency


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows for {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--paper-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    repo = args.repo.resolve()
    paper_root = args.paper_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    commit = run_git(repo, "rev-parse", "HEAD")
    commit_info = run_git(repo, "log", "-1", "--format=%H%n%ci%n%s").splitlines()
    tracked_list = run_git(repo, "ls-files").splitlines()
    tracked = {to_repo_path(item) for item in tracked_list}
    status = run_git(repo, "status", "--short").splitlines()

    workbook_path = repo / "data" / "benchmark_cases" / "benchmark_cases_release_final.xlsx"
    workbook = openpyxl.load_workbook(workbook_path, data_only=True, read_only=True)
    sheet = workbook["BenchmarkCases"]
    values = list(sheet.iter_rows(values_only=True))
    headers = [str(value) for value in values[0]]
    cases = [dict(zip(headers, row)) for row in values[1:] if row[0] is not None]

    knowledge_rows, knowledge_ok = knowledge_manifest(repo, tracked, paper_root, cases)
    write_csv(output_dir / "knowledge_snapshot_manifest.csv", knowledge_rows)

    crosswalk_rows: list[dict[str, object]] = []
    eligibility_rows: list[dict[str, object]] = []
    for record in cases:
        case_id = int(record["case_id"])
        manuscript_label = ""
        if case_id == 1:
            manuscript_label = "Case Study 2"
        elif case_id == 2:
            manuscript_label = "Case Study 1"
        crosswalk_rows.append(
            {
                "repo_case_id": case_id,
                "repo_case_slug": record["case_slug"],
                "repo_case_name": record["case_name"],
                "manuscript_case_label": manuscript_label,
                "canonical_context_variant": record["canonical_context_variant"],
                "heldout_reference_file": record["heldout_reference_file"],
                "cutoff_year": record["cutoff_year"],
                "note": "Do not renumber repository files; use this crosswalk during revision.",
            }
        )

        expected_topic = normalize_text(str(record["debate_topic"]))
        expected_year = str(record["cutoff_year"])
        for condition, (final_rel_raw, meta_rel_raw) in output_paths(record).items():
            final_rel = to_repo_path(final_rel_raw)
            meta_rel = to_repo_path(meta_rel_raw)
            final_path = repo / final_rel
            meta_path = repo / meta_rel
            text = meta_path.read_text(encoding="utf-8", errors="replace") if meta_path.exists() else ""
            topic = normalize_text(extract_field(text, ("Topic", "topic")))
            date_value = extract_field(text, ("Date", "simulation_date"))
            year = extract_year(date_value)
            model = extract_field(text, ("Model", "model"))
            temperature = extract_field(text, ("Temperature", "temperature"))
            max_tokens = extract_field(text, ("MaxOutputTokens", "max_output_tokens"))
            rounds = extract_field(text, ("rounds",))
            timestamp = extract_field(text, ("run_timestamp_utc",))
            code_rel = find_case_code(tracked, case_id, condition)
            code_path = repo / code_rel if code_rel else Path()

            checks = {
                "output_exists": final_path.exists() and final_path.stat().st_size > 0,
                "output_tracked": final_rel in tracked,
                "metadata_file_tracked": meta_rel in tracked,
                "topic_matches": topic == expected_topic,
                "cutoff_year_matches": year == expected_year,
                "model_matches": model == EXPECTED_MODEL,
                "temperature_matches": temperature == EXPECTED_TEMPERATURE,
                "max_tokens_matches": max_tokens == EXPECTED_MAX_OUTPUT_TOKENS,
                "rounds_match": condition not in {"ds", "mpds"} or rounds == "3",
                "case_code_found": bool(code_rel) and code_rel in tracked,
                "knowledge_snapshot_verified": condition == "raw" or knowledge_ok[case_id],
            }
            practical_eligible = all(checks.values())
            strict_eligible = practical_eligible and bool(timestamp) and "code_sha256" in text and "usage_metadata" in text
            reasons = [name for name, ok in checks.items() if not ok]
            if practical_eligible and not strict_eligible:
                reasons.extend(["run_specific_code_hash_missing", "exact_token_usage_missing"])
                if not timestamp:
                    reasons.append("run_timestamp_missing")

            eligibility_rows.append(
                {
                    "case_id": case_id,
                    "repo_case_slug": record["case_slug"],
                    "case_name": record["case_name"],
                    "manuscript_case_label": manuscript_label,
                    "condition": condition,
                    "practical_eligible_as_replicate_1": practical_eligible,
                    "strict_eligible_as_replicate_1": strict_eligible,
                    "status": "PRACTICAL_ELIGIBLE_WITH_CAVEATS" if practical_eligible else "INELIGIBLE",
                    "reasons_or_caveats": ";".join(reasons),
                    "expected_topic": expected_topic,
                    "observed_topic": topic,
                    "expected_cutoff_year": expected_year,
                    "observed_date": date_value,
                    "model": model,
                    "temperature": temperature,
                    "max_output_tokens": max_tokens,
                    "rounds": rounds,
                    "run_timestamp_utc": timestamp,
                    "output_file": final_rel,
                    "metadata_file": meta_rel,
                    "case_code_file": code_rel,
                    "case_code_sha256": sha256_file(code_path) if code_rel and code_path.exists() else "",
                    "output_sha256": sha256_file(final_path) if final_path.exists() else "",
                    "source_commit": commit,
                }
            )

    write_csv(output_dir / "case_crosswalk.csv", crosswalk_rows)
    write_csv(output_dir / "replicate1_eligibility.csv", eligibility_rows)

    practical_counts = Counter(row["condition"] for row in eligibility_rows if row["practical_eligible_as_replicate_1"])
    strict_counts = Counter(row["condition"] for row in eligibility_rows if row["strict_eligible_as_replicate_1"])
    practical_calls = sum(
        (3 - int(bool(row["practical_eligible_as_replicate_1"]))) * CALLS_PER_RUN[str(row["condition"])]
        for row in eligibility_rows
    )
    strict_calls = sum(
        (3 - int(bool(row["strict_eligible_as_replicate_1"]))) * CALLS_PER_RUN[str(row["condition"])]
        for row in eligibility_rows
    )
    invalid = [
        {
            "case_id": row["case_id"],
            "condition": row["condition"],
            "reasons": row["reasons_or_caveats"],
        }
        for row in eligibility_rows
        if not row["practical_eligible_as_replicate_1"]
    ]
    summary = {
        "audit_generated_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_repository": "https://github.com/ohgiracho/mpds-paper",
        "canonical_commit": commit,
        "commit_timestamp": commit_info[1] if len(commit_info) > 1 else "",
        "commit_subject": commit_info[2] if len(commit_info) > 2 else "",
        "tracked_file_count": len(tracked),
        "working_tree_status": status,
        "case_count": len(cases),
        "eligibility_row_count": len(eligibility_rows),
        "knowledge_snapshot_count": len(knowledge_rows),
        "practical_eligible_counts": dict(practical_counts),
        "strict_eligible_counts": dict(strict_counts),
        "practical_additional_generation_calls_for_n3": practical_calls,
        "strict_clean_generation_calls_for_n3": strict_calls,
        "practical_ineligible_rows": invalid,
        "policy_note": {
            "practical": "Reuse a legacy output when observable settings, canonical topic/cutoff, tracked code, and frozen evidence snapshots match. Missing run-specific code hash/token metadata remains disclosed.",
            "strict": "Require embedded run timestamp, exact code hash, and API usage metadata. No legacy output currently meets this standard.",
        },
    }
    (output_dir / "baseline_audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
