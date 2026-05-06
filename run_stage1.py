"""
Run source ingestion and display results.

Usage:
    python run_stage1.py                    # Run all fetchers
    python run_stage1.py --rss-only         # Run only RSS feeds (no API key needed)
    python run_stage1.py --skip-fulltext    # Skip the full text retrieval step (faster testing)
"""

from __future__ import annotations

import argparse
import logging

from src.stats_report import append_stage_report, format_count_line
from src.stage1_ingest import SourceIngestion
from src.utils import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 1 source ingestion pipeline")
    parser.add_argument(
        "--rss-only",
        action="store_true",
        help="Only fetch RSS feeds; skip NewsAPI and Google News RSS.",
    )
    parser.add_argument(
        "--skip-fulltext",
        action="store_true",
        help="Skip article page fetches for full text extraction.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N RSS feeds.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(logging.INFO)

    ingestion = SourceIngestion(config_path="config/sources.yaml")
    articles = ingestion.run(
        rss_only=args.rss_only,
        skip_fulltext=args.skip_fulltext,
        limit=args.limit,
    )
    ingestion.save_results(articles, path="data/output/stage1_articles.json")
    ingestion.print_summary(articles)
    report_text = format_count_line("Total Number of articles scanned", len(articles))
    print(report_text)
    report_path = append_stage_report("run_stage1.py", report_text, reset=True)
    print(f"Stats report updated: {report_path}")


if __name__ == "__main__":
    main()
