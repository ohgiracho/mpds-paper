from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path


def load_runner(path: Path):
    spec = importlib.util.spec_from_file_location("revision_run_condition", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    repo = (root.parent / "mpds_github_prep" / "github_repo").resolve()
    runner = load_runner(root / "tools" / "run_condition.py")
    errors: list[str] = []
    scripts: set[Path] = set()
    plans = 0

    required_common = {
        "--simulation-date",
        "--debate-topic",
        "--user-context-file",
        "--model",
        "--temperature",
        "--max-output-tokens",
        "--output-file",
    }
    for case_id in range(1, 31):
        try:
            record = runner.load_case(repo, case_id)
            knowledge_a, knowledge_b, _ = runner.knowledge_paths(root / "audit", case_id)
            user_context = (repo / str(record["public_case_input_dir"]) / "user_context.txt").resolve()
            if not user_context.exists():
                errors.append(f"case {case_id}: missing user context")
            for path in (knowledge_a, knowledge_b):
                if not path.exists():
                    errors.append(f"case {case_id}: missing evidence {path}")
            for condition in runner.CONDITIONS:
                script = runner.find_script(repo, root, case_id, condition).resolve()
                scripts.add(script)
                text = script.read_text(encoding="utf-8", errors="replace")
                required = set(required_common)
                if condition != "raw":
                    required |= {"--knowledge-a", "--knowledge-b"}
                if condition in {"ds", "mpds"}:
                    required |= {"--rounds", "--min-evidence-pointers", "--turn-sleep-sec"}
                absent = sorted(flag for flag in required if flag not in text)
                if absent:
                    errors.append(f"case {case_id} {condition}: missing CLI flags {absent} in {script}")
                runner.build_command(
                    script,
                    condition,
                    record,
                    user_context,
                    knowledge_a,
                    knowledge_b,
                    root / "runs" / "validation-placeholder.txt",
                )
                plans += 1
        except Exception as exc:
            errors.append(f"case {case_id}: {type(exc).__name__}: {exc}")

    registry_summary = {}
    for policy in ("practical", "strict"):
        rows = csv_rows(root / "audit" / f"run_registry_{policy}.csv")
        status = Counter(row["status"] for row in rows)
        calls = sum(int(row["logical_generation_calls"]) for row in rows)
        registry_summary[policy] = {"rows": len(rows), "status": dict(status), "generation_calls": calls}
        if len(rows) != 630:
            errors.append(f"{policy} registry has {len(rows)} rows, expected 630")

    result = {
        "status": "PASS" if not errors else "FAIL",
        "case_count": 30,
        "conditions_per_case": len(runner.CONDITIONS),
        "validated_run_plans": plans,
        "unique_scripts": len(scripts),
        "registry_summary": registry_summary,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
