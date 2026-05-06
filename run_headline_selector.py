"""
Select newsletter headlines, generate teaser blurbs, and optionally create images.

Usage:
    python3 run_headline_selector.py
    python3 run_headline_selector.py --blurbs-only
    python3 run_headline_selector.py --images-only
    python3 run_headline_selector.py --input data/output/summarized_stories.json
"""

from __future__ import annotations

import argparse
import logging
import time

from src.headline_selector import HeadlineSelector
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
    selector = HeadlineSelector(input_path=args.input)

    if args.images_only:
        headlines = selector.attach_summaries(selector.load_saved_picks())
    else:
        headlines = selector.run()

    if args.blurbs_only:
        for headline in headlines:
            headline["image_path"] = None
    else:
        for index, headline in enumerate(headlines, start=1):
            headline["image_path"] = selector.generate_headline_image(headline, index)
            if index < len(headlines):
                time.sleep(IMAGE_REQUEST_DELAY_SECONDS)

    selector.save_picks(headlines)
    report_text = format_headline_selection(headlines)
    print(report_text)
    report_path = append_stage_report("run_headline_selector.py", report_text)
    print(f"Stats report updated: {report_path}")
    print(f"Saved {len(headlines)} headline picks to {selector.output_path}")


if __name__ == "__main__":
    main()
