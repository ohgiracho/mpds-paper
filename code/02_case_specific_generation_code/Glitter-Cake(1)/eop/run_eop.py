from __future__ import annotations

import argparse
import os
import re
import time
from pathlib import Path

try:
    from google import genai
except ImportError as exc:
    raise SystemExit("Install dependency: pip install google-genai") from exc

from merge_knowledge import merge_knowledge_texts


def default_case_number() -> str:
    case_match = re.search(r"\((\d+)\)$", Path(__file__).resolve().parent.parent.name)
    return case_match.group(1) if case_match else "1"


CASE_NUMBER = default_case_number()
SCRIPT_DIR = Path(__file__).resolve().parent
PARENT_DIR = SCRIPT_DIR.parent

DEFAULT_SIMULATION_DATE = "2024"
DEFAULT_DEBATE_TOPIC = (
    "How should a high-loading ASSB cathode composite be structured so that NCM811, "
    "LPSCl shell thickness, and small solid-electrolyte fillers jointly preserve ionic "
    "percolation, electronic access, and packing density?"
)
DEFAULT_USER_CONTEXT_FILE = str(PARENT_DIR / f"user_context({CASE_NUMBER}).txt")
DEFAULT_MODEL = "models/gemini-2.5-pro"
DEFAULT_KNOWLEDGE_A = str(SCRIPT_DIR / "Topic_NCM811_composite_cathode_solid-state_battery_2015-2024_Knowledge.txt")
DEFAULT_KNOWLEDGE_B = str(SCRIPT_DIR / "Topic_sulfide_solid-state_battery_cathode_composite_2015-2024_Knowledge.txt")
DEFAULT_MERGED_KNOWLEDGE = str(SCRIPT_DIR / f"Merged_Knowledge({CASE_NUMBER}).txt")


def default_output_file() -> str:
    return f"EOP_Answer({CASE_NUMBER}).txt"


def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def resolve_api_key() -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    api_key = api_key.strip('"').strip("'")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY or GOOGLE_API_KEY.")
    return api_key


def is_retryable(message: str) -> bool:
    text = (message or "").upper()
    keys = (
        "429",
        "RESOURCE_EXHAUSTED",
        "DEADLINE_EXCEEDED",
        "INTERNAL",
        "UNAVAILABLE",
        "SERVICE UNAVAILABLE",
        "503",
        "502",
        "500",
    )
    return any(k in text for k in keys)


def generate_with_retry(
    client: genai.Client,
    model_name: str,
    prompt: str,
    temperature: float,
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
                    "temperature": temperature,
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


def parse_from_debate_log(path: Path) -> tuple[str, str, str, str, str]:
    text = read_text(path)
    date_match = re.search(r"(?im)^\s*(?:Date|simulation_date)\s*:\s*(.+?)\s*$", text)
    topic_match = re.search(r"(?im)^\s*(?:Topic|topic)\s*:\s*(.+?)\s*$", text)
    context_patterns = [
        r"^\s*\[[^\]\n]*?(?:User(?:'s)?\s*Context|Context|맥락|컨텍스트)[^\]\n]*\]\s*(.+?)(?=^\s*\[[^\n]+\]|\Z)",
        r"^\s*(?:User(?:'s)?\s*Context|Context|[^\n:]*?(?:맥락|컨텍스트))\s*:\s*(.+?)(?=^\s*(?:Model:|Temperature:|MaxOutputTokens:|language:|rounds:|=+|\[)|\Z)",
    ]
    user_context = ""
    for pattern in context_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            user_context = match.group(1).strip()
            if user_context:
                break

    def resolve_logged_path(label: str) -> str:
        match = re.search(rf"(?im)^\s*{label}\s*:\s*(.+?)\s*$", text)
        if match:
            candidate = match.group(1).strip()
            if candidate and Path(candidate).exists():
                return candidate
        topic_files = sorted(path.parent.glob("Topic_*_Knowledge.txt"))
        if len(topic_files) >= 2:
            return str(topic_files[0] if label.endswith("a_file") else topic_files[1])
        return ""

    if not topic_match or not user_context:
        raise ValueError("Failed to parse debate log for topic/context.")

    simulation_date = date_match.group(1).strip() if date_match else ""
    debate_topic = topic_match.group(1).strip()
    return simulation_date, debate_topic, user_context, resolve_logged_path("knowledge_a_file"), resolve_logged_path("knowledge_b_file")


def build_persona_source(knowledge_a_text: str, knowledge_b_text: str, per_source_chars: int = 35000) -> str:
    excerpt_a = (knowledge_a_text or "")[:per_source_chars]
    excerpt_b = (knowledge_b_text or "")[:per_source_chars]
    return (
        "[Knowledge A Excerpt]\n"
        f"{excerpt_a}\n\n"
        "[Knowledge B Excerpt]\n"
        f"{excerpt_b}"
    ).strip()


def build_persona_prompt(simulation_date: str, persona_source_text: str) -> str:
    return f"""
[Context Setting]
Current Date: {simulation_date}
You are a scientist living in this era. Future knowledge (post-{simulation_date}) is unknown to you.

[Task]
Analyze the provided [Research Database] to extract the dominant research philosophy, technical instincts,
and problem-solving style implied by the evidence snapshot. Then synthesize one compact scientist persona
that can be used for a single evidence-grounded answer.

[DATA START]
{persona_source_text}
[DATA END]

### Phase 1: Pattern Extraction
1. What technical language and material priorities dominate this evidence base?
2. What failure modes, trade-offs, and design instincts appear repeatedly?
3. What style of scientific reasoning best fits this literature cluster?

### Phase 2: Persona Synthesis
Write a concise persona prompt that captures this style.
- Identity: tone, attitude, and technical posture
- Filter: how claims are judged and prioritized
- Answer style: how the scientist explains and commits to a route

### OUTPUT FORMAT
===ANALYSIS_SUMMARY===
(summary)

===SYSTEM_PROMPT===
(system prompt; MUST include "I am a scientist in {simulation_date}.")

===ONE_LINE_ID===
(one-line identity)
""".strip()


def _extract_tagged_block(text: str, tag: str) -> str:
    pattern = rf"==={tag}===\s*(.*?)(?=\n===|$)"
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_persona_response(text: str) -> tuple[str, str, str]:
    summary = _extract_tagged_block(text, "ANALYSIS_SUMMARY")
    system_prompt = _extract_tagged_block(text, "SYSTEM_PROMPT")
    one_line_id = _extract_tagged_block(text, "ONE_LINE_ID")

    if system_prompt:
        return summary, system_prompt, one_line_id or "Persona synthesized from analysis."

    clean = text.strip()
    return "", clean, "Persona synthesized from analysis."


def build_answer_prompt(
    simulation_date: str,
    debate_topic: str,
    user_context: str,
    persona_system_prompt: str,
    merged_knowledge: str,
) -> str:
    return f"""
You are a single-model evidence-only persona baseline assistant for battery materials research.

Constraints:
1) Current date is {simulation_date}.
2) Do not use knowledge published after {simulation_date}.
3) Use the evidence snapshot below as external knowledge.
4) Do not simulate debate or multiple agents.
5) Adopt the following scientist persona distilled from the evidence snapshot.
6) Keep the answer free-form.
7) For major mechanistic, design, or trade-off claims, cite supporting papers inline as [ID: n].
8) Use only IDs that exist in the evidence snapshot.
9) If evidence is weak or conflicting, say so explicitly.

[Persona]
{persona_system_prompt}

Debate topic:
{debate_topic}

User context:
{user_context}

[Evidence Snapshot]
{merged_knowledge}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-date", default=DEFAULT_SIMULATION_DATE)
    parser.add_argument("--debate-topic", default=DEFAULT_DEBATE_TOPIC)
    parser.add_argument("--user-context-file", default=DEFAULT_USER_CONTEXT_FILE)
    parser.add_argument("--debate-log", default="")
    parser.add_argument("--knowledge-a", default=DEFAULT_KNOWLEDGE_A)
    parser.add_argument("--knowledge-b", default=DEFAULT_KNOWLEDGE_B)
    parser.add_argument("--merged-knowledge", default=DEFAULT_MERGED_KNOWLEDGE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--output-file", default=default_output_file())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    simulation_date = args.simulation_date.strip()
    debate_topic = args.debate_topic.strip()
    user_context = ""
    knowledge_a = args.knowledge_a.strip()
    knowledge_b = args.knowledge_b.strip()
    merged_knowledge_path = Path(args.merged_knowledge.strip()) if args.merged_knowledge.strip() else None

    debate_log = Path(args.debate_log.strip()) if args.debate_log.strip() else None
    context_file = Path(args.user_context_file.strip()) if args.user_context_file.strip() else None

    if debate_log and debate_log.exists():
        parsed_date, parsed_topic, parsed_context, parsed_knowledge_a, parsed_knowledge_b = parse_from_debate_log(debate_log)
        if parsed_date:
            simulation_date = parsed_date
        if parsed_topic:
            debate_topic = parsed_topic
        if parsed_context:
            user_context = parsed_context
        if parsed_knowledge_a:
            knowledge_a = parsed_knowledge_a
        if parsed_knowledge_b:
            knowledge_b = parsed_knowledge_b

    if not user_context and context_file and context_file.exists():
        user_context = read_text(context_file).strip()

    if not simulation_date:
        raise SystemExit("Set --simulation-date or edit DEFAULT_SIMULATION_DATE.")
    if not debate_topic:
        raise SystemExit("Set --debate-topic or edit DEFAULT_DEBATE_TOPIC.")
    if not user_context:
        raise SystemExit("Provide --user-context-file or --debate-log.")

    merged_knowledge = ""
    merged_source = ""
    evidence_desc = ""
    knowledge_a_text = read_text(Path(knowledge_a)) if knowledge_a and Path(knowledge_a).exists() else ""
    knowledge_b_text = read_text(Path(knowledge_b)) if knowledge_b and Path(knowledge_b).exists() else ""

    if merged_knowledge_path and merged_knowledge_path.exists():
        merged_knowledge = read_text(merged_knowledge_path)
        merged_source = str(merged_knowledge_path.resolve())
        evidence_desc = merged_knowledge_path.name
    elif knowledge_a_text and knowledge_b_text:
        merged_knowledge = merge_knowledge_texts(Path(knowledge_a).name, Path(knowledge_b).name, knowledge_a_text, knowledge_b_text)
        merged_source = "in-memory merge"
        evidence_desc = f"{Path(knowledge_a).name} + {Path(knowledge_b).name}"
    else:
        raise SystemExit("Provide --merged-knowledge, or --knowledge-a and --knowledge-b, or a parsable --debate-log.")

    if not knowledge_a_text or not knowledge_b_text:
        raise SystemExit("EOP persona formation requires both --knowledge-a and --knowledge-b snapshots.")

    persona_source_text = build_persona_source(knowledge_a_text, knowledge_b_text, per_source_chars=35000)
    client = genai.Client(api_key=resolve_api_key())

    persona_raw = generate_with_retry(
        client=client,
        model_name=args.model,
        prompt=build_persona_prompt(simulation_date, persona_source_text),
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )
    persona_summary, persona_system_prompt, persona_one_line = parse_persona_response(persona_raw)

    answer_prompt = build_answer_prompt(
        simulation_date=simulation_date,
        debate_topic=debate_topic,
        user_context=user_context,
        persona_system_prompt=persona_system_prompt,
        merged_knowledge=merged_knowledge,
    )
    answer = generate_with_retry(
        client=client,
        model_name=args.model,
        prompt=answer_prompt,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )

    output_header = (
        "BaselineType: Evidence-Only Persona LLM (single-pass answer after persona synthesis)\n"
        "Source: merged external knowledge snapshot + evidence-derived persona\n"
        f"Evidence: {evidence_desc}\n"
        f"MergedKnowledgeSource: {merged_source}\n"
        f"PersonaSource: {Path(knowledge_a).name}[:35000] + {Path(knowledge_b).name}[:35000]\n"
        f"PersonaSummary: {persona_one_line}\n"
        f"Model: {args.model}\n"
        f"Temperature: {args.temperature}\n"
        f"MaxOutputTokens: {args.max_output_tokens}\n"
        "Language: en\n"
        f"Date: {simulation_date}\n"
        f"Topic: {debate_topic}\n"
    )
    if persona_summary:
        output_header += f"PersonaAnalysisSummary: {persona_summary}\n"

    output = output_header + "=" * 60 + "\n[EOP Answer]\n" + answer + "\n"
    Path(args.output_file).write_text(output, encoding="utf-8")
    print(f"[DONE] {args.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
