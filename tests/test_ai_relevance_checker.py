import json
import tempfile
import unittest
from pathlib import Path

from src.AI_relevance_checker import AIRelevanceChecker


class TestAIRelevanceChecker(unittest.TestCase):
    def _write_articles(self, directory: str, articles: list[dict]) -> Path:
        path = Path(directory) / "stage1_articles.json"
        path.write_text(json.dumps(articles), encoding="utf-8")
        return path

    def _article(self, title: str, text: str) -> dict:
        return {
            "title": title,
            "url": "https://example.com/article",
            "source_name": "Example",
            "source_type": "rss",
            "published_date": None,
            "text": text,
            "text_completeness": "full",
            "fetch_method": "rss",
        }

    def test_short_keyword_uses_word_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = self._write_articles(
                tmpdir,
                [
                    self._article(
                        title="General tech update",
                        text="This email roundup said the wait was fair.",
                    )
                ],
            )
            checker = AIRelevanceChecker(input_path=str(input_path))
            relevant, removed = checker.run()

            self.assertEqual(len(relevant), 0)
            self.assertEqual(len(removed), 1)

    def test_relevant_when_long_keyword_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = self._write_articles(
                tmpdir,
                [
                    self._article(
                        title="OpenAI launches a new model",
                        text="Details on rollout and capabilities.",
                    )
                ],
            )
            checker = AIRelevanceChecker(input_path=str(input_path))
            relevant, removed = checker.run()

            self.assertEqual(len(relevant), 1)
            self.assertEqual(len(removed), 0)


if __name__ == "__main__":
    unittest.main()
