"""
Render the newsletter HTML from summarized stories and headline picks.

Usage:
    python3 scripts/run_template_assembler.py
    python3 scripts/run_template_assembler.py --date 2026-05-01
    python3 scripts/run_template_assembler.py --output public/index.html
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

from src.template_assembler import TemplateAssembler
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render newsletter HTML from summarized stories and headline picks."
    )
    parser.add_argument(
        "--stories",
        default="data/output/summarized_stories.json",
        help="Override the summarized stories input path.",
    )
    parser.add_argument(
        "--headlines",
        default="data/output/headline_picks.json",
        help="Override the headline picks input path.",
    )
    parser.add_argument(
        "--template",
        default="templates/newsletter.html",
        help="Override the Jinja template path.",
    )
    parser.add_argument(
        "--output",
        default="public/index.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional publish date override, ideally in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)
    assembler = TemplateAssembler(
        stories_path=args.stories,
        headlines_path=args.headlines,
        template_path=args.template,
    )
    assembler.run(publish_date=args.date, output_path=args.output)
    print(f"Saved newsletter HTML to {args.output}")


if __name__ == "__main__":
    main()
