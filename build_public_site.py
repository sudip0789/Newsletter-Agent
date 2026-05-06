from __future__ import annotations

import argparse
from pathlib import Path

from src.public_site_builder import build_public_site


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deployable public site bundle."
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Optional publish date override, ideally in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parent
    build_public_site(project_root=project_root, publish_date=args.date)
    print("Built public site in public/")


if __name__ == "__main__":
    main()
