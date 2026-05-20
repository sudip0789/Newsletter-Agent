import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.models import Article, ScoredStory, StoryCluster, SummarizedStory
from src.title_rewriter import TitleRewriter


class TestTitleRewriter(unittest.TestCase):
    def _article(self, title: str, text: str = "A" * 200) -> Article:
        return Article(
            title=title,
            url=f"https://example.com/{title.replace(' ', '-').lower()}",
            source_name="Example Source",
            source_type="rss",
            published_date=datetime(2026, 4, 21, tzinfo=timezone.utc),
            text=text,
            text_completeness="full",
            fetch_method="feedparser",
        )

    def _summarized_story(self, cluster_id: str, title: str) -> SummarizedStory:
        article = self._article(title=title)
        cluster = StoryCluster(
            cluster_id=cluster_id,
            primary_article=article,
            all_articles=[article],
            coverage_count=1,
            sources_involved=[article.source_name],
        )
        scored_story = ScoredStory(
            cluster=cluster,
            scores={
                "ai_relevance": 0.9,
                "impact": 0.8,
                "audience_relevance": 0.7,
                "novelty": 0.6,
                "source_quality": 0.8,
                "buzz_momentum": 0.5,
            },
            composite_score=0.77,
            rationale="Example rationale.",
            section="enterprise_ai",
            tier="body",
        )
        return SummarizedStory(
            scored_story=scored_story,
            summary=f"Summary for {cluster_id}",
            needs_manual_review=False,
        )

    def _make_rewriter(
        self,
        stories: list[SummarizedStory],
        *,
        top_n: int = 30,
    ) -> TitleRewriter:
        rewriter = TitleRewriter.__new__(TitleRewriter)
        rewriter.input_path = Path("/tmp/summarized_stories.json")
        rewriter.output_path = rewriter.input_path
        rewriter.top_n = top_n
        rewriter.model_name = "sonnet-4.6"
        rewriter.model_config = TitleRewriter.MODEL_CONFIGS["sonnet-4.6"]
        rewriter.provider = "anthropic"
        rewriter.api_model = "claude-sonnet-4-20250514"
        rewriter.summarized_stories = stories
        rewriter.client = MagicMock()
        return rewriter

    def test_run_rewrites_titles_for_top_n_and_keeps_rest(self) -> None:
        stories = [
            self._summarized_story("one", "Original title one"),
            self._summarized_story("two", "Original title two"),
            self._summarized_story("three", "Original title three"),
        ]
        rewriter = self._make_rewriter(stories, top_n=2)
        rewriter.rewrite_title = MagicMock(
            side_effect=[
                "Rewritten headline for story one",
                "Rewritten headline for story two",
            ]
        )

        results = rewriter.run()

        self.assertEqual(results[0].newsletter_title, "Rewritten headline for story one")
        self.assertEqual(results[1].newsletter_title, "Rewritten headline for story two")
        self.assertEqual(results[2].newsletter_title, "")
        self.assertEqual(
            [story.scored_story.cluster.primary_article.title for story in results],
            ["Original title one", "Original title two", "Original title three"],
        )

    def test_rewrite_title_uses_anthropic_text_response(self) -> None:
        story = self._summarized_story(
            "anthropic",
            "Original title for anthropic rewrite",
        )
        rewriter = self._make_rewriter([story])
        rewriter.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="Fresh legal AI title update")]
        )

        rewritten = rewriter.rewrite_title(story)

        self.assertEqual(rewritten, "Fresh legal AI title update")
        call_kwargs = rewriter.client.messages.create.call_args.kwargs
        user_message = call_kwargs["messages"][0]["content"]
        self.assertIn("Summary:\nSummary for anthropic", user_message)
        self.assertNotIn("Article text:", user_message)

    def test_rewrite_title_unescapes_html_entities(self) -> None:
        story = self._summarized_story("encoded", "Original encoded title")
        rewriter = self._make_rewriter([story])
        rewriter.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="China&#39;s legal AI keeps growing")]
        )

        rewritten = rewriter.rewrite_title(story)

        self.assertEqual(rewritten, "China's legal AI keeps growing")

    def test_rewrite_title_retries_when_first_output_is_verbatim(self) -> None:
        primary = (
            "Hackers Used AI to Develop First Known Zero-Day 2FA Bypass "
            "for Mass Exploitation"
        )
        story = self._summarized_story("verbatim_retry", primary)
        rewriter = self._make_rewriter([story])
        second_headline = (
            "Researchers Report AI Built Novel Zero-Day Exploiting "
            "Two-Factor Authentication at Scale"
        )
        rewriter.client.messages.create.side_effect = [
            MagicMock(content=[MagicMock(type="text", text=primary)]),
            MagicMock(content=[MagicMock(type="text", text=second_headline)]),
        ]

        rewritten = rewriter.rewrite_title(story)

        self.assertEqual(rewritten, second_headline)
        self.assertEqual(rewriter.client.messages.create.call_count, 2)

    def test_run_falls_back_to_original_title_when_rewrite_is_invalid(self) -> None:
        story = self._summarized_story("fallback", "Original fallback title")
        rewriter = self._make_rewriter([story])
        rewriter.client.messages.create.return_value = MagicMock(
            content=[MagicMock(type="text", text="Too short")]
        )

        results = rewriter.run()

        self.assertEqual(results[0].newsletter_title, "Original fallback title")

    def test_save_results_updates_same_output_file_with_newsletter_title(self) -> None:
        story = self._summarized_story("save", "Original save title")
        story.newsletter_title = "Saved rewritten newsletter title"
        rewriter = self._make_rewriter([story])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "summarized_stories.json"
            rewriter.input_path = output_path
            rewriter.output_path = output_path
            rewriter.save_results([story])
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload[0]["newsletter_title"], "Saved rewritten newsletter title")
        self.assertEqual(payload[0]["summary"], "Summary for save")
        self.assertEqual(payload[0]["needs_manual_review"], False)
        self.assertNotIn("text", payload[0]["scored_story"]["cluster"]["primary_article"])

    @patch("src.title_rewriter.load_dotenv")
    @patch.object(TitleRewriter, "_build_client")
    @patch("src.title_rewriter.os.getenv")
    def test_init_uses_same_input_file_for_output(
        self,
        mock_getenv: MagicMock,
        mock_build_client: MagicMock,
        _mock_load_dotenv: MagicMock,
    ) -> None:
        mock_getenv.return_value = "test-key"
        mock_build_client.return_value = MagicMock()
        payload = [
            {
                "scored_story": {
                    "cluster": {
                        "cluster_id": "cluster_001",
                        "primary_article": {
                            "title": "Compact Story",
                            "url": "https://example.com/story",
                            "source_name": "Example Source",
                            "source_type": "rss",
                            "published_date": "2026-04-21T00:00:00+00:00",
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
                    "section": "enterprise_ai",
                    "tier": "body",
                },
                "summary": "Existing summary",
                "needs_manual_review": False,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "summarized_stories.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            rewriter = TitleRewriter(input_path=str(input_path), model="sonnet-4.6")

        self.assertEqual(rewriter.output_path, input_path)
        self.assertEqual(len(rewriter.summarized_stories), 1)
        self.assertEqual(
            rewriter.summarized_stories[0].scored_story.cluster.primary_article.text,
            "",
        )


if __name__ == "__main__":
    unittest.main()
