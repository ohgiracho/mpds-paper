from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCOPED = re.compile(r"Scientist\s*([AB])\s*\[ID\s*:\s*(\d+)\]", re.IGNORECASE)
BARE = re.compile(r"\[ID\s*:\s*(\d+)\]", re.IGNORECASE)
LEGACY = re.compile(r"\[([AB])-ID\s*:\s*(\d+)\]", re.IGNORECASE)
ANY_ID = re.compile(r"\[[^\]\r\n]*ID\s*:[^\]\r\n]*\]", re.IGNORECASE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def valid_ids(path: Path, pool: str) -> set[str]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return {f"{pool}:{value}" for value in re.findall(r"(?m)^ID:\s*(\d+)\s*$", text)}


def citation_check(text: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    matches = list(SCOPED.finditer(text))
    cited = {f"{m.group(1).upper()}:{m.group(2)}" for m in matches}
    spans = [m.span() for m in matches]
    bare = [
        m.group(0)
        for m in BARE.finditer(text)
        if not any(m.start() >= start and m.end() <= end for start, end in spans)
    ]
    malformed = [
        m.group(0)
        for m in ANY_ID.finditer(text)
        if BARE.fullmatch(m.group(0)) is None and LEGACY.fullmatch(m.group(0)) is None
    ]
    pools = {item.split(":", 1)[0] for item in cited}
    return {
        "passed": len(cited) >= 3
        and not (cited - allowed)
        and not bare
        and not list(LEGACY.finditer(text))
        and not malformed
        and required <= pools,
        "unique_citations": len(cited),
        "invalid": sorted(cited - allowed),
        "bare": bare,
        "malformed": malformed,
        "missing_pools": sorted(required - pools),
    }


def parse_output(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(
        r"\[RUN METADATA\]\s*(\{.*\})\s*\[FINAL SYNTHESIS\]\s*(.*?)\s*",
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("full_output.txt does not match the required two-section format")
    return json.loads(match.group(1)), match.group(2)


def audit_run(run_dir: Path) -> dict[str, Any]:
    problems: list[str] = []
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return {"run_directory": str(run_dir), "passed": False, "problems": ["missing manifest"]}

    manifest = read_json(manifest_path)
    condition = manifest.get("condition")
    full_path, final_path = run_dir / "full_output.txt", run_dir / "final.txt"
    for path in (full_path, final_path, run_dir / "api_calls.jsonl"):
        if not path.exists():
            problems.append(f"missing {path.name}")
    if problems:
        return {"run_id": manifest.get("run_id"), "passed": False, "problems": problems}

    if manifest.get("status") != "COMPLETE" or manifest.get("return_code") != 0:
        problems.append("manifest is not COMPLETE with return_code 0")
    if manifest.get("vertex_project") not in (None, ""):
        problems.append("vertex project identifier was persisted")
    if sha256(full_path) != manifest.get("full_output_sha256"):
        problems.append("full_output hash mismatch")
    if sha256(final_path) != manifest.get("final_sha256"):
        problems.append("final hash mismatch")
    script_path = Path(manifest["script"])
    if sha256(script_path) != manifest.get("script_sha256"):
        problems.append("generation script hash mismatch")

    try:
        meta, final = parse_output(full_path)
    except Exception as exc:
        problems.append(str(exc))
        meta, final = {}, ""
    if final and final.strip() != final_path.read_text(encoding="utf-8").strip():
        problems.append("extracted final does not equal final.txt")

    allowed_a = valid_ids(Path(manifest["knowledge_a"]), "A")
    allowed_b = valid_ids(Path(manifest["knowledge_b"]), "B")
    final_check = citation_check(final, allowed_a | allowed_b, {"A", "B"})
    if not final_check["passed"]:
        problems.append(f"final citation audit failed: {final_check}")
    if meta.get("citation_validation", {}).get("passed") is not True:
        problems.append("embedded final citation validation is not PASS")
    if meta.get("rubric_aware_prompting") is not False:
        problems.append("rubric_aware_prompting is not false")

    if condition == "sair":
        trajectory_path = run_dir / "trajectory.json"
        if not trajectory_path.exists():
            problems.append("missing trajectory.json")
        else:
            trajectory = read_json(trajectory_path)
            expected = [
                "initial", "critique_1", "revision_1", "critique_2",
                "revision_2", "critique_3", "revision_3",
            ]
            if [row.get("stage") for row in trajectory] != expected:
                problems.append("SAIR stage order mismatch")
            exposed = {row.get("stage") for row in trajectory if row.get("raw_evidence_supplied")}
            if exposed != {"initial", "revision_1", "revision_2"}:
                problems.append(f"SAIR evidence schedule mismatch: {sorted(exposed)}")
            for row in trajectory:
                if row.get("stage") in {"initial", "revision_1", "revision_2", "revision_3"}:
                    check = citation_check(row.get("text", ""), allowed_a | allowed_b, {"A", "B"})
                    if not check["passed"]:
                        problems.append(f"{row.get('stage')} citation audit failed: {check}")
        if meta.get("logical_generation_calls") != 7:
            problems.append("SAIR logical call count is not 7")
    elif condition == "ses":
        independent_path = run_dir / "independent_answers.json"
        if not independent_path.exists():
            problems.append("missing independent_answers.json")
        else:
            independent = read_json(independent_path)
            for key, allowed, pool in (
                ("scientist_a", allowed_a, "A"),
                ("scientist_b", allowed_b, "B"),
            ):
                check = citation_check(independent.get(key, {}).get("text", ""), allowed, {pool})
                if not check["passed"]:
                    problems.append(f"SES {key} citation audit failed: {check}")
        if meta.get("logical_generation_calls") != 3:
            problems.append("SES logical call count is not 3")
    else:
        problems.append(f"unexpected condition: {condition}")

    usage = manifest.get("api_log_summary", {})
    if usage.get("successful_calls", 0) < manifest.get("expected_logical_generation_calls", 0):
        problems.append("too few successful model calls")

    return {
        "run_id": manifest.get("run_id"),
        "condition": condition,
        "passed": not problems,
        "problems": problems,
        "final_citations": final_check,
        "successful_calls": usage.get("successful_calls"),
        "failed_calls": usage.get("failed_calls"),
        "usage_metadata_sums": usage.get("usage_metadata_sums", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit completed SAIR/SES component-control runs")
    parser.add_argument("--run-set", type=Path, default=ROOT / "runs_component_controls_core10_v2")
    parser.add_argument("--case", type=int, action="append")
    args = parser.parse_args()

    manifests = sorted(
        path
        for path in args.run_set.resolve().glob("case_*/**/replicate_*/run_manifest.json")
        if re.fullmatch(r"replicate_\d+", path.parent.name)
    )
    if args.case:
        wanted = {f"case_{case_id:02d}" for case_id in args.case}
        manifests = [path for path in manifests if any(part in wanted for part in path.parts)]
    results = [audit_run(path.parent) for path in manifests]
    report = {
        "status": "PASS" if results and all(row["passed"] for row in results) else "FAIL",
        "audited_runs": len(results),
        "passed_runs": sum(bool(row["passed"]) for row in results),
        "failed_runs": sum(not bool(row["passed"]) for row in results),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
