"""Search facilities using Ollama web search."""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable

try:  # Optional in testing contexts
    from ollama import web_search
except ImportError:  # pragma: no cover - fallback for test environments
    def web_search(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_search at runtime")

from .config import AppConfig
from .models import SearchHit
from .utils import canonicalise_url, domain_of


def _coerce_hit(raw: Any) -> dict[str, Any]:
    """Normalise hit objects from ollama.web_search into dictionaries."""

    if isinstance(raw, dict):
        data = dict(raw)
        if "url" not in data:
            for alt in ("link", "href", "source_url"):
                value = data.get(alt)
                if isinstance(value, str):
                    data.setdefault("url", value)
                    break
        if "url" not in data:
            content = data.get("content")
            if isinstance(content, dict):
                for alt in ("url", "link", "href"):
                    value = content.get(alt)
                    if isinstance(value, str):
                        data.setdefault("url", value)
                        break
                if "title" not in data and isinstance(content.get("title"), str):
                    data["title"] = content["title"]
                if "snippet" not in data and isinstance(content.get("snippet"), str):
                    data["snippet"] = content["snippet"]
        if "title" not in data:
            for alt in ("headline", "name", "title_text"):
                if isinstance(data.get(alt), str):
                    data["title"] = data[alt]
                    break
        if "snippet" not in data:
            for alt in ("description", "summary", "content", "text"):
                value = data.get(alt)
                if isinstance(value, str):
                    data["snippet"] = value
                    break
        return data

    if isinstance(raw, (list, tuple)):
        # Sometimes results arrive as (score, {...}) or similar.
        for item in raw:
            if isinstance(item, dict):
                return item

        strings = [item for item in raw if isinstance(item, str)]
        url = next((s for s in strings if s.startswith(("http://", "https://"))), None)
        title = next((s for s in strings if s is not url), None)
        snippet = next((s for s in strings if s not in {url, title}), None)
        return {"url": url, "title": title, "snippet": snippet}

    return {}


def _iter_hit_candidates(payload: Any) -> Iterable[Any]:
    """Breadth-first traversal yielding potential hit records."""

    queue: deque[Any] = deque([payload])
    while queue:
        item = queue.popleft()
        if item is None:
            continue

        if hasattr(item, "results"):
            queue.append(getattr(item, "results"))
            # Some SDK objects also carry metadata attributes
            for attr in ("data", "items", "hits"):
                if hasattr(item, attr):
                    queue.append(getattr(item, attr))
            continue

        if hasattr(item, "dict") and callable(getattr(item, "dict")):
            try:
                queue.append(item.dict())
                continue
            except Exception:  # pragma: no cover - defensive
                pass
        if hasattr(item, "model_dump") and callable(getattr(item, "model_dump")):
            try:
                queue.append(item.model_dump())
                continue
            except Exception:  # pragma: no cover - defensive
                pass

        if isinstance(item, dict):
            yield item
            for value in item.values():
                if isinstance(value, (dict, list, tuple, set)) and not isinstance(value, str):
                    queue.append(value)
            continue
        elif isinstance(item, list):
            queue.extend(item)
        elif isinstance(item, tuple):
            if item and all(isinstance(elem, str) for elem in item):
                yield item
            else:
                queue.extend(item)
        elif isinstance(item, set):
            queue.extend(item)
        elif isinstance(item, str):
            continue
        elif isinstance(item, (int, float, bool)):
            continue
        else:
            yield item


def _filter_hits(
    hits: Iterable[Any],
    cfg: AppConfig,
) -> list[SearchHit]:
    prefer = set(cfg.prefer_domains)
    exclude = set(cfg.exclude_domains)

    seen: set[str] = set()
    filtered: list[SearchHit] = []
    for raw in _iter_hit_candidates(hits):
        data = _coerce_hit(raw)
        url = data.get("url") or ""
        if not url:
            continue
        canonical = canonicalise_url(url)
        if canonical in seen:
            continue

        domain = domain_of(url)
        if exclude and domain in exclude:
            continue

        seen.add(canonical)
        filtered.append(
            SearchHit(
                title=data.get("title") or url,
                url=canonical,
                snippet=data.get("snippet"),
            )
        )

    if prefer:
        filtered.sort(key=lambda hit: (domain_of(hit.url) not in prefer))

    return filtered[: cfg.max_results_per_topic]


def search_topic(topic: str, cfg: AppConfig, logger) -> list[SearchHit]:
    """Run a web search for the given topic."""
    logger.info("Searching topic '%s' …", topic)
    try:
        results = web_search(query=topic, max_results=cfg.max_results_per_topic)
    except Exception as exc:  # pragma: no cover - network failure path
        logger.error("web_search failed for '%s': %s", topic, exc)
        raise

    logger.debug("Raw search response: %r", results)

    filtered = _filter_hits(results, cfg)
    logger.info("Found %s hits for '%s'", len(filtered), topic)
    return filtered
