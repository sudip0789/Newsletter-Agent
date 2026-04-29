import unittest
from pathlib import Path

from src.stage1_ingest import SourceIngestion


class TestStage1CompletenessScoring(unittest.TestCase):
    def setUp(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        config_path = project_root / "config" / "sources.yaml"
        self.ingestor = SourceIngestion(config_path=str(config_path))

    def test_short_well_formed_article_can_be_full(self) -> None:
        text = (
            "Open-source maintainers published a concise release note. "
            "The update includes security fixes and migration guidance. "
            "Teams should update dependencies this week. "
            "The patch improves latency and removes deprecated flags. "
            "No breaking API changes were reported."
        )
        score = self.ingestor._score_text_completeness(  # pylint: disable=protected-access
            text,
            title="Maintainers publish release note with migration guidance",
            source_mode="article_tag",
            prior_text_len=0,
        )

        self.assertGreaterEqual(score["score"], 70)
        self.assertEqual(
            self.ingestor._label_from_score(  # pylint: disable=protected-access
                score["score"], score["strong_truncation"]
            ),
            "full",
        )

    def test_long_truncated_text_is_not_full(self) -> None:
        text = (
            "This investigative report covers financial disclosures and regulatory "
            "responses across multiple agencies. "
            * 30
        ) + "Read more..."
        score = self.ingestor._score_text_completeness(  # pylint: disable=protected-access
            text,
            title="Investigative report on regulatory disclosures",
            source_mode="summary",
            prior_text_len=0,
        )

        self.assertTrue(score["strong_truncation"])
        self.assertNotEqual(
            self.ingestor._label_from_score(  # pylint: disable=protected-access
                score["score"], score["strong_truncation"]
            ),
            "full",
        )

    def test_growth_bonus_improves_fulltext_confidence(self) -> None:
        prior = "Short teaser text for the story."
        extracted = (
            "The full article provides context, quotes, and timeline details. " * 20
        ).strip()
        score = self.ingestor._score_text_completeness(  # pylint: disable=protected-access
            extracted,
            title="Full timeline and quotes from the investigation",
            source_mode="article_tag",
            prior_text_len=len(prior),
        )

        self.assertGreaterEqual(score["signals"]["growth_bonus"], 10)
        self.assertGreaterEqual(score["score"], 70)


if __name__ == "__main__":
    unittest.main()
