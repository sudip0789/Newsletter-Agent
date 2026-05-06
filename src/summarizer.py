from __future__ import annotations

import html
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from src.models import ScoredStory, StoryCluster, SummarizedStory
from src.text_utils import normalize_markdown_escaped_text

LOGGER = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = """You are a newsletter blurb writer for "The AI Upload Weekly Digest" published by Stanford Law School's Robert Crown Law Library. Your audience is law students, faculty, and legal professionals who follow AI developments.

Your job is to produce a short AI news blurb from the article text provided. You do NOT speculate, add outside context, or editorialize. You stick strictly to facts from the provided text.

Write 1 to 3 short paragraphs. Total length: 100-200 words. Cover what happened, why it matters, and who it affects. Clear, concise, original prose. Mildly persuasive — make the reader want to click through. Stick ONLY to facts from the provided article text. No speculation, no outside context, no editorial additions. No cliché openings, no hype language, no restating the headline at the end. Third person. No bullet points. No formatting — just plain text paragraphs."""

USER_MESSAGE_TEMPLATE = """Title: {title}
Source: {source_name}
Date: {published_date}

Article text:
{text}"""


class Summarizer:
    DEFAULT_TOP_N = 30
    DEFAULT_MODEL = "sonnet-4.6"
    MAX_WORKERS = 6
    MAX_TEXT_CHARS = 10000
    MIN_TEXT_CHARS = 100
    FAILURE_SUMMARY = "Summary generation failed — manual review required."
    MODEL_CONFIGS = {
        "gpt-5.4": {
            "provider": "openai",
            "api_model": "gpt-5.4",
            "env_var": "OPENAI_API_KEY",
            "output_label": "openai_gpt_5_4",
        },
        "sonnet-4.6": {
            "provider": "anthropic",
            "api_model": "claude-sonnet-4-20250514",
            "env_var": "ANTHROPIC_API_KEY",
            "output_label": "anthropic_sonnet_4_6",
        },
    }

    def __init__(
        self,
        input_path: str = "data/output/scored_stories.json",
        top_n: int = DEFAULT_TOP_N,
        model: str = DEFAULT_MODEL,
    ):
        """Load scored stories and init OpenAI client."""
        load_dotenv()
        self.model_name = model
        self.model_config = self._resolve_model_config(model)
        required_env_var = self.model_config["env_var"]
        if not os.getenv(required_env_var):
            raise ValueError(f"{required_env_var} is required for summarization.")

        self.provider = self.model_config["provider"]
        self.api_model = self.model_config["api_model"]
        self.input_path = Path(input_path)
        self.output_path = (
            self.input_path.parent
            / f"summarized_stories_{self.model_config['output_label']}.json"
        )
        self.top_n = top_n

        raw_stories = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.scored_stories = [
            ScoredStory.model_validate(self._normalize_story_payload(item))
            for item in raw_stories
        ]
        self.client = self._build_client()

    def run(self) -> list[SummarizedStory]:
        """
        1. Take the top N stories by composite score.
        2. For each story, check text_completeness:
           - If 'full' or 'partial': summarize via LLM call.
           - If 'snippet': skip LLM, use the existing text as-is, flag for manual review.
        3. Run LLM calls in parallel using ThreadPoolExecutor (max 6 workers).
        4. Return list of SummarizedStory objects.
        """
        top_stories = sorted(
            self.scored_stories,
            key=lambda story: story.composite_score,
            reverse=True,
        )[: self.top_n]
        results: list[SummarizedStory | None] = [None] * len(top_stories)
        llm_jobs: list[tuple[int, ScoredStory]] = []

        for index, story in enumerate(top_stories):
            article = story.cluster.primary_article
            text = (article.text or "").strip()
            if article.text_completeness == "snippet":
                results[index] = self.handle_snippet(story)
            elif len(text) < self.MIN_TEXT_CHARS:
                LOGGER.warning(
                    "Very short text for '%s' — flagged for manual review",
                    article.title,
                )
                results[index] = SummarizedStory(
                    scored_story=story,
                    summary=text,
                    needs_manual_review=True,
                )
            else:
                llm_jobs.append((index, story))

        for batch_start in range(0, len(llm_jobs), self.MAX_WORKERS):
            batch = llm_jobs[batch_start : batch_start + self.MAX_WORKERS]
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
                batch_results = list(
                    executor.map(lambda item: self.summarize_story(item[1]), batch)
                )
            for (index, _story), summarized in zip(batch, batch_results):
                results[index] = summarized
            if batch_start + self.MAX_WORKERS < len(llm_jobs):
                time.sleep(0.5)

        return [story for story in results if story is not None]

    def handle_snippet(self, story: ScoredStory) -> SummarizedStory:
        """
        For articles where text_completeness is 'snippet':
        - Do NOT call the LLM. Do not generate a summary.
        - Use the existing snippet text as the summary.
        - Set needs_manual_review = True.
        - Log a warning: "Snippet only for '{title}' — flagged for manual review"
        """
        title = story.cluster.primary_article.title
        LOGGER.warning("Snippet only for '%s' — flagged for manual review", title)
        return SummarizedStory(
            scored_story=story,
            summary=self._normalize_text(story.cluster.primary_article.text),
            needs_manual_review=True,
        )

    def summarize_story(self, story: ScoredStory) -> SummarizedStory:
        """
        Single LLM call per story.
        Model: configured provider/model
        Send the system prompt + article text.
        Return the generated summary.
        """
        article = story.cluster.primary_article
        text = (article.text or "")[: self.MAX_TEXT_CHARS]
        user_message = USER_MESSAGE_TEMPLATE.format(
            title=article.title,
            source_name=article.source_name,
            published_date=article.published_date.isoformat()
            if article.published_date
            else "Unknown",
            text=text,
        )

        try:
            summary = self._normalize_text(self._generate_summary(user_message))
            if not summary:
                raise ValueError("Empty response content from summarization model")
            return SummarizedStory(
                scored_story=story,
                summary=summary,
                needs_manual_review=False,
            )
        except Exception as exc:  # pragma: no cover - defensive against API/runtime issues
            LOGGER.warning(
                "Summary generation failed for '%s': %s",
                article.title,
                exc,
            )
            return SummarizedStory(
                scored_story=story,
                summary=self.FAILURE_SUMMARY,
                needs_manual_review=True,
            )

    def save_results(self, stories: list[SummarizedStory]) -> None:
        """Save to summarized_stories.json"""
        payload = [self._serialize_story(story) for story in stories]
        self.output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _normalize_story_payload(self, payload: dict) -> dict:
        cluster = dict(payload.get("cluster", {}))
        if "all_articles" not in cluster and cluster.get("primary_article"):
            cluster["all_articles"] = [cluster["primary_article"]]

        normalized = dict(payload)
        normalized["cluster"] = cluster
        return normalized

    def _serialize_story(self, story: SummarizedStory) -> dict:
        scored_story = story.scored_story
        cluster = scored_story.cluster
        return {
            "scored_story": {
                "cluster": {
                    "cluster_id": cluster.cluster_id,
                    "primary_article": cluster.primary_article.model_dump(mode="json"),
                    "coverage_count": cluster.coverage_count,
                    "sources_involved": cluster.sources_involved,
                },
                "scores": scored_story.scores,
                "composite_score": scored_story.composite_score,
                "rationale": scored_story.rationale,
                "section": scored_story.section,
                "tier": scored_story.tier,
            },
            "summary": normalize_markdown_escaped_text(story.summary),
            "needs_manual_review": story.needs_manual_review,
        }

    def _resolve_model_config(self, model: str) -> dict[str, str]:
        try:
            return self.MODEL_CONFIGS[model]
        except KeyError as exc:
            choices = ", ".join(sorted(self.MODEL_CONFIGS))
            raise ValueError(f"Unsupported summarization model '{model}'. Use one of: {choices}.") from exc

    def _build_client(self) -> Any:
        if self.provider == "openai":
            return OpenAI()
        if self.provider == "anthropic":
            try:
                from anthropic import Anthropic
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for sonnet-4.6 summarization. "
                    "Add it to the environment before using this model."
                ) from exc
            return Anthropic()
        raise ValueError(f"Unsupported summarization provider '{self.provider}'.")

    def _normalize_text(self, value: Any) -> str:
        return html.unescape("" if value is None else str(value)).strip()

    def _generate_summary(self, user_message: str) -> str:
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.api_model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
            )
            return (response.choices[0].message.content or "").strip()

        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.api_model,
                max_tokens=400,
                temperature=0.7,
                system=SUMMARIZER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            text_parts = [
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ]
            return "".join(text_parts).strip()

        raise ValueError(f"Unsupported summarization provider '{self.provider}'.")
