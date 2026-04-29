from __future__ import annotations

import json
import re
from pathlib import Path

from src.models import Article

AI_KEYWORDS = [
    "artificial intelligence",
    "machine learning",
    "deep learning",
    "generative ai",
    "gen ai",
    "genai",
    "large language model",
    "llm",
    "foundation model",
    "neural network",
    "transformer model",
    "diffusion model",
    "natural language processing",
    "nlp",
    "computer vision",
    "reinforcement learning",
    "ai agent",
    "agentic ai",
    "agentic",
    "ai-driven",
    "ai-powered",
    "ai safety",
    "ai regulation",
    "ai coding",
    "ai model",
    "vibe coding",
    "prompt engineering",
    "fine-tuning",
    "fine-tune",
    "retrieval augmented",
    "rag pipeline",
    "vector database",
    "embedding",
    "tokenizer",
    "inference",
    "text-to-image",
    "text-to-video",
    "text-to-speech",
    "openai",
    "anthropic",
    "deepseek",
    "mistral",
    "google deepmind",
    "meta ai",
    "microsoft ai",
    "nvidia",
    "jensen huang",
    "sam altman",
    "dario amodei",
    "chatgpt",
    "claude",
    "gemini",
    "copilot",
    "gpt-4",
    "gpt-5",
    "gpt-6",
    "dall-e",
    "midjourney",
    "stable diffusion",
    "sora",
    "veo",
    "runway ai",
    "suno",
    "elevenlabs",
    "eleven labs",
    "cursor ai",
    "replit ai",
    "loveable",
    "perplexity",
    "notebooklm",
    "notebook lm",
    "hugging face",
    "huggingface",
    "ollama",
    "vercel ai",
    "google ai studio",
    "ai studio",
    "cocounsel",
    "harvey ai",
    "legora",
    "lextext",
    "rhetoric ai",
    "protege ai",
    "nano banana",
    "open claw",
    "nemo claw",
    "google stitch",
]

SHORT_KEYWORDS = ["ai", "llm", "nlp", "gpt", "rag", "gpu"]
SHORT_KEYWORDS_REGEX = re.compile(
    r"\b(" + "|".join(SHORT_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
LONG_KEYWORDS = [kw for kw in AI_KEYWORDS if len(kw) > 3 and kw not in SHORT_KEYWORDS]


class AIRelevanceChecker:
    def __init__(self, input_path: str = "data/output/stage1_articles.json"):
        """Load articles from the Stage 1 JSON output."""
        self.input_path = Path(input_path)
        raw_articles = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.articles = [Article.model_validate(item) for item in raw_articles]
        self.matched_keywords_by_url: dict[str, list[str]] = {}

    def run(self) -> tuple[list[Article], list[Article]]:
        """
        Filter articles for AI relevance.
        Returns two lists: (relevant_articles, removed_articles)
        """
        relevant_articles: list[Article] = []
        removed_articles: list[Article] = []

        for article in self.articles:
            if self.is_relevant(article):
                relevant_articles.append(article)
            else:
                removed_articles.append(article)

        return relevant_articles, removed_articles

    def _combined_text(self, article: Article) -> str:
        return f"{article.title}\n{article.text[:500]}"

    def _get_matched_keywords(self, article: Article) -> list[str]:
        combined_text = self._combined_text(article)
        combined_text_lower = combined_text.lower()
        matched: list[str] = []

        short_matches = SHORT_KEYWORDS_REGEX.findall(combined_text)
        for short_keyword in short_matches:
            short_keyword_lower = short_keyword.lower()
            if short_keyword_lower not in matched:
                matched.append(short_keyword_lower)

        for keyword in LONG_KEYWORDS:
            if keyword.lower() in combined_text_lower and keyword not in matched:
                matched.append(keyword)

        return matched

    def is_relevant(self, article: Article) -> bool:
        """
        Check if a single article is AI-relevant.
        Checks title + first 500 characters of text for keyword matches.
        Case-insensitive. Returns True if at least one keyword matches.
        """
        matched = self._get_matched_keywords(article)
        if matched:
            self.matched_keywords_by_url[article.url] = matched
            return True
        return False

    def print_summary(self, relevant: list[Article], removed: list[Article]) -> None:
        """Print detailed filtering summary to console."""
        total = len(relevant) + len(removed)
        relevant_pct = (len(relevant) / total * 100) if total else 0
        removed_pct = (len(removed) / total * 100) if total else 0

        print("=== AI Relevance Filter ===")
        print(f"Input articles: {total}")
        print(f"AI-relevant: {len(relevant)} ({relevant_pct:.1f}%)")
        print(f"Removed: {len(removed)} ({removed_pct:.1f}%)")

    def save_results(self, relevant: list[Article], removed: list[Article]) -> None:
        """Save both lists to separate JSON files."""
        output_dir = self.input_path.parent
        relevant_path = output_dir / "relevant_articles.json"
        removed_path = output_dir / "removed_articles.json"

        relevant_json = [article.model_dump(mode="json") for article in relevant]
        removed_json = [article.model_dump(mode="json") for article in removed]

        relevant_path.write_text(
            json.dumps(relevant_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        removed_path.write_text(
            json.dumps(removed_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
