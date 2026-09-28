from __future__ import annotations

import argparse
import csv
from pathlib import Path


CALLS_PER_RUN = {
    "raw": 1,
    "eo": 1,
    "eop": 2,
    "ds": 7,
    "mpds": 9,
    "sair": 7,
    "ses": 3,
}


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_registry(
    eligibility: list[dict[str, str]],
    policy: str,
    include_new_baselines: bool,
) -> list[dict[str, object]]:
    if policy not in {"practical", "strict"}:
        raise ValueError(policy)

    rows: list[dict[str, object]] = []
    case_lookup: dict[int, dict[str, str]] = {}
    for item in eligibility:
        case_id = int(item["case_id"])
        case_lookup.setdefault(case_id, item)
        reusable = as_bool(item[f"{policy}_eligible_as_replicate_1"])
        condition = item["condition"]
        for replicate in (1, 2, 3):
            legacy = replicate == 1 and reusable
            rows.append(
                {
                    "run_id": f"case_{case_id:02d}__{condition}__rep_{replicate:02d}",
                    "case_id": case_id,
                    "repo_case_slug": item["repo_case_slug"],
                    "case_name": item["case_name"],
                    "manuscript_case_label": item["manuscript_case_label"],
                    "condition": condition,
                    "replicate_id": replicate,
                    "policy": policy,
                    "status": "LEGACY_REUSE" if legacy else "PLANNED",
                    "logical_generation_calls": 0 if legacy else CALLS_PER_RUN[condition],
                    "legacy_output_file": item["output_file"] if legacy else "",
                    "source_commit": item["source_commit"],
                    "notes": item["reasons_or_caveats"] if legacy else "",
                }
            )

    if include_new_baselines:
        for case_id in sorted(case_lookup):
            item = case_lookup[case_id]
            for condition in ("sair", "ses"):
                for replicate in (1, 2, 3):
                    rows.append(
                        {
                            "run_id": f"case_{case_id:02d}__{condition}__rep_{replicate:02d}",
                            "case_id": case_id,
                            "repo_case_slug": item["repo_case_slug"],
                            "case_name": item["case_name"],
                            "manuscript_case_label": item["manuscript_case_label"],
                            "condition": condition,
                            "replicate_id": replicate,
                            "policy": policy,
                            "status": "PLANNED",
                            "logical_generation_calls": CALLS_PER_RUN[condition],
                            "legacy_output_file": "",
                            "source_commit": item["source_commit"],
                            "notes": "New reviewer-requested baseline; no legacy result exists.",
                        }
                    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eligibility", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    eligibility = read_csv(args.eligibility)
    for policy in ("practical", "strict"):
        rows = build_registry(eligibility, policy, include_new_baselines=True)
        target = args.output_dir / f"run_registry_{policy}.csv"
        write_csv(target, rows)
        planned_runs = sum(row["status"] == "PLANNED" for row in rows)
        legacy_runs = sum(row["status"] == "LEGACY_REUSE" for row in rows)
        calls = sum(int(row["logical_generation_calls"]) for row in rows)
        print(f"{policy}: rows={len(rows)} planned_runs={planned_runs} legacy_reuse={legacy_runs} calls={calls}")


if __name__ == "__main__":
    main()
