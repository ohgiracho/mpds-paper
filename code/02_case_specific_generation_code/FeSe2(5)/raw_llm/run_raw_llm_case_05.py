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


DEFAULT_SIMULATION_DATE = "2017"
DEFAULT_DEBATE_TOPIC = "What FeSe2/carbon architecture would best balance sodium storage capacity, volume-change buffering, and electrical wiring without collapsing the hollow carbon host?"
DEFAULT_USER_CONTEXT_FILE = str((Path(__file__).resolve().parent / "user_context(5).txt"))
DEFAULT_MODEL = "models/gemini-2.5-pro"




def default_output_file() -> str:
    case_match = re.search(r"\((\d+)\)$", Path(__file__).stem)
    if case_match:
        return f"Raw_LLM_Answer({case_match.group(1)}).txt"
    return "Raw_LLM_Answer.txt"

def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def resolve_api_key() -> str:
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip().strip("\"'")
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


def parse_from_debate_log(path: Path) -> tuple[str, str, str]:
    text = read_text(path)
    date_match = re.search(r"(?im)^\s*(?:Date|simulation_date)\s*:\s*(.+?)\s*$", text)
    topic_match = re.search(r"(?im)^\s*(?:Topic|topic)\s*:\s*(.+?)\s*$", text)

    # Supports [User Context], [User's Context], Context:, and Korean variants like 맥락/컨텍스트 labels.
    context_patterns = [
        r"^\s*\[[^\]\n]*?(?:User(?:'|’)?s?\s*Context|Context|\ub9e5\ub77d|\ucee8\ud14d\uc2a4\ud2b8)[^\]\n]*\]\s*(.+?)(?=^\s*\[[^\n]+\]|\Z)",
        r"^\s*(?:User(?:'|’)?s?\s*Context|Context|[^\n:]*?(?:\ub9e5\ub77d|\ucee8\ud14d\uc2a4\ud2b8))\s*:\s*(.+?)(?=^\s*(?:Model:|Temperature:|MaxOutputTokens:|language:|rounds:|=+|\[)|\Z)",
    ]

    user_context = ""
    for pattern in context_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if match:
            user_context = match.group(1).strip()
            if user_context:
                break

    if not topic_match or not user_context:
        raise ValueError("Failed to parse debate log for topic/context.")

    simulation_date = date_match.group(1).strip() if date_match else ""
    debate_topic = topic_match.group(1).strip()
    return simulation_date, debate_topic, user_context


def build_prompt(simulation_date: str, debate_topic: str, user_context: str) -> str:
    return f"""
You are a single-model raw baseline assistant for battery materials research.

Constraints:
1) Current date is {simulation_date}.
2) Do not use knowledge published after {simulation_date}.


Debate topic:
{debate_topic}

User context:
{user_context}
""".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-date", default=DEFAULT_SIMULATION_DATE)
    parser.add_argument("--debate-topic", default=DEFAULT_DEBATE_TOPIC)
    parser.add_argument("--user-context-file", default=DEFAULT_USER_CONTEXT_FILE)
    parser.add_argument("--debate-log", default="")
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

    debate_log = Path(args.debate_log.strip()) if args.debate_log.strip() else None
    context_file = Path(args.user_context_file.strip()) if args.user_context_file.strip() else None

    if debate_log and debate_log.exists():
        parsed_date, parsed_topic, parsed_context = parse_from_debate_log(debate_log)
        if not simulation_date:
            simulation_date = parsed_date
        if not debate_topic:
            debate_topic = parsed_topic
        user_context = parsed_context

    if not user_context and context_file and context_file.exists():
        user_context = read_text(context_file).strip()

    if not simulation_date:
        raise SystemExit("Set --simulation-date or edit DEFAULT_SIMULATION_DATE.")
    if not debate_topic:
        raise SystemExit("Set --debate-topic or edit DEFAULT_DEBATE_TOPIC.")
    if not user_context:
        raise SystemExit("Provide --user-context-file or --debate-log.")

    client = genai.Client(api_key=resolve_api_key())
    prompt = build_prompt(simulation_date, debate_topic, user_context)

    # Single-pass baseline: exactly one generation call per run (retry only on transient API errors).
    answer = generate_with_retry(
        client=client,
        model_name=args.model,
        prompt=prompt,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
    )

    output_header = (
        "BaselineType: Raw LLM (parametric-only, single-pass)\n"
        "Source: Model internal knowledge\n"
        "Evidence: None\n"
        f"Model: {args.model}\n"
        f"Temperature: {args.temperature}\n"
        f"MaxOutputTokens: {args.max_output_tokens}\n"
        "Language: en\n"
        f"Date: {simulation_date}\n"
        f"Topic: {debate_topic}\n"
    )

    output = output_header + "=" * 60 + "\n[Raw LLM Answer]\n" + answer + "\n"
    Path(args.output_file).write_text(output, encoding="utf-8")
    print(f"[DONE] {args.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





