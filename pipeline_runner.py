"""
Run the full newsletter pipeline in serial using the existing stage runners.

Usage:
    python pipeline_runner.py
    python pipeline_runner.py --rss-only --skip-fulltext --limit 5
    python pipeline_runner.py --threshold 0.7 --show-clusters
    python pipeline_runner.py --top 10 --model sonnet-4.6
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


RUNNER_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full AI newsletter pipeline in serial."
    )

    parser.add_argument(
        "--rss-only",
        action="store_true",
        help="Only fetch RSS feeds during stage 1.",
    )
    parser.add_argument(
        "--skip-fulltext",
        action="store_true",
        help="Skip full text retrieval during stage 1.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N RSS feeds during stage 1.",
    )
    parser.add_argument(
        "--show-removed",
        action="store_true",
        help="Print removed article titles during AI relevance filtering.",
    )
    parser.add_argument(
        "--show-matched-keywords",
        action="store_true",
        help="Print matched keywords for relevant articles.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Override the deduplication similarity threshold.",
    )
    parser.add_argument(
        "--recompute-embeddings",
        action="store_true",
        help="Recompute embeddings instead of using any cached values.",
    )
    parser.add_argument(
        "--show-clusters",
        action="store_true",
        help="Print full cluster contents after deduplication.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Shared top-N value for both scoring selection and summarization.",
    )
    parser.add_argument(
        "--show-all-scores",
        action="store_true",
        help="Print scores for all successfully scored stories.",
    )
    parser.add_argument(
        "--model",
        choices=["gpt-5.4", "sonnet-4.6"],
        default=None,
        help="Summarization model to use for the final stage.",
    )
    return parser.parse_args()


def build_stage_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []

    stage1_cmd = [sys.executable, "run_stage1.py"]
    if args.rss_only:
        stage1_cmd.append("--rss-only")
    if args.skip_fulltext:
        stage1_cmd.append("--skip-fulltext")
    if args.limit is not None:
        stage1_cmd.extend(["--limit", str(args.limit)])
    commands.append(("stage1_ingest", stage1_cmd))

    relevance_cmd = [sys.executable, "run_ai_relevance_checker.py"]
    if args.show_removed:
        relevance_cmd.append("--show-removed")
    if args.show_matched_keywords:
        relevance_cmd.append("--show-matched-keywords")
    commands.append(("AI_relevance_checker", relevance_cmd))

    dedup_cmd = [sys.executable, "run_dedup.py"]
    if args.threshold is not None:
        dedup_cmd.extend(["--threshold", str(args.threshold)])
    if args.recompute_embeddings:
        dedup_cmd.append("--recompute-embeddings")
    if args.show_clusters:
        dedup_cmd.append("--show-clusters")
    commands.append(("dedup_cluster", dedup_cmd))

    scorer_cmd = [sys.executable, "run_scorer.py"]
    if args.top is not None:
        scorer_cmd.extend(["--top", str(args.top)])
    if args.show_all_scores:
        scorer_cmd.append("--show-all-scores")
    commands.append(("scorer", scorer_cmd))

    summarizer_cmd = [sys.executable, "run_summarizer.py"]
    if args.top is not None:
        summarizer_cmd.extend(["--top", str(args.top)])
    if args.model is not None:
        summarizer_cmd.extend(["--model", args.model])
    commands.append(("summarizer", summarizer_cmd))

    return commands


def run_stage(stage_name: str, command: list[str]) -> None:
    print(f"\n=== Running {stage_name} ===", flush=True)
    print("Command:", " ".join(command), flush=True)
    try:
        subprocess.run(command, cwd=RUNNER_DIR, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Pipeline failed during '{stage_name}' with exit code "
            f"{exc.returncode}. Command: {' '.join(command)}"
        ) from exc


def main() -> None:
    args = parse_args()
    for stage_name, command in build_stage_commands(args):
        run_stage(stage_name, command)
    print("\nPipeline completed successfully.", flush=True)


if __name__ == "__main__":
    main()
