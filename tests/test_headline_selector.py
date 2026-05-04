from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from src.headline_selector import HeadlineSelector
from run_headline_selector import main, parse_args


class TestHeadlineSelector(unittest.TestCase):
    def _story_payload(
        self,
        cluster_id: str,
        section: str,
        score: float,
        summary: str,
        needs_manual_review: bool = False,
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
            "needs_manual_review": needs_manual_review,
        }

    def _write_input(self, stories: list[dict]) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        input_path = Path(tmpdir.name) / "summarized_stories.json"
        input_path.write_text(json.dumps(stories), encoding="utf-8")
        return input_path

    def test_run_picks_preferred_categories_and_fallbacks_without_duplicates(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("industry_top", "industry", 0.98, "Industry summary"),
                self._story_payload(
                    "tools_skip",
                    "tools_and_products",
                    0.97,
                    "Skipped summary",
                    needs_manual_review=True,
                ),
                self._story_payload("creative_empty", "creative_ai", 0.96, "   "),
                self._story_payload("tools_keep", "tools_and_products", 0.95, "Tools summary"),
                self._story_payload("policy_fallback", "policy", 0.94, "Policy summary"),
                self._story_payload("legal_other", "legal_intelligence", 0.93, "Legal summary"),
            ]
        )
        selector = HeadlineSelector(input_path=str(input_path))
        selector.generate_blurb = MagicMock(
            side_effect=lambda story: f"Teaser for {story['title']}"
        )

        picks = selector.run()

        self.assertEqual(
            [pick["section"] for pick in picks],
            ["industry", "tools_and_products", "legal_intelligence"],
        )
        self.assertEqual(
            [pick["title"] for pick in picks],
            ["Story industry_top", "Story tools_keep", "Story legal_other"],
        )
        self.assertEqual(
            [pick["blurb"] for pick in picks],
            [
                "Teaser for Story industry_top",
                "Teaser for Story tools_keep",
                "Teaser for Story legal_other",
            ],
        )

    def test_run_sorts_final_three_picks_by_descending_composite_score(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("industry", "industry", 0.91, "Industry summary"),
                self._story_payload("tools", "tools_and_products", 0.88, "Tools summary"),
                self._story_payload("creative", "creative_ai", 0.97, "Creative summary"),
                self._story_payload("policy", "policy", 0.96, "Policy summary"),
            ]
        )
        selector = HeadlineSelector(input_path=str(input_path))
        selector.generate_blurb = MagicMock(side_effect=lambda story: story["title"])

        picks = selector.run()

        self.assertEqual(
            [pick["title"] for pick in picks],
            ["Story creative", "Story policy", "Story industry"],
        )
        self.assertEqual(
            [pick["composite_score"] for pick in picks],
            [0.97, 0.96, 0.91],
        )

    def test_run_uses_input_order_as_tiebreaker(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("industry_a", "industry", 0.91, "First industry summary"),
                self._story_payload("industry_b", "industry", 0.91, "Second industry summary"),
                self._story_payload("tools", "tools_and_products", 0.90, "Tools summary"),
                self._story_payload("creative", "creative_ai", 0.89, "Creative summary"),
            ]
        )
        selector = HeadlineSelector(input_path=str(input_path))
        selector.generate_blurb = MagicMock(side_effect=lambda story: story["title"])

        picks = selector.run()

        self.assertEqual(picks[0]["title"], "Story industry_a")

    def test_run_fails_when_fewer_than_three_eligible_stories_exist(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("industry", "industry", 0.91, "Industry summary"),
                self._story_payload("tools", "tools_and_products", 0.90, "Tools summary"),
                self._story_payload(
                    "creative",
                    "creative_ai",
                    0.89,
                    "Creative summary",
                    needs_manual_review=True,
                ),
            ]
        )
        selector = HeadlineSelector(input_path=str(input_path))

        with self.assertRaisesRegex(ValueError, "Fewer than 3 eligible headline stories"):
            selector.run()

    def test_generate_blurb_uses_anthropic_and_returns_trimmed_sentence(self) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.blurb_client = MagicMock()
        selector.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="  A sharp teaser for the newsletter.  ")]
        )

        blurb = selector.generate_blurb(
            {
                "title": "OpenAI infrastructure pivot",
                "summary": "A summary about compute strategy shifts.",
            }
        )

        self.assertEqual(blurb, "A sharp teaser for the newsletter.")
        call_kwargs = selector.blurb_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")
        self.assertIn("Title: OpenAI infrastructure pivot", call_kwargs["messages"][0]["content"])
        self.assertIn("Summary: A summary about compute strategy shifts.", call_kwargs["messages"][0]["content"])

    def test_generate_blurb_raises_when_output_exceeds_twenty_words(self) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.blurb_client = MagicMock()
        selector.blurb_client.messages.create.return_value = MagicMock(
            content=[
                MagicMock(
                    type="text",
                    text="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone",
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "under 20 words"):
            selector.generate_blurb({"title": "Test", "summary": "Summary"})

    def test_run_rewrites_long_headline_titles_before_returning_picks(self) -> None:
        long_title = (
            "Microsoft lays out a sweeping new enterprise AI rollout across "
            "copilots models platforms and internal tooling"
        )
        input_path = self._write_input(
            [
                self._story_payload("industry", "industry", 0.97, "Industry summary"),
                self._story_payload("legal", "legal_intelligence", 0.96, "Legal summary"),
                self._story_payload(
                    "tools",
                    "tools_and_products",
                    0.95,
                    "Tools summary",
                    title=long_title,
                ),
            ]
        )
        selector = HeadlineSelector(input_path=str(input_path))
        selector.generate_blurb = MagicMock(side_effect=lambda story: story["title"])
        selector.generate_short_title = MagicMock(
            return_value="Microsoft's enterprise AI push"
        )

        picks = selector.run()

        self.assertEqual(picks[0]["title"], "Story industry")
        self.assertEqual(picks[1]["title"], "Story legal")
        self.assertEqual(picks[2]["title"], "Microsoft's enterprise AI push")
        selector.generate_short_title.assert_called_once_with(
            {"title": long_title, "summary": "Tools summary"}
        )

    def test_generate_short_title_uses_anthropic_and_enforces_word_count(self) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.blurb_client = MagicMock()
        selector.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="  OpenAI courtroom trial showdown begins  ")]
        )

        short_title = selector.generate_short_title(
            {
                "title": "Elon gets his day in trial against Sam Altman and OpenAI",
                "summary": "A summary about the trial and testimony.",
            }
        )

        self.assertEqual(short_title, "OpenAI courtroom trial showdown begins")
        call_kwargs = selector.blurb_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")
        self.assertIn("Original title:", call_kwargs["messages"][0]["content"])

    def test_generate_short_title_raises_when_word_count_is_out_of_range(self) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.blurb_client = MagicMock()
        selector.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="too short")]
        )

        with self.assertRaisesRegex(ValueError, "5-8 words"):
            selector.generate_short_title({"title": "Test", "summary": "Summary"})

    def test_generate_headline_image_saves_file_and_returns_path(
        self,
    ) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.assets_dir = input_path.parent / "assets" / "generated"
        selector.image_client = MagicMock()

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(b64_json=base64.b64encode(b"png-bytes").decode("ascii"))
        ]
        selector.image_client.images.generate.return_value = mock_response

        image_path = selector.generate_headline_image(
            {"title": "AI title", "summary": "AI summary"},
            2,
        )

        self.assertTrue(Path(image_path).exists())
        self.assertEqual(Path(image_path).name, "headline_2.png")
        selector.image_client.images.generate.assert_called_once()

    def test_generate_headline_image_returns_none_on_failure(
        self,
    ) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.assets_dir = input_path.parent / "assets" / "generated"
        selector.image_client = MagicMock()
        selector.image_client.images.generate.side_effect = RuntimeError("boom")

        image_path = selector.generate_headline_image(
            {"title": "AI title", "summary": "AI summary"},
            1,
        )

        self.assertIsNone(image_path)

    def test_save_picks_writes_expected_json_shape(self) -> None:
        input_path = self._write_input([])
        selector = HeadlineSelector(input_path=str(input_path))
        selector.output_path = input_path.parent / "headline_picks.json"
        picks = [
            {
                "title": "Story 1",
                "source_name": "Example Source",
                "url": "https://example.com/1",
                "section": "industry",
                "composite_score": 0.91,
                "summary": "Hidden summary",
                "blurb": "Visible blurb",
                "image_path": None,
            }
        ]

        selector.save_picks(picks)
        payload = json.loads(selector.output_path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload,
            [
                {
                    "title": "Story 1",
                    "source_name": "Example Source",
                    "url": "https://example.com/1",
                    "section": "industry",
                    "composite_score": 0.91,
                    "blurb": "Visible blurb",
                    "image_path": None,
                }
            ],
        )


class TestRunHeadlineSelector(unittest.TestCase):
    def test_parse_args_rejects_conflicting_mode_flags(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["run_headline_selector.py", "--blurbs-only", "--images-only"],
        ):
            with self.assertRaises(SystemExit):
                parse_args()

    @patch("run_headline_selector.setup_logging")
    @patch("run_headline_selector.time.sleep")
    @patch("run_headline_selector.HeadlineSelector")
    def test_main_full_run_generates_images_and_saves(
        self,
        mock_selector_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        selector = mock_selector_cls.return_value
        selector.run.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]
        selector.generate_headline_image.side_effect = [
            "assets/generated/headline_1.png",
            "assets/generated/headline_2.png",
            None,
        ]

        with patch.object(sys, "argv", ["run_headline_selector.py"]):
            main()

        self.assertEqual(selector.generate_headline_image.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(10), call(10)])
        selector.save_picks.assert_called_once_with(
            [
                {
                    "title": "Story 1",
                    "summary": "Summary 1",
                    "blurb": "Blurb 1",
                    "image_path": "assets/generated/headline_1.png",
                },
                {
                    "title": "Story 2",
                    "summary": "Summary 2",
                    "blurb": "Blurb 2",
                    "image_path": "assets/generated/headline_2.png",
                },
                {
                    "title": "Story 3",
                    "summary": "Summary 3",
                    "blurb": "Blurb 3",
                    "image_path": None,
                },
            ]
        )

    @patch("run_headline_selector.setup_logging")
    @patch("run_headline_selector.time.sleep")
    @patch("run_headline_selector.HeadlineSelector")
    def test_main_blurbs_only_saves_null_image_paths(
        self,
        mock_selector_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        selector = mock_selector_cls.return_value
        selector.run.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]

        with patch.object(sys, "argv", ["run_headline_selector.py", "--blurbs-only"]):
            main()

        selector.generate_headline_image.assert_not_called()
        mock_sleep.assert_not_called()
        selector.save_picks.assert_called_once_with(
            [
                {
                    "title": "Story 1",
                    "summary": "Summary 1",
                    "blurb": "Blurb 1",
                    "image_path": None,
                },
                {
                    "title": "Story 2",
                    "summary": "Summary 2",
                    "blurb": "Blurb 2",
                    "image_path": None,
                },
                {
                    "title": "Story 3",
                    "summary": "Summary 3",
                    "blurb": "Blurb 3",
                    "image_path": None,
                },
            ]
        )

    @patch("run_headline_selector.setup_logging")
    @patch("run_headline_selector.time.sleep")
    @patch("run_headline_selector.HeadlineSelector")
    def test_main_images_only_refreshes_saved_picks(
        self,
        mock_selector_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        selector = mock_selector_cls.return_value
        selector.load_saved_picks.return_value = [
            {"title": "Story 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "blurb": "Blurb 3"},
        ]
        selector.attach_summaries.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]
        selector.generate_headline_image.side_effect = [
            "assets/generated/headline_1.png",
            None,
            "assets/generated/headline_3.png",
        ]

        with patch.object(sys, "argv", ["run_headline_selector.py", "--images-only"]):
            main()

        selector.run.assert_not_called()
        self.assertEqual(mock_sleep.call_args_list, [call(10), call(10)])
        selector.save_picks.assert_called_once_with(
            [
                {
                    "title": "Story 1",
                    "summary": "Summary 1",
                    "blurb": "Blurb 1",
                    "image_path": "assets/generated/headline_1.png",
                },
                {
                    "title": "Story 2",
                    "summary": "Summary 2",
                    "blurb": "Blurb 2",
                    "image_path": None,
                },
                {
                    "title": "Story 3",
                    "summary": "Summary 3",
                    "blurb": "Blurb 3",
                    "image_path": "assets/generated/headline_3.png",
                },
            ]
        )


if __name__ == "__main__":
    unittest.main()
