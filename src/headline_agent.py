from __future__ import annotations

import base64
import html
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.models import SummarizedStory

LOGGER = logging.getLogger(__name__)

BLURB_SYSTEM_PROMPT = (
    "Write a small teaser (under 30 words) for a newsletter headline card. "
    "Make it catchy and informative. No hype language. Do not restate or closely echo the title."
    "Just the core hook that makes someone want to read more."
)

HEADLINE_SELECTION_SYSTEM_PROMPT = """You are the lead editor for an AI news newsletter.

Your job is to choose exactly 3 headline stories from the candidate list. Think like a human editor, not a deterministic ranking script.

Prioritize:
- highly popular product launches from the current week
- stories that feel broadly important, conversation-driving, and genuinely headline-worthy
- big company moments, public failures, business risk, strategy shocks, executive conflict, or market-moving news
- lawsuits, regulatory action, copyright disputes, security incidents, or other high-stakes AI controversies

Avoid selecting three headlines that feel like the same story type unless the week is clearly dominated by that topic. Aim for variety across the final 3 picks when possible.

Respond with ONLY a JSON object in this shape:
{
  "selected_headlines": [
    {"url": "https://example.com/1"},
    {"url": "https://example.com/2"},
    {"url": "https://example.com/3"}
  ]
}
"""


class HeadlineAgent:
    HEADLINE_SELECTION_MODEL = "gpt-5.4"
    BLURB_MODEL = "claude-sonnet-4-6"
    IMAGE_MODEL = "gpt-image-1.5"
    HEADLINE_COUNT = 3
    SELECTION_TEMPERATURE = 0.65

    def __init__(self, input_path: str = "data/output/summarized_stories.json"):
        """Load summarized stories."""
        load_dotenv()
        self.input_path = Path(input_path)
        self.output_path = self.input_path.parent / "headline_picks.json"
        self.assets_dir = Path("assets/generated")
        raw_stories = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.summarized_stories = [
            SummarizedStory.model_validate(self._normalize_story_payload(item))
            for item in raw_stories
        ]
        self.selection_client: Any | None = None
        self.blurb_client: Any | None = None
        self.image_client: Any | None = None

    def run(self) -> list[dict[str, Any]]:
        """
        Select 3 headline stories, generate blurbs, and return the headline payloads.
        """
        selected_stories = self._select_headline_stories()
        headlines: list[dict[str, Any]] = []
        for story in selected_stories:
            blurb = self.generate_blurb(story)
            headlines.append(
                {
                    **story,
                    "blurb": blurb,
                    "image_path": None,
                }
            )

        return headlines

    def generate_blurb(self, story: dict[str, Any]) -> str:
        """
        Generate a short, catchy one-liner (under 20 words) for the headline card.
        """
        client = self._get_blurb_client()
        user_message = f"Title: {story['title']}\nSummary: {story['summary']}"
        response = client.messages.create(
            model=self.BLURB_MODEL,
            max_tokens=80,
            temperature=0.6,
            system=BLURB_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        blurb = self._normalize_text("".join(text_parts))
        if not blurb:
            raise ValueError("Blurb generation returned empty content.")
        if len(blurb.split()) >= 20:
            LOGGER.warning("Blurb too long (%d words), retrying: %s", len(blurb.split()), blurb)
            response = client.messages.create(
                model=self.BLURB_MODEL,
                max_tokens=60,
                temperature=0.4,
                system=BLURB_SYSTEM_PROMPT + " You MUST stay under 20 words.",
                messages=[{"role": "user", "content": user_message}],
            )
            text_parts = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            blurb = self._normalize_text("".join(text_parts))
        if not blurb:
            raise ValueError("Blurb generation returned empty content on retry.")
        if len(blurb.split()) >= 20:
            LOGGER.warning("Blurb still over 20 words after retry, using as-is: %s", blurb)
        return blurb

    def generate_headline_image(self, story: dict[str, Any], index: int) -> str | None:
        """
        Generate a headline card image using OpenAI's image API.
        """
        client = self._get_image_client()
        prompt_context = story.get("blurb") or ""
        prompt = (
            f"Flat vector icon illustration representing: {story['title']}. "
            f"Context: {prompt_context}. "
            "Style: modern product-style icon (similar to Stripe or Notion illustrations). "
            "Clean geometric shapes, soft gradients, subtle shadows. "
            "Color palette: muted professional tones (navy, teal, gray) with small accent colors (red or yellow). "
            "Composition: single centered icon, simple and bold, high contrast, "
            "easily recognizable at small size (thumbnail). "
            "Visual: use a clear, literal metaphor. No brains, no nodes, no robots in logos.No scales of justice, no gravel. "
            "Constraints: no text, no letters, no numbers, no logos, no realistic faces, "
            "no photorealism, no complex background. "
            "Tone: clean, polished, modern tech editorial icon."
        )

        try:
            response = client.images.generate(
                model=self.IMAGE_MODEL,
                prompt=prompt,
                size="1024x1024",
                quality="low",
                output_format="png",
            )
            image_bytes = self._extract_image_bytes(response)
            self.assets_dir.mkdir(parents=True, exist_ok=True)
            image_path = self.assets_dir / f"headline_{index}.png"
            image_path.write_bytes(image_bytes)
            return str(image_path)
        except Exception as exc:  # pragma: no cover - defensive against API/runtime issues
            LOGGER.warning(
                "Headline image generation failed for '%s': %s",
                story.get("title", "Unknown story"),
                exc,
            )
            return None

    def save_picks(self, headlines: list[dict[str, Any]]) -> None:
        """
        Save to data/output/headline_picks.json for review.
        """
        payload = [
            {
                "title": headline["title"],
                "source_name": headline["source_name"],
                "url": headline["url"],
                "section": headline["section"],
                "composite_score": headline["composite_score"],
                "blurb": headline["blurb"],
                "image_path": headline.get("image_path"),
            }
            for headline in headlines
        ]
        self.output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_saved_picks(self) -> list[dict[str, Any]]:
        return json.loads(self.output_path.read_text(encoding="utf-8"))

    def preserve_existing_image_paths(
        self,
        headlines: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        try:
            saved_picks = self.load_saved_picks()
        except FileNotFoundError:
            return [{**headline, "image_path": headline.get("image_path")} for headline in headlines]

        saved_paths_by_url = {
            pick.get("url", ""): pick.get("image_path")
            for pick in saved_picks
            if pick.get("url") and pick.get("image_path")
        }
        same_order = len(saved_picks) == len(headlines) and all(
            saved_picks[index].get("url") == headlines[index].get("url")
            for index in range(len(headlines))
        )

        refreshed: list[dict[str, Any]] = []
        for index, headline in enumerate(headlines, start=1):
            image_path = headline.get("image_path") or saved_paths_by_url.get(
                headline.get("url", "")
            )
            if image_path is None and same_order:
                conventional_path = self.assets_dir / f"headline_{index}.png"
                if conventional_path.exists():
                    image_path = str(conventional_path)
            refreshed.append({**headline, "image_path": image_path})
        return refreshed

    def attach_summaries(self, picks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries_by_url = {
            story.scored_story.cluster.primary_article.url: story.summary
            for story in self.summarized_stories
        }
        enriched: list[dict[str, Any]] = []
        for pick in picks:
            summary = summaries_by_url.get(pick.get("url", ""), pick.get("blurb", ""))
            enriched.append({**pick, "summary": summary})
        return enriched

    def _select_headline_stories(self) -> list[dict[str, Any]]:
        ranked_stories = self._rank_eligible_stories()
        by_url = {story["url"]: story for story in ranked_stories}

        selected_urls = self._select_urls_with_llm(ranked_stories)
        if selected_urls is None:
            return ranked_stories[: self.HEADLINE_COUNT]

        return [by_url[url] for url in selected_urls]

    def _rank_eligible_stories(self) -> list[dict[str, Any]]:
        eligible_stories = [
            (index, self._to_story_dict(story))
            for index, story in enumerate(self.summarized_stories)
            if self._is_eligible(story)
        ]
        if len(eligible_stories) < self.HEADLINE_COUNT:
            raise ValueError("Fewer than 3 eligible headline stories were found.")

        ranked_stories = sorted(
            eligible_stories,
            key=lambda item: (-item[1]["composite_score"], item[0]),
        )
        return [story for _index, story in ranked_stories]

    def _select_urls_with_llm(
        self,
        ranked_stories: list[dict[str, Any]],
    ) -> list[str] | None:
        client = self._get_selection_client()
        response = client.chat.completions.create(
            model=self.HEADLINE_SELECTION_MODEL,
            response_format={"type": "json_object"},
            temperature=self.SELECTION_TEMPERATURE,
            messages=[
                {"role": "system", "content": HEADLINE_SELECTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": self._build_selection_user_prompt(ranked_stories),
                },
            ],
        )
        content = response.choices[0].message.content
        if not content:
            LOGGER.warning("Headline selection returned empty content. Using fallback.")
            return None

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            LOGGER.warning("Headline selection returned invalid JSON. Using fallback.")
            return None

        selected_items = parsed.get("selected_headlines")
        if not isinstance(selected_items, list):
            LOGGER.warning("Headline selection JSON missing selected_headlines. Using fallback.")
            return None

        candidate_urls = {story["url"] for story in ranked_stories}
        selected_urls: list[str] = []
        seen: set[str] = set()

        for item in selected_items:
            if not isinstance(item, dict):
                LOGGER.warning("Headline selection item is not an object. Using fallback.")
                return None
            url = self._normalize_text(item.get("url"))
            if not url or url not in candidate_urls or url in seen:
                LOGGER.warning("Headline selection returned invalid or duplicate URLs. Using fallback.")
                return None
            selected_urls.append(url)
            seen.add(url)

        if len(selected_urls) != self.HEADLINE_COUNT:
            LOGGER.warning("Headline selection returned %s URLs. Using fallback.", len(selected_urls))
            return None

        return selected_urls

    def _build_selection_user_prompt(self, ranked_stories: list[dict[str, Any]]) -> str:
        candidates = [
            {
                "title": story["title"],
                "source_name": story["source_name"],
                "url": story["url"],
                "section": story["section"],
                "composite_score": story["composite_score"],
                "summary": story["summary"],
                "published_date": story["published_date"],
                "coverage_count": story["coverage_count"],
                "sources_involved": story["sources_involved"],
            }
            for story in ranked_stories
        ]
        return json.dumps(
            {
                "instructions": "Choose the three strongest headline stories in ranked order.",
                "candidate_stories": candidates,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _get_selection_client(self) -> Any:
        if self.selection_client is not None:
            return self.selection_client

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for headline selection.")

        self.selection_client = OpenAI()
        return self.selection_client

    def _get_blurb_client(self) -> Any:
        if self.blurb_client is not None:
            return self.blurb_client

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for headline blurbs.")

        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for headline blurb generation."
            ) from exc

        self.blurb_client = Anthropic()
        return self.blurb_client

    def _get_image_client(self) -> Any:
        if self.image_client is not None:
            return self.image_client

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for headline image generation.")

        self.image_client = OpenAI()
        return self.image_client

    def _is_eligible(self, story: SummarizedStory) -> bool:
        return bool(story.summary.strip()) and not story.needs_manual_review

    def _to_story_dict(self, story: SummarizedStory) -> dict[str, Any]:
        article = story.scored_story.cluster.primary_article
        cluster = story.scored_story.cluster
        return {
            "title": story.newsletter_title or article.title,
            "source_name": article.source_name,
            "url": article.url,
            "section": story.scored_story.section,
            "composite_score": story.scored_story.composite_score,
            "summary": story.summary,
            "published_date": article.published_date.isoformat()
            if article.published_date
            else None,
            "coverage_count": cluster.coverage_count,
            "sources_involved": cluster.sources_involved,
        }

    def _extract_image_bytes(self, payload: Any) -> bytes:
        data_items = getattr(payload, "data", None)
        if data_items is None and isinstance(payload, dict):
            data_items = payload.get("data", [])

        for item in data_items or []:
            encoded = getattr(item, "b64_json", None)
            if encoded is None and isinstance(item, dict):
                encoded = item.get("b64_json")
            if encoded:
                return base64.b64decode(encoded)
        raise ValueError("No image data returned by OpenAI.")

    def _normalize_text(self, value: Any) -> str:
        return " ".join(html.unescape("" if value is None else str(value)).split())

    def _normalize_story_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        scored_story = dict(payload.get("scored_story", {}))
        cluster = dict(scored_story.get("cluster", {}))
        if "all_articles" not in cluster and cluster.get("primary_article"):
            cluster["all_articles"] = [cluster["primary_article"]]

        normalized_scored_story = dict(scored_story)
        normalized_scored_story["cluster"] = cluster

        normalized = dict(payload)
        normalized["scored_story"] = normalized_scored_story
        return normalized
