"""
Select newsletter headlines, generate teaser blurbs, and optionally create images.

Usage:
    python3 scripts/run_headline_agent.py
    python3 scripts/run_headline_agent.py --blurbs-only
    python3 scripts/run_headline_agent.py --images-only
    python3 scripts/run_headline_agent.py --input data/output/summarized_stories.json
"""

from __future__ import annotations

import argparse
import logging
import time

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

configure_script_environment()

from src.headline_agent import HeadlineAgent
from src.stats_report import append_stage_report, format_headline_selection
from src.utils import setup_logging

IMAGE_REQUEST_DELAY_SECONDS = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Select newsletter headlines and generate blurbs/images"
    )
    parser.add_argument(
        "--input",
        default="data/output/summarized_stories.json",
        help="Override the default summarized stories input file path.",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--blurbs-only",
        action="store_true",
        help="Select headlines and generate blurbs only.",
    )
    mode_group.add_argument(
        "--images-only",
        action="store_true",
        help="Refresh images for the existing headline picks file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)
    agent = HeadlineAgent(input_path=args.input)

    if args.images_only:
        headlines = agent.attach_summaries(agent.load_saved_picks())
    else:
        headlines = agent.run()

    if args.blurbs_only:
        headlines = agent.preserve_existing_image_paths(headlines)
    else:
        for index, headline in enumerate(headlines, start=1):
            headline["image_path"] = agent.generate_headline_image(headline, index)
            if index < len(headlines):
                time.sleep(IMAGE_REQUEST_DELAY_SECONDS)

    agent.save_picks(headlines)
    report_text = format_headline_selection(headlines)
    print(report_text)
    report_path = append_stage_report("run_headline_agent.py", report_text)
    print(f"Stats report updated: {report_path}")
    print(f"Saved {len(headlines)} headline picks to {agent.output_path}")


if __name__ == "__main__":
    main()
