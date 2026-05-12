from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.models import ScoredStory, StoryCluster
from src.utils import load_yaml_config

LOGGER = logging.getLogger(__name__)

SCORING_SYSTEM_PROMPT = """You are an editorial assistant for "The AI Upload Weekly Digest," a newsletter published by Stanford Law School's Robert Crown Law Library.

Your job is to score articles for inclusion in the newsletter. Be STRICT. The newsletter only covers AI and AI-related topics. Not general tech, not general business, not general cybersecurity.

Your audience is: law students, faculty, legal professionals, and higher education staff who follow AI developments — with particular interest in legal AI, AI policy, AI in universities, AI in Libraries, AI in higher education, security implications, and major AI industry shifts.

Score the following article on these dimensions (0.0 to 1.0):

- ai_relevance (0.0 to 1.0): IS THIS ARTICLE ACTUALLY ABOUT AI? This is the most important score. If the article is not primarily about AI, artificial intelligence, machine learning, or AI-related tools/policy/companies, score this 0.0. An article about a person associated with AI is 0.0 if the story itself isn't about AI (e.g. personal news, non-AI business ventures). Score 0.5-0.7 if AI is mentioned but isn't the central focus. Score 0.8-1.0 only if AI is the core subject.

- impact (0.0 to 1.0): How significant is this story within the AI space? A record funding round for an AI company, a major model release, or a landmark AI court case scores high. A minor feature update or a routine hire scores low.

- audience_relevance (0.0 to 1.0): How much does the SPECIFIC Stanford Law audience care? AI + law intersection (court cases, regulation, legal AI tools) = 0.8-1.0. AI + higher education = 0.7-0.9. AI policy and government action = 0.7-0.9. Major AI industry news = 0.5-0.7. Highly technical AI research only accessible to ML engineers = 0.2-0.4. General consumer AI product updates = 0.3-0.5.

- novelty (0.0 to 1.0): Is this genuinely new? A first-time announcement scores high. A follow-up or rehash of known information scores low.

- source_quality (0.0 to 1.0): Is the source credible? Original reporting or official company announcements score high. Aggregator rewrites or speculation score low.

- buzz_momentum (0.0 to 1.0): Is this generating unusual attention across the AI community?

Also assign the article to exactly one newsletter section:
- "legal_intelligence" — AI + law, legal tech, AI regulation, copyright, court cases on AI
- "higher_education" — AI in universities, AI in Libraries, AI in higher education, AI in law schools, academic research on AI, student/faculty AI use
- "security" — security vulnerabilities in AI systems, AI-powered cyber threats, AI safety incidents
- "creative_ai" — AI music, video, image, design tools and platforms
- "industry" — AI company funding, acquisitions, strategy, leadership, partnerships
- "policy" — government AI regulation, executive orders, international AI policy, legislative action
- "impact_on_environment" — AI's environmental footprint, energy use, water use, emissions, sustainability impact, resource consumption
- "ethics_and_bias" — fairness, discrimination, harmful outputs, labor/rights concerns, accountability, ethical AI debates
- "tools_and_products" — new AI tool launches, AI product updates, developer AI tools
- "research" — academic papers, benchmarks, technical breakthroughs, AI index reports

Respond with ONLY a JSON object, no markdown, no explanation:
{
  "ai_relevance": 0.0,
  "impact": 0.0,
  "audience_relevance": 0.0,
  "novelty": 0.0,
  "source_quality": 0.0,
  "buzz_momentum": 0.0,
  "section": "section_name",
  "rationale": "One sentence explaining the scores."
}"""

VALID_SECTIONS = {
    "legal_intelligence",
    "higher_education",
    "security",
    "creative_ai",
    "industry",
    "policy",
    "impact_on_environment",
    "ethics_and_bias",
    "tools_and_products",
    "research",
}

SCORE_FIELDS = (
    "ai_relevance",
    "impact",
    "audience_relevance",
    "novelty",
    "source_quality",
    "buzz_momentum",
)

LOWER_BUZZ_THRESHOLD_SECTIONS = {
    "creative_ai",
    "tools_and_products",
    "higher_education",
}

DEFAULT_SECTION_CAP = 6
SECTION_CAPS = {
    "policy": 4,
    "security": 4,
}
GUARANTEED_SECTIONS = (
    "impact_on_environment",
    "ethics_and_bias",
)


class Scorer:
    MAX_WORKERS = 6

    def __init__(
        self,
        input_path: str = "data/output/clustered_stories.json",
        rubric_path: str = "config/scoring_rubric.yaml",
    ):
        """Load clusters and scoring rubric. Init OpenAI client."""
        load_dotenv()
        self.input_path = Path(input_path)
        self.output_path = self.input_path.parent / "scored_stories.json"
        self.rubric_path = rubric_path
        self.rubric = load_yaml_config(rubric_path)

        raw_clusters = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.clusters = [StoryCluster.model_validate(item) for item in raw_clusters]
        self.weights = self._validate_weights(self.rubric.get("weights", {}))
        self.selection_total = int(self.rubric.get("selection", {}).get("total_top", 30))
        self.model = str(self.rubric.get("model", "gpt-5.4"))
        self.client = OpenAI()

        self.all_scored_stories: list[ScoredStory] = []
        self.selected_stories: list[ScoredStory] = []
        self.failed_clusters: list[str] = []

    def run(self) -> list[ScoredStory]:
        """
        Full pipeline:
        1. Score each cluster via LLM call, using up to 6 worker threads
        2. Compute composite scores using rubric weights
        3. Assign newsletter sections
        4. Select top 30
        Return all 30 sorted by composite score.
        """
        scored: list[ScoredStory] = []
        self.failed_clusters = []

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            for scored_story, failed_title in executor.map(
                self._score_cluster_with_error_handling,
                self.clusters,
            ):
                if scored_story is not None:
                    scored.append(scored_story)
                elif failed_title is not None:
                    self.failed_clusters.append(failed_title)

        self.all_scored_stories = sorted(
            scored,
            key=lambda story: story.composite_score,
            reverse=True,
        )
        self.selected_stories = self.select_top_30(self.all_scored_stories)
        self._assign_tiers(self.selected_stories)
        self.print_summary(self.selected_stories)
        self.save_results(self.selected_stories)
        return self.selected_stories

    def score_story(self, cluster: StoryCluster) -> ScoredStory:
        """
        Single LLM call per cluster.

        Send the primary article's title + text to gpt-5.4.
        Request a JSON response with:
        - ai_relevance: float 0-1 (is this story actually about AI?)
        - impact: float 0-1 (how significant is this story objectively?)
        - audience_relevance: float 0-1 (how much does a Stanford Law audience care?)
        - novelty: float 0-1 (is this genuinely new vs rehashed?)
        - source_quality: float 0-1 (is this from a credible, authoritative source?)
        - buzz_momentum: float 0-1 (is this generating unusual attention?)
        - section: string (which newsletter section it belongs to)
        - rationale: string (one-line explanation of the scores)

        Use response_format={"type": "json_object"} to enforce JSON output.
        Model: gpt-5.4
        """
        article = cluster.primary_article
        prompt = (
            f"Title: {article.title}\n"
            f"Source: {article.source_name}\n"
            f"Coverage: This story was covered by {cluster.coverage_count} outlets: "
            f"{', '.join(cluster.sources_involved)}\n"
            "Article text:\n"
            f"{(article.text or '')[:3000]}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            temperature=0.1,
            messages=[
                {"role": "system", "content": SCORING_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response content from scoring model")

        parsed = json.loads(content)
        scores = {field: self._coerce_score(parsed.get(field)) for field in SCORE_FIELDS}
        section = self._normalize_section(parsed.get("section"), article.title)
        rationale = str(parsed.get("rationale") or "No rationale provided.").strip()
        composite_score = self.compute_composite(scores)

        return ScoredStory(
            cluster=cluster,
            scores=scores,
            composite_score=composite_score,
            rationale=rationale,
            section=section,
            tier="body",
        )

    def _score_cluster_with_error_handling(
        self,
        cluster: StoryCluster,
    ) -> tuple[ScoredStory | None, str | None]:
        try:
            return self.score_story(cluster), None
        except Exception as exc:  # pragma: no cover - defensive against API/runtime issues
            title = cluster.primary_article.title
            LOGGER.warning("Skipping cluster '%s' due to scoring error: %s", title, exc)
            return None, title

    def compute_composite(self, scores: dict[str, float]) -> float:
        """
        Weighted sum using rubric weights:
        composite = (ai_relevance * w1) + (impact * w2) + (audience_relevance * w3) + (novelty * w4)
                    + (source_quality * w5) + (buzz_momentum * w6)
        Normalize to 0-1 range.
        """
        return sum(scores.get(name, 0.0) * self.weights[name] for name in SCORE_FIELDS)

    def select_top_30(self, stories: list[ScoredStory]) -> list[ScoredStory]:
        """
        1. Sort all stories by composite_score descending.
        2. Apply per-section caps, including stricter caps for policy and security.
        3. Apply buzz threshold gating unless fewer than 20 stories qualify.
        4. Guarantee one environment and one ethics story when available.
        5. Return the 30 stories.
        """
        sorted_stories = sorted(
            stories,
            key=lambda story: story.composite_score,
            reverse=True,
        )

        selected = self._select_stories(sorted_stories, apply_buzz_filter=True)
        if len(selected) < 20:
            selected = self._select_stories(sorted_stories, apply_buzz_filter=False)
        selected = self._ensure_guaranteed_sections(selected, sorted_stories)
        selected = sorted(
            selected,
            key=lambda story: story.composite_score,
            reverse=True,
        )

        if len(selected) < min(self.selection_total, len(sorted_stories)):
            LOGGER.warning(
                "Selected %s stories out of requested %s because section caps were reached.",
                len(selected),
                self.selection_total,
            )

        return selected

    def _select_stories(
        self,
        sorted_stories: list[ScoredStory],
        *,
        apply_buzz_filter: bool,
    ) -> list[ScoredStory]:
        """Select stories in score order while enforcing section caps and optional buzz gating."""
        selected: list[ScoredStory] = []
        section_counts: Counter[str] = Counter()

        for story in sorted_stories:
            if len(selected) >= self.selection_total:
                break
            if section_counts[story.section] >= self._section_cap(story.section):
                continue
            if apply_buzz_filter and not self._meets_buzz_threshold(story):
                continue
            selected.append(story)
            section_counts[story.section] += 1

        return selected

    def _ensure_guaranteed_sections(
        self,
        selected: list[ScoredStory],
        sorted_stories: list[ScoredStory],
    ) -> list[ScoredStory]:
        guaranteed_candidates = self._find_guaranteed_candidates(sorted_stories)
        if not guaranteed_candidates:
            return selected

        ensured = list(selected)
        max_total = min(self.selection_total, len(sorted_stories))

        for section in GUARANTEED_SECTIONS:
            story = guaranteed_candidates.get(section)
            if story is None or self._contains_story(ensured, story):
                continue

            if len(ensured) < max_total:
                ensured.append(story)
                continue

            replacement_index = self._find_guarantee_replacement_index(
                ensured,
                story,
                guaranteed_candidates,
            )
            if replacement_index is None:
                LOGGER.warning(
                    "Unable to guarantee section '%s' in final selection.",
                    section,
                )
                continue

            ensured[replacement_index] = story

        return ensured

    def _find_guaranteed_candidates(
        self,
        sorted_stories: list[ScoredStory],
    ) -> dict[str, ScoredStory]:
        candidates: dict[str, ScoredStory] = {}
        for section in GUARANTEED_SECTIONS:
            for story in sorted_stories:
                if story.section == section:
                    candidates[section] = story
                    break
        return candidates

    def _find_guarantee_replacement_index(
        self,
        selected: list[ScoredStory],
        guaranteed_story: ScoredStory,
        guaranteed_candidates: dict[str, ScoredStory],
    ) -> int | None:
        protected_ids = {
            story.cluster.cluster_id
            for story in guaranteed_candidates.values()
            if self._contains_story(selected, story)
        }

        for index in range(len(selected) - 1, -1, -1):
            candidate = selected[index]
            candidate_id = candidate.cluster.cluster_id
            if candidate_id in protected_ids:
                continue
            if candidate_id == guaranteed_story.cluster.cluster_id:
                continue
            if self._replacement_respects_caps(selected, index, guaranteed_story):
                return index

        return None

    def _replacement_respects_caps(
        self,
        selected: list[ScoredStory],
        replacement_index: int,
        incoming_story: ScoredStory,
    ) -> bool:
        section_counts = Counter(
            story.section
            for index, story in enumerate(selected)
            if index != replacement_index
        )
        section_counts[incoming_story.section] += 1
        return all(
            count <= self._section_cap(section)
            for section, count in section_counts.items()
        )

    def _contains_story(
        self,
        stories: list[ScoredStory],
        target_story: ScoredStory,
    ) -> bool:
        target_id = target_story.cluster.cluster_id
        return any(story.cluster.cluster_id == target_id for story in stories)

    def _meets_buzz_threshold(self, story: ScoredStory) -> bool:
        threshold = 0.3 if story.section in LOWER_BUZZ_THRESHOLD_SECTIONS else 0.4
        return story.scores.get("buzz_momentum", 0.0) >= threshold

    def _section_cap(self, section: str) -> int:
        return SECTION_CAPS.get(section, DEFAULT_SECTION_CAP)

    def print_summary(self, stories: list[ScoredStory]) -> None:
        """Print scoring summary."""
        strong = sum(1 for story in self.all_scored_stories if story.composite_score >= 0.8)
        solid = sum(
            1 for story in self.all_scored_stories if 0.6 <= story.composite_score < 0.8
        )
        mid = sum(
            1 for story in self.all_scored_stories if 0.4 <= story.composite_score < 0.6
        )
        weak = sum(1 for story in self.all_scored_stories if story.composite_score < 0.4)
        section_counts = Counter(story.section for story in stories)

        print("=== Scoring & Ranking Complete ===")
        print(f"Input clusters: {len(self.clusters)}")
        print(f"Scored successfully: {len(self.all_scored_stories)}")
        if self.failed_clusters:
            print(f"Skipped after scoring errors: {len(self.failed_clusters)}")
        print("\nScore distribution:")
        print(f"  - 0.8+  (strong): {strong}")
        print(f"  - 0.6-0.8 (solid): {solid}")
        print(f"  - 0.4-0.6 (mid): {mid}")
        print(f"  - Below 0.4 (weak): {weak}")

        print(f"\nTop {len(stories)} selected:")
        for index, story in enumerate(stories, start=1):
            title = story.cluster.primary_article.title
            print(
                f"  {index:02d}. [{story.section}] {story.composite_score:.3f} - {title}"
            )

        print("\nSection breakdown:")
        for section, count in sorted(section_counts.items()):
            print(f"  - {section}: {count}")

        print(f"\nResults saved: {self.output_path} ({len(stories)} stories)")

    def save_results(self, stories: list[ScoredStory]) -> None:
        """Save to scored_stories.json with ensure_ascii=False."""
        payload = [self._serialize_story(story) for story in stories]
        self.output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _assign_tiers(self, stories: list[ScoredStory]) -> None:
        headline_cutoff = min(5, len(stories))
        honorable_count = min(5, max(0, len(stories) - 25))
        honorable_start = len(stories) - honorable_count

        for index, story in enumerate(stories):
            if index < headline_cutoff:
                story.tier = "headline"
            elif index >= honorable_start:
                story.tier = "honorable_mention"
            else:
                story.tier = "body"

    def _coerce_score(self, value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            numeric = 0.0
        return max(0.0, min(1.0, numeric))

    def _normalize_section(self, section: Any, article_title: str) -> str:
        normalized = str(section or "").strip().lower()
        if normalized not in VALID_SECTIONS:
            LOGGER.warning(
                "Invalid section '%s' for article '%s'; defaulting to industry.",
                section,
                article_title,
            )
            return "industry"
        return normalized

    def _validate_weights(self, weights: dict[str, Any]) -> dict[str, float]:
        validated: dict[str, float] = {}
        for field in SCORE_FIELDS:
            try:
                validated[field] = float(weights[field])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Missing or invalid scoring weight for '{field}'") from exc

        total = sum(validated.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total:.6f}")
        return validated

    def _serialize_story(self, story: ScoredStory) -> dict[str, Any]:
        cluster = story.cluster
        return {
            "cluster": {
                "cluster_id": cluster.cluster_id,
                "primary_article": cluster.primary_article.model_dump(mode="json"),
                "coverage_count": cluster.coverage_count,
                "sources_involved": cluster.sources_involved,
            },
            "scores": story.scores,
            "composite_score": story.composite_score,
            "rationale": story.rationale,
            "section": story.section,
            "tier": story.tier,
        }
