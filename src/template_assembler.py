from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from src.text_utils import normalize_markdown_escaped_text


class TemplateAssembler:
    ALL_SECTIONS = [
        ("industry", "Industry"),
        ("legal_intelligence", "Legal Intelligence"),
        ("tools_and_products", "Tools & Products"),
        ("security", "Security"),
        ("policy", "Policy"),
        ("creative_ai", "Creative AI"),
        ("higher_education", "Higher Education"),
        ("research", "Research"),
    ]
    SECTION_ICON_FILENAMES = {
        "industry": "industry.png",
        "legal_intelligence": "legal_intelligence.png",
        "tools_and_products": "tools.png",
        "security": "security.png",
        "policy": "policy.png",
        "creative_ai": "creative_ai.png",
        "higher_education": "higher_education.png",
        "research": "research.png",
    }

    def __init__(
        self,
        stories_path: str = "data/output/summarized_stories.json",
        headlines_path: str = "data/output/headline_picks.json",
        template_path: str = "templates/newsletter.html",
        headline_asset_root: str | Path | None = None,
    ):
        self.stories_path = Path(stories_path)
        self.headlines_path = Path(headlines_path)
        self.template_path = Path(template_path)
        self.project_root = self.template_path.parent.parent.resolve()
        self.headline_asset_root = (
            None if headline_asset_root is None else Path(headline_asset_root).resolve()
        )
        self.stories = self._load_json(self.stories_path)
        self.headlines = self._load_json(self.headlines_path)
        self.jinja = Environment(
            autoescape=select_autoescape(default_for_string=True, default=True)
        )

    def run(
        self,
        publish_date: date | datetime | str | None = None,
        output_path: str | None = None,
        archive_url: str | None = None,
        latest_issue_url: str | None = None,
    ) -> str:
        output_file = (
            self.project_root / "public" / "index.html"
            if output_path is None
            else Path(output_path)
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)

        exclude_urls = [headline.get("url", "") for headline in self.headlines]
        grouped = self.group_by_section(self.stories, exclude_urls=exclude_urls)
        active_sections = self.get_active_sections(grouped)
        section_navigation = [
            {
                "key": key,
                "name": name,
                "icon_path": self._resolve_section_icon_path(output_file, key),
            }
            for key, name in active_sections
        ]
        sections = [
            {
                "key": key,
                "name": name,
                "articles": grouped[key],
            }
            for key, name in active_sections
        ]

        logo_path = self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/newsletter_logo.png"),
        )
        sidebar_logo_path = self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/news_brief.png"),
        )
        headlines = [
            {
                **headline,
                "image_path": self._resolve_headline_image_path(output_file, headline),
            }
            for headline in self.headlines
        ]

        template = self.jinja.from_string(self.template_path.read_text(encoding="utf-8"))
        html = template.render(
            publish_date=self._format_publish_date(publish_date),
            logo_path=logo_path,
            sidebar_logo_path=sidebar_logo_path,
            headlines=headlines,
            active_sections=section_navigation,
            sections=sections,
            archive_url=archive_url,
            latest_issue_url=latest_issue_url,
        )
        output_file.write_text(html, encoding="utf-8")
        return html

    def group_by_section(
        self, stories: list[dict], exclude_urls: list[str]
    ) -> dict[str, list[dict]]:
        exclude_set = {url for url in exclude_urls if url}
        grouped: dict[str, list[dict]] = {}

        for story in stories:
            article = self._story_to_article(story)
            if article["url"] in exclude_set:
                continue

            grouped.setdefault(article["section"], []).append(article)

        ordered_grouped: dict[str, list[dict]] = {}
        for key, _name in self.ALL_SECTIONS:
            items = grouped.get(key, [])
            if not items:
                continue
            ordered_grouped[key] = sorted(
                items,
                key=lambda item: item["composite_score"],
                reverse=True,
            )

        return ordered_grouped

    def get_active_sections(self, grouped: dict) -> list[tuple]:
        return [
            (key, name)
            for key, name in self.ALL_SECTIONS
            if grouped.get(key)
        ]

    def _story_to_article(self, story: dict[str, Any]) -> dict[str, Any]:
        scored_story = story.get("scored_story", {})
        cluster = scored_story.get("cluster", {})
        primary_article = cluster.get("primary_article", {})
        summary = normalize_markdown_escaped_text(story.get("summary", "") or "")
        return {
            "title": primary_article.get("title", ""),
            "url": primary_article.get("url", ""),
            "source_name": primary_article.get("source_name", ""),
            "section": scored_story.get("section", ""),
            "composite_score": float(scored_story.get("composite_score", 0.0) or 0.0),
            "summary": summary,
            "summary_paragraphs": self._split_summary_paragraphs(summary),
            "needs_manual_review": bool(story.get("needs_manual_review", False)),
        }

    def _split_summary_paragraphs(self, summary: str) -> list[str]:
        return [part.strip() for part in summary.split("\n\n") if part.strip()]

    def _load_json(self, path: Path) -> list[dict[str, Any]]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _resolve_headline_image_path(self, output_file: Path, headline: dict[str, Any]) -> str:
        raw_path = headline.get("image_path")
        if raw_path:
            if self.headline_asset_root is not None:
                return self._to_relative_asset_path(
                    output_file,
                    self.headline_asset_root / Path(raw_path),
                )
            return self._resolve_project_asset_path(output_file, Path(raw_path))
        return self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/newsletter_logo.png"),
        )

    def _resolve_section_icon_path(self, output_file: Path, section_key: str) -> str:
        filename = self.SECTION_ICON_FILENAMES.get(section_key, "newsletter_logo.png")
        return self._resolve_project_asset_path(
            output_file,
            Path("assets/logos") / filename,
        )

    def _resolve_project_asset_path(self, output_file: Path, relative_asset_path: Path) -> str:
        asset_root = (
            self.project_root / "public"
            if self._is_public_output(output_file)
            else self.project_root
        )
        return self._to_relative_asset_path(output_file, asset_root / relative_asset_path)

    def _is_public_output(self, output_file: Path) -> bool:
        public_root = (self.project_root / "public").resolve()
        try:
            output_file.resolve().relative_to(public_root)
        except ValueError:
            return False
        return True

    def _to_relative_asset_path(self, output_file: Path, asset_path: Path) -> str:
        return os.path.relpath(asset_path.resolve(), start=output_file.parent.resolve())

    def _format_publish_date(
        self, publish_date: date | datetime | str | None
    ) -> str:
        if publish_date is None:
            resolved_date = datetime.now().date()
        elif isinstance(publish_date, datetime):
            resolved_date = publish_date.date()
        elif isinstance(publish_date, date):
            resolved_date = publish_date
        elif isinstance(publish_date, str):
            try:
                resolved_date = datetime.fromisoformat(publish_date).date()
            except ValueError:
                return publish_date.strip()
        else:
            raise TypeError("publish_date must be a date, datetime, string, or None.")

        day = resolved_date.day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return resolved_date.strftime("%B ") + f"{day}{suffix}, {resolved_date.year}"
