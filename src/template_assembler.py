from __future__ import annotations

import json
import math
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape

from src.publish_dates import resolve_publication_date
from src.text_utils import normalize_markdown_escaped_text


class TemplateAssembler:
    ALL_SECTIONS = [
        ("enterprise_ai", "Enterprise AI"),
        ("legal_intelligence", "Legal Intelligence"),
        ("ai_products", "AI Products"),
        ("security", "Security"),
        ("policy", "Policy"),
        ("responsible_ai", "Responsible AI"),
        ("ai_sustainability", "AI Sustainability"),
        ("creative_ai", "Creative AI"),
        ("higher_education", "Higher Education"),
        ("research", "Research"),
    ]
    SECTION_ICON_FILENAMES = {
        "enterprise_ai": "enterprise_ai.svg",
        "legal_intelligence": "legal_intelligence.svg",
        "ai_products": "ai_products.svg",
        "security": "security.svg",
        "policy": "policy.svg",
        "responsible_ai": "responsible_ai.svg",
        "ai_sustainability": "ai_sustainability.svg",
        "creative_ai": "creative_ai.svg",
        "higher_education": "higher_education.svg",
        "research": "research.svg",
    }

    def __init__(
        self,
        stories_path: str = "data/output/summarized_stories.json",
        headlines_path: str = "data/output/headline_picks.json",
        template_path: str = "templates/newsletter.html",
        headline_asset_root: str | Path | None = None,
        media: dict | None = None,
    ):
        self.stories_path = Path(stories_path)
        self.headlines_path = Path(headlines_path)
        self.template_path = Path(template_path)
        self.project_root = self.template_path.parent.parent.resolve()
        self.headline_asset_root = (
            None if headline_asset_root is None else Path(headline_asset_root).resolve()
        )
        self.media = media or {}
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
        pdf_url: str | None = None,
        pdf_download_name: str | None = None,
        publish_date_is_resolved: bool = False,
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
                "index": index,
                "story_count": len(grouped[key]),
            }
            for index, (key, name) in enumerate(active_sections, start=1)
        ]
        sections = [
            {
                "key": key,
                "name": name,
                "articles": grouped[key],
            }
            for key, name in active_sections
        ]
        issue_date = self._resolve_publish_date(
            publish_date,
            publish_date_is_resolved=publish_date_is_resolved,
        )
        issue_metadata = self._build_issue_metadata(issue_date)

        logo_path = self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/RBG_RCLL_vrt.png"),
        )
        podcast_cover_path = self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/Podcast_edition.png"),
        )
        video_cover_path = self._resolve_project_asset_path(
            output_file,
            Path("assets/logos/Video_Overview.png"),
        )
        drive_images = self.media.get("headline_images", [])
        headlines = []
        for i, headline in enumerate(self.headlines):
            drive_url = drive_images[i] if i < len(drive_images) and drive_images[i] else None
            image_path = drive_url or self._resolve_headline_image_path(
                output_file,
                headline,
                index=i + 1,
            )
            headlines.append({**headline, "image_path": image_path})

        template = self.jinja.from_string(self.template_path.read_text(encoding="utf-8"))
        section_story_count = sum(len(section["articles"]) for section in sections)
        html = template.render(
            publish_date=self._format_publish_date(issue_date),
            issue_label=issue_metadata["issue_label"],
            publish_weekday=issue_metadata["weekday"],
            publish_month_day=issue_metadata["month_day"],
            publish_year=issue_metadata["year"],
            story_count=section_story_count + len(headlines),
            section_story_count=section_story_count,
            section_count=len(sections),
            read_time_minutes=self._estimate_read_time_minutes(sections, headlines),
            headline_module_title="This Week's Headline" if len(headlines) == 1 else "This Week's Headlines",
            logo_path=logo_path,
            podcast_cover_path=podcast_cover_path,
            video_cover_path=video_cover_path,
            headlines=headlines,
            active_sections=section_navigation,
            sections=sections,
            archive_url=archive_url,
            latest_issue_url=latest_issue_url,
            pdf_url=pdf_url,
            pdf_download_name=pdf_download_name,
            podcast_embed_url=self.media.get("podcast_embed_url"),
            podcast_audio_url=self.media.get("podcast_audio_url"),
            video_embed_url=self.media.get("video_embed_url"),
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
        newsletter_title = story.get("newsletter_title") or primary_article.get("title", "")
        return {
            "title": newsletter_title,
            "original_title": primary_article.get("title", ""),
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

    def _resolve_headline_image_path(
        self,
        output_file: Path,
        headline: dict[str, Any],
        index: int | None = None,
    ) -> str:
        raw_path = headline.get("image_path")
        if raw_path:
            if self.headline_asset_root is not None:
                return self._to_relative_asset_path(
                    output_file,
                    self.headline_asset_root / Path(raw_path),
                )
            return self._resolve_project_asset_path(output_file, Path(raw_path))
        if index is not None:
            conventional_path = Path("assets/generated") / f"headline_{index}.png"
            candidate_root = (
                self.headline_asset_root if self.headline_asset_root is not None else self.project_root
            )
            candidate_path = candidate_root / conventional_path
            if candidate_path.exists():
                if self.headline_asset_root is not None:
                    return self._to_relative_asset_path(output_file, candidate_path)
                return self._resolve_project_asset_path(output_file, conventional_path)
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

    def _resolve_publish_date(
        self,
        publish_date: date | datetime | str | None,
        *,
        publish_date_is_resolved: bool,
    ) -> date | str:
        if publish_date_is_resolved:
            if publish_date is None:
                return datetime.now().date()
            if isinstance(publish_date, datetime):
                return publish_date.date()
            if isinstance(publish_date, date):
                return publish_date
            if isinstance(publish_date, str):
                try:
                    return datetime.fromisoformat(publish_date).date()
                except ValueError:
                    return publish_date.strip()
            raise TypeError("publish_date must be a date, datetime, string, or None.")

        return resolve_publication_date(publish_date)

    def _build_issue_metadata(self, publish_date: date | str) -> dict[str, str]:
        issue_number = self._resolve_issue_number(publish_date)
        if isinstance(publish_date, str):
            return {
                "issue_label": f"ISSUE {issue_number:02d}",
                "weekday": publish_date.upper(),
                "month_day": "",
                "year": "",
            }

        return {
            "issue_label": f"ISSUE {issue_number:02d}",
            "weekday": publish_date.strftime("%A").upper(),
            "month_day": publish_date.strftime("%b %d").upper(),
            "year": publish_date.strftime("%Y"),
        }

    def _resolve_issue_number(self, publish_date: date | str) -> int:
        snapshots_root = self.project_root / "issue_snapshots"
        if not snapshots_root.exists():
            return 1

        snapshot_dates = sorted(
            path.name
            for path in snapshots_root.iterdir()
            if path.is_dir()
        )
        if not snapshot_dates:
            return 1

        issue_key = publish_date.isoformat() if isinstance(publish_date, date) else publish_date
        if issue_key in snapshot_dates:
            return snapshot_dates.index(issue_key) + 1
        return len(snapshot_dates) + 1

    def _estimate_read_time_minutes(
        self,
        sections: list[dict[str, Any]],
        headlines: list[dict[str, Any]],
    ) -> int:
        word_count = 0

        for headline in headlines:
            word_count += self._count_words(headline.get("title", ""))
            word_count += self._count_words(headline.get("blurb", ""))

        for section in sections:
            for article in section["articles"]:
                word_count += self._count_words(article.get("title", ""))
                word_count += self._count_words(article.get("summary", ""))

        return max(1, math.ceil(word_count / 300))

    def _count_words(self, text: str) -> int:
        return len((text or "").split())

    def _format_publish_date(
        self, publish_date: date | str
    ) -> str:
        if isinstance(publish_date, str):
            return publish_date.strip()

        resolved_date = publish_date

        day = resolved_date.day
        if 10 <= day % 100 <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return resolved_date.strftime("%B ") + f"{day}{suffix}, {resolved_date.year}"
