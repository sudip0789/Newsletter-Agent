"""
Deduplicate and cluster articles into story groups.

Usage:
    python scripts/run_dedup.py
    python scripts/run_dedup.py --input data/output/relevant_articles.json
    python scripts/run_dedup.py --threshold 0.60
    python scripts/run_dedup.py --recompute-embeddings
    python scripts/run_dedup.py --show-clusters
"""

from __future__ import annotations

import argparse

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._bootstrap import configure_script_environment
else:
    from ._bootstrap import configure_script_environment

configure_script_environment()

from src.dedup_cluster import Deduplicator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deduplicate and cluster relevant articles into story groups"
    )
    parser.add_argument(
        "--input",
        default="data/output/relevant_articles.json",
        help="Override the default input file path.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help=(
            "Cosine similarity threshold for clustering. "
            "Higher is stricter; lower is more aggressive."
        ),
    )
    parser.add_argument(
        "--recompute-embeddings",
        action="store_true",
        help="Ignore cached embeddings and recompute from scratch.",
    )
    parser.add_argument(
        "--show-clusters",
        action="store_true",
        help="Print all clusters with article titles and sources.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    deduplicator = Deduplicator(
        input_path=args.input,
        similarity_threshold=args.threshold,
        recompute_embeddings=args.recompute_embeddings,
        show_clusters=args.show_clusters,
    )
    clusters = deduplicator.run()
    print(f"Total Unique articles found: {len(clusters)}")


if __name__ == "__main__":
    main()
