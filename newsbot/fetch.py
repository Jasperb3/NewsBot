"""Fetch article content using Ollama web fetch with trafilatura fallback."""
from __future__ import annotations

import time
from typing import Iterable

try:  # Optional during offline testing
    from ollama import web_fetch
except ImportError:  # pragma: no cover - fallback stub
    def web_fetch(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_fetch at runtime")

try:  # Optional dependency; degrades to snippet fallback if missing
    from trafilatura import extract as _trafilatura_extract, fetch_url as _trafilatura_fetch
except ImportError:  # pragma: no cover - optional path
    _trafilatura_extract = None  # type: ignore
    _trafilatura_fetch = None  # type: ignore

from .config import AppConfig
from .models import FetchedPage, SearchHit


_MIN_CONTENT_LENGTH = 200
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0


def _try_ollama(hit: SearchHit, cfg: AppConfig, logger) -> FetchedPage | None:
    """Attempt to fetch via ollama.web_fetch with retries. Returns None on failure or short content."""
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = web_fetch(url=hit.url)
            content = (result or {}).get("content") or ""
            if len(content) < _MIN_CONTENT_LENGTH:
                logger.debug(
                    "ollama.web_fetch returned short content for %s (%s chars)",
                    hit.url,
                    len(content),
                )
                return None
            trimmed = content[: cfg.max_chars_per_page]
            return FetchedPage(
                url=hit.url,
                title=(result.get("title") or hit.title or hit.url),
                content=trimmed,
                links=list(result.get("links") or []),
                topic="",
                is_snippet=False,
                fetcher="ollama",
            )
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)

    if last_exc is not None:
        logger.debug(
            "ollama.web_fetch failed for %s after %s attempts: %s",
            hit.url,
            _MAX_RETRIES,
            last_exc,
        )
    return None


def _try_trafilatura(hit: SearchHit, cfg: AppConfig, logger) -> FetchedPage | None:
    """Attempt to fetch and extract article via trafilatura. Returns None if unavailable or extraction fails."""
    if _trafilatura_fetch is None or _trafilatura_extract is None:
        return None

    try:
        downloaded = _trafilatura_fetch(hit.url)
    except Exception as exc:
        logger.debug("trafilatura.fetch_url failed for %s: %s", hit.url, exc)
        return None

    if not downloaded:
        logger.debug("trafilatura.fetch_url returned empty payload for %s", hit.url)
        return None

    try:
        content = _trafilatura_extract(downloaded)
    except Exception as exc:
        logger.debug("trafilatura.extract failed for %s: %s", hit.url, exc)
        return None

    if not content or len(content) < _MIN_CONTENT_LENGTH:
        logger.debug(
            "trafilatura returned insufficient content for %s (%s chars)",
            hit.url,
            len(content) if content else 0,
        )
        return None

    logger.info("trafilatura recovered content for %s (%s chars)", hit.url, len(content))
    return FetchedPage(
        url=hit.url,
        title=hit.title or hit.url,
        content=content[: cfg.max_chars_per_page],
        links=[],
        topic="",
        is_snippet=False,
        fetcher="trafilatura",
    )


def _snippet_fallback(hit: SearchHit, logger) -> FetchedPage | None:
    if not hit.snippet:
        logger.error("All fetchers failed for %s and no snippet available", hit.url)
        return None
    logger.warning("Falling back to search snippet for %s", hit.url)
    return FetchedPage(
        url=hit.url,
        title=hit.title or hit.url,
        content=hit.snippet,
        links=[],
        topic="",
        is_snippet=True,
        fetcher="snippet",
    )


def _fetch_one(hit: SearchHit, cfg: AppConfig, logger) -> FetchedPage | None:
    """Fetch a single page: try ollama → trafilatura → snippet."""
    page = _try_ollama(hit, cfg, logger)
    if page is not None:
        return page

    page = _try_trafilatura(hit, cfg, logger)
    if page is not None:
        return page

    return _snippet_fallback(hit, logger)


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

    by_fetcher: dict[str, int] = {}
    for page in kept:
        by_fetcher[page.fetcher] = by_fetcher.get(page.fetcher, 0) + 1
    logger.info(
        "Fetched %s pages for '%s' (by source: %s)",
        len(kept),
        topic or "",
        ", ".join(f"{name}={count}" for name, count in sorted(by_fetcher.items())) or "none",
    )
    return kept
