from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from sklearn.cluster import AgglomerativeClustering

from src.models import Article, StoryCluster


class Deduplicator:
    def __init__(
        self,
        input_path: str = "data/output/relevant_articles.json",
        similarity_threshold: float = 0.60,
        recompute_embeddings: bool = False,
        show_clusters: bool = False,
    ):
        """Load articles from relevance checker output and init embedding client."""
        load_dotenv()
        self.input_path = Path(input_path)
        self.output_dir = self.input_path.parent
        self.embeddings_path = self.output_dir / "embeddings.npy"
        self.clustered_path = self.output_dir / "clustered_stories.json"
        self.similarity_threshold = similarity_threshold
        self.distance_threshold = 1 - similarity_threshold
        self.recompute_embeddings = recompute_embeddings
        self.show_clusters = show_clusters

        raw_articles = json.loads(self.input_path.read_text(encoding="utf-8"))
        self.articles = [Article.model_validate(item) for item in raw_articles]
        self.client = OpenAI()

    def run(self) -> list[StoryCluster]:
        """
        Full pipeline:
        1. Remove exact URL duplicates
        2. Generate embeddings for all articles
        3. Cluster by cosine similarity
        4. Select best article per cluster
        Return list of StoryCluster objects.
        """
        deduped_articles = self.deduplicate_urls(self.articles)
        embeddings = self.generate_embeddings(deduped_articles)
        clusters = self.cluster_articles(deduped_articles, embeddings)
        self.save_results(clusters)
        self.print_summary(
            articles_before=len(self.articles),
            articles_after_dedup=len(deduped_articles),
            clusters=clusters,
        )

        if self.show_clusters:
            print("\n=== Cluster Details ===")
            for cluster in clusters:
                print(f"{cluster.cluster_id} ({cluster.coverage_count} articles)")
                for article in cluster.all_articles:
                    print(f"  - [{article.source_name}] {article.title}")

        return clusters

    def deduplicate_urls(self, articles: list[Article]) -> list[Article]:
        """
        Remove exact URL duplicates.
        Normalize URLs before comparison:
        - Strip trailing slashes
        - Remove utm_* query parameters
        - Remove www. prefix
        - Lowercase the domain portion
        When duplicates exist, keep the version with the longest text.
        """
        by_normalized_url: dict[str, Article] = {}
        for article in articles:
            normalized = self._normalize_url(article.url)
            existing = by_normalized_url.get(normalized)
            if existing is None or len(article.text or "") > len(existing.text or ""):
                by_normalized_url[normalized] = article
        return list(by_normalized_url.values())

    def generate_embeddings(self, articles: list[Article]) -> np.ndarray:
        """
        Generate embeddings for each article using OpenAI's API.

        Text to embed per article: title + " " + first 300 characters of text.
        Model: "text-embedding-3-small"

        Batch API calls in groups of 100

        Cache the resulting numpy array to data/output/embeddings.npy
        so re-runs don't recompute. Only recompute if --recompute-embeddings
        flag is passed or the cache file doesn't exist.
        """
        if (
            not self.recompute_embeddings
            and self.embeddings_path.exists()
            and len(articles) > 0
        ):
            cached = np.load(self.embeddings_path)
            if cached.shape[0] == len(articles):
                return cached

        if not articles:
            return np.array([])

        texts = [f"{a.title} {a.text[:300]}".strip() for a in articles]
        vectors: list[list[float]] = []
        batch_size = 100

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model="text-embedding-3-small",
                input=batch,
            )
            vectors.extend([item.embedding for item in response.data])

        embeddings = np.array(vectors, dtype=np.float32)
        np.save(self.embeddings_path, embeddings)
        return embeddings

    def cluster_articles(
        self, articles: list[Article], embeddings: np.ndarray
    ) -> list[StoryCluster]:
        """
        1. Compute cosine similarity matrix from embeddings.
        2. Use AgglomerativeClustering from scikit-learn:
           - metric='cosine'
           - linkage='average'
           - distance_threshold=0.30 (i.e. similarity > 0.70 = same story)
           - n_clusters=None (let the algorithm decide cluster count)
        3. Group articles by their cluster label.
        4. For each group, call select_primary_article() to pick the best one.
        5. Return list of StoryCluster objects.
        """
        if not articles:
            return []

        if len(articles) == 1:
            article = articles[0]
            return [
                StoryCluster(
                    cluster_id="cluster_001",
                    primary_article=article,
                    all_articles=[article],
                    coverage_count=1,
                    sources_involved=[article.source_name],
                )
            ]

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        safe_norms = np.clip(norms, 1e-12, None)
        normalized_embeddings = embeddings / safe_norms
        _similarity_matrix = normalized_embeddings @ normalized_embeddings.T

        model = AgglomerativeClustering(
            metric="cosine",
            linkage="average",
            distance_threshold=self.distance_threshold,
            n_clusters=None,
        )
        labels = model.fit_predict(embeddings)
        grouped: dict[int, list[Article]] = defaultdict(list)
        for idx, label in enumerate(labels):
            grouped[int(label)].append(articles[idx])

        sorted_groups = sorted(
            grouped.values(),
            key=lambda group: (-len(group), group[0].title.lower()),
        )

        clusters: list[StoryCluster] = []
        for idx, group_articles in enumerate(sorted_groups, start=1):
            primary = self.select_primary_article(group_articles)
            sources = sorted({article.source_name for article in group_articles})
            clusters.append(
                StoryCluster(
                    cluster_id=f"cluster_{idx:03d}",
                    primary_article=primary,
                    all_articles=group_articles,
                    coverage_count=len(sources),
                    sources_involved=sources,
                )
            )
        return clusters

    def select_primary_article(self, articles: list[Article]) -> Article:
        """
        Pick the best representative article from a cluster.
        Score each article and pick the highest:

        1. Text completeness: full=3, partial=2, snippet=1
        2. Text length: longer articles score higher (normalize to 0-2 range)

        Composite: text_completeness + text_length_score
        Highest composite wins.
        """
        if len(articles) == 1:
            return articles[0]

        completeness_scores = {"full": 3.0, "partial": 2.0, "snippet": 1.0}
        lengths = [len(article.text or "") for article in articles]
        max_len = max(lengths) if lengths else 0

        best_article = articles[0]
        best_score = -1.0
        for article, text_len in zip(articles, lengths):
            completeness = completeness_scores.get(article.text_completeness, 0.0)
            length_score = (text_len / max_len * 2.0) if max_len > 0 else 0.0
            score = completeness + length_score
            if score > best_score:
                best_score = score
                best_article = article

        return best_article

    def print_summary(
        self,
        articles_before: int,
        articles_after_dedup: int,
        clusters: list[StoryCluster],
    ) -> None:
        """Print detailed summary to console."""
        cluster_sizes = Counter(len(cluster.all_articles) for cluster in clusters)
        one_article = cluster_sizes.get(1, 0)
        two_articles = cluster_sizes.get(2, 0)
        three_to_five = sum(
            count for size, count in cluster_sizes.items() if 3 <= size <= 5
        )

        print("=== Deduplication & Clustering Complete ===")
        print(f"Input articles: {articles_before}")
        print(f"After URL dedup: {articles_after_dedup}")
        print(f"Story clusters formed: {len(clusters)}")
        print("\nClusters by size:")
        print(f"  - 1 article (unique stories): {one_article}")
        print(f"  - 2 articles: {two_articles}")
        print(f"  - 3-5 articles: {three_to_five}")
        print("\nResults saved:")
        print(f"  - {self.clustered_path} ({len(clusters)} clusters)")
        print(f"  - {self.embeddings_path} (cached)")

    def save_results(self, clusters: list[StoryCluster]) -> None:
        """Save to data/output/clustered_stories.json with ensure_ascii=False."""
        payload = [cluster.model_dump(mode="json") for cluster in clusters]
        self.clustered_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _normalize_url(self, url: str) -> str:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        if hostname.startswith("www."):
            hostname = hostname[4:]
        netloc = hostname
        if parsed.port:
            netloc = f"{hostname}:{parsed.port}"

        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_pairs = [
            (key, value)
            for key, value in query_pairs
            if not key.lower().startswith("utm_")
        ]
        query = urlencode(filtered_pairs, doseq=True)

        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        return urlunparse(
            (
                parsed.scheme.lower(),
                netloc,
                path,
                parsed.params,
                query,
                parsed.fragment,
            )
        )
