"""
Score and rank story clusters for newsletter selection.

Usage:
    python run_scorer.py
    python run_scorer.py --input data/output/clustered_stories.json
    python run_scorer.py --top 30
    python run_scorer.py --show-all-scores
"""

from __future__ import annotations

import argparse
import logging

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
        default=30,
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
