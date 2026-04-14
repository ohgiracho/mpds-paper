from __future__ import annotations

import argparse
import os
import re
import time
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from google import genai
except ImportError as exc:
    raise SystemExit("Install dependency: pip install google-genai") from exc


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


configure_stdio()
DEFAULT_SIMULATION_DATE = "2017"
DEFAULT_DEBATE_TOPIC = "What FeSe2/carbon architecture would best balance sodium storage capacity, volume-change buffering, and electrical wiring without collapsing the hollow carbon host?"
DEFAULT_USER_CONTEXT_FILE = str((Path(__file__).resolve().parent / "user_context(5).txt"))
DEFAULT_SITUATION_FILE = str((Path(__file__).resolve().parent / "상황부여.txt"))
DEFAULT_KNOWLEDGE_A = str((Path(__file__).resolve().parent / "Topic_iron_selenide_anodes_2008-2017_Knowledge.txt"))
DEFAULT_KNOWLEDGE_B = str((Path(__file__).resolve().parent / "Topic_carbon_encapsulation_2008-2017_Knowledge.txt"))
DEFAULT_MODEL = "models/gemini-2.5-pro"
DEFAULT_MIN_EVIDENCE_POINTERS = 3
DEFAULT_TURN_SLEEP_SEC = 0.2
MAX_VALIDATION_REGEN_ATTEMPTS = 5

CITATION_STYLE_GUIDE = (
    "Mandatory inline format: [ID: <n>]\n"
    "- Use IDs that exist in MY DATA.\n"
    "- Do not fabricate bibliographic metadata."
)


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


def build_persona_prompt(simulation_date: str, knowledge: str) -> str:
    return f"""
[Context Setting]
Current Date: {simulation_date}
You are a scientist living in this era. Future knowledge (post-{simulation_date}) is unknown to you.

[Task]
Analyze the provided [Research Database] to extract the author's research philosophy, personality, and debate style.
Then, be reborn as that specific persona.

[DATA START]
{knowledge[:70000]}
[DATA END]

### Phase 1: Deep Text Analysis
1. Keyword Signature: What technical terms define this researcher?
2. Problem-Solving: How do they approach experimental failure? (Theoretical vs. Practical)
3. Value System: What do they value most? (Efficiency, Stability, Novelty?)

### Phase 2: Persona Synthesis
Based on the analysis, write your own [System Prompt].
- Identity: Define who you are (Tone, Attitude).
- Filter: How do you verify scientific claims?
- Debate Style: How do you critique others?

### OUTPUT FORMAT
===ANALYSIS_SUMMARY===
(summary)

===SYSTEM_PROMPT===
(system prompt; MUST include "I am a scientist in {simulation_date}.")

===ONE_LINE_ID===
(one-line identity)
""".strip()


def build_turn_prompt(
    simulation_date: str,
    debate_topic: str,
    persona_system_prompt: str,
    knowledge: str,
    turn_instruction: str,
) -> str:
    return f"""
[SYSTEM INSTRUCTION: Persona & Constraints]
1. Current Date: {simulation_date} (Do not use knowledge from the future.)
2. Your Persona: {persona_system_prompt}

[YOUR KNOWLEDGE BASE (Internal Memory)]
--- MY DATA START ---
{knowledge}
--- MY DATA END ---

[INTERACTION RULES]
1. Separate Databases (CRITICAL):
   - You and your opponent have different datasets.
   - Opponent's [ID: X] does not equal your [ID: X].
2. Verification Strategy:
   - Debate scientific logic, not citation-id validity.
   - Cite by attaching [ID: n] pointers that refer to entries in MY DATA.
   - Do not fabricate bibliographic metadata.
3. Citation Style (MANDATORY):
   - {CITATION_STYLE_GUIDE}
   - Attach [ID: n] to each key claim.

[Debate Topic]
{debate_topic}

[Turn Instruction]
{turn_instruction}
""".strip()


def build_judge_prompt(
    simulation_date: str,
    debate_topic: str,
    original_situation: str,
    transcript: str,
) -> str:
    return f"""
You are a Research Director in {simulation_date}.
Review the scientific debate regarding: "{debate_topic}".

[Debate Log]
{transcript}

[Task]
1. Synthesize the arguments from both sides.
2. Recommend the most probable successful composition, architecture, or strategy for this case.
3. Use only knowledge available up to {simulation_date}.
4. Do not introduce new scientific content beyond what already appeared in the debate.
5. Preserve citation traceability using debater-scoped citations such as Scientist A [ID: n] and Scientist B [ID: n].
6. Write in English as a concise research-director memorandum.

Preferred output style:
- **To / From / Date / Subject**
- **### 1. Synthesis of Arguments**
- **### 2. Director's Assessment and Recommended Path Forward**
- **### 3. Evidence Map for Recommended Composition**
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


def parse_snapshot_index(knowledge_text: str) -> dict[int, dict[str, str]]:
    index: dict[int, dict[str, str]] = {}
    current: dict[str, str] | None = None

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        id_text = current.get("id", "").strip()
        if id_text.isdigit():
            paper_id = int(id_text)
            index[paper_id] = {
                "id": str(paper_id),
                "title": current.get("title", "N/A"),
                "year": current.get("year", "N/A"),
                "first_author": current.get("first_author", "N/A"),
                "venue": current.get("venue", "N/A"),
                "doi": current.get("doi", "N/A"),
                "openalex_id": current.get("openalex_id", "N/A"),
            }
        current = None

    for raw_line in knowledge_text.splitlines():
        line = raw_line.strip()
        if line.startswith("ID:"):
            flush_current()
            current = {
                "id": line.split(":", 1)[1].strip(),
                "title": "N/A",
                "year": "N/A",
                "first_author": "N/A",
                "venue": "N/A",
                "doi": "N/A",
                "openalex_id": "N/A",
            }
            continue

        if current is None:
            continue

        if line.startswith("Title:"):
            current["title"] = line.split(":", 1)[1].strip() or "N/A"
        elif line.startswith("Year:"):
            current["year"] = line.split(":", 1)[1].strip() or "N/A"
        elif line.startswith("FirstAuthor:"):
            current["first_author"] = line.split(":", 1)[1].strip() or "N/A"
        elif line.startswith("Venue:"):
            current["venue"] = line.split(":", 1)[1].strip() or "N/A"
        elif line.startswith("DOI:"):
            current["doi"] = line.split(":", 1)[1].strip() or "N/A"
        elif line.startswith("OpenAlexID:"):
            current["openalex_id"] = line.split(":", 1)[1].strip() or "N/A"
        elif line and set(line) == {"-"}:
            flush_current()

    flush_current()
    return index


def extract_referenced_ids(text: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"\[ID\s*:\s*(\d+)\]", text or "", flags=re.IGNORECASE)]


def extract_judge_referenced_ids(text: str) -> dict[str, list[int]]:
    refs_a: list[int] = []
    refs_b: list[int] = []
    scoped_spans: list[tuple[int, int]] = []

    for m in re.finditer(r"Scientist\s*A\s*\[ID\s*:\s*(\d+)\]", text or "", flags=re.IGNORECASE):
        refs_a.append(int(m.group(1)))
        scoped_spans.append(m.span())
    for m in re.finditer(r"Scientist\s*B\s*\[ID\s*:\s*(\d+)\]", text or "", flags=re.IGNORECASE):
        refs_b.append(int(m.group(1)))
        scoped_spans.append(m.span())

    unscoped: list[int] = []
    for m in re.finditer(r"\[ID\s*:\s*(\d+)\]", text or "", flags=re.IGNORECASE):
        in_scoped = any(m.start() >= s and m.end() <= e for s, e in scoped_spans)
        if not in_scoped:
            unscoped.append(int(m.group(1)))

    return {"A": refs_a, "B": refs_b, "unscoped": unscoped}


def validate_turn_response(
    response_text: str,
    snapshot_index: dict[int, dict[str, str]],
    min_evidence_pointers: int,
) -> tuple[bool, str, dict[str, Any]]:
    distinct_ids = sorted(set(extract_referenced_ids(response_text)))
    missing_ids = [i for i in distinct_ids if i not in snapshot_index]
    valid_ids = [i for i in distinct_ids if i in snapshot_index]

    if len(distinct_ids) < min_evidence_pointers:
        return (
            False,
            f"Insufficient evidence pointers: found {len(distinct_ids)}, need >= {min_evidence_pointers}.",
            {"distinct_ids": distinct_ids, "missing_ids": missing_ids, "valid_ids": valid_ids},
        )
    if missing_ids:
        return (
            False,
            f"Referenced IDs do not exist in snapshot: {missing_ids}",
            {"distinct_ids": distinct_ids, "missing_ids": missing_ids, "valid_ids": valid_ids},
        )
    return (
        True,
        "",
        {"distinct_ids": distinct_ids, "missing_ids": [], "valid_ids": valid_ids},
    )


def validate_judge_response(
    response_text: str,
    snapshot_index_a: dict[int, dict[str, str]],
    snapshot_index_b: dict[int, dict[str, str]],
    min_evidence_pointers: int,
) -> tuple[bool, str, dict[str, Any]]:
    refs = extract_judge_referenced_ids(response_text)
    ids_a = sorted(set(refs["A"]))
    ids_b = sorted(set(refs["B"]))
    total_distinct = sorted(set(ids_a + ids_b))

    unscoped_ids = sorted(set(refs["unscoped"]))
    if len(total_distinct) < min_evidence_pointers:
        return (
            False,
            f"Insufficient debater-scoped evidence pointers: found {len(total_distinct)}, need >= {min_evidence_pointers}.",
            {"ids_a": ids_a, "ids_b": ids_b},
        )
    if not ids_a or not ids_b:
        return (
            False,
            "Judge must reference both Scientist A and Scientist B IDs.",
            {"ids_a": ids_a, "ids_b": ids_b},
        )

    missing_a = [i for i in ids_a if i not in snapshot_index_a]
    missing_b = [i for i in ids_b if i not in snapshot_index_b]
    if missing_a or missing_b:
        return (
            False,
            f"Judge referenced non-existent IDs (A missing: {missing_a}, B missing: {missing_b}).",
            {"ids_a": ids_a, "ids_b": ids_b},
        )

    return True, "", {"ids_a": ids_a, "ids_b": ids_b}


def format_evidence_entry(paper_id: int, entry: dict[str, str]) -> str:
    first_author = entry.get("first_author", "N/A")
    year = entry.get("year", "N/A")
    title = entry.get("title", "N/A")
    venue = entry.get("venue", "N/A")
    doi = entry.get("doi", "N/A")
    openalex_id = entry.get("openalex_id", "N/A")

    parts = [f"ID: {paper_id}", f"{first_author}, {year}", title]
    if venue and venue != "N/A":
        parts.append(f"Venue: {venue}")
    if doi and doi != "N/A":
        parts.append(f"DOI: {doi}")
    if openalex_id and openalex_id != "N/A":
        parts.append(f"OpenAlexID: {openalex_id}")
    return "- [" + " | ".join(parts) + "]"


def append_evidence_appendix(
    response_text: str,
    ids: list[int],
    snapshot_index: dict[int, dict[str, str]],
    debater_label: str,
) -> str:
    lines = [response_text.rstrip(), "", "--- Evidence Appendix (auto-generated from snapshot) ---", f"Snapshot: {debater_label}"]
    if not ids:
        lines.append("- (No valid IDs found)")
    else:
        for paper_id in sorted(set(ids)):
            if paper_id in snapshot_index:
                lines.append(format_evidence_entry(paper_id, snapshot_index[paper_id]))
    return "\n".join(lines).rstrip() + "\n"


def append_judge_evidence_appendix(
    response_text: str,
    ids_a: list[int],
    ids_b: list[int],
    snapshot_index_a: dict[int, dict[str, str]],
    snapshot_index_b: dict[int, dict[str, str]],
) -> str:
    lines = [response_text.rstrip(), "", "--- Evidence Appendix (Scientist A snapshot) ---"]
    if not ids_a:
        lines.append("- (No valid Scientist A IDs found)")
    else:
        for paper_id in sorted(set(ids_a)):
            if paper_id in snapshot_index_a:
                lines.append(format_evidence_entry(paper_id, snapshot_index_a[paper_id]))

    lines.append("")
    lines.append("--- Evidence Appendix (Scientist B snapshot) ---")
    if not ids_b:
        lines.append("- (No valid Scientist B IDs found)")
    else:
        for paper_id in sorted(set(ids_b)):
            if paper_id in snapshot_index_b:
                lines.append(format_evidence_entry(paper_id, snapshot_index_b[paper_id]))
    return "\n".join(lines).rstrip() + "\n"


def extract_reproducibility_header(knowledge_text: str) -> str:
    lines = knowledge_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("REPRODUCIBILITY:"):
            start = i
            break
    if start is None:
        return "REPRODUCIBILITY:\n(not found)"

    out: list[str] = []
    for j in range(start, len(lines)):
        out.append(lines[j].rstrip())
        stripped = lines[j].strip()
        if j > start and stripped and set(stripped) == {"="}:
            break
    return "\n".join(out).strip()


def prepend_validation_failure_note(base_prompt: str, reason: str) -> str:
    return (
        "VALIDATION FAILED: Your answer had insufficient/invalid evidence pointers. "
        "Re-answer and attach [ID: n] to each key claim.\n"
        f"Validation details: {reason}\n\n"
        f"{base_prompt}"
    )


def generate_validated_response(
    client: genai.Client,
    model_name: str,
    base_prompt: str,
    temperature: float,
    max_output_tokens: int,
    validate_fn: Callable[[str], tuple[bool, str, dict[str, Any]]],
    context_label: str,
    max_regen_attempts: int = MAX_VALIDATION_REGEN_ATTEMPTS,
) -> tuple[str, dict[str, Any]]:
    prompt_to_use = base_prompt
    last_reason = "unknown"
    last_payload: dict[str, Any] = {}

    for attempt in range(max_regen_attempts + 1):
        candidate = generate_with_retry(
            client=client,
            model_name=model_name,
            prompt=prompt_to_use,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        ok, reason, payload = validate_fn(candidate)
        if ok:
            return candidate, payload

        last_reason = reason
        last_payload = payload
        if attempt < max_regen_attempts:
            print(
                f"[VALIDATION] {context_label} failed: {reason} "
                f"(regen {attempt + 1}/{max_regen_attempts})"
            )
            prompt_to_use = prepend_validation_failure_note(base_prompt, reason)

    raise RuntimeError(
        f"{context_label} failed validation after {max_regen_attempts} regenerations. "
        f"Last reason: {last_reason}. Last payload: {last_payload}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation-date", default=DEFAULT_SIMULATION_DATE)
    parser.add_argument("--debate-topic", default=DEFAULT_DEBATE_TOPIC)
    parser.add_argument("--user-context-file", default=DEFAULT_USER_CONTEXT_FILE)
    parser.add_argument("--situation-file", default=DEFAULT_SITUATION_FILE)
    parser.add_argument("--knowledge-a", default=DEFAULT_KNOWLEDGE_A)
    parser.add_argument("--knowledge-b", default=DEFAULT_KNOWLEDGE_B)
    parser.add_argument("--name-a", default="The Architect (Scientist A)")
    parser.add_argument("--name-b", default="The Engineer (Scientist B)")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--max-output-tokens", type=int, default=8192)
    parser.add_argument("--min-evidence-pointers", type=int, default=DEFAULT_MIN_EVIDENCE_POINTERS)
    parser.add_argument("--turn-sleep-sec", type=float, default=DEFAULT_TURN_SLEEP_SEC)
    parser.add_argument("--output-file", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    simulation_date = args.simulation_date.strip()
    debate_topic = args.debate_topic.strip()
    context_file = Path(args.user_context_file.strip())
    situation_file = Path(args.situation_file.strip())
    knowledge_a_file = Path(args.knowledge_a.strip())
    knowledge_b_file = Path(args.knowledge_b.strip())

    if not simulation_date:
        raise SystemExit("Set --simulation-date or edit DEFAULT_SIMULATION_DATE.")
    if not debate_topic:
        raise SystemExit("Set --debate-topic or edit DEFAULT_DEBATE_TOPIC.")
    if not context_file.exists():
        raise SystemExit("User context file does not exist.")
    if not situation_file.exists():
        raise SystemExit("Situation file does not exist.")
    if not knowledge_a_file.exists() or not knowledge_b_file.exists():
        raise SystemExit("Knowledge file path is invalid.")
    if args.min_evidence_pointers < 1:
        raise SystemExit("--min-evidence-pointers must be >= 1.")
    if args.turn_sleep_sec < 0:
        raise SystemExit("--turn-sleep-sec must be >= 0.")

    user_context = read_text(context_file).strip()
    original_situation = read_text(situation_file).strip()
    knowledge_a = read_text(knowledge_a_file)
    knowledge_b = read_text(knowledge_b_file)

    snapshot_index_a = parse_snapshot_index(knowledge_a)
    snapshot_index_b = parse_snapshot_index(knowledge_b)
    if not snapshot_index_a:
        raise SystemExit("Failed to parse any paper blocks from knowledge-a snapshot.")
    if not snapshot_index_b:
        raise SystemExit("Failed to parse any paper blocks from knowledge-b snapshot.")

    reproducibility_a = extract_reproducibility_header(knowledge_a)
    reproducibility_b = extract_reproducibility_header(knowledge_b)
    run_timestamp_utc = datetime.now(timezone.utc).isoformat()

    client = genai.Client(api_key=resolve_api_key())
    print(f"Model fixed to: {args.model}")
    print(f"Simulation date: {simulation_date}")
    print(f"Snapshot A indexed papers: {len(snapshot_index_a)}")
    print(f"Snapshot B indexed papers: {len(snapshot_index_b)}\n")

    print(f"[{args.name_a}] Building persona from data mining... (date anchor: {simulation_date})")
    persona_a_raw = generate_with_retry(
        client,
        args.model,
        build_persona_prompt(simulation_date, knowledge_a),
        args.temperature,
        args.max_output_tokens,
    )
    _, persona_a_system_prompt, persona_a_one_line = parse_persona_response(persona_a_raw)
    print(f"   Persona summary: {persona_a_one_line}")

    print(f"\n[{args.name_b}] Building persona from data mining... (date anchor: {simulation_date})")
    persona_b_raw = generate_with_retry(
        client,
        args.model,
        build_persona_prompt(simulation_date, knowledge_b),
        args.temperature,
        args.max_output_tokens,
    )
    _, persona_b_system_prompt, persona_b_one_line = parse_persona_response(persona_b_raw)
    print(f"   Persona summary: {persona_b_one_line}")

    print(f"\n[Debate Start] Topic: {debate_topic}")

    log_content = (
        "[RUN CONFIG]\n"
        f"run_timestamp_utc: {run_timestamp_utc}\n"
        f"model: {args.model}\n"
        f"temperature: {args.temperature}\n"
        f"max_output_tokens: {args.max_output_tokens}\n"
        'language: "en"\n'
        f"min_evidence_pointers: {args.min_evidence_pointers}\n"
        f"turn_sleep_sec: {args.turn_sleep_sec}\n"
        f"rounds: {args.rounds}\n"
        f"simulation_date: {simulation_date}\n"
        f"topic: {debate_topic}\n\n"
        f"knowledge_a_file: {knowledge_a_file.resolve()}\n"
        f"{reproducibility_a}\n\n"
        f"knowledge_b_file: {knowledge_b_file.resolve()}\n"
        f"{reproducibility_b}\n\n"
        f"Context: {user_context}\n\n"
        + "=" * 60
        + "\n\n"
    )

    current_input = f"""
[Current Date: {simulation_date}]
[User's Context]
{user_context}

[Question]
Based on your persona and data, diagnose the problem and propose a solution.
Use [ID: n] pointers from your own snapshot for each key claim.
""".strip()

    debaters = [
        {
            "role_label": "Scientist A",
            "name": args.name_a,
            "knowledge": knowledge_a,
            "persona": persona_a_system_prompt,
            "snapshot_index": snapshot_index_a,
        },
        {
            "role_label": "Scientist B",
            "name": args.name_b,
            "knowledge": knowledge_b,
            "persona": persona_b_system_prompt,
            "snapshot_index": snapshot_index_b,
        },
    ]

    last_response_content = ""

    for round_index in range(1, args.rounds + 1):
        print(f"--- [Round {round_index}/{args.rounds}] ---")
        for idx, debater in enumerate(debaters):
            print(f"Thinking ({debater['name']})...")

            if idx == 0 and round_index == 1:
                turn_instruction = current_input
            else:
                prev_speaker = debaters[idx - 1]["name"] if idx > 0 else debaters[-1]["name"]
                turn_instruction = f"""
[Date: {simulation_date}]
[{prev_speaker}'s Argument]
"{last_response_content}"

[Instruction]
Critique the argument and propose your solution using MY DATA.
Cite claims only with your own snapshot IDs as [ID: n].
""".strip()

            turn_prompt = build_turn_prompt(
                simulation_date=simulation_date,
                debate_topic=debate_topic,
                persona_system_prompt=debater["persona"],
                knowledge=debater["knowledge"],
                turn_instruction=turn_instruction,
            )

            response_body, validation_payload = generate_validated_response(
                client=client,
                model_name=args.model,
                base_prompt=turn_prompt,
                temperature=args.temperature,
                max_output_tokens=args.max_output_tokens,
                validate_fn=lambda text, idx_map=debater["snapshot_index"]: validate_turn_response(
                    response_text=text,
                    snapshot_index=idx_map,
                    min_evidence_pointers=args.min_evidence_pointers,
                ),
                context_label=f"{debater['role_label']} Round {round_index}",
                max_regen_attempts=MAX_VALIDATION_REGEN_ATTEMPTS,
            )

            response = append_evidence_appendix(
                response_text=response_body,
                ids=validation_payload["valid_ids"],
                snapshot_index=debater["snapshot_index"],
                debater_label=debater["role_label"],
            )

            print(f"\n[{debater['name']}]:\n{response}\n")
            log_content += f"[{debater['name']} - Round {round_index}]\n{response}\n"
            last_response_content = response
            if args.turn_sleep_sec > 0:
                time.sleep(args.turn_sleep_sec)

    print("\n" + "=" * 60)
    print("Debate complete.")

    judge_prompt = build_judge_prompt(
        simulation_date=simulation_date,
        debate_topic=debate_topic,
        original_situation=original_situation,
        transcript=log_content,
    )
    final_body, judge_payload = generate_validated_response(
        client=client,
        model_name=args.model,
        base_prompt=judge_prompt,
        temperature=args.temperature,
        max_output_tokens=args.max_output_tokens,
        validate_fn=lambda text: validate_judge_response(
            response_text=text,
            snapshot_index_a=snapshot_index_a,
            snapshot_index_b=snapshot_index_b,
            min_evidence_pointers=args.min_evidence_pointers,
        ),
        context_label="Judge Synthesis",
        max_regen_attempts=MAX_VALIDATION_REGEN_ATTEMPTS,
    )

    final_verdict = append_judge_evidence_appendix(
        response_text=final_body,
        ids_a=judge_payload["ids_a"],
        ids_b=judge_payload["ids_b"],
        snapshot_index_a=snapshot_index_a,
        snapshot_index_b=snapshot_index_b,
    )
    print(f"\n[Final Synthesis]\n{final_verdict}")

    output_file = args.output_file.strip()
    if not output_file:
        case_match = re.search(r"\((\d+)\)$", Path(__file__).stem)
        if case_match:
            output_file = f"Debate_Log({case_match.group(1)}).txt"
        else:
            safe_date = re.sub(r"[^0-9A-Za-z_]+", "", simulation_date.replace(" ", "_"))
            output_file = f"Debate_Log_{safe_date}.txt"

    output_text = log_content + f"\n{'=' * 60}\n[FINAL SYNTHESIS]\n{final_verdict}\n"
    Path(output_file).write_text(output_text, encoding="utf-8")
    print(f"Saved: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





