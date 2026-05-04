"""
Print scored stories with only title, scores, composite score, and section.

Usage:
    python3 run_scored_story_viewer.py
    python3 run_scored_story_viewer.py data/output/scored_stories.json
    python3 run_scored_story_viewer.py --output data/output/scored_story_view.json
    python3 run_scored_story_viewer.py --print
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List scored stories ordered by scores.buzz_momentum with only the "
            "requested fields."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="data/output/scored_stories.json",
        help="Path to the scored stories JSON file.",
    )
    parser.add_argument(
        "--output",
        default="data/output/scored_story_view.json",
        help="Optional path to save the filtered, sorted JSON payload.",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="Print the filtered payload to stdout.",
    )
    return parser.parse_args(argv)


def load_ranked_stories(input_path: str) -> list[dict[str, Any]]:
    raw_stories = json.loads(Path(input_path).read_text(encoding="utf-8"))

    ranked_stories = sorted(
        raw_stories,
        key=lambda story: story.get("scores", {}).get("buzz_momentum", 0),
        reverse=True,
    )

    return [
        {
            "rank": index,
            "title": story.get("cluster", {})
            .get("primary_article", {})
            .get("title"),
            "scores": story.get("scores", {}),
            "composite_score": story.get("composite_score"),
            "section": story.get("section"),
        }
        for index, story in enumerate(ranked_stories, start=1)
    ]


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    payload = load_ranked_stories(args.input)
    Path(args.output).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if args.print:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
