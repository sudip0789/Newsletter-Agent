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

    def test_build_public_site_syncs_assets_and_renders_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)
            (project_root / "public").mkdir(parents=True)

            repo_template_path = (
                Path(__file__).resolve().parent.parent / "templates" / "newsletter.html"
            )
            (project_root / "templates" / "newsletter.html").write_text(
                repo_template_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload()],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload()],
            )

            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")
            for name in [
                "newsletter_logo.png",
                "news_brief.png",
                "security.png",
            ]:
                (project_root / "assets" / "logos" / name).write_bytes(b"png")

            html = build_public_site(project_root=project_root, publish_date="2026-05-01")

            public_index = project_root / "public" / "index.html"
            self.assertTrue(public_index.exists())
            self.assertEqual(public_index.read_text(encoding="utf-8"), html)
            self.assertIn("May 1st, 2026", html)
            self.assertNotIn("{{ publish_date }}", html)
            self.assertTrue((project_root / "public" / "assets" / "generated" / "headline_1.png").exists())
            self.assertTrue((project_root / "public" / "assets" / "logos" / "newsletter_logo.png").exists())
            self.assertIn("src=\"assets/generated/headline_1.png\"", html)
            self.assertIn("src=\"assets/logos/security.png\"", html)


if __name__ == "__main__":
    unittest.main()
