"""Topic summarisation using Ollama chat."""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Iterable, List, Sequence, Tuple

try:  # Optional during offline testing
    from ollama import chat, web_fetch, web_search
except ImportError:  # pragma: no cover - fallback stub
    def chat(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for chat at runtime")

    def web_search(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_search at runtime")

    def web_fetch(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_fetch at runtime")

from .config import AppConfig
from .models import ClusterBullet, ClusterSummary, FetchedPage, Story, TopicSummary
from .prompts import (
    JSON_SYSTEM_PROMPT,
    JSON_USER_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)
from .utils import (
    chunk_texts_by_char_limit,
    ensure_citation_suffix,
    ensure_headline_case,
    extract_iso_dates,
    normalise_spaces,
    strip_code_fences,
    strip_telemetry_lines,
    strip_trailing_citations,
    truncate_sentence,
)

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")
_HEADING_PATTERN = re.compile(r"^(#+)\s+(.*)")
_BOLD_HEADING_PATTERN = re.compile(r"^\*\*(.+?)\*\*\s*$")
_NON_MARKDOWN_FENCE = re.compile(r"^(```|~~~)")
_MAX_CLUSTER_BULLET_CHARS = 320


def _extract_message_content(response: Any) -> str:
    """Safely extract assistant content from an Ollama chat response."""

    if hasattr(response, "message"):
        message = getattr(response, "message")
        if message is not None:
            content = getattr(message, "content", None)
            if content:
                return content
            if isinstance(message, dict):
                content = message.get("content")
                if content:
                    return content
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if content:
                return content
        content = response.get("content")
        if content:
            return content
    return ""


def _sanitise_json_text(text: str) -> str:
    cleaned = strip_telemetry_lines(text)
    cleaned = strip_code_fences(cleaned)
    return cleaned.strip()


def _make_excerpt(text: str, max_chars: int) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    excerpt_parts: list[str] = []
    running_len = 0
    for sentence in sentences:
        if not sentence:
            continue
        sentence = sentence.strip()
        if running_len + len(sentence) > max_chars:
            if not excerpt_parts:
                return sentence[:max_chars]
            break
        excerpt_parts.append(sentence)
        running_len += len(sentence) + 1
    return " ".join(excerpt_parts)[:max_chars]


def _sources_block(pages: Sequence[FetchedPage], max_chars: int) -> tuple[str, list[tuple[int, str, str]]]:
    rows: list[str] = []
    mapping: list[tuple[int, str, str]] = []
    excerpts: list[str] = []
    for idx, page in enumerate(pages, start=1):
        excerpt = _make_excerpt(page.content, max_chars)
        excerpts.append(excerpt)
        rows.append(
            f"{idx}. {page.title} — {page.url}\n\"\"\"\n{excerpt}\n\"\"\""
        )
        mapping.append((idx, page.title, page.url))

    block = "\n\n".join(rows)
    if len(block) > max_chars:
        # Fall back to chunking excerpts to stay within bounds
        chunked = chunk_texts_by_char_limit(rows, max_chars)
        block = "\n\n".join("\n\n".join(chunk) for chunk in chunked[:1])
    return block, mapping


def _parse_json_stories(
    raw_json: str,
    sources_table: Sequence[tuple[int, str, str]],
    logger,
) -> list[Story]:
    if not raw_json:
        return []

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:  # pragma: no cover - validation path
        logger.debug("Failed to decode JSON summary: %s", exc)
        raise

    if not isinstance(data, dict):
        raise ValueError("JSON summary must be an object")

    stories_data = data.get("stories")
    if not isinstance(stories_data, list) or not stories_data:
        raise ValueError("JSON summary must include a non-empty 'stories' list")

    index_lookup = {idx: (title, url) for idx, title, url in sources_table}
    max_index = len(sources_table)
    stories: list[Story] = []

    for entry in stories_data[:5]:
        if not isinstance(entry, dict):
            raise ValueError("Each story must be an object")
        headline = ensure_headline_case(str(entry.get("headline") or "").strip())
        why = normalise_spaces(str(entry.get("why") or ""))
        date = entry.get("date")
        if date is not None:
            date = str(date).strip() or None
        bullets_raw = entry.get("bullets")
        source_indices_raw = entry.get("source_indices")
        if not headline or not why:
            raise ValueError("Story requires headline and why")
        if not isinstance(bullets_raw, list) or not (2 <= len(bullets_raw) <= 4):
            raise ValueError("Story bullets must be a list of length 2-4")
        if not isinstance(source_indices_raw, list) or not source_indices_raw:
            raise ValueError("Story must include source_indices")

        source_indices: list[int] = []
        for idx in source_indices_raw:
            if not isinstance(idx, int) or idx < 1 or idx > max_index:
                raise ValueError("Story source index out of range")
            if idx not in index_lookup:
                continue
            source_indices.append(idx)
        source_indices = sorted(dict.fromkeys(source_indices))
        if not source_indices:
            raise ValueError("Story source_indices did not match provided sources")

        bullets: list[str] = []
        for bullet_text in bullets_raw:
            if not isinstance(bullet_text, str):
                raise ValueError("Bullet entries must be strings")
            bullet_clean = normalise_spaces(bullet_text)
            citations = _extract_citations(bullet_clean, max_index)
            if not citations:
                raise ValueError("Each bullet must include at least one citation")
            if any(citation not in source_indices for citation in citations):
                raise ValueError("Bullet citations must reference source_indices")
            bullet_clean = ensure_citation_suffix(bullet_clean, citations)
            bullets.append(bullet_clean)

        urls = [index_lookup[idx][1] for idx in source_indices if idx in index_lookup]
        stories.append(
            Story(
                headline=headline,
                date=date,
                why=why,
                bullets=bullets,
                source_indices=source_indices,
                urls=urls,
            )
        )

    return stories


def _sanitise_content(text: str) -> str:
    """Remove telemetry, tool dumps, and stray fences from model output."""

    if not text:
        return ""

    stripped = strip_telemetry_lines(text)
    if not stripped:
        return ""

    lines: list[str] = []
    for raw_line in stripped.splitlines():
        line = raw_line.rstrip()
        if not line:
            lines.append("")
            continue
        if _NON_MARKDOWN_FENCE.match(line) and "```markdown" not in line.lower():
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    return cleaned.strip()


def _extract_citations(text: str, max_index: int) -> list[int]:
    citations: list[int] = []
    for match in _CITATION_PATTERN.finditer(text):
        idx = int(match.group(1))
        if 1 <= idx <= max_index:
            citations.append(idx)
    return citations


def _parse_clusters(raw: str, max_index: int) -> list[ClusterSummary]:
    lines = [line.rstrip() for line in raw.splitlines()]
    clusters: list[ClusterSummary] = []
    current_heading = ""
    current_bullets: list[ClusterBullet] = []

    def flush() -> None:
        nonlocal current_heading, current_bullets
        if current_bullets:
            clusters.append(ClusterSummary(heading=current_heading or "Summary", bullets=current_bullets))
        current_heading = ""
        current_bullets = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        heading_match = _HEADING_PATTERN.match(stripped)
        if heading_match:
            flush()
            current_heading = heading_match.group(2).strip()
            continue
        bold_match = _BOLD_HEADING_PATTERN.match(stripped)
        if bold_match:
            flush()
            current_heading = bold_match.group(1).strip()
            continue
        if stripped.endswith(":") and not stripped.startswith("-") and not stripped.startswith("*"):
            flush()
            current_heading = stripped[:-1].strip()
            continue
        if stripped[0] in {"-", "*", "•"}:
            bullet_text = stripped.lstrip("-*• ").strip()
            citations = _extract_citations(bullet_text, max_index)
            current_bullets.append(ClusterBullet(text=bullet_text, citations=citations))
        else:
            if current_bullets:
                # continuation of previous bullet
                current_bullets[-1].text += f" {stripped}"
            else:
                current_heading = stripped

    flush()
    return clusters


def _fallback_clusters(raw: str, max_index: int) -> list[ClusterSummary]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    bullets: list[ClusterBullet] = []
    for line in lines:
        if line.startswith(("- ", "• ", "* ")):
            text = line[2:].strip()
        else:
            text = line
        citations = _extract_citations(text, max_index)
        bullets.append(ClusterBullet(text=text, citations=citations))
        if len(bullets) >= 5:
            break
    if not bullets and raw.strip():
        citations = _extract_citations(raw, max_index)
        bullets = [ClusterBullet(text=raw.strip(), citations=citations)]
    return [ClusterSummary(heading="Summary", bullets=bullets)]


def _clamp_bullets(clusters: list[ClusterSummary]) -> list[ClusterSummary]:
    clamped: list[ClusterSummary] = []
    for cluster in clusters:
        bullets = cluster.bullets
        if len(bullets) > 5:
            bullets = bullets[:5]
        elif len(bullets) == 0:
            continue
        clamped.append(ClusterSummary(heading=cluster.heading or "Summary", bullets=bullets))
    return clamped


def _enforce_topic_bullet_cap(clusters: list[ClusterSummary], cap: int = 25) -> list[ClusterSummary]:
    """Keep at most ``cap`` bullets across clusters, preferring corroborated and recent ones."""

    catalogue: list[tuple[int, int, ClusterBullet, bool, dt.date, int, int]] = []
    sequence = 0
    for cluster_idx, cluster in enumerate(clusters):
        for bullet_idx, bullet in enumerate(cluster.bullets):
            dates = extract_iso_dates(bullet.text)
            latest = max(dates) if dates else dt.date.min
            unique_citations = sorted(set(bullet.citations))
            corroborated = False
            if len(unique_citations) >= 2:
                corroborated = True
            catalogue.append(
                (
                    cluster_idx,
                    bullet_idx,
                    bullet,
                    corroborated,
                    latest,
                    len(unique_citations),
                    sequence,
                )
            )
            sequence += 1

    if len(catalogue) <= cap:
        return clusters

    catalogue.sort(
        key=lambda item: (
            1 if item[3] else 0,
            item[4],
            item[5],
            -len(item[2].text),
            -item[6],
        ),
        reverse=True,
    )
    survivors = { (entry[0], entry[1]) for entry in catalogue[:cap] }

    pruned: list[ClusterSummary] = []
    for cluster_idx, cluster in enumerate(clusters):
        new_bullets = [
            bullet for bullet_idx, bullet in enumerate(cluster.bullets)
            if (cluster_idx, bullet_idx) in survivors
        ]
        if new_bullets:
            pruned.append(ClusterSummary(heading=cluster.heading, bullets=new_bullets))
    return pruned


def _normalise_bullets(clusters: list[ClusterSummary]) -> list[ClusterSummary]:
    """Tidy bullet texts and ensure citations are well-formed."""

    normalised: list[ClusterSummary] = []
    for cluster in clusters:
        bullets: list[ClusterBullet] = []
        for bullet in cluster.bullets:
            deduped = sorted(dict.fromkeys(bullet.citations))
            if not deduped:
                continue
            text = normalise_spaces(bullet.text)
            text = strip_trailing_citations(text)
            text = truncate_sentence(text, _MAX_CLUSTER_BULLET_CHARS)
            text = ensure_citation_suffix(text, deduped)
            bullets.append(ClusterBullet(text=text, citations=deduped))
        if bullets:
            normalised.append(ClusterSummary(heading=cluster.heading or "Summary", bullets=bullets))
    return normalised


def _stories_to_clusters(stories: Sequence[Story]) -> list[ClusterSummary]:
    bullets: list[ClusterBullet] = []
    for story in stories:
        summary_text = strip_trailing_citations(f"{story.headline} — {story.why}")
        summary_text = truncate_sentence(summary_text, _MAX_CLUSTER_BULLET_CHARS)
        summary_text = ensure_citation_suffix(summary_text, story.source_indices)
        bullets.append(ClusterBullet(text=summary_text, citations=story.source_indices))
    return [ClusterSummary(heading="Top Stories", bullets=bullets)] if bullets else []


def summarise_topic(
    topic: str,
    pages: list[FetchedPage],
    cfg: AppConfig,
    logger,
    corroborate: bool,
) -> tuple[TopicSummary, list[tuple[int, str, str]]]:
    """Summarise a topic given fetched pages."""
    if not pages:
        logger.warning("No pages supplied for summarising '%s'", topic)
        empty_summary = TopicSummary(topic=topic, clusters=[])
        return empty_summary, []

    logger.info("Summarising '%s' …", topic)

    excerpt_limit = max(400, cfg.max_batch_chars // max(len(pages), 1))
    sources_block, sources_table = _sources_block(pages, excerpt_limit)

    tools = [web_search, web_fetch] if corroborate else None

    messages_json = [
        {"role": "system", "content": JSON_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JSON_USER_TEMPLATE.format(
                topic=topic,
                max_sources=len(sources_table),
                sources_block=sources_block,
            ),
        },
    ]

    json_response = None
    try:
        json_response = chat(model=cfg.model, messages=messages_json, tools=tools)
    except Exception as exc:  # pragma: no cover - network failure path
        logger.error("JSON chat completion failed for '%s': %s", topic, exc)
    stories: list[Story] = []

    if json_response is not None:
        content = _extract_message_content(json_response)
        sanitised_json = _sanitise_json_text(content)
        if sanitised_json:
            try:
                stories = _parse_json_stories(sanitised_json, sources_table, logger)
            except Exception as exc:
                logger.warning("JSON summary parsing failed for '%s': %s", topic, exc)

    if stories:
        summary = TopicSummary(
            topic=topic,
            clusters=_stories_to_clusters(stories),
            stories=stories,
        )
        return summary, sources_table

    # Fallback to legacy markdown clustering
    user_prompt = USER_PROMPT_TEMPLATE.format(topic=topic, sources_block=sources_block)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = chat(model=cfg.model, messages=messages, tools=tools)
    except Exception as exc:  # pragma: no cover - network failure path
        logger.error("chat completion failed for '%s': %s", topic, exc)
        raise

    content = _extract_message_content(response)
    if not content:
        logger.warning("Empty summary content for '%s'", topic)
        return TopicSummary(topic=topic, clusters=[]), sources_table

    sanitised = _sanitise_content(content)

    clusters = _parse_clusters(sanitised, max_index=len(sources_table))
    if not clusters:
        clusters = _fallback_clusters(sanitised or content, max_index=len(sources_table))
    clusters = _clamp_bullets(clusters)
    clusters = _normalise_bullets(clusters)
    clusters = _enforce_topic_bullet_cap(clusters)

    summary = TopicSummary(topic=topic, clusters=clusters)
    return summary, sources_table
