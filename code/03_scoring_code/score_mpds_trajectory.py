from __future__ import annotations

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


STAGE_ORDER = ["round1", "round2", "round3", "final"]
STAGE_LABELS = {
    "round1": "Round 1",
    "round2": "Round 2",
    "round3": "Round 3",
    "final": "Final",
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
ROUND_STAGE_HEADING_RE = re.compile(r"^\[Scientist [AB] - Round [123]\]\s*$", re.I)
APPENDIX_BANNER_RE = re.compile(r"^\s*---\s*Evidence Appendix\b.*---\s*$", re.I)


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
                "Do not assume later stages should score higher.",
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
                "Do not reward memo style, polish, confidence, evidence maps, or provenance labels.",
                "Do not assume later stages should score higher.",
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


def default_rubric_path(script_dir: Path, explicit_framework: str) -> Path:
    if explicit_framework == "erhq":
        return script_dir / "260327" / "내가 만든 루브릭.txt"
    return script_dir / "Universal IHQ Scoring Rules.txt"


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


def strip_metadata_and_markers(text: str) -> str:
    cleaned = text.replace("\r\n", "\n")
    cleaned = METADATA_LINE_RE.sub("", cleaned)
    for marker in ("[Raw LLM Answer]", "[DS Final Synthesis]", "[EO Answer]", "[Final Synthesis]", "[FINAL SYNTHESIS]"):
        cleaned = cleaned.replace(marker, "")
    cleaned = cleaned.lstrip("=\n ")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_trailing_support_sections(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    for line in lines:
        if is_truncation_header(line) or APPENDIX_BANNER_RE.match(line):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def remove_embedded_support_sections(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if skipping:
            if ROUND_STAGE_HEADING_RE.match(line):
                skipping = False
                kept.append(line)
            continue
        if APPENDIX_BANNER_RE.match(line) or is_truncation_header(line):
            skipping = True
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def clean_stage_body(stage: str, raw_text: str) -> str:
    body = strip_metadata_and_markers(raw_text)
    if stage == "final":
        body = strip_trailing_support_sections(body)
    else:
        body = remove_embedded_support_sections(body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def parse_situation(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    patterns = {
        "debate_topic": r'DEBATE_TOPIC\s*=\s*"([^"]+)"',
        "user_context": r'USER_CONTEXT\s*=\s*"""(.*?)"""',
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.DOTALL)
        result[key] = match.group(1).strip() if match else ""
    card_fields = [
        ("background", r"- Background:\s*(.*?)(?:\n- |\Z)"),
        ("main_bottleneck", r"- Main bottleneck:\s*(.*?)(?:\n- |\Z)"),
        ("transport_bottleneck", r"- Transport bottleneck:\s*(.*?)(?:\n- |\Z)"),
        ("structural_bottleneck", r"- Structural bottleneck:\s*(.*?)(?:\n- |\Z)"),
        ("process_concern", r"- Process concern:\s*(.*?)(?:\n- |\Z)"),
    ]
    for key, pattern in card_fields:
        match = re.search(pattern, result.get("user_context", ""), re.DOTALL)
        result[key] = re.sub(r"\s+", " ", match.group(1).strip()) if match else ""
    return result


def find_case_dir(paper_root: Path, case_no: int) -> Path | None:
    for path in sorted(paper_root.iterdir()):
        if not path.is_dir():
            continue
        match = CASE_DIR_PATTERN.search(path.name)
        if match and int(match.group(1)) == case_no:
            return path
    return None


def find_situation_file(case_dir: Path) -> Path | None:
    preferred = case_dir / "재실험" / "상황부여.txt"
    if preferred.exists():
        return preferred
    matches = sorted(path for path in case_dir.rglob("상황부여.txt") if path.is_file())
    return matches[0] if matches else None


def find_stage_file(case_dir: Path, stage: str, case_no: int) -> Path | None:
    target_name = {
        "round1": f"mpds_round1({case_no}).txt",
        "round2": f"mpds_round2({case_no}).txt",
        "round3": f"mpds_round3({case_no}).txt",
        "final": f"mpds_final({case_no}).txt",
    }[stage]
    candidates = [path for path in case_dir.rglob(target_name) if path.is_file()]
    if stage == "final":
        candidates = [path for path in candidates if "새로만든final" not in str(path)]
    if not candidates:
        return None
    candidates.sort(key=lambda path: (len(path.parts), len(str(path)), str(path)))
    return candidates[0]


def build_case_record(paper_root: Path, case_no: int) -> dict | None:
    case_dir = find_case_dir(paper_root, case_no)
    if case_dir is None:
        return None

    situation_path = find_situation_file(case_dir)
    situation = parse_situation(read_text(situation_path)) if situation_path else {}

    stages: dict[str, dict] = {}
    missing: dict[str, str] = {}
    for stage in STAGE_ORDER:
        path = find_stage_file(case_dir, stage, case_no)
        if path is None:
            missing[stage] = "not_found"
            continue
        raw_text = read_text(path)
        stages[stage] = {
            "path": str(path),
            "body": clean_stage_body(stage, raw_text),
        }
    return {
        "case": case_no,
        "folder": case_dir.name,
        "topic": situation.get("debate_topic", ""),
        "background": situation.get("background", ""),
        "main_bottleneck": situation.get("main_bottleneck", ""),
        "outputs": stages,
        "missing": missing,
    }


def alias_outputs(outputs: dict[str, dict], seed: int) -> tuple[dict[str, dict], dict[str, str]]:
    stages = list(outputs.keys())
    random.Random(seed).shuffle(stages)
    aliased: dict[str, dict] = {}
    mapping: dict[str, str] = {}
    for alias, stage in zip(("A", "B", "C", "D"), stages, strict=False):
        aliased[alias] = outputs[stage]
        mapping[alias] = stage
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

    return f"""You are conducting a conservative blind evaluation of MPDS trajectory stages.

Use ONLY the rubric below and ONLY the substantive answer body of each output.
Do not use prior expectations, prior scores, prior mappings, or assumptions from earlier conversations.
Do not reward length, citations, formatting, memo style, polish, confidence, section headers, evidence maps, or provenance labels.
Keep scores absolute rather than forcing artificial spread.
Do not infer or reveal the true stage labels.
Evaluate each output independently; do not assume later stages should score higher.
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
- Main bottleneck: {case_record["main_bottleneck"] or "N/A"}

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


def compute_stage_averages(scored_cases: list[dict], config: FrameworkConfig) -> dict[str, dict]:
    metrics = [*config.item_fields, "total"]
    stage_scores: dict[str, dict[str, list[float]]] = {
        stage: {metric: [] for metric in metrics} for stage in STAGE_ORDER
    }
    for case in scored_cases:
        for stage, score in case["stage_scores"].items():
            bucket = stage_scores[stage]
            for metric in metrics:
                bucket[metric].append(float(score[metric]))

    averages: dict[str, dict] = {}
    for stage in STAGE_ORDER:
        bucket = stage_scores[stage]
        if not bucket["total"]:
            continue
        averages[stage] = {
            "count": len(bucket["total"]),
            "means": {metric: round(statistics.mean(values), 4) for metric, values in bucket.items()},
        }
    return averages


def top_axis_gains(case: dict, config: FrameworkConfig) -> list[tuple[str, float]]:
    gains = []
    round1 = case["stage_scores"]["round1"]
    final = case["stage_scores"]["final"]
    for label, field in zip(config.item_labels, config.item_fields, strict=True):
        gains.append((label, final[field] - round1[field]))
    gains.sort(key=lambda item: (-item[1], item[0]))
    return gains


def build_case_summary(case: dict, config: FrameworkConfig) -> dict[str, object]:
    totals = [case["stage_scores"][stage]["total"] for stage in STAGE_ORDER]
    delta = totals[-1] - totals[0]
    monotonic = all(later >= earlier for earlier, later in zip(totals, totals[1:], strict=False))
    gains = top_axis_gains(case, config)
    top_gain_text = ", ".join(f"{label} {gain:+.0f}" for label, gain in gains[:2])
    summary_text = (
        f"Total rises {totals[0]} -> {totals[-1]} ({delta:+d}). "
        f"Largest axis change: {top_gain_text}. "
        f"Trend is {'monotonic' if monotonic else 'non-monotonic'} across stages."
    )
    return {
        "round1_to_final_delta": delta,
        "monotonic_total_trend": monotonic,
        "top_axis_gains": gains,
        "summary_text": summary_text,
    }


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
        "stage_averages": compute_stage_averages(scored_cases, config),
        "missing_cases": missing_cases,
    }
    (out_dir / "trajectory_scores.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_stage_means_csv(out_dir: Path, config: FrameworkConfig, scored_cases: list[dict]) -> None:
    averages = compute_stage_averages(scored_cases, config)
    header = ["stage", "count", *config.item_fields, "total"]
    with (out_dir / "trajectory_stage_means.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for stage in STAGE_ORDER:
            if stage not in averages:
                continue
            row = [stage, averages[stage]["count"]]
            row.extend(averages[stage]["means"][field] for field in config.item_fields)
            row.append(averages[stage]["means"]["total"])
            writer.writerow(row)


def write_case_totals_csv(out_dir: Path, scored_cases: list[dict]) -> None:
    header = [
        "case",
        "folder",
        "topic",
        "round1_total",
        "round2_total",
        "round3_total",
        "final_total",
        "delta_round1_to_final",
        "monotonic_total_trend",
    ]
    with (out_dir / "trajectory_case_totals.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for case in scored_cases:
            summary = case["trajectory_summary"]
            writer.writerow(
                [
                    case["case"],
                    case["folder"],
                    case["topic"],
                    case["stage_scores"]["round1"]["total"],
                    case["stage_scores"]["round2"]["total"],
                    case["stage_scores"]["round3"]["total"],
                    case["stage_scores"]["final"]["total"],
                    summary["round1_to_final_delta"],
                    "yes" if summary["monotonic_total_trend"] else "no",
                ]
            )


def maybe_generate_charts(out_dir: Path, config: FrameworkConfig, scored_cases: list[dict]) -> None:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("[WARN] matplotlib not installed; skipping chart generation.")
        return

    averages = compute_stage_averages(scored_cases, config)
    stages = [stage for stage in STAGE_ORDER if stage in averages]
    x_labels = [STAGE_LABELS[stage] for stage in stages]

    plt.figure(figsize=(7.2, 4.2), dpi=180)
    totals = [averages[stage]["means"]["total"] for stage in stages]
    plt.plot(x_labels, totals, marker="o", linewidth=2.4, color="#0F766E")
    plt.ylim(bottom=0)
    plt.title("Mean Total by Stage")
    plt.ylabel("Total Score")
    plt.grid(axis="y", alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_dir / "trajectory_mean_totals.png", bbox_inches="tight")
    plt.close()

    plt.figure(figsize=(7.2, 4.4), dpi=180)
    palette = ["#B45309", "#0F766E", "#1D4ED8", "#6B7280", "#7C3AED"]
    for idx, (label, field) in enumerate(zip(config.item_labels, config.item_fields, strict=True)):
        values = [averages[stage]["means"][field] for stage in stages]
        plt.plot(x_labels, values, marker="o", linewidth=2.0, label=label, color=palette[idx % len(palette)])
    plt.ylim(0, 5)
    plt.title("Mean Axis Scores by Stage")
    plt.ylabel("Axis Score")
    plt.grid(axis="y", alpha=0.25)
    plt.legend(loc="upper left", fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "trajectory_mean_axes.png", bbox_inches="tight")
    plt.close()

    ranked = sorted(
        scored_cases,
        key=lambda item: (-item["trajectory_summary"]["round1_to_final_delta"], item["case"]),
    )[:10]
    plt.figure(figsize=(7.4, 4.6), dpi=180)
    labels = [f"{item['case']:02d}" for item in ranked]
    values = [item["trajectory_summary"]["round1_to_final_delta"] for item in ranked]
    plt.bar(labels, values, color="#1D4ED8")
    plt.title("Top Round1->Final Total Gains")
    plt.xlabel("Case")
    plt.ylabel("Gain")
    plt.tight_layout()
    plt.savefig(out_dir / "trajectory_top_gains.png", bbox_inches="tight")
    plt.close()


def default_out_dir(script_dir: Path, config: FrameworkConfig) -> Path:
    return script_dir / "workspace" / f"{config.framework_id}_mpds_trajectory_universal"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Blind trajectory scorer for MPDS round1-3 and final outputs.",
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
    parser.add_argument("--seed-base", type=int, default=3000, help="Base seed for blind alias shuffling.")
    parser.add_argument("--model", default="models/gemini-2.5-pro", help="Gemini model name.")
    parser.add_argument("--max-output-tokens", type=int, default=5000, help="Max output tokens for the judge response.")
    parser.add_argument("--out-dir", help="Directory for packets, bad responses, and summary files.")
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

    out_dir = Path(args.out_dir).resolve() if args.out_dir else default_out_dir(script_dir, config)
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

        if set(case_record["outputs"]) != set(STAGE_ORDER):
            missing_cases.append({"case": case_no, "reason": "missing_stages", "missing": case_record["missing"]})
            continue

        aliased_outputs, mapping = alias_outputs(case_record["outputs"], seed=args.seed_base + case_no)
        packet_lines = [
            f"# Case {case_no:02d}",
            "",
            f"- Folder: {case_record['folder']}",
            f"- Topic: {case_record['topic'] or 'N/A'}",
            f"- Main bottleneck: {case_record['main_bottleneck'] or 'N/A'}",
            "",
        ]
        for alias in sorted(aliased_outputs):
            packet_lines.extend([f"## Output {alias}", "", aliased_outputs[alias]["body"], ""])
        (packet_dir / f"case_{case_no:02d}.md").write_text("\n".join(packet_lines).strip() + "\n", encoding="utf-8")

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

        stage_scores = {stage: validated[alias] for alias, stage in mapping.items()}
        case_payload = {
            "case": case_no,
            "folder": case_record["folder"],
            "topic": case_record["topic"],
            "background": case_record["background"],
            "main_bottleneck": case_record["main_bottleneck"],
            "mapping": mapping,
            "stage_scores": stage_scores,
            "raw_model_response": response_text,
        }
        case_payload["trajectory_summary"] = build_case_summary(case_payload, config)
        scored_cases.append(case_payload)
        save_progress(out_dir, config, rubric_path, paper_root, scored_cases, missing_cases, args.model)
        print(f"[OK] case {case_no:02d} scored")
        sys.stdout.flush()

    scored_cases.sort(key=lambda item: item["case"])
    save_progress(out_dir, config, rubric_path, paper_root, scored_cases, missing_cases, args.model)
    write_stage_means_csv(out_dir, config, scored_cases)
    write_case_totals_csv(out_dir, scored_cases)
    maybe_generate_charts(out_dir, config, scored_cases)
    print(f"[DONE] framework={config.framework_id}")
    print(f"[DONE] scored_cases={len(scored_cases)}")
    print(f"[DONE] output_dir={out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
