"""Triage logic for fetched pages."""
from __future__ import annotations

import datetime as dt
from typing import List

from .models import FetchedPage
from .utils import domain_of, extract_iso_dates


def _normalise_title(title: str) -> str:
    return "".join(ch.lower() for ch in title if ch.isalnum())


def dedupe_by_title(pages: list[FetchedPage]) -> list[FetchedPage]:
    """Drop pages with near-duplicate titles."""
    seen: set[str] = set()
    unique: list[FetchedPage] = []
    for page in pages:
        key = _normalise_title(page.title)
        if key in seen:
            continue
        seen.add(key)
        unique.append(page)
    return unique


def ensure_domain_diversity(pages: list[FetchedPage], min_domains: int = 2) -> list[FetchedPage]:
    """Ensure that a mix of domains are represented, best-effort."""
    if not pages or min_domains <= 1:
        return pages

    selected: list[FetchedPage] = []
    seen_domains: set[str] = set()
    for page in pages:
        domain = domain_of(page.url)
        if domain not in seen_domains:
            selected.append(page)
            seen_domains.add(domain)

    if len(seen_domains) >= min_domains:
        return selected

    for page in pages:
        if page in selected:
            continue
        selected.append(page)
        seen_domains.add(domain_of(page.url))
        if len(seen_domains) >= min_domains:
            break

    return selected


def order_by_recency_hint(pages: list[FetchedPage]) -> list[FetchedPage]:
    """Sort pages by the most recent ISO date mentioned in title/content."""
    scored: list[tuple[dt.date | None, FetchedPage]] = []
    for page in pages:
        snippet = f"{page.title}\n{page.content[:1000]}"
        dates = extract_iso_dates(snippet)
        scored.append((max(dates) if dates else None, page))

    scored.sort(key=lambda item: item[0] or dt.date.min, reverse=True)
    return [page for _, page in scored]


def triage_pages(pages: list[FetchedPage]) -> list[FetchedPage]:
    """Apply dedupe, domain diversity, and recency ordering."""
    deduped = dedupe_by_title(pages)
    diverse = ensure_domain_diversity(deduped)
    ordered = order_by_recency_hint(diverse)
    return ordered
