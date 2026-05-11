from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from scripts.run_headline_agent import main, parse_args
from src.headline_agent import HeadlineAgent


class TestHeadlineAgent(unittest.TestCase):
    def _story_payload(
        self,
        cluster_id: str,
        section: str,
        score: float,
        summary: str,
        needs_manual_review: bool = False,
        title: str | None = None,
        source_name: str = "Example Source",
    ) -> dict:
        story_title = title or f"Story {cluster_id}"
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": cluster_id,
                    "primary_article": {
                        "title": story_title,
                        "url": f"https://example.com/{cluster_id}",
                        "source_name": source_name,
                        "source_type": "rss",
                        "published_date": "2026-04-21T00:00:00+00:00",
                        "text": "Example article text",
                        "text_completeness": "full",
                        "fetch_method": "feedparser",
                    },
                    "coverage_count": 3,
                    "sources_involved": [source_name, "Another Source"],
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

    def _selection_response(self, urls: list[str]) -> MagicMock:
        payload = {
            "selected_headlines": [{"url": url} for url in urls]
        }
        return MagicMock(
            choices=[MagicMock(message=MagicMock(content=json.dumps(payload)))]
        )

    def test_run_uses_gpt54_selection_order_and_prompt(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("launch", "tools_and_products", 0.98, "Launch summary"),
                self._story_payload("lawsuit", "legal_intelligence", 0.95, "Lawsuit summary"),
                self._story_payload("risk", "industry", 0.94, "Risk summary"),
                self._story_payload("research", "research", 0.93, "Research summary"),
            ]
        )
        agent = HeadlineAgent(input_path=str(input_path))
        agent.selection_client = MagicMock()
        agent.selection_client.chat.completions.create.return_value = self._selection_response(
            [
                "https://example.com/lawsuit",
                "https://example.com/launch",
                "https://example.com/risk",
            ]
        )
        agent.generate_blurb = MagicMock(side_effect=lambda story: f"Teaser for {story['title']}")

        picks = agent.run()

        self.assertEqual(
            [pick["title"] for pick in picks],
            ["Story lawsuit", "Story launch", "Story risk"],
        )
        call_kwargs = agent.selection_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "gpt-5.4")
        self.assertEqual(call_kwargs["response_format"], {"type": "json_object"})
        self.assertGreater(call_kwargs["temperature"], 0.0)
        system_prompt = call_kwargs["messages"][0]["content"]
        self.assertIn("popular product launches", system_prompt)
        self.assertIn("lawsuits", system_prompt)
        self.assertIn("variety across the final 3 picks", system_prompt)
        user_prompt = call_kwargs["messages"][1]["content"]
        self.assertIn("https://example.com/launch", user_prompt)
        self.assertIn("Example Source", user_prompt)
        self.assertIn("coverage_count", user_prompt)

    def test_run_falls_back_to_score_ranked_selection_when_llm_output_is_invalid(self) -> None:
        input_path = self._write_input(
            [
                self._story_payload("launch", "tools_and_products", 0.98, "Launch summary"),
                self._story_payload("lawsuit", "legal_intelligence", 0.95, "Lawsuit summary"),
                self._story_payload("risk", "industry", 0.94, "Risk summary"),
                self._story_payload("research", "research", 0.93, "Research summary"),
            ]
        )
        agent = HeadlineAgent(input_path=str(input_path))
        agent.selection_client = MagicMock()
        agent.selection_client.chat.completions.create.return_value = self._selection_response(
            [
                "https://example.com/launch",
                "https://example.com/launch",
                "https://example.com/missing",
            ]
        )
        agent.generate_blurb = MagicMock(side_effect=lambda story: story["title"])

        picks = agent.run()

        self.assertEqual(
            [pick["title"] for pick in picks],
            ["Story launch", "Story lawsuit", "Story risk"],
        )

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
        agent = HeadlineAgent(input_path=str(input_path))
        agent.selection_client = MagicMock()
        agent.selection_client.chat.completions.create.return_value = self._selection_response(
            [
                "https://example.com/industry",
                "https://example.com/legal",
                "https://example.com/tools",
            ]
        )
        agent.generate_blurb = MagicMock(side_effect=lambda story: story["title"])
        agent.generate_short_title = MagicMock(
            return_value="Microsoft's enterprise AI push"
        )

        picks = agent.run()

        self.assertEqual(picks[0]["title"], "Story industry")
        self.assertEqual(picks[1]["title"], "Story legal")
        self.assertEqual(picks[2]["title"], "Microsoft's enterprise AI push")
        agent.generate_short_title.assert_called_once_with(
            {"title": long_title, "summary": "Tools summary"}
        )

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
        agent = HeadlineAgent(input_path=str(input_path))

        with self.assertRaisesRegex(ValueError, "Fewer than 3 eligible headline stories"):
            agent.run()

    def test_generate_blurb_uses_anthropic_and_returns_trimmed_sentence(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.blurb_client = MagicMock()
        agent.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="  A sharp teaser for the newsletter.  ")]
        )

        blurb = agent.generate_blurb(
            {
                "title": "OpenAI infrastructure pivot",
                "summary": "A summary about compute strategy shifts.",
            }
        )

        self.assertEqual(blurb, "A sharp teaser for the newsletter.")
        call_kwargs = agent.blurb_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")
        self.assertIn("Title: OpenAI infrastructure pivot", call_kwargs["messages"][0]["content"])
        self.assertIn("Summary: A summary about compute strategy shifts.", call_kwargs["messages"][0]["content"])

    def test_generate_blurb_raises_when_output_exceeds_twenty_words(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.blurb_client = MagicMock()
        agent.blurb_client.messages.create.return_value = MagicMock(
            content=[
                MagicMock(
                    type="text",
                    text="one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twentyone",
                )
            ]
        )

        with self.assertRaisesRegex(ValueError, "under 20 words"):
            agent.generate_blurb({"title": "Test", "summary": "Summary"})

    def test_generate_short_title_uses_anthropic_and_enforces_word_count(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.blurb_client = MagicMock()
        agent.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="  OpenAI courtroom trial showdown begins  ")]
        )

        short_title = agent.generate_short_title(
            {
                "title": "Elon gets his day in trial against Sam Altman and OpenAI",
                "summary": "A summary about the trial and testimony.",
            }
        )

        self.assertEqual(short_title, "OpenAI courtroom trial showdown begins")
        call_kwargs = agent.blurb_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")
        self.assertIn("Original title:", call_kwargs["messages"][0]["content"])

    def test_generate_short_title_raises_when_word_count_is_out_of_range(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.blurb_client = MagicMock()
        agent.blurb_client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="too short")]
        )

        with self.assertRaisesRegex(ValueError, "5-8 words"):
            agent.generate_short_title({"title": "Test", "summary": "Summary"})

    def test_generate_headline_image_saves_file_and_returns_path(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.assets_dir = input_path.parent / "assets" / "generated"
        agent.image_client = MagicMock()

        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(b64_json=base64.b64encode(b"png-bytes").decode("ascii"))
        ]
        agent.image_client.images.generate.return_value = mock_response

        image_path = agent.generate_headline_image(
            {"title": "AI title", "summary": "AI summary"},
            2,
        )

        self.assertTrue(Path(image_path).exists())
        self.assertEqual(Path(image_path).name, "headline_2.png")
        agent.image_client.images.generate.assert_called_once()

    def test_generate_headline_image_returns_none_on_failure(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.assets_dir = input_path.parent / "assets" / "generated"
        agent.image_client = MagicMock()
        agent.image_client.images.generate.side_effect = RuntimeError("boom")

        image_path = agent.generate_headline_image(
            {"title": "AI title", "summary": "AI summary"},
            1,
        )

        self.assertIsNone(image_path)

    def test_save_picks_writes_expected_json_shape(self) -> None:
        input_path = self._write_input([])
        agent = HeadlineAgent(input_path=str(input_path))
        agent.output_path = input_path.parent / "headline_picks.json"
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

        agent.save_picks(picks)
        payload = json.loads(agent.output_path.read_text(encoding="utf-8"))

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


class TestRunHeadlineAgent(unittest.TestCase):
    def test_parse_args_rejects_conflicting_mode_flags(self) -> None:
        with patch.object(
            sys,
            "argv",
            ["run_headline_agent.py", "--blurbs-only", "--images-only"],
        ):
            with self.assertRaises(SystemExit):
                parse_args()

    @patch("scripts.run_headline_agent.setup_logging")
    @patch("scripts.run_headline_agent.time.sleep")
    @patch("scripts.run_headline_agent.HeadlineAgent")
    def test_main_full_run_generates_images_and_saves(
        self,
        mock_agent_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        agent = mock_agent_cls.return_value
        agent.run.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]
        agent.generate_headline_image.side_effect = [
            "assets/generated/headline_1.png",
            "assets/generated/headline_2.png",
            None,
        ]

        with patch.object(sys, "argv", ["run_headline_agent.py"]):
            main()

        self.assertEqual(agent.generate_headline_image.call_count, 3)
        self.assertEqual(mock_sleep.call_args_list, [call(10), call(10)])
        agent.save_picks.assert_called_once_with(
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

    @patch("scripts.run_headline_agent.setup_logging")
    @patch("scripts.run_headline_agent.time.sleep")
    @patch("scripts.run_headline_agent.HeadlineAgent")
    def test_main_blurbs_only_saves_null_image_paths(
        self,
        mock_agent_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        agent = mock_agent_cls.return_value
        agent.run.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]

        with patch.object(sys, "argv", ["run_headline_agent.py", "--blurbs-only"]):
            main()

        agent.generate_headline_image.assert_not_called()
        mock_sleep.assert_not_called()
        agent.save_picks.assert_called_once_with(
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

    @patch("scripts.run_headline_agent.setup_logging")
    @patch("scripts.run_headline_agent.time.sleep")
    @patch("scripts.run_headline_agent.HeadlineAgent")
    def test_main_images_only_refreshes_saved_picks(
        self,
        mock_agent_cls: MagicMock,
        mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        agent = mock_agent_cls.return_value
        agent.load_saved_picks.return_value = [
            {"title": "Story 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "blurb": "Blurb 3"},
        ]
        agent.attach_summaries.return_value = [
            {"title": "Story 1", "summary": "Summary 1", "blurb": "Blurb 1"},
            {"title": "Story 2", "summary": "Summary 2", "blurb": "Blurb 2"},
            {"title": "Story 3", "summary": "Summary 3", "blurb": "Blurb 3"},
        ]
        agent.generate_headline_image.side_effect = [
            "assets/generated/headline_1.png",
            None,
            "assets/generated/headline_3.png",
        ]

        with patch.object(sys, "argv", ["run_headline_agent.py", "--images-only"]):
            main()

        agent.run.assert_not_called()
        self.assertEqual(mock_sleep.call_args_list, [call(10), call(10)])
        agent.save_picks.assert_called_once_with(
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
