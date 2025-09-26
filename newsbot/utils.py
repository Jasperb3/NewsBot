"""Utility helpers for news-digest-bot."""
from __future__ import annotations

import datetime as dt
import re
import urllib.parse
from typing import Iterable, List, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - for type hints only
    from .models import ClusterBullet, ClusterSummary

_TRACKING_PARAM_PREFIXES = ("utm_", "icid", "gclid", "fbclid", "mc_cid", "mc_eid")
_TELEMETRY_PATTERN = re.compile(r"^\s*(?:\w+=[^\s]+(?:\s+|$)){3,}")
_TRAILING_CITATIONS_RE = re.compile(r"(\s*(\[[0-9]+\]))+$")
_DATE_IN_LINE = re.compile(r"\b(20\d{2}|19\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b")


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


def strip_telemetry_lines(text: str) -> str:
    """Remove lines that resemble telemetry/log output from the model response."""

    if not text:
        return ""

    artefact_keywords = (
        "message=Message(",
        "tool_calls=",
        "images=",
        "metadata=",
        "usage=",
        "created_at=",
        "total_duration=",
        "eval_count=",
    )
    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if _TELEMETRY_PATTERN.match(stripped):
            continue
        lowered = stripped.lower()
        if any(keyword in stripped for keyword in artefact_keywords):
            continue
        if lowered.startswith(("assistant:", "system:", "thinking:", "message(", "tool:", "tools:")):
            continue
        if stripped.startswith("<<<") or stripped.startswith(">>>"):
            continue
        cleaned.append(stripped)

    while cleaned and cleaned[0].startswith("```"):
        cleaned.pop(0)
    while cleaned and cleaned[-1].startswith("```"):
        cleaned.pop()

    # Collapse successive blanks to single blank lines.
    normalised: list[str] = []
    previous_blank = False
    for line in cleaned:
        if not line:
            if not previous_blank:
                normalised.append("")
            previous_blank = True
        else:
            normalised.append(line)
            previous_blank = False

    return "\n".join(normalised).strip()


def collect_used_citations(clusters: Sequence["ClusterSummary"]) -> set[int]:
    """Collect unique citation indices referenced across clusters."""

    used: set[int] = set()
    for cluster in clusters:
        for bullet in cluster.bullets:
            used.update(bullet.citations)
    return used


def citations_to_domains(
    citations: Iterable[int],
    sources_lookup: dict[int, tuple[str, str]],
) -> set[str]:
    """Map citation indices to their domains."""

    domains: set[str] = set()
    for idx in citations:
        if idx in sources_lookup:
            _, url = sources_lookup[idx]
            domains.add(domain_of(url))
    return domains


def extract_dates_from_bullets(bullets: Sequence["ClusterBullet"]) -> list[tuple[dt.date, "ClusterBullet"]]:
    """Extract ISO-like dates from bullet text, returning sorted pairs."""

    dated: list[tuple[dt.date, "ClusterBullet"]] = []
    for bullet in bullets:
        dates = extract_iso_dates(bullet.text)
        if not dates:
            continue
        dated.append((max(dates), bullet))
    dated.sort(key=lambda item: item[0], reverse=True)
    return dated


def ensure_citation_suffix(text: str, citations: Sequence[int]) -> str:
    """Ensure the bullet text ends with its citation markers."""

    if not citations:
        return text.strip()
    markers = "".join(f"[{idx}]" for idx in citations)
    stripped = text.rstrip()
    if stripped.endswith(markers):
        return stripped
    stripped = _TRAILING_CITATIONS_RE.sub("", stripped).rstrip()
    return f"{stripped} {markers}".strip()


def normalise_spaces(text: str) -> str:
    """Collapse repeated whitespace and trim surrounding spaces."""

    return re.sub(r"\s+", " ", text or "").strip()


def truncate_sentence(text: str, max_chars: int) -> str:
    """Truncate text at word boundaries, appending ellipsis if needed."""

    if max_chars <= 0:
        return ""
    clean = normalise_spaces(text)
    if len(clean) <= max_chars:
        return clean
    words = clean.split()
    acc: list[str] = []
    length = 0
    for word in words:
        pending = (length + len(word) + (1 if acc else 0))
        if pending > max_chars:
            break
        acc.append(word)
        length = pending
    if not acc:
        return clean[: max_chars - 1] + "…"
    return " ".join(acc).rstrip(".,;:") + "…"


def strip_trailing_citations(text: str) -> str:
    """Remove trailing citation markers from text."""

    return _TRAILING_CITATIONS_RE.sub("", text or "").strip()


def to_title_case(text: str) -> str:
    """Convert text to basic title case while preserving acronyms."""

    words = text.split()
    titled: list[str] = []
    for word in words:
        if len(word) >= 3 and word.isupper():
            titled.append(word)
        else:
            titled.append(word.capitalize())
    return " ".join(titled)


def sorted_domains(domains: Iterable[str]) -> list[str]:
    """Return sorted unique domains from an iterable."""

    return sorted({domain for domain in domains if domain})


def first_sentence(text: str) -> str:
    """Return the first sentence-like fragment from text."""

    cleaned = normalise_spaces(text)
    match = re.search(r"([^.?!]+[.?!])", cleaned)
    return (match.group(1) if match else cleaned).strip()
