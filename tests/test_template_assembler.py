from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from src.template_assembler import TemplateAssembler


class TestTemplateAssembler(unittest.TestCase):
    def _story_payload(
        self,
        cluster_id: str,
        section: str,
        score: float,
        summary: str,
        title: str | None = None,
        newsletter_title: str | None = None,
    ) -> dict:
        story_title = title or f"Story {cluster_id}"
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": cluster_id,
                    "primary_article": {
                        "title": story_title,
                        "url": f"https://example.com/{cluster_id}",
                        "source_name": "Example Source",
                        "source_type": "rss",
                        "published_date": "2026-04-21T00:00:00+00:00",
                        "text": "Example article text",
                        "text_completeness": "full",
                        "fetch_method": "feedparser",
                    },
                    "coverage_count": 1,
                    "sources_involved": ["Example Source"],
                },
                "scores": {
                    "ai_relevance": score,
                    "impact": score,
                    "audience_relevance": score,
                    "novelty": score,
                    "source_quality": score,
                    "buzz_momentum": score,
                },
                "composite_score": score,
                "rationale": "Example rationale.",
                "section": section,
                "tier": "body",
            },
            "newsletter_title": newsletter_title or story_title,
            "summary": summary,
            "needs_manual_review": False,
        }

    def _headline_payload(self, url: str, title: str, image_path: str) -> dict:
        return {
            "title": title,
            "source_name": "Headline Source",
            "url": url,
            "section": "enterprise_ai",
            "composite_score": 0.99,
            "blurb": "A short headline blurb.",
            "image_path": image_path,
        }

    def _write_json(self, path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_group_by_section_excludes_headlines_sorts_scores_and_drops_empty_sections(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            stories_path = tmpdir / "summarized_stories.json"
            headlines_path = tmpdir / "headline_picks.json"
            template_path = tmpdir / "newsletter.html"
            self._write_json(
                stories_path,
                [
                    self._story_payload("industry_headline", "enterprise_ai", 0.91, "Industry lead"),
                    self._story_payload("industry_body", "enterprise_ai", 0.89, "Industry body"),
                    self._story_payload("security_high", "security", 0.95, "Security high"),
                    self._story_payload("security_low", "security", 0.82, "Security low"),
                    self._story_payload("policy_headline", "policy", 0.88, "Policy lead"),
                ],
            )
            self._write_json(
                headlines_path,
                [
                    self._headline_payload(
                        "https://example.com/industry_headline",
                        "Industry headline",
                        "assets/generated/headline_1.png",
                    ),
                    self._headline_payload(
                        "https://example.com/policy_headline",
                        "Policy headline",
                        "assets/generated/headline_2.png",
                    ),
                    self._headline_payload(
                        "https://example.com/other_headline",
                        "Other headline",
                        "assets/generated/headline_3.png",
                    ),
                ],
            )
            template_path.write_text("{{ active_sections|length }}", encoding="utf-8")

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )
            grouped = assembler.group_by_section(
                assembler.stories,
                exclude_urls=[item["url"] for item in assembler.headlines],
            )

            self.assertEqual(list(grouped.keys()), ["enterprise_ai", "security"])
            self.assertEqual(
                [story["title"] for story in grouped["security"]],
                ["Story security_high", "Story security_low"],
            )
            self.assertEqual(
                assembler.get_active_sections(grouped),
                [("enterprise_ai", "Enterprise AI"), ("security", "Security")],
            )

    def test_run_renders_expected_html_with_active_sections_and_paragraphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            project_root.mkdir()
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "templates").mkdir()
            (project_root / "data" / "output").mkdir(parents=True)

            stories_path = project_root / "data" / "output" / "summarized_stories.json"
            headlines_path = project_root / "data" / "output" / "headline_picks.json"
            template_path = project_root / "templates" / "newsletter.html"
            output_path = project_root / "data" / "output" / "newsletter.html"
            repo_template_path = (
                Path(__file__).resolve().parent.parent / "templates" / "newsletter.html"
            )

            self._write_json(
                stories_path,
                [
                    self._story_payload(
                        "industry_headline",
                        "enterprise_ai",
                        0.98,
                        "Headline story summary",
                        title="Industry headline story",
                    ),
                    self._story_payload(
                        "security_story",
                        "security",
                        0.94,
                        "Paragraph one.\n\nParagraph two.",
                        title="Security story",
                        newsletter_title="Rewritten security story",
                    ),
                    self._story_payload(
                        "research_story",
                        "research",
                        0.87,
                        "Research summary",
                        title="Research story",
                    ),
                    self._story_payload(
                        "policy_headline",
                        "policy",
                        0.86,
                        "Policy headline summary",
                        title="Policy headline story",
                    ),
                    self._story_payload(
                        "tools_headline",
                        "ai_products",
                        0.85,
                        "Tools headline summary",
                        title="Tools headline story",
                    ),
                ],
            )
            self._write_json(
                headlines_path,
                [
                    {
                        "title": "Industry headline",
                        "source_name": "Headline Source",
                        "url": "https://example.com/industry_headline",
                        "section": "enterprise_ai",
                        "composite_score": 0.98,
                        "blurb": "Industry blurb",
                        "image_path": "assets/generated/headline_1.png",
                    },
                    {
                        "title": "Policy headline",
                        "source_name": "Headline Source",
                        "url": "https://example.com/policy_headline",
                        "section": "policy",
                        "composite_score": 0.86,
                        "blurb": "Policy blurb",
                        "image_path": "assets/generated/headline_2.png",
                    },
                    {
                        "title": "Tools headline",
                        "source_name": "Headline Source",
                        "url": "https://example.com/tools_headline",
                        "section": "ai_products",
                        "composite_score": 0.85,
                        "blurb": "Tools blurb",
                        "image_path": "assets/generated/headline_3.png",
                    },
                ],
            )
            template_path.write_text(repo_template_path.read_text(encoding="utf-8"))

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )

            html = assembler.run(publish_date="2026-05-01", output_path=str(output_path))

            self.assertEqual(output_path.read_text(encoding="utf-8"), html)
            self.assertIn("The AI Upload", html)
            self.assertIn("WEEKLY DIGEST", html.upper())
            self.assertIn("SATURDAY", html)
            self.assertIn("MAY 02", html)
            self.assertIn("2026", html)
            self.assertIn("ISSUE 01", html)
            self.assertIn("This Week&#39;s Headlines", html)
            self.assertRegex(html, re.compile(r">\d{2} Min<"))
            self.assertIn("href=\"#security\"", html)
            self.assertNotIn("href=\"#policy\"", html)
            self.assertIn("id=\"security\"", html)
            self.assertIn(">Rewritten security story<", html)
            self.assertNotIn(">Security story<", html)
            self.assertRegex(
                html,
                re.compile(
                    r'<h3 class="article-title">\s*<a href="https://example.com/security_story" target="_blank" rel="noreferrer">Rewritten security story</a>\s*</h3>'
                ),
            )
            self.assertIn(">Example Source<", html)
            self.assertIn("<p>Paragraph one.</p>", html)
            self.assertIn("<p>Paragraph two.</p>", html)
            self.assertIn(">Headline Source<", html)
            self.assertIn("../../assets/generated/headline_1.png", html)
            self.assertNotIn("../../assets/logos/newsletter_logo.png", html)
            self.assertIn(
                "This newsletter contains AI-generated content that may contain inaccuracies.",
                html,
            )
            self.assertIn(
                "For research or citation purposes, please read and cite the original source article, not this newsletter.",
                html,
            )
            self.assertIn('class="newsletter-disclaimer"', html)

    def test_run_defaults_to_public_index_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            project_root.mkdir()
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "templates").mkdir()
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "public").mkdir()

            stories_path = project_root / "data" / "output" / "summarized_stories.json"
            headlines_path = project_root / "data" / "output" / "headline_picks.json"
            template_path = project_root / "templates" / "newsletter.html"
            output_path = project_root / "public" / "index.html"
            repo_template_path = (
                Path(__file__).resolve().parent.parent / "templates" / "newsletter.html"
            )

            self._write_json(
                stories_path,
                [
                    self._story_payload(
                        "security_story",
                        "security",
                        0.94,
                        "Paragraph one.\n\nParagraph two.",
                        title="Security story",
                        newsletter_title="Rewritten security story",
                    ),
                ],
            )
            self._write_json(
                headlines_path,
                [
                    self._headline_payload(
                        "https://example.com/other_headline",
                        "Other headline",
                        "assets/generated/headline_1.png",
                    ),
                ],
            )
            template_path.write_text(repo_template_path.read_text(encoding="utf-8"))

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )

            html = assembler.run(publish_date="2026-05-01")

            self.assertTrue(output_path.exists())
            self.assertEqual(output_path.read_text(encoding="utf-8"), html)
            self.assertNotIn("{{ publish_date }}", html)
            self.assertIn("ISSUE 01", html)
            self.assertIn("SATURDAY", html)
            self.assertIn("MAY 02", html)
            self.assertIn("src=\"assets/logos/RBG_RCLL_vrt.png\"", html)
            self.assertIn("src=\"assets/generated/headline_1.png\"", html)
            self.assertNotIn("news_brief.png", html)
            self.assertIn('class="brand-mark"', html)
            self.assertIn('class="stats-strip"', html)
            self.assertIn('class="sidebar"', html)
            self.assertIn('class="content-section"', html)
            self.assertIn("This Week&#39;s Briefing", html)
            self.assertIn("Stanford Law School Robert Crown Law Library", html)

    def test_run_shifts_publish_date_forward_one_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            project_root.mkdir()
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "templates").mkdir()
            (project_root / "data" / "output").mkdir(parents=True)

            stories_path = project_root / "data" / "output" / "summarized_stories.json"
            headlines_path = project_root / "data" / "output" / "headline_picks.json"
            template_path = project_root / "templates" / "newsletter.html"
            output_path = project_root / "data" / "output" / "newsletter.html"
            repo_template_path = (
                Path(__file__).resolve().parent.parent / "templates" / "newsletter.html"
            )

            self._write_json(
                stories_path,
                [
                    self._story_payload(
                        "security_story",
                        "security",
                        0.94,
                        "Paragraph one.\n\nParagraph two.",
                    ),
                ],
            )
            self._write_json(
                headlines_path,
                [
                    self._headline_payload(
                        "https://example.com/other_headline",
                        "Other headline",
                        "assets/generated/headline_1.png",
                    ),
                ],
            )
            template_path.write_text(repo_template_path.read_text(encoding="utf-8"))

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )

            html = assembler.run(publish_date="2026-05-26", output_path=str(output_path))

            self.assertIn("WEDNESDAY", html)
            self.assertIn("MAY 27", html)

    def test_story_to_article_prefers_newsletter_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            stories_path = tmpdir / "summarized_stories.json"
            headlines_path = tmpdir / "headline_picks.json"
            template_path = tmpdir / "newsletter.html"
            self._write_json(
                stories_path,
                [
                    self._story_payload(
                        "security_story",
                        "security",
                        0.94,
                        "Paragraph one.\n\nParagraph two.",
                        title="Original security title",
                        newsletter_title="Rewritten security title",
                    ),
                ],
            )
            self._write_json(headlines_path, [])
            template_path.write_text("{{ sections|length }}", encoding="utf-8")

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )

            article = assembler._story_to_article(assembler.stories[0])

            self.assertEqual(article["title"], "Rewritten security title")
            self.assertEqual(article["original_title"], "Original security title")

    def test_new_sections_appear_in_active_navigation_and_rendered_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            project_root.mkdir()
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "templates").mkdir()
            (project_root / "data" / "output").mkdir(parents=True)

            stories_path = project_root / "data" / "output" / "summarized_stories.json"
            headlines_path = project_root / "data" / "output" / "headline_picks.json"
            template_path = project_root / "templates" / "newsletter.html"
            output_path = project_root / "data" / "output" / "newsletter.html"
            repo_template_path = (
                Path(__file__).resolve().parent.parent / "templates" / "newsletter.html"
            )

            self._write_json(
                stories_path,
                [
                    self._story_payload(
                        "ethics_story",
                        "responsible_ai",
                        0.93,
                        "Ethics summary.",
                        title="Ethics story",
                    ),
                    self._story_payload(
                        "environment_story",
                        "ai_sustainability",
                        0.92,
                        "Environment summary.",
                        title="Environment story",
                    ),
                ],
            )
            self._write_json(headlines_path, [])
            template_path.write_text(repo_template_path.read_text(encoding="utf-8"))

            assembler = TemplateAssembler(
                stories_path=str(stories_path),
                headlines_path=str(headlines_path),
                template_path=str(template_path),
            )
            grouped = assembler.group_by_section(assembler.stories, exclude_urls=[])
            self.assertEqual(
                assembler.get_active_sections(grouped),
                [
                    ("responsible_ai", "Responsible AI"),
                    ("ai_sustainability", "AI Sustainability"),
                ],
            )

            html = assembler.run(publish_date="2026-05-01", output_path=str(output_path))

            self.assertIn("href=\"#responsible_ai\"", html)
            self.assertIn("href=\"#ai_sustainability\"", html)
            self.assertIn("id=\"responsible_ai\"", html)
            self.assertIn("id=\"ai_sustainability\"", html)
            self.assertIn(">Responsible AI<", html)
            self.assertIn(">AI Sustainability<", html)
            self.assertIn('class="sidebar"', html)
            self.assertIn('class="content-section"', html)
