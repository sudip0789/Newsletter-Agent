from __future__ import annotations

import json
import shutil
from datetime import date, datetime
from pathlib import Path
from typing import Any

from src.public_site_builder import build_public_site


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

    build_public_site(project_root=root, publish_date=issue_date)
    return issue_root
