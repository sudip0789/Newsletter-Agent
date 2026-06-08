"""
Generate archive index headlines and cache them in data/output/archive.json.

Reads each issue's headline_picks.json (the three top stories) and asks Claude
Sonnet 4.6 for a single 2-3 line cover headline used on the archive index cards.

Usage:
    python3 scripts/run_archive_headlines.py                 # backfill any issues missing a headline
    python3 scripts/run_archive_headlines.py --date 2026-06-10   # also (re)generate the current issue from data/output
    python3 scripts/run_archive_headlines.py --force        # regenerate all issues

By default already-cached issues are skipped so the model only runs once per issue.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

PROJECT_ROOT = configure_script_environment()

from src.archive_headline import build_anthropic_client, generate_archive_headline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
LOGGER = logging.getLogger("run_archive_headlines")

ARCHIVE_JSON_PATH = PROJECT_ROOT / "data" / "output" / "archive.json"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_archive() -> dict[str, str]:
    if ARCHIVE_JSON_PATH.exists():
        try:
            data = _load_json(ARCHIVE_JSON_PATH)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Could not read existing archive.json (%s); starting fresh.", exc)
    return {}


def _save_archive(archive: dict[str, str]) -> None:
    ARCHIVE_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = {date: archive[date] for date in sorted(archive, reverse=True)}
    ARCHIVE_JSON_PATH.write_text(
        json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _collect_sources(current_date: str | None) -> list[tuple[str, Path]]:
    """Return (issue_date, headline_picks.json path) pairs to consider."""
    sources: dict[str, Path] = {}

    snapshots_root = PROJECT_ROOT / "issue_snapshots"
    if snapshots_root.exists():
        for issue_dir in sorted(p for p in snapshots_root.iterdir() if p.is_dir()):
            picks = issue_dir / "headline_picks.json"
            if picks.exists():
                sources[issue_dir.name] = picks

    # The issue currently being published is not a snapshot yet; read it from
    # data/output so its archive headline is ready before publish_issue snapshots it.
    if current_date:
        picks = PROJECT_ROOT / "data" / "output" / "headline_picks.json"
        if picks.exists():
            sources[current_date] = picks

    return sorted(sources.items(), key=lambda item: item[0], reverse=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate archive index headlines.")
    parser.add_argument(
        "--date",
        default=None,
        help="Issue date (YYYY-MM-DD) currently being published; reads data/output/headline_picks.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate headlines even for issues already cached in archive.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archive = _load_archive()
    sources = _collect_sources(args.date)

    if not sources:
        LOGGER.info("No issues with headline_picks.json found; nothing to do.")
        return

    pending = [
        (issue_date, picks)
        for issue_date, picks in sources
        if args.force or issue_date == args.date or issue_date not in archive
    ]

    if not pending:
        LOGGER.info("All %d issue(s) already have archive headlines.", len(sources))
        return

    client = build_anthropic_client()

    generated = 0
    for issue_date, picks_path in pending:
        try:
            headlines = _load_json(picks_path)
            headline = generate_archive_headline(client, headlines)
        except Exception as exc:  # pragma: no cover - per-issue resilience
            LOGGER.warning("Skipping %s: %s", issue_date, exc)
            continue
        archive[issue_date] = headline
        generated += 1
        LOGGER.info("%s -> %s", issue_date, headline)

    if generated:
        _save_archive(archive)
        LOGGER.info("Wrote %d headline(s) to %s", generated, ARCHIVE_JSON_PATH)


if __name__ == "__main__":
    main()
