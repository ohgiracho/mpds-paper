from __future__ import annotations

import argparse
import re
import sys

import run_pass2_split_anthropic as base
import validate_judge_outputs as validator


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Thin alias-subset adapter for the frozen split-candidate Pass 2 runner"
    )
    parser.add_argument("--packet", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--aliases", nargs="+", required=True)
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    parser.add_argument("--api-key-env", default="ANTHROPIC_API_KEY")
    args = parser.parse_args()

    aliases = list(args.aliases)
    if not aliases or len(aliases) != len(set(aliases)):
        raise RuntimeError("Aliases must be a nonempty unique list")
    if any(not re.fullmatch(r"Candidate [A-E]", alias) for alias in aliases):
        raise RuntimeError(f"Unsupported aliases: {aliases}")

    base.ALIASES = aliases
    base.SECTION_RE = re.compile(
        r"(?m)^## (" + "|".join(re.escape(alias) for alias in aliases) + r")\s*$"
    )
    validator.ALIASES = set(aliases)

    sys.argv = [
        sys.argv[0],
        "--packet",
        args.packet,
        "--output-dir",
        args.output_dir,
        "--model",
        args.model,
        "--max-output-tokens",
        str(args.max_output_tokens),
        "--api-key-env",
        args.api_key_env,
        "--max-workers",
        "1",
    ]
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
