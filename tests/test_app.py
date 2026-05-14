from __future__ import annotations

import sys
import types
import unittest

class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _cache_data(**_kwargs):
    def decorator(func):
        return func

    return decorator


streamlit_stub = types.SimpleNamespace(
    set_page_config=lambda **_kwargs: None,
    cache_data=_cache_data,
    markdown=lambda *_args, **_kwargs: None,
    selectbox=lambda *_args, **_kwargs: "",
    empty=lambda: _DummyContext(),
    columns=lambda spec: [_DummyContext() for _ in range(len(spec))],
    container=lambda **_kwargs: _DummyContext(),
    sidebar=_DummyContext(),
    caption=lambda *_args, **_kwargs: None,
    warning=lambda *_args, **_kwargs: None,
    info=lambda *_args, **_kwargs: None,
    title=lambda *_args, **_kwargs: None,
)
sys.modules.setdefault("streamlit", streamlit_stub)

from app import build_article_records


class TestAppArticleRecords(unittest.TestCase):
    def test_build_article_records_keeps_original_title_and_exposes_newsletter_title(self) -> None:
        scored_stories = [
            {
                "cluster": {
                    "primary_article": {
                        "title": "Original source title",
                        "url": "https://example.com/story",
                        "source_name": "Example Source",
                        "published_date": "2026-05-01T00:00:00+00:00",
                    },
                    "sources_involved": ["Example Source"],
                    "coverage_count": 1,
                },
                "composite_score": 0.92,
                "section": "industry",
                "scores": {"impact": 0.92},
                "rationale": "Example rationale.",
            }
        ]
        gpt_lookup = {
            "https://example.com/story": {
                "newsletter_title": "Rewritten newsletter title",
                "summary": "Generated summary",
                "needs_manual_review": False,
            }
        }
        sonnet_lookup = {
            "https://example.com/story": {
                "newsletter_title": "Alternate rewritten title",
                "summary": "Alternate summary",
                "needs_manual_review": False,
            }
        }

        articles = build_article_records(scored_stories, gpt_lookup, sonnet_lookup)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Original source title")
        self.assertEqual(articles[0]["newsletter_title"], "Rewritten newsletter title")
        self.assertEqual(articles[0]["summary_status"], "has both summaries")


if __name__ == "__main__":
    unittest.main()
