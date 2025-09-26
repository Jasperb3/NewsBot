"""Data models for news-digest-bot."""
from __future__ import annotations

from dataclasses import dataclass


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
class TopicSummary:
    topic: str
    clusters: list[ClusterSummary]


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
