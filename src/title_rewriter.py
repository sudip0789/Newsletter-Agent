from __future__ import annotations

import html
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.models import SummarizedStory

LOGGER = logging.getLogger(__name__)

TITLE_REWRITER_SYSTEM_PROMPT = """You are a newsletter title editor for "The AI Upload Weekly Digest" published by Stanford Law School's Robert Crown Law Library.

Your job is to rewrite the source article title into a newsletter title.

Rules for newsletter_title:
- 5 to 15 words.
- Preserve the same core meaning as the source title.
- Make it slightly punchier, but still factual.
- Do not copy the original title verbatim.
- No clickbait, no speculation, no hype.

Return ONLY the rewritten title text."""

USER_MESSAGE_TEMPLATE = """Title: {title}
Source: {source_name}
Date: {published_date}

Summary:
{summary}"""


class TitleRewriter:
    DEFAULT_TOP_N = 30
    DEFAULT_MODEL = "sonnet-4.6"
    MAX_WORKERS = 6
    MAX_TEXT_CHARS = 10000
    TITLE_MIN_WORDS = 5
    TITLE_MAX_WORDS = 15
    TITLE_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)*")
    TITLE_COMPARISON_PATTERN = re.compile(r"[^a-z0-9]+")
    MODEL_CONFIGS = {
        "gpt-5.4": {
            "provider": "openai",
            "api_model": "gpt-5.4",
            "env_var": "OPENAI_API_KEY",
            "output_label": "openai_gpt_5_4",
        },
        "sonnet-4.6": {
            "provider": "anthropic",
            "api_model": "claude-sonnet-4-6",
            "env_var": "ANTHROPIC_API_KEY",
            "output_label": "anthropic_sonnet_4_6",
        },
    }

    def __init__(
        self,
        input_path: str | None = None,
        top_n: int = DEFAULT_TOP_N,
        model: str = DEFAULT_MODEL,
    ):
        load_dotenv()
        self.model_name = model
        self.model_config = self._resolve_model_config(model)
        required_env_var = self.model_config["env_var"]
        if not os.getenv(required_env_var):
            raise ValueError(f"{required_env_var} is required for title rewriting.")

        self.provider = self.model_config["provider"]
        self.api_model = self.model_config["api_model"]
        if input_path is None:
            input_path = (
                "data/output/"
                f"summarized_stories_{self.model_config['output_label']}.json"
            )
        self.input_path = Path(input_path)
        self.output_path = self.input_path
        self.top_n = top_n

        raw_stories = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.summarized_stories = [
            SummarizedStory.model_validate(self._normalize_story_payload(item))
            for item in raw_stories
        ]
        self.client = self._build_client()

    def run(self) -> list[SummarizedStory]:
        stories = list(self.summarized_stories)
        indexed_stories = list(enumerate(stories[: self.top_n]))

        for batch_start in range(0, len(indexed_stories), self.MAX_WORKERS):
            batch = indexed_stories[batch_start : batch_start + self.MAX_WORKERS]
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                batch_titles = list(
                    executor.map(lambda item: self._rewrite_story_title(item[1]), batch)
                )
            for (index, _story), newsletter_title in zip(batch, batch_titles):
                stories[index].newsletter_title = newsletter_title
            if batch_start + self.MAX_WORKERS < len(indexed_stories):
                time.sleep(0.5)

        return stories

    def rewrite_title(self, story: SummarizedStory) -> str:
        article = story.scored_story.cluster.primary_article
        summary = (story.summary or "")[: self.MAX_TEXT_CHARS]
        user_message = USER_MESSAGE_TEMPLATE.format(
            title=article.title,
            source_name=article.source_name,
            published_date=article.published_date.isoformat()
            if article.published_date
            else "Unknown",
            summary=summary,
        )
        rewritten = self._normalize_text(self._generate_title(user_message))
        self._validate_newsletter_title(rewritten, article.title)
        return rewritten

    def save_results(self, stories: list[SummarizedStory]) -> None:
        payload = [self._serialize_story(story) for story in stories]
        self.output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _rewrite_story_title(self, story: SummarizedStory) -> str:
        article = story.scored_story.cluster.primary_article
        try:
            return self.rewrite_title(story)
        except Exception as exc:  # pragma: no cover - defensive against API/runtime issues
            LOGGER.warning(
                "Title rewrite failed for '%s': %s",
                article.title,
                exc,
            )
            return article.title

    def _serialize_story(self, story: SummarizedStory) -> dict[str, Any]:
        scored_story = story.scored_story
        cluster = scored_story.cluster
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": cluster.cluster_id,
                    "primary_article": cluster.primary_article.model_dump(
                        mode="json",
                        exclude={"text"},
                    ),
                    "coverage_count": cluster.coverage_count,
                    "sources_involved": cluster.sources_involved,
                },
                "scores": scored_story.scores,
                "composite_score": scored_story.composite_score,
                "rationale": scored_story.rationale,
                "section": scored_story.section,
                "tier": scored_story.tier,
            },
            "newsletter_title": story.newsletter_title
            or cluster.primary_article.title,
            "summary": story.summary,
            "needs_manual_review": story.needs_manual_review,
        }

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

    def _resolve_model_config(self, model: str) -> dict[str, str]:
        try:
            return self.MODEL_CONFIGS[model]
        except KeyError as exc:
            choices = ", ".join(sorted(self.MODEL_CONFIGS))
            raise ValueError(
                f"Unsupported title rewriting model '{model}'. Use one of: {choices}."
            ) from exc

    def _build_client(self) -> Any:
        if self.provider == "openai":
            return OpenAI()
        if self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for sonnet-4.6 title rewriting."
                ) from exc
            return Anthropic()
        raise ValueError(f"Unsupported title rewriting provider '{self.provider}'.")

    def _normalize_text(self, value: Any) -> str:
        return " ".join(html.unescape("" if value is None else str(value)).split())

    def _validate_newsletter_title(
        self,
        newsletter_title: str,
        original_title: str,
    ) -> None:
        if not newsletter_title:
            raise ValueError("Title rewriter returned an empty newsletter title")

        word_count = self._newsletter_title_word_count(newsletter_title)
        if word_count < self.TITLE_MIN_WORDS or word_count > self.TITLE_MAX_WORDS:
            raise ValueError(
                f"Newsletter title must be {self.TITLE_MIN_WORDS}-{self.TITLE_MAX_WORDS} words."
            )

        if self._normalize_title_for_comparison(
            newsletter_title
        ) == self._normalize_title_for_comparison(original_title):
            raise ValueError("Newsletter title must not match the original title verbatim.")

    def _newsletter_title_word_count(self, title: str) -> int:
        return len(self.TITLE_TOKEN_PATTERN.findall(title))

    def _normalize_title_for_comparison(self, title: str) -> str:
        lowered = self._normalize_text(title).lower()
        return self.TITLE_COMPARISON_PATTERN.sub("", lowered)

    def _generate_title(self, user_message: str) -> str:
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.api_model,
                temperature=0.5,
                messages=[
                    {"role": "system", "content": TITLE_REWRITER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            return (response.choices[0].message.content or "").strip()

        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.api_model,
                max_tokens=60,
                temperature=0.5,
                system=TITLE_REWRITER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            text_parts = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            return "".join(text_parts).strip()

        raise ValueError(f"Unsupported title rewriting provider '{self.provider}'.")
