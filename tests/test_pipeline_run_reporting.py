from __future__ import annotations

import io
import sys
import types
import unittest
from datetime import datetime, timezone
from importlib import import_module
from unittest.mock import MagicMock, patch

from src.models import Article, ScoredStory, StoryCluster, SummarizedStory


class TestPipelineRunReporting(unittest.TestCase):
    def _article(self, title: str) -> Article:
        return Article(
            title=title,
            url=f"https://example.com/{title.replace(' ', '-').lower()}",
            source_name="Example Source",
            source_type="rss",
            published_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
            text="Example article text",
            text_completeness="full",
            fetch_method="feedparser",
        )

    def _scored_story(self, title: str, section: str, score: float) -> ScoredStory:
        article = self._article(title)
        cluster = StoryCluster(
            cluster_id=title.replace(" ", "_").lower(),
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
            section=section,
            tier="body",
        )

    def test_run_stage1_prints_document_count(
        self,
    ) -> None:
        ingestion_cls = MagicMock()
        ingestion = ingestion_cls.return_value
        ingestion.run.return_value = [object(), object(), object()]
        fake_stage1_ingest = types.SimpleNamespace(SourceIngestion=ingestion_cls)
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        sys.modules.pop("scripts.run_stage1", None)
        with patch.dict(sys.modules, {"src.stage1_ingest": fake_stage1_ingest}):
            run_stage1 = import_module("scripts.run_stage1")
            with patch.object(run_stage1, "setup_logging"):
                with patch.object(run_stage1, "append_stage_report", return_value=report_path) as mock_append:
                    with patch.object(sys, "argv", ["run_stage1.py"]):
                        with patch("sys.stdout", stdout):
                            run_stage1.main()

        self.assertIn("Total Number of articles scanned: 3", stdout.getvalue())
        self.assertIn(f"Stats report updated: {report_path}", stdout.getvalue())
        mock_append.assert_called_once_with(
            "run_stage1.py",
            "Total Number of articles scanned: 3",
            reset=True,
        )

    def test_run_ai_relevance_checker_prints_document_count(
        self,
    ) -> None:
        from scripts.run_ai_relevance_checker import main

        mock_checker_cls = MagicMock()
        checker = mock_checker_cls.return_value
        checker.run.return_value = ([object(), object()], [object()])
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        with patch("scripts.run_ai_relevance_checker.AIRelevanceChecker", mock_checker_cls):
            with patch("scripts.run_ai_relevance_checker.append_stage_report", return_value=report_path) as mock_append:
                with patch.object(sys, "argv", ["run_ai_relevance_checker.py"]):
                    with patch("sys.stdout", stdout):
                        main()

        self.assertIn(
            "Total Number of high AI relevant articles found: 2",
            stdout.getvalue(),
        )
        self.assertIn(f"Stats report updated: {report_path}", stdout.getvalue())
        mock_append.assert_called_once_with(
            "run_ai_relevance_checker.py",
            "Total Number of high AI relevant articles found: 2",
        )

    def test_run_dedup_prints_unique_article_count(
        self,
    ) -> None:
        mock_dedup_cls = MagicMock()
        dedup = mock_dedup_cls.return_value
        dedup.run.return_value = [object(), object(), object(), object()]
        fake_dedup_cluster = types.SimpleNamespace(Deduplicator=mock_dedup_cls)
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        sys.modules.pop("scripts.run_dedup", None)
        with patch.dict(sys.modules, {"src.dedup_cluster": fake_dedup_cluster}):
            run_dedup = import_module("scripts.run_dedup")
            with patch.object(run_dedup, "append_stage_report", return_value=report_path) as mock_append:
                with patch.object(sys, "argv", ["run_dedup.py"]):
                    with patch("sys.stdout", stdout):
                        run_dedup.main()

        self.assertIn("Total Unique articles found: 4", stdout.getvalue())
        self.assertIn(f"Stats report updated: {report_path}", stdout.getvalue())
        mock_append.assert_called_once_with(
            "run_dedup.py",
            "Total Unique articles found: 4",
        )

    @patch("scripts.run_scorer.setup_logging")
    @patch("scripts.run_scorer.Scorer")
    def test_run_scorer_prints_grouped_selection_summary(
        self,
        mock_scorer_cls: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        from scripts.run_scorer import main

        scorer = mock_scorer_cls.return_value
        scorer.run.return_value = [
            self._scored_story("Policy story", "policy", 0.95),
            self._scored_story("Legal story", "legal_intelligence", 0.94),
        ]
        scorer.all_scored_stories = []
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        with patch("scripts.run_scorer.append_stage_report", return_value=report_path) as mock_append:
            with patch.object(sys, "argv", ["run_scorer.py"]):
                with patch("sys.stdout", stdout):
                    main()

        output = stdout.getvalue()
        self.assertIn("Top 30 articles selected:", output)
        self.assertIn("Policy:", output)
        self.assertIn("- Policy story", output)
        self.assertIn("Legal Intelligence:", output)
        self.assertIn(f"Stats report updated: {report_path}", output)
        mock_append.assert_called_once()

    @patch("scripts.run_summarizer.setup_logging")
    @patch("scripts.run_summarizer.Summarizer")
    def test_run_summarizer_prints_manual_review_titles(
        self,
        mock_summarizer_cls: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        from scripts.run_summarizer import main

        summarizer = mock_summarizer_cls.return_value
        summarizer.run.return_value = [
            SummarizedStory(
                scored_story=self._scored_story("Reviewed story", "enterprise_ai", 0.9),
                newsletter_title="Reviewed newsletter title",
                summary="Looks good.",
                needs_manual_review=False,
            ),
            SummarizedStory(
                scored_story=self._scored_story("Needs review", "policy", 0.8),
                newsletter_title="Needs review",
                summary="Manual review required.",
                needs_manual_review=True,
            ),
        ]
        summarizer.output_path = "data/output/summarized_stories.json"
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        with patch("scripts.run_summarizer.append_stage_report", return_value=report_path) as mock_append:
            with patch.object(sys, "argv", ["run_summarizer.py"]):
                with patch("sys.stdout", stdout):
                    main()

        output = stdout.getvalue()
        self.assertIn("Manual review required:", output)
        self.assertIn("- Needs review", output)
        self.assertIn(f"Stats report updated: {report_path}", output)
        mock_append.assert_called_once()

    @patch("scripts.run_headline_agent.setup_logging")
    @patch("scripts.run_headline_agent.time.sleep")
    @patch("scripts.run_headline_agent.HeadlineAgent")
    def test_run_headline_agent_prints_selected_headlines(
        self,
        mock_agent_cls: MagicMock,
        _mock_sleep: MagicMock,
        _mock_setup_logging: MagicMock,
    ) -> None:
        from scripts.run_headline_agent import main

        agent = mock_agent_cls.return_value
        agent.run.return_value = [
            {
                "title": "Short rewritten title",
                "summary": "Summary 1",
                "blurb": "Blurb 1",
                "source_name": "TechCrunch",
            },
            {
                "title": "Second headline",
                "summary": "Summary 2",
                "blurb": "Blurb 2",
                "source_name": "Reuters",
            },
            {
                "title": "Third headline",
                "summary": "Summary 3",
                "blurb": "Blurb 3",
                "source_name": "Bloomberg",
            },
        ]
        agent.generate_headline_image.side_effect = [
            "assets/generated/headline_1.png",
            None,
            "assets/generated/headline_3.png",
        ]
        stdout = io.StringIO()
        report_path = "data/output/stats_report.txt"

        with patch("scripts.run_headline_agent.append_stage_report", return_value=report_path) as mock_append:
            with patch.object(sys, "argv", ["run_headline_agent.py"]):
                with patch("sys.stdout", stdout):
                    main()

        output = stdout.getvalue()
        self.assertIn("3 selected headline articles:", output)
        self.assertIn("1. Short rewritten title", output)
        self.assertIn("Publisher: TechCrunch", output)
        self.assertIn("Blurb: Blurb 1", output)
        self.assertIn(
            "Headline image generated: assets/generated/headline_1.png",
            output,
        )
        self.assertIn(f"Stats report updated: {report_path}", output)
        mock_append.assert_called_once()


if __name__ == "__main__":
    unittest.main()
