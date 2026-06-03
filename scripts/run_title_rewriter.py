"""
Rewrite newsletter titles for summarized stories in place.

Usage:
    python3 scripts/run_title_rewriter.py
    python3 scripts/run_title_rewriter.py --top 25
    python3 scripts/run_title_rewriter.py --input data/output/summarized_stories.json
    python3 scripts/run_title_rewriter.py --model gpt-5.4
"""

from __future__ import annotations

import argparse
import logging

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

configure_script_environment()

from src.title_rewriter import TitleRewriter
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite newsletter titles in summarized stories output"
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Override the summarized stories input file path.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Number of stories to rewrite titles for.",
    )
    parser.add_argument(
        "--model",
        choices=["gpt-5.4", "sonnet-4.6"],
        default="sonnet-4.6",
        help="Title rewriting model to use.",
    )
    return parser.parse_args()


def format_title_rewrite_summary(stories: list) -> str:
    lines = [f"Newsletter titles written: {len(stories)}"]
    for index, story in enumerate(stories, start=1):
        lines.append(f"{index}. {story.newsletter_title}")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)

    rewriter = TitleRewriter(
        input_path=args.input,
        top_n=args.top,
        model=args.model,
    )
    stories = rewriter.run()
    rewriter.save_results(stories)
    report_text = format_title_rewrite_summary(stories[: args.top])
    print(report_text)
    print(
        f"Saved {min(len(stories), args.top)} rewritten titles using {args.model} "
        f"to {rewriter.output_path}"
    )


if __name__ == "__main__":
    main()
