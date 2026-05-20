from __future__ import annotations

import json
import logging
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.public_site_builder import build_public_site

LOGGER = logging.getLogger(__name__)


def _normalize_issue_date(publish_date: date | datetime | str | None) -> str:
    if publish_date is None:
        return datetime.now().date().isoformat()
    if isinstance(publish_date, datetime):
        return publish_date.date().isoformat()
    if isinstance(publish_date, date):
        return publish_date.isoformat()
    return str(publish_date).strip()


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_drive_media(
    issue_root: Path,
    issue_date: str,
    headlines: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Upload images + placeholders to Drive. Returns media dict or None if Drive not configured."""
    from src import drive_publisher

    if not drive_publisher.is_configured():
        return None

    parent_folder_id = drive_publisher.get_parent_folder_id()
    LOGGER.info("Creating Drive folder for %s ...", issue_date)
    folder_id = drive_publisher.create_week_folder(issue_date, parent_folder_id)
    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    LOGGER.info("Drive folder: %s", folder_url)

    image_direct_urls: list[str] = []
    for i, headline in enumerate(headlines, start=1):
        image_path = headline.get("image_path")
        if not image_path:
            image_direct_urls.append("")
            continue
        local_image = issue_root / image_path
        if not local_image.exists():
            LOGGER.warning("Image not found at %s, skipping Drive upload.", local_image)
            image_direct_urls.append("")
            continue
        LOGGER.info("Uploading headline_%d.png to Drive ...", i)
        urls = drive_publisher.upload_file(folder_id, local_image, f"headline_{i}.png")
        image_direct_urls.append(urls["direct_url"])

    LOGGER.info("Uploading podcast placeholder ...")
    podcast_urls = drive_publisher.upload_audio_placeholder(folder_id)

    LOGGER.info("Uploading video placeholder ...")
    video_urls = drive_publisher.upload_video_placeholder(folder_id)

    return {
        "folder_id": folder_id,
        "folder_url": folder_url,
        "headline_images": image_direct_urls,
        "podcast_embed_url": podcast_urls["embed_url"],
        "video_embed_url": video_urls["embed_url"],
    }


def publish_issue(
    project_root: Path | None = None,
    publish_date: date | datetime | str | None = None,
) -> Path:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    issue_date = _normalize_issue_date(publish_date)
    issue_root = root / "issue_snapshots" / issue_date

    if issue_root.exists():
        raise FileExistsError(f"Issue snapshot already exists for {issue_date}")

    issue_root.mkdir(parents=True, exist_ok=False)

    for filename in ("summarized_stories.json", "headline_picks.json"):
        shutil.copy2(root / "data" / "output" / filename, issue_root / filename)

    headlines = _load_json(issue_root / "headline_picks.json")
    for headline in headlines:
        image_path = headline.get("image_path")
        if not image_path:
            continue
        source_path = root / image_path
        target_path = issue_root / image_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)

    media = _build_drive_media(issue_root, issue_date, headlines)
    if media:
        media_json = json.dumps(media, indent=2, ensure_ascii=False)
        (issue_root / "media.json").write_text(media_json, encoding="utf-8")
        (root / "data" / "output" / "media.json").write_text(media_json, encoding="utf-8")
        LOGGER.info(
            "Drive folder ready for editor: %s",
            media["folder_url"],
        )
        print(f"\nEditor Drive folder: {media['folder_url']}\n")

    build_public_site(project_root=root, publish_date=issue_date)
    return issue_root
