"""
Score and rank story clusters for newsletter selection.

Usage:
    python scripts/run_scorer.py
    python scripts/run_scorer.py --input data/output/clustered_stories.json
    python scripts/run_scorer.py --top 25
    python scripts/run_scorer.py --show-all-scores
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

from src.stats_report import append_stage_report, format_selected_stories_by_section
from src.scorer import Scorer
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score and rank story clusters for newsletter selection"
    )
    parser.add_argument(
        "--input",
        default="data/output/clustered_stories.json",
        help="Override the default input file path.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=25,
        help="Number of stories to select after scoring.",
    )
    parser.add_argument(
        "--show-all-scores",
        action="store_true",
        help="Print scores for all successfully scored stories.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)

    scorer = Scorer(input_path=args.input)
    scorer.selection_total = args.top
    selected = scorer.run()
    report_text = format_selected_stories_by_section(
        selected,
        requested_total=args.top,
    )
    print(report_text)
    report_path = append_stage_report("run_scorer.py", report_text)
    print(f"Stats report updated: {report_path}")

    if args.show_all_scores:
        print("\n=== All Scored Stories ===")
        for index, story in enumerate(scorer.all_scored_stories, start=1):
            title = story.cluster.primary_article.title
            ai_relevance = story.scores.get("ai_relevance", 0.0)
            print(
                f"{index:03d}. {story.composite_score:.3f} | "
                f"ai_relevance={ai_relevance:.2f} | "
                f"{story.section} | {story.tier} | {title}"
            )

    if not selected:
        print("\nNo stories were selected. Check earlier warnings for scoring failures.")


if __name__ == "__main__":
    main()
