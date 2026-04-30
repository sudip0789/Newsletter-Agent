"""
Deduplicate and cluster articles into story groups.

Usage:
    python run_dedup.py
    python run_dedup.py --input data/output/relevant_articles.json
    python run_dedup.py --threshold 0.60
    python run_dedup.py --recompute-embeddings
    python run_dedup.py --show-clusters
"""

from __future__ import annotations

import argparse

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
    deduplicator.run()


if __name__ == "__main__":
    main()
