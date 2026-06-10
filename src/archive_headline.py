"""
Generate a short 2-3 line "issue headline" for the archive index cards.

Reads a week's three headline picks (title + blurb) and asks Claude Opus 4.8
to synthesize one editorial headline that captures the issue's through-line.
Results are cached per issue date in data/output/archive.json so the model only
runs once per issue.
"""

from __future__ import annotations

import logging
import re
from typing import Any

LOGGER = logging.getLogger(__name__)

ARCHIVE_HEADLINE_MODEL = "claude-opus-4-8"

ARCHIVE_HEADLINE_SYSTEM_PROMPT = (
    "You write the one-line cover headline for a weekly AI newsletter's archive "
    "index card. You are given the issue's three top stories (title + blurb). "
    "Synthesize them into a SINGLE editorial headline that captures the week's "
    "through-line.\n\n"
    "Rules:\n"
    "- 10-18 words, fitting on 2-3 short lines.\n"
    "- Reference the through-line of all three stories, usually as a list joined "
    "with commas and a final 'and' (e.g. \"Multimodal AI Arrives, Teen Mental "
    "Health Meets the Chatbot, and the Grid Buckles\").\n"
    "- Confident, vivid, editorial — like a magazine cover. Title Case.\n"
    "- No subtitle, no quotation marks, no trailing period, no emoji, no source names.\n"
    "- Output ONLY the headline text."
)


def _normalize(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = cleaned.strip('"“”')
    return cleaned.rstrip(".").strip()


def build_anthropic_client() -> Any:
    """Create an Anthropic client (requires ANTHROPIC_API_KEY in the environment)."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "The 'anthropic' package is required for archive headline generation."
        ) from exc
    return Anthropic()


def generate_archive_headline(client: Any, headlines: list[dict[str, Any]]) -> str:
    """Generate a single cover headline from the issue's headline picks."""
    if not headlines:
        raise ValueError("Cannot generate an archive headline without headline picks.")

    story_lines = []
    for headline in headlines:
        title = (headline.get("title") or "").strip()
        blurb = (headline.get("blurb") or "").strip()
        if not title:
            continue
        story_lines.append(f"- {title}" + (f" — {blurb}" if blurb else ""))

    user_message = "This week's top stories:\n" + "\n".join(story_lines)

    response = client.messages.create(
        model=ARCHIVE_HEADLINE_MODEL,
        max_tokens=120,
        system=ARCHIVE_HEADLINE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )
    headline = _normalize(text)
    if not headline:
        raise ValueError("Archive headline generation returned empty content.")
    return headline
