from __future__ import annotations

import json
from html import escape
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from src.text_utils import to_safe_html_text


st.set_page_config(page_title="AI Upload Review", layout="wide")


SECTION_ORDER = [
    "legal_intelligence",
    "higher_education",
    "security",
    "creative_ai",
    "enterprise_ai",
    "policy",
    "ai_sustainability",
    "responsible_ai",
    "ai_products",
    "research",
]

SECTION_COLORS = {
    "legal_intelligence": "#2563eb",
    "higher_education": "#16a34a",
    "security": "#dc2626",
    "creative_ai": "#9333ea",
    "enterprise_ai": "#ea580c",
    "policy": "#0f766e",
    "ai_sustainability": "#15803d",
    "responsible_ai": "#be185d",
    "ai_products": "#6b7280",
    "research": "#4338ca",
}

SCORE_DIMENSIONS = [
    "ai_relevance",
    "impact",
    "audience_relevance",
    "novelty",
    "source_quality",
    "buzz_momentum",
]

SUMMARY_STATUS_OPTIONS = [
    "all",
    "has summary",
    "needs summary",
    "needs manual review",
]


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .app-title {
            font-size: 1.6rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .stat-card {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 1rem;
            min-height: 104px;
        }
        .stat-label {
            color: #475569;
            font-size: 0.9rem;
            margin-bottom: 0.35rem;
        }
        .stat-value {
            color: #0f172a;
            font-size: 1.7rem;
            font-weight: 700;
            line-height: 1.1;
        }
        .section-badge {
            display: inline-block;
            color: #ffffff;
            border-radius: 999px;
            padding: 0.22rem 0.65rem;
            font-size: 0.8rem;
            font-weight: 700;
            margin-top: 0.25rem;
        }
        .article-title a {
            color: #0f172a;
            text-decoration: none;
            font-weight: 700;
            font-size: 1.15rem;
        }
        .newsletter-title {
            color: #475569;
            font-size: 0.92rem;
            margin-top: 0.25rem;
        }
        .article-title a:hover {
            text-decoration: underline;
        }
        .summary-box {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 0.9rem 1rem;
            margin-top: 0.35rem;
            white-space: pre-wrap;
        }
        .summary-note {
            background: #f3f4f6;
            border: 1px solid #d1d5db;
            color: #4b5563;
            border-radius: 12px;
            padding: 0.85rem 1rem;
            margin-top: 0.35rem;
        }
        .score-row {
            margin-bottom: 0.45rem;
        }
        .score-label {
            font-size: 0.85rem;
            color: #334155;
            margin-bottom: 0.15rem;
        }
        .score-track {
            width: 100%;
            height: 0.5rem;
            background: #e2e8f0;
            border-radius: 999px;
            overflow: hidden;
        }
        .score-fill {
            height: 100%;
            background: linear-gradient(90deg, #2563eb, #0ea5e9);
            border-radius: 999px;
        }
        .score-value {
            font-size: 0.82rem;
            color: #475569;
            margin-top: 0.12rem;
        }
        .bar-row {
            margin-bottom: 0.65rem;
        }
        .bar-label {
            display: flex;
            justify-content: space-between;
            font-size: 0.9rem;
            margin-bottom: 0.18rem;
            color: #334155;
        }
        .bar-track {
            width: 100%;
            height: 0.7rem;
            background: #e5e7eb;
            border-radius: 999px;
            overflow: hidden;
        }
        .bar-fill {
            height: 100%;
            border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def candidate_data_dirs() -> list[Path]:
    root = Path(__file__).resolve().parent
    return [
        root / "data" / "output",
        root / "newsletter-agent" / "data" / "output",
    ]


def find_data_file(filename: str) -> Path | None:
    for directory in candidate_data_dirs():
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@st.cache_data(show_spinner=False)
def load_optional_json(filename: str) -> tuple[list[dict[str, Any]], Path | None]:
    file_path = find_data_file(filename)
    if not file_path:
        return [], None
    data = load_json_file(file_path)
    return data if isinstance(data, list) else [], file_path


def parse_date(value: str | None) -> str:
    if not value:
        return "Date unavailable"
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).strftime("%B %d, %Y")
    except ValueError:
        return value


def story_url(story: dict[str, Any]) -> str:
    primary = story.get("cluster", {}).get("primary_article", {})
    return primary.get("url", "")


def normalize_summary_lookup(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for item in items:
        story = item.get("scored_story", {})
        url = story_url(story)
        if url:
            lookup[url] = item
    return lookup


def get_summary_status(article: dict[str, Any]) -> str:
    has_summary = bool((article.get("summary") or "").strip())
    manual_review = article.get("needs_manual_review", False)

    if manual_review:
        return "needs manual review"
    if has_summary:
        return "has summary"
    return "needs summary"


def format_score_breakdown(scores: dict[str, Any]) -> None:
    for dimension in SCORE_DIMENSIONS:
        score = float(scores.get(dimension, 0.0) or 0.0)
        st.markdown(
            f"""
            <div class="score-row">
                <div class="score-label">{dimension.replace("_", " ").title()}</div>
                <div class="score-track">
                    <div class="score-fill" style="width: {max(0.0, min(score, 1.0)) * 100:.0f}%;"></div>
                </div>
                <div class="score-value">{score:.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_section_chart(section_counts: Counter[str], total_articles: int) -> None:
    max_count = max(section_counts.values(), default=1)
    for section in SECTION_ORDER:
        count = section_counts.get(section, 0)
        width = 0 if max_count == 0 else (count / max_count) * 100
        color = SECTION_COLORS.get(section, "#64748b")
        st.markdown(
            f"""
            <div class="bar-row">
                <div class="bar-label">
                    <span>{section}</span>
                    <span>{count} / {total_articles}</span>
                </div>
                <div class="bar-track">
                    <div class="bar-fill" style="width: {width:.0f}%; background: {color};"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_summary(summary: str | None) -> None:
    if summary:
        st.markdown(
            f'<div class="summary-box">{to_safe_html_text(summary)}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="summary-note">Summary not yet generated</div>',
            unsafe_allow_html=True,
        )


def build_article_records(
    scored_stories: list[dict[str, Any]],
    summary_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []

    for rank, story in enumerate(
        sorted(scored_stories, key=lambda item: item.get("composite_score", 0), reverse=True),
        start=1,
    ):
        primary = story.get("cluster", {}).get("primary_article", {})
        url = primary.get("url", "")
        summary_item = summary_lookup.get(url, {})
        sources = story.get("cluster", {}).get("sources_involved", [])
        coverage_count = story.get("cluster", {}).get("coverage_count", len(sources))
        source_name = primary.get("source_name") or (sources[0] if sources else "Unknown source")
        newsletter_title = (
            summary_item.get("newsletter_title")
            or primary.get("title", "Untitled article")
        )
        summary = summary_item.get("summary") or ""

        article = {
            "rank": rank,
            "score": float(story.get("composite_score", 0.0) or 0.0),
            "title": primary.get("title", "Untitled article"),
            "newsletter_title": newsletter_title,
            "url": url,
            "source": source_name,
            "published_date": parse_date(primary.get("published_date")),
            "section": story.get("section", "unassigned"),
            "scores": story.get("scores", {}),
            "rationale": story.get("rationale", ""),
            "coverage_count": coverage_count,
            "sources": sources,
            "summary": summary,
            "needs_manual_review": bool(
                summary_item.get("needs_manual_review") or not summary.strip()
            ),
        }
        article["summary_status"] = get_summary_status(article)
        articles.append(article)

    return articles


def filtered_articles(
    articles: list[dict[str, Any]],
    section_filter: str,
    status_filter: str,
) -> list[dict[str, Any]]:
    results = articles
    if section_filter != "show all":
        results = [article for article in results if article.get("section") == section_filter]
    if status_filter != "all":
        results = [article for article in results if article.get("summary_status") == status_filter]
    return results


def render_sidebar() -> tuple[str, str, Any]:
    with st.sidebar:
        st.markdown(
            '<div class="app-title">AI Upload Weekly Digest — Review Dashboard</div>',
            unsafe_allow_html=True,
        )
        section_filter = st.selectbox(
            "Section",
            ["show all", *SECTION_ORDER],
        )
        status_filter = st.selectbox(
            "Summary status",
            SUMMARY_STATUS_OPTIONS,
        )
        count_placeholder = st.empty()
    return section_filter, status_filter, count_placeholder


def render_overview(articles: list[dict[str, Any]]) -> None:
    section_counts = Counter(article.get("section", "unassigned") for article in articles)
    summary_count = sum(1 for article in articles if (article.get("summary") or "").strip())
    missing_summary_count = len(articles) - summary_count
    manual_review_count = sum(1 for article in articles if article.get("needs_manual_review"))

    col1, col2, col3, col4 = st.columns(4)
    stats = [
        ("Total articles", str(len(articles))),
        ("Summaries available", str(summary_count)),
        ("Missing summaries", str(missing_summary_count)),
        ("Needs manual review", str(manual_review_count)),
    ]
    for col, (label, value) in zip((col1, col2, col3, col4), stats):
        with col:
            st.markdown(
                f"""
                <div class="stat-card">
                    <div class="stat-label">{label}</div>
                    <div class="stat-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("### Section Breakdown")
    render_section_chart(section_counts, len(articles))


def render_article_card(article: dict[str, Any]) -> None:
    section = article.get("section", "unassigned")
    badge_color = SECTION_COLORS.get(section, "#64748b")
    coverage_sources = ", ".join(article.get("sources") or []) or "No outlet data"

    with st.container(border=True):
        header_col, meta_col = st.columns([3, 1.2])
        with header_col:
            st.markdown(f"## #{article['rank']} — Score: {article['score']:.3f}")
            if article["url"]:
                st.markdown(
                    (
                        '<div class="article-title">'
                        f'<a href="{escape(article["url"], quote=True)}" target="_blank">{escape(article["title"])}</a>'
                        "</div>"
                    ),
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"**{article['title']}**")
            newsletter_title = article.get("newsletter_title", "").strip()
            if newsletter_title and newsletter_title != article["title"]:
                st.markdown(
                    f'<div class="newsletter-title">Newsletter title: {escape(newsletter_title)}</div>',
                    unsafe_allow_html=True,
                )
            st.caption(f"{article['source']} · {article['published_date']}")
        with meta_col:
            st.markdown(
                f'<div class="section-badge" style="background: {badge_color};">{section}</div>',
                unsafe_allow_html=True,
            )
            st.caption(article["summary_status"].replace("_", " ").title())

        score_col, details_col = st.columns([1.2, 2.3])
        with score_col:
            st.markdown("**Score breakdown**")
            format_score_breakdown(article.get("scores", {}))
        with details_col:
            rationale = article.get("rationale") or "No rationale available."
            st.markdown(
                f'<div class="summary-box"><em>{to_safe_html_text(rationale)}</em></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f"**Coverage** — Covered by {article['coverage_count']} outlets: {coverage_sources}"
            )
            if article.get("needs_manual_review"):
                st.warning("⚠️ Needs manual review before publication")

            st.markdown("**Summary**")
            render_summary(article.get("summary"))


def main() -> None:
    inject_styles()
    st.title("AI Upload Review")

    scored_stories, scored_path = load_optional_json("scored_stories.json")
    if not scored_path:
        st.info("No scored stories found. Run the pipeline first: python run_pipeline.py")
        return

    summary_items, summary_path = load_optional_json("summarized_stories.json")

    if not summary_path:
        st.info("Summaries not found. Articles without summaries will be flagged for manual review.")

    articles = build_article_records(
        scored_stories,
        normalize_summary_lookup(summary_items),
    )

    default_section = "show all"
    default_status = "all"
    section_filter, status_filter, count_placeholder = render_sidebar()
    if section_filter == "":
        section_filter = default_section
    if status_filter == "":
        status_filter = default_status

    visible_articles = filtered_articles(articles, section_filter, status_filter)
    count_placeholder.caption(f"Showing {len(visible_articles)} of {len(articles)} articles")

    render_overview(articles)
    st.markdown("---")

    if not visible_articles:
        st.info("No articles match the current filters.")
        return

    for article in visible_articles:
        render_article_card(article)


if __name__ == "__main__":
    main()
