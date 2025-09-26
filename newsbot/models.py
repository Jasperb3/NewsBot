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
