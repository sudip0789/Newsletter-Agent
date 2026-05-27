from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

PROJECT_ROOT = configure_script_environment()

from src.issue_publisher import publish_issue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Snapshot the approved issue, rebuild the archive, and prepare the site "
            "for deployment. Weekly audio/video links are read from "
            "data/output/media_inputs.json."
        )
    )
    parser.add_argument(
        "--date",
        required=True,
        help="Issue date for the snapshot in YYYY-MM-DD format; the published issue uses that same day.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    issue_root = publish_issue(project_root=PROJECT_ROOT, publish_date=args.date)
    print(f"Published issue snapshot at {issue_root}")


if __name__ == "__main__":
    main()
