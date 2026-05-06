from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from src.template_assembler import TemplateAssembler


def build_public_site(
    project_root: Path | None = None,
    publish_date: date | datetime | str | None = None,
) -> str:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    source_assets = root / "assets"
    target_assets = root / "public" / "assets"

    if target_assets.exists():
        shutil.rmtree(target_assets)
    shutil.copytree(source_assets, target_assets)

    assembler = TemplateAssembler(
        stories_path=str(root / "data" / "output" / "summarized_stories.json"),
        headlines_path=str(root / "data" / "output" / "headline_picks.json"),
        template_path=str(root / "templates" / "newsletter.html"),
    )
    return assembler.run(
        publish_date=publish_date,
        output_path=str(root / "public" / "index.html"),
    )
