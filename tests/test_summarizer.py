import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.models import Article, ScoredStory, StoryCluster, SummarizedStory
from src.summarizer import Summarizer


class TestSummarizer(unittest.TestCase):
    def _article(
        self,
        title: str,
        text: str,
        text_completeness: str = "full",
    ) -> Article:
        return Article(
            title=title,
            url=f"https://example.com/{title.replace(' ', '-').lower()}",
            source_name="Example Source",
            source_type="rss",
            published_date=datetime(2026, 4, 21, tzinfo=timezone.utc),
            text=text,
            text_completeness=text_completeness,
            fetch_method="feedparser",
        )

    def _scored_story(
        self,
        cluster_id: str,
        score: float,
        text: str,
        text_completeness: str = "full",
    ) -> ScoredStory:
        article = self._article(
            title=f"Story {cluster_id}",
            text=text,
            text_completeness=text_completeness,
        )
        cluster = StoryCluster(
            cluster_id=cluster_id,
            primary_article=article,
            all_articles=[article],
            coverage_count=1,
            sources_involved=[article.source_name],
        )
        return ScoredStory(
            cluster=cluster,
            scores={
                "ai_relevance": score,
                "impact": score,
                "audience_relevance": score,
                "novelty": score,
                "source_quality": score,
                "buzz_momentum": score,
            },
            composite_score=score,
            rationale="Example rationale.",
            section="industry",
            tier="body",
        )

    def _make_summarizer(self, stories: list[ScoredStory], top_n: int = 10) -> Summarizer:
        summarizer = Summarizer.__new__(Summarizer)
        summarizer.input_path = Path("/tmp/scored_stories.json")
        summarizer.output_path = Path("/tmp/summarized_stories.json")
        summarizer.top_n = top_n
        summarizer.scored_stories = stories
        summarizer.client = MagicMock()
        summarizer.provider = "openai"
        summarizer.api_model = "gpt-5.4"
        summarizer.model_name = "gpt-5.4"
        summarizer.model_config = Summarizer.MODEL_CONFIGS["gpt-5.4"]
        return summarizer

    def test_run_selects_top_n_by_composite_score(self) -> None:
        stories = [
            self._scored_story("low", 0.4, "A" * 200),
            self._scored_story("high", 0.9, "B" * 200),
            self._scored_story("mid", 0.7, "C" * 200),
        ]
        summarizer = self._make_summarizer(stories, top_n=2)
        summarizer.summarize_story = MagicMock(
            side_effect=lambda story: SummarizedStory(
                scored_story=story,
                summary=f"Summary for {story.cluster.cluster_id}",
            )
        )

        results = summarizer.run()

        self.assertEqual(
            [story.scored_story.cluster.cluster_id for story in results],
            ["high", "mid"],
        )

    def test_snippet_story_bypasses_llm_and_flags_manual_review(self) -> None:
        story = self._scored_story("snippet", 0.8, "Snippet text", "snippet")
        summarizer = self._make_summarizer([story], top_n=1)
        summarizer.summarize_story = MagicMock()

        results = summarizer.run()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].summary, "Snippet text")
        self.assertTrue(results[0].needs_manual_review)
        summarizer.summarize_story.assert_not_called()

    def test_short_text_flags_manual_review_without_llm(self) -> None:
        story = self._scored_story("short", 0.8, "Too short", "full")
        summarizer = self._make_summarizer([story], top_n=1)
        summarizer.summarize_story = MagicMock()

        results = summarizer.run()

        self.assertEqual(results[0].summary, "Too short")
        self.assertTrue(results[0].needs_manual_review)
        summarizer.summarize_story.assert_not_called()

    def test_summarize_story_truncates_text_to_10000_chars(self) -> None:
        story = self._scored_story("long", 0.8, "X" * 12000, "full")
        summarizer = self._make_summarizer([story])
        summarizer.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Generated summary"))]
        )

        result = summarizer.summarize_story(story)
        call_kwargs = summarizer.client.chat.completions.create.call_args.kwargs
        user_message = call_kwargs["messages"][1]["content"]

        self.assertEqual(result.summary, "Generated summary")
        self.assertIn("Article text:\n", user_message)
        self.assertEqual(user_message.count("X"), 10000)

    def test_summarize_story_unescapes_html_entities(self) -> None:
        story = self._scored_story("encoded", 0.8, "Z" * 200, "full")
        summarizer = self._make_summarizer([story])
        summarizer.client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="China&#39;s AI push"))]
        )

        result = summarizer.summarize_story(story)

        self.assertEqual(result.summary, "China's AI push")

    def test_handle_snippet_unescapes_html_entities(self) -> None:
        story = self._scored_story("snippet", 0.8, "China&#39;s policy update", "snippet")
        summarizer = self._make_summarizer([story], top_n=1)

        result = summarizer.handle_snippet(story)

        self.assertEqual(result.summary, "China's policy update")
        self.assertTrue(result.needs_manual_review)

    def test_summarize_story_failure_returns_manual_review_fallback(self) -> None:
        story = self._scored_story("failure", 0.8, "Y" * 200, "full")
        summarizer = self._make_summarizer([story])
        summarizer.client.chat.completions.create.side_effect = RuntimeError("boom")

        result = summarizer.summarize_story(story)

        self.assertEqual(
            result.summary,
            "Summary generation failed — manual review required.",
        )
        self.assertTrue(result.needs_manual_review)

    def test_save_results_writes_utf8_json(self) -> None:
        story = self._scored_story("utf8", 0.8, "Résumé text " * 20, "full")
        summarized = SummarizedStory(
            scored_story=story,
            summary="Résumé summary.",
            needs_manual_review=False,
        )
        summarizer = self._make_summarizer([story])

        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer.output_path = Path(tmpdir) / "summarized_stories.json"
            summarizer.save_results([summarized])
            payload = json.loads(summarizer.output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload[0]["summary"], "Résumé summary.")
        self.assertIn("scored_story", payload[0])
        self.assertNotIn("all_articles", payload[0]["scored_story"]["cluster"])

    @patch("src.summarizer.load_dotenv")
    @patch.object(Summarizer, "_build_client")
    @patch("src.summarizer.os.getenv")
    def test_init_requires_openai_api_key(
        self,
        mock_getenv: MagicMock,
        _mock_build_client: MagicMock,
        _mock_load_dotenv: MagicMock,
    ) -> None:
        mock_getenv.return_value = None
        with self.assertRaisesRegex(
            ValueError, "OPENAI_API_KEY is required for summarization."
        ):
            Summarizer()

    @patch("src.summarizer.load_dotenv")
    @patch.object(Summarizer, "_build_client")
    @patch("src.summarizer.os.getenv")
    def test_init_normalizes_compact_scored_story_payload(
        self,
        mock_getenv: MagicMock,
        mock_build_client: MagicMock,
        _mock_load_dotenv: MagicMock,
    ) -> None:
        mock_getenv.return_value = "test-key"
        mock_build_client.return_value = MagicMock()
        payload = [
            {
                "cluster": {
                    "cluster_id": "cluster_001",
                    "primary_article": {
                        "title": "Compact Story",
                        "url": "https://example.com/story",
                        "source_name": "Example Source",
                        "source_type": "rss",
                        "published_date": "2026-04-21T00:00:00+00:00",
                        "text": "Z" * 200,
                        "text_completeness": "full",
                        "fetch_method": "feedparser",
                    },
                    "coverage_count": 1,
                    "sources_involved": ["Example Source"],
                },
                "scores": {
                    "ai_relevance": 0.9,
                    "impact": 0.8,
                    "audience_relevance": 0.7,
                    "novelty": 0.6,
                    "source_quality": 0.8,
                    "buzz_momentum": 0.5,
                },
                "composite_score": 0.77,
                "rationale": "Example rationale.",
                "section": "industry",
                "tier": "body",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scored_stories.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            summarizer = Summarizer(input_path=str(input_path))

        self.assertEqual(len(summarizer.scored_stories), 1)
        self.assertEqual(
            len(summarizer.scored_stories[0].cluster.all_articles),
            1,
        )
        self.assertEqual(
            summarizer.output_path.name,
            "summarized_stories_openai_gpt_5_4.json",
        )

    @patch("src.summarizer.load_dotenv")
    @patch.object(Summarizer, "_build_client")
    @patch("src.summarizer.os.getenv")
    def test_init_requires_anthropic_api_key_for_sonnet(
        self,
        mock_getenv: MagicMock,
        _mock_build_client: MagicMock,
        _mock_load_dotenv: MagicMock,
    ) -> None:
        mock_getenv.return_value = None
        with self.assertRaisesRegex(
            ValueError, "ANTHROPIC_API_KEY is required for summarization."
        ):
            Summarizer(model="sonnet-4.6")

    @patch("src.summarizer.load_dotenv")
    @patch.object(Summarizer, "_build_client")
    @patch("src.summarizer.os.getenv")
    def test_init_labels_sonnet_output_file(
        self,
        mock_getenv: MagicMock,
        mock_build_client: MagicMock,
        _mock_load_dotenv: MagicMock,
    ) -> None:
        mock_getenv.return_value = "test-key"
        mock_build_client.return_value = MagicMock()
        payload = []

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scored_stories.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            summarizer = Summarizer(input_path=str(input_path), model="sonnet-4.6")

        self.assertEqual(summarizer.provider, "anthropic")
        self.assertEqual(summarizer.api_model, "claude-sonnet-4-20250514")
        self.assertEqual(
            summarizer.output_path.name,
            "summarized_stories_anthropic_sonnet_4_6.json",
        )


if __name__ == "__main__":
    unittest.main()
