"""Utility helpers for news-digest-bot."""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from typing import Iterable, List

_TRACKING_PARAM_PREFIXES = ("utm_", "icid", "gclid", "fbclid", "mc_cid", "mc_eid")


def canonicalise_url(url: str) -> str:
    """Return a normalised, comparable URL string."""
    parsed = urllib.parse.urlsplit(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    if netloc.startswith("www."):
        netloc = netloc[4:]

    hostname, sep, port = netloc.partition(":")
    if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
        netloc = hostname

    query_items = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    filtered_items = [
        (k, v)
        for k, v in query_items
        if not any(k.lower().startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES)
    ]
    query = urllib.parse.urlencode(filtered_items, doseq=True)

    normalised = urllib.parse.urlunsplit(
        (scheme, netloc, parsed.path or "/", query, "")
    )
    return normalised


def domain_of(url: str) -> str:
    """Extract the registrable domain from a URL (best-effort)."""
    parsed = urllib.parse.urlsplit(url.strip())
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def split_and_strip_csv(value: str | None) -> list[str]:
    """Split a comma-separated string into a list of trimmed items."""
    if not value:
        return []
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


_ISO_DATE_PATTERN = re.compile(r"(20\d{2}|19\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])")


def extract_iso_dates(text: str) -> list[dt.date]:
    """Find ISO-like dates within text."""
    dates: list[dt.date] = []
    for match in _ISO_DATE_PATTERN.finditer(text):
        year, month, day = match.group(1), match.group(2), match.group(3)
        try:
            dates.append(dt.date(int(year), int(month), int(day)))
        except ValueError:
            continue
    return dates


def chunk_texts_by_char_limit(texts: list[str], max_chars: int) -> list[list[str]]:
    """Batch strings so that each batch stays below ``max_chars`` characters."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_len = 0

    for text in texts:
        text_len = len(text)
        if text_len > max_chars:
            # Split excessively long single entries into their own batch pieces
            for start in range(0, text_len, max_chars):
                chunk = text[start : start + max_chars]
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_len = 0
                batches.append([chunk])
            continue

        if current_len + text_len > max_chars and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_len = 0

        current_batch.append(text)
        current_len += text_len

    if current_batch:
        batches.append(current_batch)

    return batches
