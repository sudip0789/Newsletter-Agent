from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

configure_script_environment()

from src.AI_relevance_checker import AIRelevanceChecker


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
    print(f"Total Number of high AI relevant articles found: {len(relevant)}")

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
