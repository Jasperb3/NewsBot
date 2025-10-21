"""Data models for news-digest-bot."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SearchHit:
    title: str
    url: str
    snippet: str | None = None


@dataclass(slots=True)
class FetchedPage:
    url: str
    title: str
    content: str
    links: list[str]
    topic: str


@dataclass(slots=True)
class ClusterBullet:
    text: str
    citations: list[int]


@dataclass(slots=True)
class ClusterSummary:
    heading: str
    bullets: list[ClusterBullet]


@dataclass(slots=True)
class Story:
    headline: str
    date: str | None
    why: str
    bullets: list[str]
    source_indices: list[int]
    urls: list[str]
    updated: bool = False
    update_note: str | None = None

    def calculate_importance(self) -> float:
        """Calculate importance score (0-100) based on multiple factors."""
        score = 0.0

        # Corroboration (0-40 points): More sources = higher confidence
        corroboration = min(len(self.source_indices) * 10, 40)
        score += corroboration

        # Recency (0-30 points): Updated content is more important
        if self.updated:
            score += 30

        # Date presence (0-10 points): Stories with dates are more time-sensitive
        if self.date:
            score += 10
            # Additional recency boost for very recent dates
            try:
                import datetime as dt
                date_obj = dt.date.fromisoformat(self.date)
                days_old = (dt.date.today() - date_obj).days
                if days_old <= 7:
                    score += 10  # Very recent
                elif days_old <= 30:
                    score += 5   # Recent
            except (ValueError, ImportError):
                pass

        # Content depth (0-20 points): More bullets = more comprehensive
        bullet_score = min(len(self.bullets) * 5, 20)
        score += bullet_score

        return score


@dataclass(slots=True)
class TopicSummary:
    topic: str
    clusters: list[ClusterSummary]
    used_source_indices: list[int] = field(default_factory=list)
    unused_sources: list[tuple[str, str]] = field(default_factory=list)
    coverage_domains: int = 0
    corroborated_bullets: int = 0
    total_bullets: int = 0
    stories: list[Story] = field(default_factory=list)


@dataclass(slots=True)
class Digest:
    run_id: str
    run_time_iso: str
    timezone: str
    model: str
    topics: list[TopicSummary]
    sources: list[tuple[int, str, str]]
    elapsed_seconds: float | None = None


SourcesTable = list[tuple[int, str, str]]
