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

from src.public_site_builder import build_public_site
from src.issue_publisher import refresh_drive_headline_images


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deployable public site bundle."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional issue date override in YYYY-MM-DD format; the built site uses that same day as the publish date.",
    )
    parser.add_argument(
        "--refresh-drive-images",
        action="store_true",
        help="Refresh headline image files in the existing issue Drive folder before rebuilding.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.refresh_drive_images:
        if not args.date:
            raise SystemExit("--refresh-drive-images requires --date YYYY-MM-DD")
        refresh_drive_headline_images(project_root=PROJECT_ROOT, publish_date=args.date)
        print(f"Refreshed Drive headline images for {args.date}")
    build_public_site(project_root=PROJECT_ROOT, publish_date=args.date)
    print("Built public site in public/")


if __name__ == "__main__":
    main()
