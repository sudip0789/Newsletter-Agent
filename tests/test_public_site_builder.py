from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.public_site_builder import build_public_site


class TestPublicSiteBuilder(unittest.TestCase):
    def _story_payload(self) -> dict:
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": "security_story",
                    "primary_article": {
                        "title": "Security story",
                        "url": "https://example.com/security_story",
                        "source_name": "Example Source",
                    },
                },
                "composite_score": 0.94,
                "section": "security",
            },
            "newsletter_title": "Rewritten security story",
            "summary": "Paragraph one.\n\nParagraph two.",
            "needs_manual_review": False,
        }

    def _headline_payload(self) -> dict:
        return {
            "title": "Other headline",
            "source_name": "Headline Source",
            "url": "https://example.com/other_headline",
            "section": "security",
            "composite_score": 0.99,
            "blurb": "A short headline blurb.",
            "image_path": "assets/generated/headline_1.png",
        }

    def _write_json(self, path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_shared_template(self, project_root: Path) -> None:
        templates_root = Path(__file__).resolve().parent.parent / "templates"
        (project_root / "templates" / "newsletter.html").write_text(
            (templates_root / "newsletter.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        (project_root / "templates" / "archive_index.html").write_text(
            (templates_root / "archive_index.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def _write_shared_logos(self, project_root: Path) -> None:
        for name in [
            "RBG_RCLL_vrt.png",
            "Podcast_edition.png",
            "Video_Overview.png",
            "security.svg",
        ]:
            (project_root / "assets" / "logos" / name).write_bytes(b"logo")

    def _write_issue_snapshot(
        self,
        project_root: Path,
        issue_date: str,
        story_title: str,
        headline_title: str,
    ) -> None:
        issue_root = project_root / "issue_snapshots" / issue_date
        (issue_root / "assets" / "generated").mkdir(parents=True)
        self._write_json(
            issue_root / "summarized_stories.json",
            [
                {
                    **self._story_payload(),
                    "newsletter_title": story_title,
                    "scored_story": {
                        **self._story_payload()["scored_story"],
                        "cluster": {
                            **self._story_payload()["scored_story"]["cluster"],
                            "primary_article": {
                                **self._story_payload()["scored_story"]["cluster"][
                                    "primary_article"
                                ],
                                "title": story_title,
                                "url": f"https://example.com/{issue_date}",
                            },
                        },
                    },
                }
            ],
        )
        self._write_json(
            issue_root / "headline_picks.json",
            [
                {
                    **self._headline_payload(),
                    "title": headline_title,
                    "url": f"https://example.com/headline-{issue_date}",
                }
            ],
        )
        (issue_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

    def test_build_public_site_syncs_assets_and_renders_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)
            (project_root / "public").mkdir(parents=True)

            self._write_shared_template(project_root)

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload()],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload()],
            )

            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")
            self._write_shared_logos(project_root)

            html = build_public_site(project_root=project_root, publish_date="2026-05-01")

            public_index = project_root / "public" / "index.html"
            self.assertTrue(public_index.exists())
            self.assertEqual(public_index.read_text(encoding="utf-8"), html)
            self.assertNotIn("{{ publish_date }}", html)
            self.assertTrue((project_root / "public" / "assets" / "generated" / "headline_1.png").exists())
            self.assertTrue((project_root / "public" / "assets" / "logos" / "RBG_RCLL_vrt.png").exists())
            self.assertIn("ISSUE 01", html)
            self.assertIn("src=\"assets/generated/headline_1.png\"", html)

    def test_build_public_site_uses_generated_headline_images_when_metadata_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)
            (project_root / "public").mkdir(parents=True)

            self._write_shared_template(project_root)
            self._write_shared_logos(project_root)

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload()],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [{**self._headline_payload(), "image_path": None}],
            )

            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            html = build_public_site(project_root=project_root, publish_date="2026-05-01")

            self.assertIn("src=\"assets/generated/headline_1.png\"", html)
            self.assertNotIn(
                '<img src="assets/logos/RBG_RCLL_vrt.png" alt="Other headline">',
                html,
            )

    def test_build_public_site_renders_archive_index_and_issue_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)
            (project_root / "public").mkdir(parents=True)

            self._write_shared_template(project_root)
            self._write_shared_logos(project_root)
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload()],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload()],
            )

            self._write_issue_snapshot(
                project_root=project_root,
                issue_date="2026-04-24",
                story_title="Archived issue story",
                headline_title="Archived issue headline",
            )
            self._write_issue_snapshot(
                project_root=project_root,
                issue_date="2026-05-01",
                story_title="More recent archived story",
                headline_title="More recent archived headline",
            )

            build_public_site(project_root=project_root, publish_date="2026-05-06")

            archive_index = project_root / "public" / "issues" / "index.html"
            archived_issue = project_root / "public" / "issues" / "2026-04-24" / "index.html"
            latest_issue = project_root / "public" / "index.html"

            self.assertTrue(archive_index.exists())
            self.assertTrue(archived_issue.exists())
            self.assertTrue(
                (
                    project_root
                    / "public"
                    / "issues"
                    / "2026-04-24"
                    / "assets"
                    / "generated"
                    / "headline_1.png"
                ).exists()
            )

            archive_html = archive_index.read_text(encoding="utf-8")
            archived_html = archived_issue.read_text(encoding="utf-8")
            latest_html = latest_issue.read_text(encoding="utf-8")

            self.assertIn("Past Issues", latest_html)
            self.assertIn("href=\"issues/\"", latest_html)
            self.assertIn("The AI Newsletter for May 1st, 2026", archive_html)
            self.assertIn("The AI Newsletter for April 24th, 2026", archive_html)
            self.assertLess(
                archive_html.index("The AI Newsletter for May 1st, 2026"),
                archive_html.index("The AI Newsletter for April 24th, 2026"),
            )
            self.assertIn("Open the full newsletter archive for this week.", archive_html)
            self.assertNotIn("More recent archived headline", archive_html)
            self.assertNotIn("Archived issue headline", archive_html)
            self.assertNotIn("More recent archived story", archive_html)
            self.assertIn("Archived issue story", archived_html)
            self.assertIn("src=\"assets/generated/headline_1.png\"", archived_html)
            self.assertIn("href=\"../../\"", archived_html)
            self.assertIn("href=\"../\"", archived_html)

    def test_build_public_site_shifts_latest_issue_date_forward_one_day(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)
            (project_root / "public").mkdir(parents=True)

            self._write_shared_template(project_root)
            self._write_shared_logos(project_root)
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload()],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload()],
            )

            html = build_public_site(project_root=project_root, publish_date="2026-05-26")

            self.assertIn("WEDNESDAY", html)
            self.assertIn("MAY 27", html)


if __name__ == "__main__":
    unittest.main()
