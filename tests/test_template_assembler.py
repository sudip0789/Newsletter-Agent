from __future__ import annotations

import json
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
            "summary": summary,
            "needs_manual_review": False,
        }

    def _headline_payload(self, url: str, title: str, image_path: str) -> dict:
        return {
            "title": title,
            "source_name": "Headline Source",
            "url": url,
            "section": "industry",
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
                    self._story_payload("industry_headline", "industry", 0.91, "Industry lead"),
                    self._story_payload("industry_body", "industry", 0.89, "Industry body"),
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

            self.assertEqual(list(grouped.keys()), ["industry", "security"])
            self.assertEqual(
                [story["title"] for story in grouped["security"]],
                ["Story security_high", "Story security_low"],
            )
            self.assertEqual(
                assembler.get_active_sections(grouped),
                [("industry", "Industry"), ("security", "Security")],
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
                        "industry",
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
                        "tools_and_products",
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
                        "section": "industry",
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
                        "section": "tools_and_products",
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
            self.assertIn("The AI Upload Weekly Digest", html)
            self.assertIn("May 1st, 2026", html)
            self.assertIn("This Week&#39;s Headlines", html)
            self.assertIn("href=\"#security\"", html)
            self.assertNotIn("href=\"#policy\"", html)
            self.assertIn("id=\"security\"", html)
            self.assertIn(">Security story<", html)
            self.assertIn("<p>Paragraph one.</p>", html)
            self.assertIn("<p>Paragraph two.</p>", html)
            self.assertIn(">Headline Source<", html)
            self.assertIn("../../assets/generated/headline_1.png", html)
            self.assertIn("../../assets/logos/newsletter_logo.png", html)

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
            self.assertIn("May 1st, 2026", html)
            self.assertNotIn("{{ publish_date }}", html)
            self.assertIn("src=\"assets/logos/newsletter_logo.png\"", html)
            self.assertIn("src=\"assets/logos/news_brief.png\"", html)
            self.assertIn("src=\"assets/logos/security.png\"", html)
            self.assertIn("src=\"assets/generated/headline_1.png\"", html)
