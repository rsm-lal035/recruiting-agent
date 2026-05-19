"""
OCBridge Recruiting Copilot — entrypoint.

Usage:
  # Use the bundled sample JD:
  python main.py

  # Use your own JD file:
  python main.py --jd path/to/jd.txt

  # Pipe a JD in:
  cat my_jd.txt | python main.py --stdin

  # Optional hiring manager notes:
  python main.py --jd jd.txt --notes notes.txt

Output:
  output.json    — written to the repo root.
  Full structured trace also printed to stdout.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from src.llm_client import LLMClient, LLMError
from src.pipeline import RecruitingPipeline, PipelineError

ROOT = Path(__file__).parent
SAMPLE_JD = ROOT / "sample_data" / "sample_jd.txt"
OUTPUT_PATH = ROOT / "output.json"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
    )


def _load_jd(args: argparse.Namespace) -> str:
    if args.stdin:
        jd = sys.stdin.read()
        if not jd.strip():
            sys.exit("ERROR: --stdin specified but stdin was empty.")
        return jd
    if args.jd:
        path = Path(args.jd)
        if not path.exists():
            sys.exit(f"ERROR: JD file not found: {path}")
        return path.read_text(encoding="utf-8")
    # Default to the bundled sample so `python main.py` Just Works.
    if not SAMPLE_JD.exists():
        sys.exit(f"ERROR: no --jd / --stdin given and sample missing at {SAMPLE_JD}")
    print(f"[info] No --jd given. Using sample JD: {SAMPLE_JD}")
    return SAMPLE_JD.read_text(encoding="utf-8")


def _load_notes(args: argparse.Namespace) -> str | None:
    if not args.notes:
        return None
    path = Path(args.notes)
    if not path.exists():
        sys.exit(f"ERROR: notes file not found: {path}")
    return path.read_text(encoding="utf-8")


def _print_summary(result: dict) -> None:
    print("\n" + "=" * 70)
    print("PIPELINE RESULT")
    print("=" * 70)

    strat = result["candidate_search_strategy"]
    print("\n[1] Candidate Search Strategy")
    print(f"    seniority         : {strat.get('seniority')}")
    print(f"    target_backgrounds: {strat.get('target_backgrounds')}")
    print(f"    target_companies  : {strat.get('target_companies')}")
    print(f"    keywords          : {strat.get('keywords')}")

    print("\n[2] Boolean Query")
    print(f"    {result['boolean_query']}")

    out = result["outreach_message"]
    print("\n[3] Outreach Message")
    print(f"    chars   : {out['character_count']} (limit 300)")
    print(f"    attempts: {out['attempts']}")
    print(f"    detail  : {out['specific_detail']!r}")
    print(f"    message : {out['outreach_message']}")

    summ = result["candidate_summary"]
    print("\n[4] Candidate Summary")
    print(f"    {summ.get('name')} — {summ.get('current_company')}")
    print(f"    skills  : {summ.get('key_skills')}")
    print(f"    fit     : {summ.get('fit_reason')}")
    print(f"    concerns: {summ.get('concerns')}")

    print("\n[5] Pipeline Trace")
    for entry in result["pipeline_trace"]:
        print(
            f"    step={entry['step']} action={entry['action']:<30} "
            f"attempt={entry['attempt']} result={entry['result']:<5} | {entry['note']}"
        )
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the recruiting copilot pipeline.")
    parser.add_argument("--jd", help="Path to a JD text file.")
    parser.add_argument("--notes", help="Path to hiring manager notes (optional).")
    parser.add_argument("--stdin", action="store_true", help="Read JD from stdin.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging.")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="Anthropic model id (default: claude-sonnet-4-5).",
    )
    args = parser.parse_args()

    _setup_logging(args.verbose)

    jd = _load_jd(args)
    notes = _load_notes(args)

    try:
        llm = LLMClient(model=args.model)
    except LLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    pipeline = RecruitingPipeline(llm)

    try:
        result = pipeline.run(jd, hm_notes=notes)
    except PipelineError as exc:
        # Graceful exit: still write whatever trace we have so reviewers can debug.
        print(f"\nPIPELINE FAILED: {exc}", file=sys.stderr)
        OUTPUT_PATH.write_text(
            json.dumps(
                {
                    "error": str(exc),
                    "pipeline_trace": pipeline.trace,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Partial trace written to {OUTPUT_PATH}", file=sys.stderr)
        return 1

    OUTPUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print_summary(result)
    print(f"\nWrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
