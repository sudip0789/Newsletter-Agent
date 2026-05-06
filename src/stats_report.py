from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from src.models import ScoredStory, SummarizedStory

DEFAULT_REPORT_PATH = Path("data/output/stats_report.txt")
REPORT_TITLE = "AI Newsletter Pipeline Report"


def format_count_line(label: str, count: int) -> str:
    return f"{label}: {count}"


def format_selected_stories_by_section(
    stories: Sequence[ScoredStory],
    requested_total: int = 30,
) -> str:
    grouped_titles: OrderedDict[str, list[str]] = OrderedDict()
    for story in stories:
        section_label = _format_section_name(story.section)
        grouped_titles.setdefault(section_label, []).append(
            story.cluster.primary_article.title
        )

    lines = [f"Top {requested_total} articles selected:"]
    for section_label, titles in grouped_titles.items():
        lines.append(f"{section_label}:")
        for title in titles:
            lines.append(f"- {title}")
    return "\n".join(lines)


def format_manual_review_summary(stories: Iterable[SummarizedStory]) -> str:
    flagged_titles = [
        story.scored_story.cluster.primary_article.title
        for story in stories
        if story.needs_manual_review
    ]
    if not flagged_titles:
        return "Manual review required: None"

    lines = ["Manual review required:"]
    lines.extend(f"- {title}" for title in flagged_titles)
    return "\n".join(lines)


def format_headline_selection(headlines: Sequence[dict[str, Any]]) -> str:
    lines = [f"{len(headlines)} selected headline articles:"]
    for index, headline in enumerate(headlines, start=1):
        lines.append(f"{index}. {headline.get('title', '')}")
        lines.append(f"Blurb: {headline.get('blurb', '')}")
        lines.append(
            "Headline image generated: "
            f"{headline.get('image_path') or 'None'}"
        )
    return "\n".join(lines)


def append_stage_report(
    stage_name: str,
    body: str,
    *,
    reset: bool = False,
    output_path: str | Path = DEFAULT_REPORT_PATH,
) -> Path:
    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    header = f"{REPORT_TITLE}\n{'=' * len(REPORT_TITLE)}\n\n"
    section = f"[{stage_name}]\n{body.strip()}\n"

    if reset:
        report_path.write_text(header + section + "\n", encoding="utf-8")
    else:
        with report_path.open("a", encoding="utf-8") as handle:
            if report_path.stat().st_size == 0:
                handle.write(header)
            handle.write(section + "\n")

    return report_path


def _format_section_name(section: str) -> str:
    return section.replace("_", " ").title()
