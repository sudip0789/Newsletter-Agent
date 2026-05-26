from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape
from src.media_config import MEDIA_INPUTS_FILENAME, load_media_inputs
from src.publish_dates import normalize_issue_date, resolve_publication_date
from src.template_assembler import TemplateAssembler


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _format_issue_date(issue_date: str) -> str:
    try:
        resolved_date = datetime.fromisoformat(issue_date).date()
    except ValueError:
        return issue_date.strip()

    day = resolved_date.day
    if 10 <= day % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return resolved_date.strftime("%B ") + f"{day}{suffix}, {resolved_date.year}"


def _collect_issue_snapshots(root: Path) -> list[dict[str, str]]:
    issues_root = root / "issue_snapshots"
    if not issues_root.exists():
        return []

    issues: list[dict[str, str]] = []
    for issue_dir in sorted(
        [path for path in issues_root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    ):
        headlines_path = issue_dir / "headline_picks.json"
        stories_path = issue_dir / "summarized_stories.json"
        if not headlines_path.exists() or not stories_path.exists():
            continue

        headlines = _load_json(headlines_path)
        stories = _load_json(stories_path)
        title = headlines[0]["title"] if headlines else issue_dir.name
        story_title = (
            stories[0]
            .get("scored_story", {})
            .get("cluster", {})
            .get("primary_article", {})
            .get("title", "")
            if stories
            else ""
        )
        issues.append(
            {
                "issue_date": issue_dir.name,
                "display_date": _format_issue_date(issue_dir.name),
                "title": title,
                "story_title": story_title,
                "source_dir": str(issue_dir),
            }
        )
    return issues


def _copy_generated_assets(source_dir: Path, target_dir: Path) -> None:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    if not source_dir.exists():
        return
    shutil.copytree(source_dir, target_dir)


def _build_archive_index(root: Path, issues: list[dict[str, str]]) -> None:
    template_path = root / "templates" / "archive_index.html"
    env = Environment(
        autoescape=select_autoescape(default_for_string=True, default=True)
    )
    template = env.from_string(template_path.read_text(encoding="utf-8"))

    archive_output = root / "public" / "issues" / "index.html"
    archive_output.parent.mkdir(parents=True, exist_ok=True)
    archive_output.write_text(
        template.render(issues=issues, latest_issue_url="../"),
        encoding="utf-8",
    )


def _load_media(path: Path) -> dict | None:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def build_public_site(
    project_root: Path | None = None,
    publish_date: date | datetime | str | None = None,
    publish_date_is_resolved: bool = False,
) -> str:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    source_assets = root / "assets"
    target_assets = root / "public" / "assets"

    if target_assets.exists():
        shutil.rmtree(target_assets)
    shutil.copytree(source_assets, target_assets)

    issues_public_root = root / "public" / "issues"
    if issues_public_root.exists():
        shutil.rmtree(issues_public_root)

    # Load media.json for the latest issue: prefer the issue snapshot (when publish_date
    # is known), fall back to data/output/media.json (committed alongside headline_picks.json).
    if publish_date is not None:
        if publish_date_is_resolved:
            issue_date = normalize_issue_date(publish_date)
        else:
            issue_date = normalize_issue_date(resolve_publication_date(publish_date))
        current_media = (
            _load_media(root / "issue_snapshots" / issue_date / "media.json")
            or _load_media(root / "data" / "output" / "media.json")
            or load_media_inputs(root / "data" / "output" / MEDIA_INPUTS_FILENAME)
        )
    else:
        current_media = (
            _load_media(root / "data" / "output" / "media.json")
            or load_media_inputs(root / "data" / "output" / MEDIA_INPUTS_FILENAME)
        )

    assembler = TemplateAssembler(
        stories_path=str(root / "data" / "output" / "summarized_stories.json"),
        headlines_path=str(root / "data" / "output" / "headline_picks.json"),
        template_path=str(root / "templates" / "newsletter.html"),
        media=current_media,
    )
    latest_html = assembler.run(
        publish_date=publish_date,
        output_path=str(root / "public" / "index.html"),
        archive_url="issues/",
        publish_date_is_resolved=publish_date_is_resolved,
    )

    for issue in _collect_issue_snapshots(root):
        issue_source_dir = Path(issue["source_dir"])
        issue_output_dir = issues_public_root / issue["issue_date"]
        issue_media = _load_media(issue_source_dir / "media.json")

        # Only copy local generated assets when there are no Drive image URLs for this issue.
        if not (issue_media and issue_media.get("headline_images")):
            _copy_generated_assets(
                issue_source_dir / "assets" / "generated",
                issue_output_dir / "assets" / "generated",
            )

        issue_assembler = TemplateAssembler(
            stories_path=str(issue_source_dir / "summarized_stories.json"),
            headlines_path=str(issue_source_dir / "headline_picks.json"),
            template_path=str(root / "templates" / "newsletter.html"),
            headline_asset_root=issue_output_dir,
            media=issue_media,
        )
        issue_assembler.run(
            publish_date=issue["issue_date"],
            output_path=str(issue_output_dir / "index.html"),
            archive_url="../",
            latest_issue_url="../../",
            publish_date_is_resolved=True,
        )

    _build_archive_index(root, _collect_issue_snapshots(root))
    return latest_html
