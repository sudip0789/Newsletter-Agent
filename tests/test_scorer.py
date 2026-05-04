import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_select_top_25_enforces_six_per_section(self) -> None:
        scorer = self._make_scorer()
        stories = [
            self._make_story(f"industry_{idx}", "industry", 0.95 - idx * 0.01)
            for idx in range(7)
        ] + [
            self._make_story("policy_1", "policy", 0.88),
            self._make_story("security_1", "security", 0.87),
        ]

        selected = scorer.select_top_25(stories)

        self.assertEqual(len(selected), 6)
        self.assertEqual(sum(1 for story in selected if story.section == "industry"), 6)
        self.assertEqual(selected[-1].section, "industry")

    def test_select_top_25_skips_low_buzz_special_sections_when_enough_stories_exist(
        self,
    ) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 25
        stories = [
            self._make_story("creative_low", "creative_ai", 0.95),
            self._make_story("tools_low", "tools_and_products", 0.94),
            self._make_story("higher_ed_low", "higher_education", 0.93),
        ]
        stories[0].scores["buzz_momentum"] = 0.29
        stories[1].scores["buzz_momentum"] = 0.29
        stories[2].scores["buzz_momentum"] = 0.29
        qualifying_sections = [
            "industry",
            "policy",
            "security",
            "research",
            "creative_ai",
            "tools_and_products",
            "higher_education",
        ]
        for idx in range(21):
            section = qualifying_sections[idx % len(qualifying_sections)]
            story = self._make_story(
                f"qualifying_{idx}",
                section,
                0.92 - idx * 0.01,
            )
            story.scores["buzz_momentum"] = 0.75 if section not in {
                "creative_ai",
                "tools_and_products",
                "higher_education",
            } else 0.30
            stories.append(story)

        selected = scorer.select_top_25(stories)

        self.assertEqual(len(selected), 21)
        self.assertNotIn("creative_low", [story.cluster.cluster_id for story in selected])
        self.assertNotIn("tools_low", [story.cluster.cluster_id for story in selected])
        self.assertNotIn("higher_ed_low", [story.cluster.cluster_id for story in selected])

    def test_select_top_25_skips_low_buzz_other_sections_when_enough_stories_exist(
        self,
    ) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 25
        stories = [
            self._make_story("industry_low", "industry", 0.96),
            self._make_story("policy_low", "policy", 0.95),
        ]
        stories[0].scores["buzz_momentum"] = 0.39
        stories[1].scores["buzz_momentum"] = 0.39
        qualifying_sections = [
            "creative_ai",
            "tools_and_products",
            "higher_education",
            "security",
            "research",
            "industry",
            "policy",
        ]
        for idx in range(21):
            section = qualifying_sections[idx % len(qualifying_sections)]
            story = self._make_story(
                f"qualifying_{idx}",
                section,
                0.94 - idx * 0.01,
            )
            story.scores["buzz_momentum"] = 0.30 if section in {
                "creative_ai",
                "tools_and_products",
                "higher_education",
            } else 0.70
            stories.append(story)

        selected = scorer.select_top_25(stories)

        self.assertEqual(len(selected), 21)
        self.assertNotIn("industry_low", [story.cluster.cluster_id for story in selected])
        self.assertNotIn("policy_low", [story.cluster.cluster_id for story in selected])

    def test_select_top_25_includes_boundary_buzz_scores(self) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 4
        stories = [
            self._make_story("creative_boundary", "creative_ai", 0.96),
            self._make_story("tools_boundary", "tools_and_products", 0.95),
            self._make_story("industry_boundary", "industry", 0.94),
            self._make_story("policy_boundary", "policy", 0.93),
        ]
        stories[0].scores["buzz_momentum"] = 0.30
        stories[1].scores["buzz_momentum"] = 0.30
        stories[2].scores["buzz_momentum"] = 0.40
        stories[3].scores["buzz_momentum"] = 0.40

        selected = scorer.select_top_25(stories)

        self.assertEqual(
            [story.cluster.cluster_id for story in selected],
            [
                "creative_boundary",
                "tools_boundary",
                "industry_boundary",
                "policy_boundary",
            ],
        )

    def test_select_top_25_disables_buzz_filter_when_fewer_than_twenty_pass(self) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 25
        passing_sections = ["industry", "policy", "security"]
        failing_sections = ["research", "legal_intelligence"]
        passing: list[ScoredStory] = []
        failing: list[ScoredStory] = []
        for idx in range(12):
            section = passing_sections[idx % len(passing_sections)]
            story = self._make_story(f"pass_{idx}", section, 1.0 - idx * 0.01)
            story.scores["buzz_momentum"] = 0.6
            passing.append(story)
        for idx in range(10):
            section = failing_sections[idx % len(failing_sections)]
            story = self._make_story(f"low_{idx}", section, 0.80 - idx * 0.01)
            story.scores["buzz_momentum"] = 0.39
            failing.append(story)

        selected = scorer.select_top_25(passing + failing)

        self.assertEqual(len(selected), 22)
        self.assertEqual(
            [story.cluster.cluster_id for story in selected[:5]],
            ["pass_0", "pass_1", "pass_2", "pass_3", "pass_4"],
        )
        self.assertIn("low_0", [story.cluster.cluster_id for story in selected])

    def test_select_top_25_keeps_section_caps_after_buzz_fallback(self) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 25
        industry = [
            self._make_story(f"industry_{idx}", "industry", 1.0 - idx * 0.01)
            for idx in range(10)
        ]
        policy = [
            self._make_story(f"policy_{idx}", "policy", 0.85 - idx * 0.01)
            for idx in range(10)
        ]
        security = [
            self._make_story(f"security_{idx}", "security", 0.70 - idx * 0.01)
            for idx in range(2)
        ]
        for story in industry[:6]:
            story.scores["buzz_momentum"] = 0.7
        for story in industry[6:]:
            story.scores["buzz_momentum"] = 0.39
        for story in policy:
            story.scores["buzz_momentum"] = 0.39
        for story in security:
            story.scores["buzz_momentum"] = 0.39

        selected = scorer.select_top_25(industry + policy + security)

        self.assertEqual(len(selected), 14)
        self.assertEqual(sum(1 for story in selected if story.section == "industry"), 6)
        self.assertEqual(sum(1 for story in selected if story.section == "policy"), 6)
        self.assertEqual(sum(1 for story in selected if story.section == "security"), 2)

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

    @patch.object(Scorer, "save_results")
    @patch.object(Scorer, "print_summary")
    @patch.object(Scorer, "_assign_tiers")
    @patch.object(Scorer, "select_top_25")
    @patch("src.scorer.ThreadPoolExecutor")
    def test_run_scores_clusters_with_max_workers_and_continues_after_failures(
        self,
        mock_executor: unittest.mock.MagicMock,
        mock_select_top: unittest.mock.MagicMock,
        mock_assign_tiers: unittest.mock.MagicMock,
        mock_print_summary: unittest.mock.MagicMock,
        mock_save_results: unittest.mock.MagicMock,
    ) -> None:
        scorer = self._make_scorer()
        scorer.selection_total = 10
        scorer.clusters = [
            self._make_story("cluster_1", "industry", 0.91).cluster,
            self._make_story("cluster_2", "policy", 0.73).cluster,
            self._make_story("cluster_3", "security", 0.84).cluster,
        ]

        selected_stories: list[ScoredStory] = []

        class FakeExecutor:
            def __init__(self, max_workers: int):
                self.max_workers = max_workers

            def __enter__(self) -> "FakeExecutor":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def map(self, func, items):
                return [func(item) for item in items]

        mock_executor.side_effect = FakeExecutor

        def fake_score_story(cluster: StoryCluster) -> ScoredStory:
            if cluster.cluster_id == "cluster_2":
                raise RuntimeError("boom")
            score = 0.91 if cluster.cluster_id == "cluster_1" else 0.84
            return self._make_story(cluster.cluster_id, "industry", score)

        def fake_select_top(stories: list[ScoredStory]) -> list[ScoredStory]:
            selected_stories.extend(stories)
            return stories

        scorer.score_story = fake_score_story  # type: ignore[method-assign]
        mock_select_top.side_effect = fake_select_top

        result = scorer.run()

        self.assertEqual(scorer.MAX_WORKERS, 6)
        mock_executor.assert_called_once_with(max_workers=6)
        self.assertEqual(
            [story.cluster.cluster_id for story in selected_stories],
            ["cluster_1", "cluster_3"],
        )
        self.assertEqual(
            [story.cluster.cluster_id for story in result],
            ["cluster_1", "cluster_3"],
        )
        self.assertEqual(scorer.failed_clusters, ["Story cluster_2"])
        mock_assign_tiers.assert_called_once()
        mock_print_summary.assert_called_once()
        mock_save_results.assert_called_once()


if __name__ == "__main__":
    unittest.main()
