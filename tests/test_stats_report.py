from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.models import Article, ScoredStory, StoryCluster, SummarizedStory
from src.stats_report import (
    DEFAULT_REPORT_PATH,
    append_stage_report,
    format_count_line,
    format_headline_selection,
    format_manual_review_summary,
    format_selected_stories_by_section,
)


class TestPipelineReporting(unittest.TestCase):
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

    def test_format_count_line(self) -> None:
        self.assertEqual(
            format_count_line("Total Number of articles scanned", 42),
            "Total Number of articles scanned: 42",
        )

    def test_format_selected_stories_by_section_groups_titles(self) -> None:
        stories = [
            self._scored_story("OpenAI policy shift", "policy", 0.96),
            self._scored_story("Courtroom AI filing", "legal_intelligence", 0.95),
            self._scored_story("Campus AI rollout", "policy", 0.94),
        ]

        self.assertEqual(
            format_selected_stories_by_section(stories),
            "\n".join(
                [
                    "Top 30 articles selected:",
                    "Policy:",
                    "- OpenAI policy shift",
                    "- Campus AI rollout",
                    "Legal Intelligence:",
                    "- Courtroom AI filing",
                ]
            ),
        )

    def test_format_manual_review_summary_lists_titles_or_none(self) -> None:
        kept_story = SummarizedStory(
            scored_story=self._scored_story("Clear summary", "industry", 0.9),
            summary="Looks good.",
            needs_manual_review=False,
        )
        flagged_story = SummarizedStory(
            scored_story=self._scored_story("Needs editor eyes", "industry", 0.8),
            summary="Manual review required.",
            needs_manual_review=True,
        )

        self.assertEqual(
            format_manual_review_summary([kept_story, flagged_story]),
            "Manual review required:\n- Needs editor eyes",
        )
        self.assertEqual(
            format_manual_review_summary([kept_story]),
            "Manual review required: None",
        )

    def test_format_headline_selection_uses_final_title_and_image_path(self) -> None:
        headlines = [
            {
                "title": "Short rewritten title",
                "blurb": "A concise teaser.",
                "image_path": "assets/generated/headline_1.png",
            },
            {
                "title": "Second headline",
                "blurb": "Another teaser.",
                "image_path": None,
            },
            {
                "title": "Third headline",
                "blurb": "Final teaser.",
                "image_path": "assets/generated/headline_3.png",
            },
        ]

        self.assertEqual(
            format_headline_selection(headlines),
            "\n".join(
                [
                    "3 selected headline articles:",
                    "1. Short rewritten title",
                    "Blurb: A concise teaser.",
                    "Headline image generated: assets/generated/headline_1.png",
                    "2. Second headline",
                    "Blurb: Another teaser.",
                    "Headline image generated: None",
                    "3. Third headline",
                    "Blurb: Final teaser.",
                    "Headline image generated: assets/generated/headline_3.png",
                ]
            ),
        )

    def test_append_stage_report_creates_default_txt_path(self) -> None:
        self.assertEqual(
            str(DEFAULT_REPORT_PATH),
            "data/output/stats_report.txt",
        )

    def test_append_stage_report_resets_then_appends(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "stats_report.txt"

            first_path = append_stage_report(
                "run_stage1.py",
                "Total Number of articles scanned: 42",
                reset=True,
                output_path=report_path,
            )
            second_path = append_stage_report(
                "run_ai_relevance_checker.py",
                "Total Number of high AI relevant articles found: 12",
                output_path=report_path,
            )

            self.assertEqual(first_path, report_path)
            self.assertEqual(second_path, report_path)
            self.assertEqual(
                report_path.read_text(encoding="utf-8"),
                "\n".join(
                    [
                        "AI Newsletter Pipeline Report",
                        "=============================",
                        "",
                        "[run_stage1.py]",
                        "Total Number of articles scanned: 42",
                        "",
                        "[run_ai_relevance_checker.py]",
                        "Total Number of high AI relevant articles found: 12",
                        "",
                        "",
                    ]
                ),
            )


if __name__ == "__main__":
    unittest.main()
