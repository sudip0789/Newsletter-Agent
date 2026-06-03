from __future__ import annotations

import argparse
import unittest

from scripts import newsletter_pipeline


class TestNewsletterPipeline(unittest.TestCase):
    def _args(self, **overrides: object) -> argparse.Namespace:
        values = {
            "date": None,
            "serve": False,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_build_stage_commands_without_date_stops_after_scorer(self) -> None:
        args = self._args()

        commands = newsletter_pipeline.build_stage_commands(args)

        stage_names = [stage_name for stage_name, _command in commands]
        self.assertEqual(
            stage_names,
            [
                "stage1_ingest",
                "AI_relevance_checker",
                "dedup_cluster",
                "scorer",
            ],
        )
        self.assertIn("--recompute-embeddings", commands[2][1])

    def test_build_stage_commands_with_date_runs_publication_flow(self) -> None:
        args = self._args(date="2026-06-02")

        commands = newsletter_pipeline.build_stage_commands(args)

        stage_names = [stage_name for stage_name, _command in commands]
        self.assertEqual(
            stage_names,
            [
                "summarizer",
                "title_rewriter",
                "headline_agent",
                "publish_issue",
            ],
        )
        self.assertEqual(commands[-1][1][-2:], ["--date", "2026-06-02"])

    def test_build_stage_commands_with_date_and_serve_adds_local_server(self) -> None:
        args = self._args(date="2026-06-02", serve=True)

        commands = newsletter_pipeline.build_stage_commands(args)

        self.assertEqual(commands[-1][0], "local_preview_server")
        self.assertEqual(
            commands[-1][1],
            [
                newsletter_pipeline.sys.executable,
                "-m",
                "http.server",
                "8000",
                "--directory",
                "public",
            ],
        )


if __name__ == "__main__":
    unittest.main()
