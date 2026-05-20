from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_scored_story_viewer import main


class TestRunScoredStoryViewer(unittest.TestCase):
    def test_main_writes_requested_fields_sorted_by_buzz_momentum(self) -> None:
        stories = [
            {
                "cluster": {
                    "primary_article": {
                        "title": "Second story",
                    }
                },
                "scores": {
                    "ai_relevance": 0.7,
                    "buzz_momentum": 0.4,
                },
                "composite_score": 0.61,
                "section": "policy",
                "tier": "body",
            },
            {
                "cluster": {
                    "primary_article": {
                        "title": "Top story",
                    }
                },
                "scores": {
                    "ai_relevance": 0.9,
                    "buzz_momentum": 0.95,
                },
                "composite_score": 0.91,
                "section": "enterprise_ai",
                "tier": "headline",
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scored_stories.json"
            output_path = Path(tmpdir) / "scored_story_view.json"
            input_path.write_text(json.dumps(stories), encoding="utf-8")
            stdout = io.StringIO()

            with patch("sys.stdout", stdout):
                main([str(input_path), "--output", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(
            payload,
            [
                {
                    "rank": 1,
                    "title": "Top story",
                    "scores": {
                        "ai_relevance": 0.9,
                        "buzz_momentum": 0.95,
                    },
                    "composite_score": 0.91,
                    "section": "enterprise_ai",
                },
                {
                    "rank": 2,
                    "title": "Second story",
                    "scores": {
                        "ai_relevance": 0.7,
                        "buzz_momentum": 0.4,
                    },
                    "composite_score": 0.61,
                    "section": "policy",
                },
            ],
        )

    def test_main_writes_payload_to_output_file(self) -> None:
        stories = [
            {
                "cluster": {
                    "primary_article": {
                        "title": "Saved story",
                    }
                },
                "scores": {
                    "ai_relevance": 0.8,
                    "buzz_momentum": 0.7,
                },
                "composite_score": 0.72,
                "section": "creative_ai",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scored_stories.json"
            output_path = Path(tmpdir) / "ranked_stories.json"
            input_path.write_text(json.dumps(stories), encoding="utf-8")

            main([str(input_path), "--output", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(
            payload,
            [
                {
                    "rank": 1,
                    "title": "Saved story",
                    "scores": {
                        "ai_relevance": 0.8,
                        "buzz_momentum": 0.7,
                    },
                    "composite_score": 0.72,
                    "section": "creative_ai",
                }
            ],
        )

    def test_main_prints_payload_only_when_requested(self) -> None:
        stories = [
            {
                "cluster": {
                    "primary_article": {
                        "title": "Printed story",
                    }
                },
                "scores": {
                    "buzz_momentum": 0.9,
                },
                "composite_score": 0.8,
                "section": "enterprise_ai",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "scored_stories.json"
            output_path = Path(tmpdir) / "scored_story_view.json"
            input_path.write_text(json.dumps(stories), encoding="utf-8")
            stdout = io.StringIO()

            with patch("sys.stdout", stdout):
                main([str(input_path), "--output", str(output_path), "--print"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload[0]["rank"], 1)
        self.assertEqual(payload[0]["title"], "Printed story")


if __name__ == "__main__":
    unittest.main()
