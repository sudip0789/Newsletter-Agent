from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class Article(BaseModel):
    title: str
    url: str
    source_name: str
    source_type: str
    published_date: Optional[datetime]
    text: str
    text_completeness: str
    fetch_method: str

    model_config = ConfigDict(
        json_encoders={datetime: lambda dt: dt.isoformat() if dt else None}
    )


class StoryCluster(BaseModel):
    cluster_id: str
    primary_article: Article
    all_articles: list[Article]
    coverage_count: int
    sources_involved: list[str]


class ScoredStory(BaseModel):
    cluster: StoryCluster
    scores: dict[str, float]
    composite_score: float
    rationale: str
    section: str
    tier: str


class SummarizedStory(BaseModel):
    scored_story: ScoredStory
    summary: str
    needs_manual_review: bool = False
