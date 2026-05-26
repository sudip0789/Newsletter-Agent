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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deployable public site bundle."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional prep date override in YYYY-MM-DD format; the built site shows the next day as the publish date.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_public_site(project_root=PROJECT_ROOT, publish_date=args.date)
    print("Built public site in public/")


if __name__ == "__main__":
    main()
