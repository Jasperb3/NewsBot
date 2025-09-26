"""Fetch article content using Ollama web fetch."""
from __future__ import annotations

from typing import Iterable

from ollama import web_fetch

from .config import AppConfig
from .models import FetchedPage, SearchHit


_MIN_CONTENT_LENGTH = 200


def fetch_pages(hits: list[SearchHit], cfg: AppConfig, logger, topic: str | None = None) -> list[FetchedPage]:
    """Retrieve pages for the provided search hits."""
    kept: list[FetchedPage] = []
    limit = min(cfg.fetch_limit_per_topic, len(hits))

    if not hits:
        logger.warning("No hits available to fetch for topic '%s'", topic or "")
        return kept

    logger.info("Fetching up to %s pages for '%s' …", limit, topic or hits[0].title)

    for position, hit in enumerate(hits[:limit], start=1):
        try:
            result = web_fetch(url=hit.url)
        except Exception as exc:  # pragma: no cover - network path
            logger.error("web_fetch failed for %s: %s", hit.url, exc)
            continue

        content = (result or {}).get("content") or ""
        if len(content) < _MIN_CONTENT_LENGTH:
            logger.debug("Skipping %s due to short content (%s chars)", hit.url, len(content))
            continue

        trimmed_content = content[: cfg.max_chars_per_page]
        page = FetchedPage(
            url=hit.url,
            title=(result.get("title") or hit.title or hit.url),
            content=trimmed_content,
            links=list(result.get("links") or []),
            topic=topic or "",
        )
        kept.append(page)

    logger.info("Fetched %s pages for '%s'", len(kept), topic or "")
    return kept
