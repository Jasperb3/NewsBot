"""Fetch article content using Ollama web fetch."""
from __future__ import annotations

import time
from typing import Iterable

try:  # Optional during offline testing
    from ollama import web_fetch
except ImportError:  # pragma: no cover - fallback stub
    def web_fetch(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_fetch at runtime")

from .config import AppConfig
from .models import FetchedPage, SearchHit


_MIN_CONTENT_LENGTH = 200
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0


def _fetch_one(hit: SearchHit, cfg: AppConfig, logger) -> FetchedPage | None:
    """Fetch a single page with retries, falling back to snippet on total failure."""
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = web_fetch(url=hit.url)
            content = (result or {}).get("content") or ""
            if len(content) < _MIN_CONTENT_LENGTH:
                logger.debug("Skipping %s due to short content (%s chars)", hit.url, len(content))
                break  # Short content is not a transient error; don't retry
            trimmed = content[: cfg.max_chars_per_page]
            return FetchedPage(
                url=hit.url,
                title=(result.get("title") or hit.title or hit.url),
                content=trimmed,
                links=list(result.get("links") or []),
                topic="",
                is_snippet=False,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    # Snippet fallback: use whatever text the search engine returned
    if hit.snippet:
        logger.warning("web_fetch failed for %s; using snippet fallback", hit.url)
        return FetchedPage(
            url=hit.url,
            title=hit.title or hit.url,
            content=hit.snippet,
            links=[],
            topic="",
            is_snippet=True,
        )

    logger.error("web_fetch failed for %s after %s attempts: %s", hit.url, _MAX_RETRIES, last_exc)
    return None


def fetch_pages(hits: list[SearchHit], cfg: AppConfig, logger, topic: str | None = None) -> list[FetchedPage]:
    """Retrieve pages for the provided search hits."""
    kept: list[FetchedPage] = []
    limit = min(cfg.fetch_limit_per_topic, len(hits))

    if not hits:
        logger.warning("No hits available to fetch for topic '%s'", topic or "")
        return kept

    logger.info("Fetching up to %s pages for '%s' …", limit, topic or hits[0].title)

    for hit in hits[:limit]:
        page = _fetch_one(hit, cfg, logger)
        if page is not None:
            page.topic = topic or ""
            kept.append(page)

    logger.info("Fetched %s pages for '%s'", len(kept), topic or "")
    return kept
