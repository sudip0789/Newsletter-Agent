from __future__ import annotations

import argparse
from pathlib import Path

from src.issue_publisher import publish_issue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Snapshot the approved issue, rebuild the archive, and prepare the site for deployment."
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Publish date for the issue snapshot, ideally in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    issue_root = publish_issue(project_root=project_root, publish_date=args.date)
    print(f"Published issue snapshot at {issue_root}")


if __name__ == "__main__":
    main()
