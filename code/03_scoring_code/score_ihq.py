from __future__ import annotations

"""
Unified 5-system blind scorer reference for Raw / EO / EOP / DS / MPDS.

Important note:
- This script encodes the unified 5-system blind-scoring procedure that would be
  used if all five systems were scored together with the same rubric pipeline.
- Archived reported scores in this project were produced by preserving existing
  Raw/EO/DS/MPDS scores and appending EOP separately. Re-running a live LLM judge
  with all five systems in one pass may not reproduce numerically identical values
  because model outputs can vary across runs and the blind comparison context changes.
"""
import argparse
import csv
import json
import os
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from google import genai
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing dependency: google-genai is not installed in this Python interpreter.\n"
        f"Current interpreter: {sys.executable}\n"
        "Install it with:\n"
        f'  "{sys.executable}" -m pip install google-genai\n'
        "Or run this script with the interpreter where google-genai is already installed."
    ) from exc


SYSTEM_ORDER = ["mpds", "eo", "eop", "ds", "raw"]
SYSTEM_LABELS = {
    "mpds": "MPDS",
    "eo": "EO",
    "eop": "EOP",
    "ds": "DS",
    "raw": "Raw_LLM",
}
CASE_DIR_PATTERN = re.compile(r"\((\d+)\)$")
METADATA_LINE_RE = re.compile(
    r"^(BaselineType|Source|Evidence|MergedKnowledgeSource|Model|Temperature|MaxOutputTokens|Language|Date|Topic):.*$",
    flags=re.M,
)
TRUNCATE_SECTION_TITLES = (
    "evidence map",
    "evidence appendix",
    "appendix",
    "appendices",
    "supporting evidence",
    "evidence table",
    "references",
    "reference list",
    "bibliography",
    "summary table",
)


@dataclass(frozen=True)
class FrameworkConfig:
    framework_id: str
    display_name: str
    item_fields: tuple[str, ...]
    item_labels: tuple[str, ...]
    extra_prompt_rules: str


FRAMEWORKS: dict[str, FrameworkConfig] = {
    "ihq": FrameworkConfig(
        framework_id="ihq",
        display_name="Universal Integrative Hypothesis Quality (4-dimension / 20-point)",
        item_fields=(
            "idea_novelty",
            "mechanistic_originality",
            "tradeoff_reframing",
            "cross_perspective_integration",
        ),
        item_labels=(
            "Idea Novelty",
            "Mechanistic Originality",
            "Trade-off Reframing",
            "Cross-Perspective Integration",
        ),
        extra_prompt_rules="\n".join(
            [
                "Score conservatively.",
                "Use 5 only when the answer is clearly exceptional by the rubric's own wording.",
                "Use 4 only when there is explicit, concrete evidence for an uncommon level of quality.",
                "A 3 means solid and meaningfully differentiated, not merely competent.",
                "Do not reward verbosity, citation density, formatting, or procedural detail alone.",
                "High scores require genuinely integrative reasoning and a coherent final direction.",
                "Do not assume the text is a final answer or synthesis unless it explicitly says so.",
            ]
        ),
    ),
    "erhq": FrameworkConfig(
        framework_id="erhq",
        display_name="Experiment-Ready Hypothesis Quality",
        item_fields=(
            "problem_capture_directional_alignment",
            "real_world_constraint_handling",
            "originality_beyond_standard_literature_patterns",
            "experimental_actionability_specificity",
        ),
        item_labels=(
            "Problem Capture & Directional Alignment",
            "Real-World Constraint Handling",
            "Originality Beyond Standard Literature Patterns",
            "Experimental Actionability & Specificity",
        ),
        extra_prompt_rules="\n".join(
            [
                "Score conservatively.",
                "Use 5 only when clearly justified by explicit textual evidence.",
                "If uncertain between two scores, choose the lower one.",
                "Evaluate only the final substantive answer body.",
                "Do not reward memo style, polish, confidence, evidence maps, or provenance labels.",
            ]
        ),
    ),
}


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=encoding)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def resolve_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")
    return api_key


def is_retryable(message: str) -> bool:
    text = message.upper()
    markers = (
        "429",
        "RESOURCE_EXHAUSTED",
        "DEADLINE_EXCEEDED",
        "INTERNAL",
        "UNAVAILABLE",
        "SERVICE UNAVAILABLE",
        "503",
        "502",
        "500",
        "TIMEOUT",
        "EMPTY MODEL RESPONSE",
    )
    return any(marker in text for marker in markers)


def generate_with_retry(
    client: genai.Client,
    model_name: str,
    prompt: str,
    max_output_tokens: int,
    retries: int = 4,
) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "temperature": 0.0,
                    "max_output_tokens": max_output_tokens,
                },
            )
            text = (response.text or "").strip()
            if not text:
                raise RuntimeError("Empty model response.")
            return text
        except Exception as exc:
            last_error = exc
            if attempt < retries and is_retryable(str(exc)):
                time.sleep(10 * attempt)
                continue
            break
    if last_error is None:
        raise RuntimeError("Unknown generation error.")
    raise last_error


def extract_topic(text: str) -> str | None:
    match = re.search(r"^Topic:\s*(.+)$", text, flags=re.M)
    return match.group(1).strip() if match else None


def strip_metadata_and_markers(text: str) -> str:
    cleaned = text.replace("\r\n", "\n")
    cleaned = METADATA_LINE_RE.sub("", cleaned)
    for marker in ("[EOP Answer]", "[EO Answer]", "[Raw LLM Answer]", "[DS Final Synthesis]", "[Final Synthesis]"):
        if marker in cleaned:
            cleaned = cleaned.split(marker, 1)[1]
    cleaned = cleaned.lstrip("=\n ")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_section_header(line: str) -> str:
    header = line.strip()
    header = re.sub(r"^\s{0,3}#{1,6}\s*", "", header)
    header = re.sub(r"^[=\-_*`~]{3,}\s*", "", header)
    header = re.sub(r"\s*[=\-_*`~]{3,}$", "", header)
    header = header.strip()
    if header.startswith("[") and header.endswith("]"):
        header = header[1:-1].strip()
    header = header.rstrip(":").strip()
    header = re.sub(r"\s+", " ", header)
    return header.lower()


def is_truncation_header(line: str) -> bool:
    normalized = normalize_section_header(line)
    if not normalized or len(normalized) > 120:
        return False
    for title in TRUNCATE_SECTION_TITLES:
        if normalized == title:
            return True
        if normalized.startswith(f"{title} ("):
            return True
        if normalized.startswith(f"{title}:"):
            return True
        if normalized.startswith(f"{title} -"):
            return True
    return False


def strip_appendix_sections(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if is_truncation_header(line):
            return "\n".join(lines[:index]).rstrip()
    return text.strip()


def clean_body(system: str, raw_text: str) -> str:
    body = strip_metadata_and_markers(raw_text)
    body = strip_appendix_sections(body)
    if system == "mpds":
        body = re.sub(r"^\s*\[FINAL SYNTHESIS\]\s*", "", body, flags=re.I)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def extract_rubric_core(text: str) -> str:
    end_markers = (
        "REQUIRED OUTPUT FORMAT",
        "STYLE REQUIREMENTS",
        "Now read the uploaded file and perform the full blind",
    )
    end = len(text)
    for marker in end_markers:
        pos = text.find(marker)
        if pos != -1:
            end = min(end, pos)
    trimmed = text[:end].strip()
    framework_markers = (
        "Integrative Hypothesis Quality",
        "Experiment-Ready Hypothesis Quality",
        "SCORING FRAMEWORK",
    )
    for marker in framework_markers:
        pos = trimmed.find(marker)
        if pos != -1:
            return trimmed[pos:].strip()
    return trimmed


def detect_framework(rubric_text: str, explicit: str) -> FrameworkConfig:
    upper = rubric_text.upper()
    if explicit == "erhq":
        return FRAMEWORKS["erhq"]
    if explicit == "ihq":
        return FRAMEWORKS["ihq"]
    if "EXPERIMENT-READY HYPOTHESIS QUALITY" in upper or "PROBLEM CAPTURE & DIRECTIONAL ALIGNMENT" in upper:
        return FRAMEWORKS["erhq"]
    if "UNIVERSAL IHQ SCORING RULES" in upper or "INTEGRATIVE HYPOTHESIS QUALITY" in upper or "IDEA NOVELTY" in upper:
        return FRAMEWORKS["ihq"]
    raise RuntimeError("Could not auto-detect framework. Use --framework ihq or --framework erhq.")


def find_case_dir(paper_root: Path, case_no: int) -> Path | None:
    for path in sorted(paper_root.iterdir()):
        if not path.is_dir():
            continue
        match = CASE_DIR_PATTERN.search(path.name)
        if match and int(match.group(1)) == case_no:
            return path
    return None


def find_output_file(case_dir: Path, system: str, case_no: int) -> Path | None:
    target_name = {
        "mpds": f"mpds_final({case_no}).txt",
        "raw": f"Raw_LLM_Answer({case_no}).txt",
        "eo": f"EO_Answer({case_no}).txt",
        "eop": f"EOP_Answer({case_no}).txt",
        "ds": f"DS_Final_Synthesis({case_no}).txt",
    }[system]
    candidates = [path for path in case_dir.rglob(target_name) if path.is_file()]
    if system == "mpds":
        candidates = [path for path in candidates if "\uc0c8\ub85c\ub9cc\ub4e0final" not in str(path)]
    if system == "mpds":
        candidates = [path for path in candidates if "새로만든final" not in str(path)]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (len(path.parts), len(str(path)), str(path)))
    return candidates[0]


def build_case_record(paper_root: Path, case_no: int) -> dict | None:
    case_dir = find_case_dir(paper_root, case_no)
    if case_dir is None:
        return None

    topic = None
    outputs: dict[str, dict] = {}
    missing: dict[str, str] = {}
    for system in SYSTEM_ORDER:
        path = find_output_file(case_dir, system, case_no)
        if path is None:
            missing[system] = "not_found"
            continue
        text = read_text(path)
        topic = topic or extract_topic(text)
        outputs[system] = {
            "path": str(path),
            "body": clean_body(system, text),
        }
    return {
        "case": case_no,
        "folder": case_dir.name,
        "topic": topic or "",
        "outputs": outputs,
        "missing": missing,
    }


# Keep aliasing blind while allowing five systems when EOP is present.
def alias_outputs(outputs: dict[str, dict], seed: int) -> tuple[dict[str, dict], dict[str, str]]:
    systems = list(outputs.keys())
    random.Random(seed).shuffle(systems)
    aliased: dict[str, dict] = {}
    mapping: dict[str, str] = {}
    for alias, system in zip(("A", "B", "C", "D", "E"), systems, strict=False):
        aliased[alias] = outputs[system]
        mapping[alias] = system
    return aliased, mapping


def build_score_template(config: FrameworkConfig, aliases: list[str]) -> str:
    alias_blocks = []
    for alias in aliases:
        field_lines = [f'      "{field}": 0,' for field in config.item_fields]
        alias_blocks.append(
            "\n".join(
                [
                    f'    "{alias}": {{',
                    *field_lines,
                    '      "total": 0,',
                    '      "brief_reason": "one short sentence"',
                    "    }},",
                ]
            )
        )
    template = "\n".join(alias_blocks).rstrip(",")
    return "{\n  \"scores\": {\n" + template + "\n  }\n}"


def build_prompt(config: FrameworkConfig, rubric_text: str, case_record: dict, aliased_outputs: dict[str, dict]) -> str:
    sections = []
    for alias in sorted(aliased_outputs):
        sections.append(f"## Output {alias}\n\n{aliased_outputs[alias]['body']}")
    blind_outputs = "\n\n".join(sections)
    score_template = build_score_template(config, sorted(aliased_outputs))

    return f"""You are conducting a conservative blind evaluation of battery-materials research outputs.

Use ONLY the rubric below and ONLY the final substantive answer body of each output.
Do not use prior expectations, prior scores, prior mappings, or assumptions from earlier conversations.
Do not reward length, citations, formatting, memo style, polish, confidence, section headers, evidence maps, or provenance labels.
Keep scores absolute rather than forcing artificial spread.
Do not infer or reveal system identities.
If uncertain between two scores, choose the lower one.
{config.extra_prompt_rules}

Scoring framework:
{config.display_name}

Rubric:
{rubric_text}

Case:
- Case number: {case_record["case"]}
- Folder: {case_record["folder"]}
- Topic: {case_record["topic"] or "N/A"}

Outputs to score:
{blind_outputs}

Return valid JSON only with no markdown fences and no commentary outside the JSON.
Use this exact structure and the exact field names:
{score_template}

All item scores must be integers from 0 to 5.
The total must equal the sum of the {len(config.item_fields)} item scores.
Include only aliases that are actually present in this case."""


def parse_model_json(text: str) -> dict:
    candidate = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, flags=re.S)
    if fence_match:
        candidate = fence_match.group(1).strip()
    elif candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Model response did not contain JSON.")
    return json.loads(candidate[start : end + 1])


def validate_scores(raw_scores: dict, config: FrameworkConfig, mapping: dict[str, str]) -> dict[str, dict]:
    expected_aliases = set(mapping)
    received_aliases = set(raw_scores)
    missing_aliases = expected_aliases - received_aliases
    if missing_aliases:
        raise ValueError(f"Missing aliases in model response: {sorted(missing_aliases)}")

    validated: dict[str, dict] = {}
    for alias in sorted(expected_aliases):
        item = raw_scores[alias]
        row: dict[str, int | str] = {}
        running_total = 0
        for field in config.item_fields:
            value = item.get(field)
            if not isinstance(value, int):
                raise ValueError(f"{alias}.{field} is not an int: {value!r}")
            if value < 0 or value > 5:
                raise ValueError(f"{alias}.{field} out of range: {value}")
            row[field] = value
            running_total += value
        total = item.get("total")
        if total != running_total:
            raise ValueError(f"{alias}.total mismatch: expected {running_total}, got {total}")
        row["total"] = total
        row["brief_reason"] = str(item.get("brief_reason", "")).strip()
        validated[alias] = row
    return validated


def compute_averages(scored_cases: list[dict], config: FrameworkConfig) -> dict[str, dict]:
    metrics = [*config.item_fields, "total"]
    system_scores: dict[str, dict[str, list[float]]] = {}
    for case in scored_cases:
        for system, score in case["system_scores"].items():
            bucket = system_scores.setdefault(system, {metric: [] for metric in metrics})
            for metric in metrics:
                bucket[metric].append(float(score[metric]))

    averages: dict[str, dict] = {}
    for system in SYSTEM_ORDER:
        if system not in system_scores:
            continue
        bucket = system_scores[system]
        averages[system] = {
            "count": len(bucket["total"]),
            "means": {metric: round(statistics.mean(values), 4) for metric, values in bucket.items()},
        }
    return averages


def save_progress(
    out_dir: Path,
    config: FrameworkConfig,
    rubric_path: Path,
    paper_root: Path,
    scored_cases: list[dict],
    missing_cases: list[dict],
    model_name: str,
) -> None:
    payload = {
        "framework": config.framework_id,
        "framework_display_name": config.display_name,
        "model": model_name,
        "rubric_file": str(rubric_path),
        "paper_root": str(paper_root),
        "scored_cases": scored_cases,
        "averages": compute_averages(scored_cases, config),
        "missing_cases": missing_cases,
    }
    (out_dir / "scores.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_summary_csv(out_dir: Path, config: FrameworkConfig, scored_cases: list[dict]) -> None:
    averages = compute_averages(scored_cases, config)
    header = ["system", "count", *config.item_fields, "total"]
    with (out_dir / "system_means.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for system in SYSTEM_ORDER:
            if system not in averages:
                continue
            row = [system, averages[system]["count"]]
            row.extend(averages[system]["means"][field] for field in config.item_fields)
            row.append(averages[system]["means"]["total"])
            writer.writerow(row)


def build_blind_packet(case_record: dict, aliased_outputs: dict[str, dict]) -> str:
    lines = [
        f"# Case {case_record['case']:02d}",
        "",
        f"- Folder: {case_record['folder']}",
        f"- Topic: {case_record['topic'] or 'N/A'}",
        "",
    ]
    for alias in sorted(aliased_outputs):
        lines.extend(
            [
                f"## Output {alias}",
                "",
                aliased_outputs[alias]["body"],
                "",
            ]
        )
    if case_record["missing"]:
        lines.extend(["## Missing Outputs", ""])
        for system in SYSTEM_ORDER:
            if system in case_record["missing"]:
                lines.append(f"- {SYSTEM_LABELS[system]}")
    return "\n".join(lines).strip() + "\n"


def default_out_dir(script_dir: Path, rubric_path: Path, config: FrameworkConfig) -> Path:
    safe_name = rubric_path.stem.strip() or "rubric"
    return script_dir / "workspace" / f"{config.framework_id}_{safe_name}"


def default_rubric_path(script_dir: Path, explicit_framework: str) -> Path:
    if explicit_framework == "erhq":
        return script_dir / "260327" / "내가 만든 루브릭.txt"
    return script_dir / "Universal IHQ Scoring Rules.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Blind rubric scorer for battery-materials outputs.",
    )
    parser.add_argument(
        "--rubric-file",
        help="Path to the rubric .txt file. Defaults to Universal IHQ Scoring Rules.txt.",
    )
    parser.add_argument(
        "--framework",
        choices=("auto", "ihq", "erhq"),
        default="auto",
        help="Rubric framework. Use auto to detect from the rubric text.",
    )
    parser.add_argument(
        "--paper-root",
        help="Root folder that contains the case directories. Defaults to the parent of the rubric folder.",
    )
    parser.add_argument("--case-start", type=int, default=1, help="First case number to score.")
    parser.add_argument("--case-end", type=int, default=30, help="Last case number to score.")
    parser.add_argument("--seed-base", type=int, default=1000, help="Base seed for blind alias shuffling.")
    parser.add_argument("--model", default="models/gemini-2.5-pro", help="Gemini model name.")
    parser.add_argument("--max-output-tokens", type=int, default=5000, help="Max output tokens for the judge response.")
    parser.add_argument("--out-dir", help="Directory for blind packets, bad responses, and summary files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_path = Path(__file__).resolve()
    script_dir = script_path.parent
    rubric_path = Path(args.rubric_file).resolve() if args.rubric_file else default_rubric_path(script_dir, args.framework)
    if not rubric_path.exists():
        raise FileNotFoundError(f"Rubric file not found: {rubric_path}")

    raw_rubric_text = read_text(rubric_path)
    config = detect_framework(raw_rubric_text, args.framework)
    rubric_text = extract_rubric_core(raw_rubric_text)

    if args.paper_root:
        paper_root = Path(args.paper_root).resolve()
    else:
        paper_root = script_dir.parent
    if not paper_root.exists():
        raise FileNotFoundError(f"Paper root not found: {paper_root}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else default_out_dir(script_dir, rubric_path, config)
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_dir = out_dir / "case_packets"
    packet_dir.mkdir(exist_ok=True)

    client = genai.Client(api_key=resolve_api_key())
    scored_cases: list[dict] = []
    missing_cases: list[dict] = []

    for case_no in range(args.case_start, args.case_end + 1):
        case_record = build_case_record(paper_root, case_no)
        if case_record is None:
            missing_cases.append({"case": case_no, "reason": "folder_not_found"})
            continue

        aliased_outputs, mapping = alias_outputs(case_record["outputs"], seed=args.seed_base + case_no)
        blind_packet = build_blind_packet(case_record, aliased_outputs)
        (packet_dir / f"case_{case_no:02d}.md").write_text(blind_packet, encoding="utf-8")

        if not aliased_outputs:
            missing_cases.append({"case": case_no, "reason": "no_outputs"})
            continue

        prompt = build_prompt(config, rubric_text, case_record, aliased_outputs)
        validated = None
        response_text = ""
        errors: list[str] = []
        for attempt in range(1, 4):
            retry_prompt = prompt
            if attempt > 1:
                retry_prompt += "\n\nYour previous response was invalid. Return valid JSON only with no commentary, no markdown fences, and no trailing commas."
            response_text = generate_with_retry(
                client=client,
                model_name=args.model,
                prompt=retry_prompt,
                max_output_tokens=args.max_output_tokens,
            )
            try:
                parsed = parse_model_json(response_text)
                validated = validate_scores(parsed["scores"], config, mapping)
                break
            except Exception as exc:
                errors.append(str(exc))
                (out_dir / f"bad_response_case_{case_no:02d}_attempt_{attempt}.txt").write_text(
                    response_text,
                    encoding="utf-8",
                )
        if validated is None:
            raise RuntimeError(f"Case {case_no:02d} could not be parsed after retries: {' | '.join(errors)}")

        system_scores = {system: validated[alias] for alias, system in mapping.items()}
        scored_cases.append(
            {
                "case": case_no,
                "folder": case_record["folder"],
                "topic": case_record["topic"],
                "mapping": mapping,
                "system_scores": system_scores,
                "missing": case_record["missing"],
                "raw_model_response": response_text,
            }
        )
        save_progress(out_dir, config, rubric_path, paper_root, scored_cases, missing_cases, args.model)
        print(f"[OK] case {case_no:02d} scored: {', '.join(sorted(system_scores))}")
        sys.stdout.flush()

    save_progress(out_dir, config, rubric_path, paper_root, scored_cases, missing_cases, args.model)
    write_summary_csv(out_dir, config, scored_cases)
    print(f"[DONE] framework={config.framework_id}")
    print(f"[DONE] scored_cases={len(scored_cases)}")
    print(f"[DONE] output_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

