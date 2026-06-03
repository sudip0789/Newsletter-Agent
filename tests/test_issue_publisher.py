from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch

from src.issue_publisher import publish_issue, refresh_drive_headline_images


class TestIssuePublisher(unittest.TestCase):
    def setUp(self) -> None:
        self.render_pdf_patcher = patch("src.pdf_renderer.render_html_to_pdf")
        self.mock_render_pdf = self.render_pdf_patcher.start()
        self.addCleanup(self.render_pdf_patcher.stop)
        self.drive_config_patcher = patch(
            "src.drive_publisher.is_configured",
            return_value=False,
        )
        self.mock_drive_configured = self.drive_config_patcher.start()
        self.addCleanup(self.drive_config_patcher.stop)

    def _story_payload(self, title: str, url: str) -> dict:
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": "security_story",
                    "primary_article": {
                        "title": title,
                        "url": url,
                        "source_name": "Example Source",
                    },
                },
                "composite_score": 0.94,
                "section": "security",
            },
            "summary": "Paragraph one.\n\nParagraph two.",
            "needs_manual_review": False,
        }

    def _headline_payload(self, title: str, url: str) -> dict:
        return {
            "title": title,
            "source_name": "Headline Source",
            "url": url,
            "section": "security",
            "composite_score": 0.99,
            "blurb": "A short headline blurb.",
            "image_path": "assets/generated/headline_1.png",
        }

    def _write_json(self, path: Path, payload: list[dict]) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_publish_issue_snapshots_current_issue_and_rebuilds_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)

            repo_root = Path(__file__).resolve().parent.parent
            (project_root / "templates" / "newsletter.html").write_text(
                (repo_root / "templates" / "newsletter.html").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (project_root / "templates" / "archive_index.html").write_text(
                (repo_root / "templates" / "archive_index.html").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            for name in [
                "RBG_RCLL_vrt.png",
                "Podcast_edition.png",
                "Video_Overview.png",
                "security.svg",
            ]:
                (project_root / "assets" / "logos" / name).write_bytes(b"logo")
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload("Latest story", "https://example.com/latest")],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload("Latest headline", "https://example.com/latest-headline")],
            )

            older_issue_root = project_root / "issue_snapshots" / "2026-04-24"
            (older_issue_root / "assets" / "generated").mkdir(parents=True)
            self._write_json(
                older_issue_root / "summarized_stories.json",
                [self._story_payload("Older story", "https://example.com/older")],
            )
            self._write_json(
                older_issue_root / "headline_picks.json",
                [self._headline_payload("Older headline", "https://example.com/older-headline")],
            )
            (older_issue_root / "assets" / "generated" / "headline_1.png").write_bytes(b"old")

            publish_issue(project_root=project_root, publish_date="2026-05-06")

            new_issue_root = project_root / "issue_snapshots" / "2026-05-06"
            self.assertTrue((new_issue_root / "summarized_stories.json").exists())
            self.assertTrue((new_issue_root / "headline_picks.json").exists())
            self.assertTrue((new_issue_root / "assets" / "generated" / "headline_1.png").exists())
            self.assertEqual(
                (new_issue_root / "assets" / "generated" / "headline_1.png").read_bytes(),
                b"png",
            )
            self.assertEqual(
                (older_issue_root / "assets" / "generated" / "headline_1.png").read_bytes(),
                b"old",
            )

            archive_html = (project_root / "public" / "issues" / "index.html").read_text(
                encoding="utf-8"
            )
            current_issue_html = (
                project_root / "public" / "issues" / "2026-05-06" / "index.html"
            ).read_text(encoding="utf-8")

            self.assertIn("The AI Newsletter for May 6th, 2026", archive_html)
            self.assertIn("The AI Newsletter for April 24th, 2026", archive_html)
            self.assertLess(
                archive_html.index("The AI Newsletter for May 6th, 2026"),
                archive_html.index("The AI Newsletter for April 24th, 2026"),
            )
            self.assertNotIn("Latest headline", archive_html)
            self.assertNotIn("Older headline", archive_html)
            self.assertIn("Latest story", current_issue_html)

    def test_publish_issue_uses_current_day_for_snapshot_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)

            repo_root = Path(__file__).resolve().parent.parent
            (project_root / "templates" / "newsletter.html").write_text(
                (repo_root / "templates" / "newsletter.html").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (project_root / "templates" / "archive_index.html").write_text(
                (repo_root / "templates" / "archive_index.html").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            for name in [
                "RBG_RCLL_vrt.png",
                "Podcast_edition.png",
                "Video_Overview.png",
                "security.svg",
            ]:
                (project_root / "assets" / "logos" / name).write_bytes(b"logo")
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload("Latest story", "https://example.com/latest")],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload("Latest headline", "https://example.com/latest-headline")],
            )

            publish_issue(project_root=project_root, publish_date="2026-05-26")

            current_issue_root = project_root / "issue_snapshots" / "2026-05-26"
            self.assertTrue(current_issue_root.exists())
            self.assertFalse((project_root / "issue_snapshots" / "2026-05-27").exists())

            archive_html = (project_root / "public" / "issues" / "index.html").read_text(
                encoding="utf-8"
            )
            self.assertIn("The AI Newsletter for May 26th, 2026", archive_html)

    def test_publish_issue_uses_weekly_media_input_urls_for_audio_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)

            repo_root = Path(__file__).resolve().parent.parent
            (project_root / "templates" / "newsletter.html").write_text(
                (repo_root / "templates" / "newsletter.html").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (project_root / "templates" / "archive_index.html").write_text(
                (repo_root / "templates" / "archive_index.html").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            for name in [
                "RBG_RCLL_vrt.png",
                "Podcast_edition.png",
                "Video_Overview.png",
                "security.svg",
            ]:
                (project_root / "assets" / "logos" / name).write_bytes(b"logo")
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload("Latest story", "https://example.com/latest")],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload("Latest headline", "https://example.com/latest-headline")],
            )
            (project_root / "data" / "output" / "media_inputs.json").write_text(
                json.dumps(
                    {
                        "audio_url": "https://drive.google.com/file/d/audio-file-id/view?usp=sharing",
                        "video_url": "https://drive.google.com/file/d/video-file-id/view?usp=sharing",
                    }
                ),
                encoding="utf-8",
            )

            publish_issue(project_root=project_root, publish_date="2026-05-06")

            issue_root = project_root / "issue_snapshots" / "2026-05-06"
            media = json.loads((issue_root / "media.json").read_text(encoding="utf-8"))

            self.assertEqual(
                media["podcast_embed_url"],
                "https://drive.google.com/file/d/audio-file-id/preview",
            )
            self.assertEqual(
                media["podcast_audio_url"],
                "https://drive.usercontent.google.com/download?id=audio-file-id&export=download",
            )
            self.assertEqual(
                media["video_embed_url"],
                "https://drive.google.com/file/d/video-file-id/preview",
            )

            latest_html = (project_root / "public" / "index.html").read_text(encoding="utf-8")
            self.assertIn(
                "https://drive.usercontent.google.com/download?id=audio-file-id&amp;export=download",
                latest_html,
            )
            self.assertIn(
                "https://drive.google.com/file/d/video-file-id/preview",
                latest_html,
            )

    def test_publish_issue_snapshots_local_podcast_audio_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "assets" / "logos").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            (project_root / "templates").mkdir(parents=True)

            repo_root = Path(__file__).resolve().parent.parent
            (project_root / "templates" / "newsletter.html").write_text(
                (repo_root / "templates" / "newsletter.html").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (project_root / "templates" / "archive_index.html").write_text(
                (repo_root / "templates" / "archive_index.html").read_text(
                    encoding="utf-8"
                ),
                encoding="utf-8",
            )

            for name in [
                "RBG_RCLL_vrt.png",
                "Podcast_edition.png",
                "Video_Overview.png",
                "security.svg",
            ]:
                (project_root / "assets" / "logos" / name).write_bytes(b"logo")
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"png")
            (project_root / "data" / "output" / "audio.mp3").write_bytes(b"mp3")

            self._write_json(
                project_root / "data" / "output" / "summarized_stories.json",
                [self._story_payload("Latest story", "https://example.com/latest")],
            )
            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [self._headline_payload("Latest headline", "https://example.com/latest-headline")],
            )

            publish_issue(project_root=project_root, publish_date="2026-05-06")

            issue_root = project_root / "issue_snapshots" / "2026-05-06"
            media = json.loads((issue_root / "media.json").read_text(encoding="utf-8"))
            latest_html = (project_root / "public" / "index.html").read_text(encoding="utf-8")

            self.assertNotIn("podcast_embed_url", media)
            self.assertEqual(
                media["podcast_audio_url"],
                "assets/media/podcast-2026-05-06.mp3",
            )
            self.assertTrue(
                (issue_root / "assets" / "media" / "podcast-2026-05-06.mp3").exists()
            )
            self.assertTrue(
                (
                    project_root
                    / "public"
                    / "assets"
                    / "media"
                    / "podcast-2026-05-06.mp3"
                ).exists()
            )
            self.assertIn('src="assets/media/podcast-2026-05-06.mp3"', latest_html)

    @patch("src.drive_publisher.replace_file")
    def test_refresh_drive_headline_images_updates_existing_issue_media(
        self,
        mock_replace_file,
    ) -> None:
        self.mock_drive_configured.return_value = True
        with tempfile.TemporaryDirectory() as tmpdir_name:
            tmpdir = Path(tmpdir_name)
            project_root = tmpdir / "project"
            (project_root / "assets" / "generated").mkdir(parents=True)
            (project_root / "data" / "output").mkdir(parents=True)
            issue_root = project_root / "issue_snapshots" / "2026-05-06"
            issue_root.mkdir(parents=True)

            self._write_json(
                project_root / "data" / "output" / "headline_picks.json",
                [
                    self._headline_payload(
                        "Headline 1",
                        "https://example.com/headline-1",
                    ),
                    {
                        **self._headline_payload(
                            "Headline 2",
                            "https://example.com/headline-2",
                        ),
                        "image_path": "assets/generated/headline_2.png",
                    },
                ],
            )
            (project_root / "assets" / "generated" / "headline_1.png").write_bytes(b"new-1")
            (project_root / "assets" / "generated" / "headline_2.png").write_bytes(b"new-2")
            (issue_root / "media.json").write_text(
                json.dumps(
                    {
                        "folder_id": "folder-123",
                        "folder_url": "https://drive.google.com/drive/folders/folder-123",
                        "headline_images": ["old-1", "old-2"],
                        "video_embed_url": "https://drive.google.com/file/d/video/preview",
                    }
                ),
                encoding="utf-8",
            )
            mock_replace_file.side_effect = [
                {"direct_url": "new-url-1"},
                {"direct_url": "new-url-2"},
            ]

            media = refresh_drive_headline_images(
                project_root=project_root,
                publish_date="2026-05-06",
            )

            self.assertEqual(media["headline_images"], ["new-url-1", "new-url-2"])
            self.assertEqual(
                media["video_embed_url"],
                "https://drive.google.com/file/d/video/preview",
            )
            mock_replace_file.assert_has_calls(
                [
                    call(
                        "folder-123",
                        (project_root / "assets" / "generated" / "headline_1.png").resolve(),
                        "headline_1.png",
                    ),
                    call(
                        "folder-123",
                        (project_root / "assets" / "generated" / "headline_2.png").resolve(),
                        "headline_2.png",
                    ),
                ]
            )
            self.assertEqual(
                json.loads((issue_root / "media.json").read_text(encoding="utf-8")),
                media,
            )
            self.assertEqual(
                json.loads(
                    (project_root / "data" / "output" / "media.json").read_text(
                        encoding="utf-8"
                    )
                ),
                media,
            )


if __name__ == "__main__":
    unittest.main()
