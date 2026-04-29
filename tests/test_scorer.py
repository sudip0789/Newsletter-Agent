import json
import tempfile
import unittest
from pathlib import Path

from src.models import Article, ScoredStory, StoryCluster
from src.scorer import Scorer


class TestScorer(unittest.TestCase):
    def _make_story(self, cluster_id: str, section: str, score: float) -> ScoredStory:
        article = Article(
            title=f"Story {cluster_id}",
            url=f"https://example.com/{cluster_id}",
            source_name="Example Source",
            source_type="rss",
            published_date=None,
            text="Example article text",
            text_completeness="full",
            fetch_method="feedparser",
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
            section=section,
            tier="body",
        )

    def _make_scorer(self) -> Scorer:
        scorer = Scorer.__new__(Scorer)
        scorer.weights = {
            "ai_relevance": 0.25,
            "impact": 0.30,
            "audience_relevance": 0.15,
            "novelty": 0.15,
            "source_quality": 0.10,
            "buzz_momentum": 0.05,
        }
        scorer.selection_total = 6
        scorer.output_path = Path("/tmp/scored_stories_test.json")
        scorer.all_scored_stories = []
        scorer.selected_stories = []
        scorer.failed_clusters = []
        scorer.clusters = []
        return scorer

    def test_compute_composite_uses_rubric_weights(self) -> None:
        scorer = self._make_scorer()
        composite = scorer.compute_composite(
            {
                "ai_relevance": 1.0,
                "impact": 1.0,
                "audience_relevance": 0.5,
                "novelty": 0.0,
                "source_quality": 1.0,
                "buzz_momentum": 0.5,
            }
        )

        self.assertAlmostEqual(composite, 0.75)

    def test_select_top_30_enforces_five_per_section(self) -> None:
        scorer = self._make_scorer()
        stories = [
            self._make_story(f"industry_{idx}", "industry", 0.95 - idx * 0.01)
            for idx in range(7)
        ] + [
            self._make_story("policy_1", "policy", 0.88),
            self._make_story("security_1", "security", 0.87),
        ]

        selected = scorer.select_top_30(stories)

        self.assertEqual(len(selected), 6)
        self.assertEqual(sum(1 for story in selected if story.section == "industry"), 5)
        self.assertEqual(selected[-1].section, "policy")

    def test_assign_tiers_sets_headline_body_and_honorable(self) -> None:
        scorer = self._make_scorer()
        stories = [
            self._make_story(f"story_{idx}", "industry", 0.99 - idx * 0.01)
            for idx in range(30)
        ]

        scorer._assign_tiers(stories)  # pylint: disable=protected-access

        self.assertEqual([story.tier for story in stories[:5]], ["headline"] * 5)
        self.assertEqual(stories[5].tier, "body")
        self.assertEqual([story.tier for story in stories[-5:]], ["honorable_mention"] * 5)

    def test_save_results_writes_utf8_json(self) -> None:
        scorer = self._make_scorer()
        story = self._make_story("utf8", "creative_ai", 0.91)
        story.rationale = "Résumé-worthy story."

        with tempfile.TemporaryDirectory() as tmpdir:
            scorer.output_path = Path(tmpdir) / "scored_stories.json"
            scorer.save_results([story])
            payload = json.loads(scorer.output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload[0]["rationale"], "Résumé-worthy story.")
        self.assertNotIn("all_articles", payload[0]["cluster"])
        self.assertEqual(payload[0]["cluster"]["cluster_id"], "utf8")
        self.assertEqual(payload[0]["scores"]["ai_relevance"], 0.91)

    def test_normalize_section_defaults_invalid_values(self) -> None:
        scorer = self._make_scorer()
        normalized = scorer._normalize_section("unknown_section", "Test story")  # pylint: disable=protected-access
        self.assertEqual(normalized, "industry")

    def test_coerce_score_clamps_out_of_range_values(self) -> None:
        scorer = self._make_scorer()
        self.assertEqual(scorer._coerce_score(1.5), 1.0)  # pylint: disable=protected-access
        self.assertEqual(scorer._coerce_score(-0.3), 0.0)  # pylint: disable=protected-access


if __name__ == "__main__":
    unittest.main()
