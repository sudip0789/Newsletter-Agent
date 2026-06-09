"""
Run the newsletter pipeline in serial using the existing stage runners.

Usage:
    python3 newsletter_pipeline
        Run ingestion through scoring, then stop for review.

    python3 newsletter_pipeline --date YYYY-MM-DD
        Run the entire pipeline end to end, including publish_issue.py.

    python3 newsletter_pipeline --date YYYY-MM-DD --publish-only
        Skip ingestion/scoring; run only the post-scorer steps through publish.

    python3 newsletter_pipeline --date YYYY-MM-DD --serve
        Same as above, then serve the built site locally.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

PROJECT_ROOT = configure_script_environment()
SCRIPT_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the AI newsletter pipeline. Without --date, runs ingestion "
            "through scoring and stops for review. With --date, runs the whole "
            "pipeline end to end through publish."
        )
    )

    parser.add_argument(
        "--date",
        default=None,
        help=(
            "Issue date in YYYY-MM-DD. When provided, run the full pipeline "
            "(ingestion through publish_issue.py) for this date."
        ),
    )
    parser.add_argument(
        "--publish-only",
        action="store_true",
        help=(
            "Skip ingestion/scoring and run only the post-scorer steps "
            "(summarizer, title rewriter, headline agent, archive headlines, "
            "publish). Requires --date."
        ),
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help=(
            "After publishing, serve the generated public/ site locally at "
            "http://localhost:8000/. Only applies with --date."
        ),
    )

    args = parser.parse_args()
    if args.publish_only and not args.date:
        parser.error("--publish-only requires --date YYYY-MM-DD")
    if args.serve and not args.date:
        parser.error("--serve requires --date YYYY-MM-DD")
    return args


def build_stage_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    # No date: run ingestion through scoring, then stop for review.
    if not args.date:
        return build_scoring_commands(args)
    # Date + publish-only: run just the post-scorer steps through publish.
    if args.publish_only:
        return build_publish_commands(args)
    # Date: run the whole pipeline end to end.
    return build_scoring_commands(args) + build_publish_commands(args)


def build_scoring_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []

    stage1_cmd = [sys.executable, str(SCRIPT_DIR / "run_stage1.py")]
    commands.append(("stage1_ingest", stage1_cmd))

    relevance_cmd = [sys.executable, str(SCRIPT_DIR / "run_ai_relevance_checker.py")]
    commands.append(("AI_relevance_checker", relevance_cmd))

    dedup_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "run_dedup.py"),
        "--recompute-embeddings",
    ]
    commands.append(("dedup_cluster", dedup_cmd))

    scorer_cmd = [sys.executable, str(SCRIPT_DIR / "run_scorer.py")]
    commands.append(("scorer", scorer_cmd))

    return commands


def build_publish_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    commands: list[tuple[str, list[str]]] = []

    summarizer_cmd = [sys.executable, str(SCRIPT_DIR / "run_summarizer.py")]
    commands.append(("summarizer", summarizer_cmd))

    title_rewriter_cmd = [sys.executable, str(SCRIPT_DIR / "run_title_rewriter.py")]
    commands.append(("title_rewriter", title_rewriter_cmd))

    headline_agent_cmd = [sys.executable, str(SCRIPT_DIR / "run_headline_agent.py")]
    commands.append(("headline_agent", headline_agent_cmd))

    archive_headlines_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "run_archive_headlines.py"),
        "--date",
        args.date,
    ]
    commands.append(("archive_headlines", archive_headlines_cmd))

    publish_issue_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "publish_issue.py"),
        "--date",
        args.date,
    ]
    commands.append(("publish_issue", publish_issue_cmd))

    if args.serve:
        serve_cmd = [
            sys.executable,
            "-m",
            "http.server",
            "8000",
            "--directory",
            "public",
        ]
        commands.append(("local_preview_server", serve_cmd))

    return commands


def run_stage(stage_name: str, command: list[str]) -> None:
    print(f"\n=== Running {stage_name} ===", flush=True)
    print("Command:", " ".join(command), flush=True)
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Pipeline failed during '{stage_name}' with exit code "
            f"{exc.returncode}. Command: {' '.join(command)}"
        ) from exc


def main() -> None:
    args = parse_args()
    for stage_name, command in build_stage_commands(args):
        if stage_name == "local_preview_server":
            print(
                "\nServing public/ at http://localhost:8000/ "
                "(press Ctrl-C to stop).",
                flush=True,
            )
        run_stage(stage_name, command)
    print("\nNewsletter pipeline completed successfully.", flush=True)


if __name__ == "__main__":
    main()
