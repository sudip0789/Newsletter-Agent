from __future__ import annotations

import argparse

from src.AI_relevance_checker import AIRelevanceChecker
from src.stats_report import append_stage_report, format_count_line


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Filter Stage 1 articles by AI relevance")
    parser.add_argument(
        "--input",
        default="data/output/stage1_articles.json",
        help="Override the default input file path.",
    )
    parser.add_argument(
        "--show-removed",
        action="store_true",
        help="Print the full list of removed article titles.",
    )
    parser.add_argument(
        "--show-matched-keywords",
        action="store_true",
        help="Show matched keyword(s) for each relevant article.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    checker = AIRelevanceChecker(input_path=args.input)
    relevant, removed = checker.run()
    checker.save_results(relevant, removed)
    checker.print_summary(relevant, removed)
    report_text = format_count_line(
        "Total Number of high AI relevant articles found",
        len(relevant),
    )
    print(report_text)
    report_path = append_stage_report("run_ai_relevance_checker.py", report_text)
    print(f"Stats report updated: {report_path}")

    if args.show_removed:
        print("\n=== Removed Article Titles ===")
        for article in removed:
            print(f"- {article.title}")

    if args.show_matched_keywords:
        print("\n=== Relevant Articles and Matched Keywords ===")
        for article in relevant:
            matched = checker.matched_keywords_by_url.get(article.url, [])
            print(f"- {article.title}")
            print(f"  matched: {', '.join(matched)}")


if __name__ == "__main__":
    main()
