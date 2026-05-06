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
    "Write a single sentence teaser (under 20 words) for a newsletter headline card. "
    "Make it catchy and informative. No hype language. Do not restate or closely echo the title."
    "Just the core hook that makes someone want to read more."
)

SHORT_TITLE_SYSTEM_PROMPT = (
    "Rewrite long newsletter headlines into a catchy 5-8 word title. "
    "Preserve the core news angle, avoid clickbait, and return only the rewritten title."
)


class HeadlineSelector:
    HEADLINE_CATEGORIES = ["industry", "legal_intelligence", "creative_ai"]
    BLURB_MODEL = "claude-sonnet-4-20250514"
    IMAGE_MODEL = "gpt-image-1.5"

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
        self.blurb_client: Any | None = None
        self.image_client: Any | None = None

    def run(self) -> list[dict]:
        """
        Select 3 headline stories, generate blurbs, and return the headline payloads.
        """
        selected_stories = self._select_headline_stories()
        headlines: list[dict] = []
        for story in selected_stories:
            blurb = self.generate_blurb(story)
            title = story["title"]
            if self._title_word_count(title) >= 18:
                title = self.generate_short_title(
                    {"title": story["title"], "summary": story["summary"]}
                )

            headlines.append(
                {
                    **story,
                    "title": title,
                    "blurb": blurb,
                    "image_path": None,
                }
            )

        return headlines

    def generate_blurb(self, story: dict) -> str:
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
            raise ValueError("Blurb must be under 20 words.")
        return blurb

    def generate_short_title(self, story: dict) -> str:
        """
        Rewrite long headline titles into a concise 5-8 word version.
        """
        client = self._get_blurb_client()
        user_message = (
            f"Original title: {story['title']}\n"
            f"Summary: {story['summary']}"
        )
        response = client.messages.create(
            model=self.BLURB_MODEL,
            max_tokens=50,
            temperature=0.5,
            system=SHORT_TITLE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        text_parts = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        short_title = self._normalize_text("".join(text_parts))
        word_count = self._title_word_count(short_title)
        if word_count < 5 or word_count > 8:
            raise ValueError("Short headline titles must be 5-8 words.")
        return short_title

    def generate_headline_image(self, story: dict, index: int) -> str | None:
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

            "Visual: use a clear, literal metaphor (e.g., database + warning symbol, "
            "graph + coins, lock + wallet, brain + signal waves). "

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

    def save_picks(self, headlines: list[dict]) -> None:
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

    def load_saved_picks(self) -> list[dict]:
        return json.loads(self.output_path.read_text(encoding="utf-8"))

    def attach_summaries(self, picks: list[dict]) -> list[dict]:
        summaries_by_url = {
            story.scored_story.cluster.primary_article.url: story.summary
            for story in self.summarized_stories
        }
        enriched: list[dict] = []
        for pick in picks:
            summary = summaries_by_url.get(pick.get("url", ""), pick.get("blurb", ""))
            enriched.append({**pick, "summary": summary})
        return enriched

    def _select_headline_stories(self) -> list[dict]:
        eligible_stories = [
            (index, self._to_story_dict(story))
            for index, story in enumerate(self.summarized_stories)
            if self._is_eligible(story)
        ]
        if len(eligible_stories) < 3:
            raise ValueError("Fewer than 3 eligible headline stories were found.")

        selected: list[dict] = []
        selected_urls: set[str] = set()
        ranked_stories = sorted(
            eligible_stories,
            key=lambda item: (-item[1]["composite_score"], item[0]),
        )

        for category in self.HEADLINE_CATEGORIES:
            match = next(
                (
                    story
                    for _index, story in ranked_stories
                    if story["section"] == category and story["url"] not in selected_urls
                ),
                None,
            )
            if match is not None:
                selected.append(match)
                selected_urls.add(match["url"])

        while len(selected) < 3:
            fallback = next(
                (
                    story
                    for _index, story in ranked_stories
                    if story["url"] not in selected_urls
                ),
                None,
            )
            if fallback is None:
                raise ValueError("Fewer than 3 eligible headline stories were found.")
            selected.append(fallback)
            selected_urls.add(fallback["url"])

        return sorted(selected, key=lambda story: story["composite_score"], reverse=True)

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
        return {
            "title": article.title,
            "source_name": article.source_name,
            "url": article.url,
            "section": story.scored_story.section,
            "composite_score": story.scored_story.composite_score,
            "summary": story.summary,
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

    def _title_word_count(self, title: str) -> int:
        return len(self._normalize_text(title).split())
