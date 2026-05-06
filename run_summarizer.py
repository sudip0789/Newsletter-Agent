"""
Generate editorial summaries for top scored stories.

Usage:
    python3 run_summarizer.py
    python3 run_summarizer.py --top 30
    python3 run_summarizer.py --input data/output/scored_stories.json
    python3 run_summarizer.py --model sonnet-4.6
    python3 run_summarizer.py --model gpt-5.4
"""

from __future__ import annotations

import argparse
import logging

from src.summarizer import Summarizer
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate editorial summaries for top scored stories"
    )
    parser.add_argument(
        "--input",
        default="data/output/scored_stories.json",
        help="Override the default input file path.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of top stories to summarize.",
    )
    parser.add_argument(
        "--model",
        choices=["gpt-5.4", "sonnet-4.6"],
        default="sonnet-4.6",
        help="Summarization model to use.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)

    summarizer = Summarizer(
        input_path=args.input,
        top_n=args.top,
        model=args.model,
    )
    stories = summarizer.run()
    summarizer.save_results(stories)
    print(
        f"Saved {len(stories)} summarized stories using {args.model} "
        f"to {summarizer.output_path}"
    )


if __name__ == "__main__":
    main()
