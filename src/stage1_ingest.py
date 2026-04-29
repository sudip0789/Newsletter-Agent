from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import feedparser
import httpx
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from src.models import Article
from src.utils import load_yaml_config

LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TRUNCATION_CUES = (
    "read more",
    "continue reading",
    "subscription required",
    "paywall",
    "full story",
    "see more",
)

BOILERPLATE_CUES = (
    "cookie policy",
    "privacy policy",
    "terms of service",
    "all rights reserved",
    "sign in",
    "subscribe",
    "advertisement",
)


class SourceIngestion:
    def __init__(self, config_path: str = "config/sources.yaml"):
        """Load source config (RSS URLs, NewsAPI queries)."""
        load_dotenv()
        self.config = load_yaml_config(config_path)
        self.lookback_days = int(self.config.get("lookback_days", 7))
        self.debug_completeness_signals = bool(
            self.config.get("debug_completeness_signals", False)
        )
        self.stats: dict[str, int] = defaultdict(int)

    def run(
        self,
        rss_only: bool = False,
        skip_fulltext: bool = False,
        limit: Optional[int] = None,
    ) -> list[Article]:
        """
        Run all fetchers in sequence:
        1. RSS feeds
        2. NewsAPI keyword search
        Then optionally fetch fuller text for snippet-like entries.
        Then deduplicate and return the final list.
        """
        self.stats = defaultdict(int)
        articles: list[Article] = []

        rss_articles = self.fetch_rss_feeds(limit=limit)
        articles.extend(rss_articles)

        if not rss_only:
            newsapi_articles = self.fetch_newsapi()
            articles.extend(newsapi_articles)
            self.stats["newsapi_articles"] = len(newsapi_articles)
        else:
            self.stats["newsapi_articles"] = 0

        if not skip_fulltext:
            for index, article in enumerate(articles):
                if article.text_completeness in {"snippet", "partial"}:
                    articles[index] = self.fetch_full_text(article)
                    time.sleep(0.5)

        deduped = self.deduplicate_by_url(articles)
        return deduped

    def _cutoff_datetime(self) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=self.lookback_days)

    def _parse_entry_datetime(self, entry: Any) -> Optional[datetime]:
        candidate = None
        if getattr(entry, "published_parsed", None):
            candidate = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif getattr(entry, "updated_parsed", None):
            candidate = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        return candidate

    def _extract_best_entry_text(self, entry: Any) -> tuple[str, str]:
        text_candidates: list[tuple[str, str]] = []
        title = getattr(entry, "title", "") or ""

        content = getattr(entry, "content", None) or []
        for item in content:
            value = item.get("value", "") if isinstance(item, dict) else ""
            if value:
                text_candidates.append((value, "content_encoded"))

        summary = getattr(entry, "summary", None)
        if summary:
            text_candidates.append((summary, "summary"))

        description = getattr(entry, "description", None)
        if description:
            text_candidates.append((description, "description"))

        if not text_candidates:
            return "", "snippet"

        best_raw, source_mode = max(text_candidates, key=lambda item: len(item[0]))
        best_clean = self._clean_html_text(best_raw)
        score_data = self._score_text_completeness(
            best_clean,
            title=title,
            source_mode=source_mode,
            prior_text_len=0,
        )
        label = self._label_from_score(
            score_data["score"], score_data["strong_truncation"]
        )
        self._maybe_log_completeness_debug(
            context="feed_entry",
            title=title,
            score_data=score_data,
            label=label,
        )
        return best_clean, label

    def fetch_rss_feeds(self, limit: Optional[int] = None) -> list[Article]:
        """
        Fetch from every RSS URL in config.
        Parse with feedparser and keep items within lookback window.
        """
        articles: list[Article] = []
        feeds = self.config.get("rss_feeds", [])
        if limit is not None:
            feeds = feeds[: max(0, limit)]

        cutoff = self._cutoff_datetime()
        for feed in feeds:
            feed_name = feed.get("name", "Unknown RSS")
            feed_url = feed.get("url")
            if not feed_url:
                continue

            try:
                parsed = feedparser.parse(feed_url)
                if getattr(parsed, "bozo", False):
                    raise ValueError(str(getattr(parsed, "bozo_exception", "parse error")))
            except Exception as exc:
                LOGGER.warning("RSS fetch failed for '%s': %s", feed_name, exc)
                continue

            for entry in parsed.entries:
                published_dt = self._parse_entry_datetime(entry)
                if published_dt and published_dt < cutoff:
                    continue

                title = getattr(entry, "title", "").strip()
                url = getattr(entry, "link", "").strip()
                if not title or not url:
                    continue

                text, completeness = self._extract_best_entry_text(entry)
                article = Article(
                    title=title,
                    url=url,
                    source_name=feed_name,
                    source_type="rss",
                    published_date=published_dt,
                    text=text,
                    text_completeness=completeness,
                    fetch_method="feedparser",
                )
                articles.append(article)

        self.stats["rss_articles"] = len(articles)
        return articles

    def fetch_newsapi(self) -> list[Article]:
        """
        Run NewsAPI /v2/everything queries, if key is available.
        """
        import os

        api_key = os.getenv("NEWS_API_KEY")
        if not api_key:
            LOGGER.warning("NEWS_API_KEY not found; skipping NewsAPI fetcher.")
            return []

        endpoint = "https://newsapi.org/v2/everything"
        cutoff = self._cutoff_datetime().date().isoformat()
        articles: list[Article] = []
        queries: list[str] = self.config.get("newsapi_queries", [])

        with httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
            for query in queries:
                params = {
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "from": cutoff,
                    "pageSize": 10,
                    "apiKey": api_key,
                }
                try:
                    response = client.get(endpoint, params=params)
                    response.raise_for_status()
                    payload = response.json()
                except Exception as exc:
                    LOGGER.warning("NewsAPI request failed for query '%s': %s", query, exc)
                    time.sleep(1.0)
                    continue

                for item in payload.get("articles", []):
                    url = (item.get("url") or "").strip()
                    title = (item.get("title") or "").strip()
                    if not url or not title or title == "[Removed]":
                        continue

                    published_at = item.get("publishedAt")
                    published_dt = None
                    if published_at:
                        try:
                            published_dt = datetime.fromisoformat(
                                published_at.replace("Z", "+00:00")
                            )
                        except ValueError:
                            published_dt = None

                    text = item.get("content") or item.get("description") or ""
                    cleaned = self._clean_html_text(text)
                    source_mode = "content_encoded" if item.get("content") else "description"
                    score_data = self._score_text_completeness(
                        cleaned,
                        title=title,
                        source_mode=source_mode,
                        prior_text_len=0,
                    )
                    completeness = self._label_from_score(
                        score_data["score"], score_data["strong_truncation"]
                    )
                    self._maybe_log_completeness_debug(
                        context="newsapi",
                        title=title,
                        score_data=score_data,
                        label=completeness,
                    )
                    articles.append(
                        Article(
                            title=title,
                            url=url,
                            source_name=(item.get("source") or {}).get("name", "NewsAPI"),
                            source_type="newsapi",
                            published_date=published_dt,
                            text=cleaned,
                            text_completeness=completeness,
                            fetch_method="newsapi_everything",
                        )
                    )

                time.sleep(1.0)

        return articles

    def _clean_html_text(self, text: str) -> str:
        soup = BeautifulSoup(text or "", "html.parser")
        cleaned = soup.get_text(separator=" ", strip=True)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _title_overlap_ratio(self, title: str, text: str) -> float:
        title_tokens = set(re.findall(r"[a-z0-9]+", title.lower()))
        if not title_tokens:
            return 0.0
        text_head = " ".join((text or "").lower().split()[:80])
        text_tokens = set(re.findall(r"[a-z0-9]+", text_head))
        if not text_tokens:
            return 0.0
        overlap = len(title_tokens.intersection(text_tokens))
        return overlap / max(len(title_tokens), 1)

    def _score_text_completeness(
        self,
        text: str,
        *,
        title: str = "",
        source_mode: str = "unknown",
        prior_text_len: int = 0,
    ) -> dict[str, Any]:
        cleaned = (text or "").strip()
        lowered = cleaned.lower()
        text_len = len(cleaned)

        if text_len >= 900:
            length_score = 20
        elif text_len >= 600:
            length_score = 16
        elif text_len >= 350:
            length_score = 12
        elif text_len >= 220:
            length_score = 10
        elif text_len >= 120:
            length_score = 3
        else:
            length_score = 0

        sentence_count = len(re.findall(r"[.!?]+(?=\s|$)", cleaned))
        if sentence_count >= 12:
            sentence_score = 20
        elif sentence_count >= 8:
            sentence_score = 15
        elif sentence_count >= 5:
            sentence_score = 14
        elif sentence_count >= 3:
            sentence_score = 8
        else:
            sentence_score = 0

        chunks = [
            part.strip()
            for part in re.split(r"\n\s*\n|(?<=[.!?])\s{2,}", cleaned)
            if part.strip()
        ]
        paragraph_count = sum(1 for chunk in chunks if len(chunk.split()) >= 8)
        if paragraph_count >= 6:
            paragraph_score = 10
        elif paragraph_count >= 4:
            paragraph_score = 8
        elif paragraph_count >= 2:
            paragraph_score = 5
        else:
            paragraph_score = 0

        overlap_ratio = self._title_overlap_ratio(title, cleaned)
        if overlap_ratio >= 0.35:
            title_score = 15
        elif overlap_ratio >= 0.2:
            title_score = 10
        elif overlap_ratio >= 0.1:
            title_score = 5
        else:
            title_score = 0

        source_score_map = {
            "article_tag": 15,
            "hinted_section": 12,
            "main_tag": 10,
            "paragraph_fallback": 6,
            "content_encoded": 8,
            "summary": -8,
            "description": -6,
        }
        source_score = source_score_map.get(source_mode, 0)

        boilerplate_hits = sum(1 for cue in BOILERPLATE_CUES if cue in lowered)
        boilerplate_penalty = -min(20, boilerplate_hits * 5)

        has_ellipsis_tail = cleaned.endswith("...") or cleaned.endswith("…")
        truncation_hits = sum(1 for cue in TRUNCATION_CUES if cue in lowered)
        strong_truncation = truncation_hits > 0 and (has_ellipsis_tail or "read more" in lowered)
        truncation_penalty = 0
        if strong_truncation:
            truncation_penalty = -35
        elif truncation_hits > 0 or has_ellipsis_tail:
            truncation_penalty = -15

        growth_bonus = 0
        if prior_text_len > 0 and text_len > prior_text_len:
            growth_ratio = text_len / prior_text_len
            if growth_ratio >= 2.0:
                growth_bonus = 15
            elif growth_ratio >= 1.5:
                growth_bonus = 10
            elif growth_ratio >= 1.2:
                growth_bonus = 5

        coherence_bonus = 16 if sentence_count >= 5 and boilerplate_hits == 0 else 0

        raw_score = (
            length_score
            + sentence_score
            + paragraph_score
            + title_score
            + source_score
            + boilerplate_penalty
            + truncation_penalty
            + growth_bonus
            + coherence_bonus
        )
        score = max(0, min(100, raw_score))
        return {
            "score": score,
            "strong_truncation": strong_truncation,
            "signals": {
                "length_score": length_score,
                "sentence_score": sentence_score,
                "paragraph_score": paragraph_score,
                "title_score": title_score,
                "source_score": source_score,
                "boilerplate_penalty": boilerplate_penalty,
                "truncation_penalty": truncation_penalty,
                "growth_bonus": growth_bonus,
                "coherence_bonus": coherence_bonus,
                "sentence_count": sentence_count,
                "paragraph_count": paragraph_count,
            },
        }

    def _label_from_score(self, score: int, strong_truncation: bool) -> str:
        if score >= 70 and not strong_truncation:
            return "full"
        if score >= 40:
            return "partial"
        return "snippet"

    def _maybe_log_completeness_debug(
        self,
        *,
        context: str,
        title: str,
        score_data: dict[str, Any],
        label: str,
    ) -> None:
        """Log score details for non-full and borderline entries."""
        if not self.debug_completeness_signals:
            return

        score = int(score_data.get("score", 0))
        if label == "full" and score >= 80:
            return

        LOGGER.debug(
            (
                "Completeness[%s] label=%s score=%s strong_truncation=%s "
                "title=%r signals=%s"
            ),
            context,
            label,
            score,
            score_data.get("strong_truncation", False),
            title[:120],
            score_data.get("signals", {}),
        )

    def fetch_full_text(self, article: Article) -> Article:
        """
        Attempt to replace partial/snippet content with fuller text.
        """
        if article.text_completeness == "full":
            return article

        try:
            with httpx.Client(
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(article.url)
                response.raise_for_status()
            raw = trafilatura.extract(response.text, url=article.url)
            extracted = (raw or "").strip()
            source_mode = "main_tag"
        except Exception as exc:
            LOGGER.debug("Full-text fetch failed for '%s': %s", article.url, exc)
            return article

        if not extracted:
            return article

        if len(extracted) <= len(article.text):
            return article

        score_data = self._score_text_completeness(
            extracted,
            title=article.title,
            source_mode=source_mode,
            prior_text_len=len(article.text or ""),
        )
        completeness = self._label_from_score(
            score_data["score"], score_data["strong_truncation"]
        )
        self._maybe_log_completeness_debug(
            context="fulltext_fetch",
            title=article.title,
            score_data=score_data,
            label=completeness,
        )
        return article.model_copy(
            update={
                "text": extracted,
                "text_completeness": completeness,
                "fetch_method": f"{article.fetch_method}+httpx_trafilatura",
            }
        )

    def _normalize_url(self, raw_url: str) -> str:
        parsed = urlparse(raw_url.strip())
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered = [
            (k, v)
            for k, v in query_pairs
            if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
        ]
        normalized_query = urlencode(filtered)

        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")

        normalized = parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=path,
            query=normalized_query,
            fragment="",
        )
        return urlunparse(normalized)

    def _score_article_completeness(self, article: Article) -> tuple[int, int]:
        rank = {"full": 3, "partial": 2, "snippet": 1}
        return (rank.get(article.text_completeness, 0), len(article.text or ""))

    def deduplicate_by_url(self, articles: list[Article]) -> list[Article]:
        """
        Deduplicate by normalized URL, keeping the most complete entry.
        """
        best_by_url: dict[str, Article] = {}
        for article in articles:
            key = self._normalize_url(article.url)
            existing = best_by_url.get(key)
            if not existing:
                best_by_url[key] = article
                continue
            if self._score_article_completeness(article) > self._score_article_completeness(
                existing
            ):
                best_by_url[key] = article

        return list(best_by_url.values())

    def print_summary(self, articles: list[Article]) -> None:
        """
        Print collection summary with counts and sample titles.
        """
        total = len(articles)
        by_type = Counter(a.source_type for a in articles)
        full_count = sum(1 for a in articles if a.text_completeness == "full")
        partialish_count = total - full_count

        print("=== Stage 1: Source Ingestion Complete ===")
        print(f"Total articles collected: {total}")
        print(f"  - RSS feeds: {by_type.get('rss', 0)}")
        print(f"  - NewsAPI: {by_type.get('newsapi', 0)}")
        print()

        full_pct = (full_count / total * 100) if total else 0.0
        partial_pct = (partialish_count / total * 100) if total else 0.0
        print(f"Full text retrieved: {full_count} ({full_pct:.1f}%)")
        print(f"Partial/snippet only: {partialish_count} ({partial_pct:.1f}%)")
        print()

        source_counts = Counter(a.source_name for a in articles).most_common(10)
        print("Top sources:")
        for idx, (name, count) in enumerate(source_counts, start=1):
            print(f"  {idx}. {name} ({count})")
        print()

        print("Sample titles (first 15):")
        for article in articles[:15]:
            print(
                f'  - "{article.title}" '
                f"({article.source_name}, {article.text_completeness})"
            )

    def save_results(
        self, articles: list[Article], path: str = "data/output/stage1_articles.json"
    ) -> None:
        """Save full article list to JSON. Create directories if needed."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps([article.model_dump() for article in articles], indent=2, default=str, ensure_ascii=False),
            encoding="utf-8",
        )
