"""Ollama-backed search provider.

Wraps :func:`ollama.web_search` and normalises its many response shapes
(dicts, tuples, SDK objects with ``.results``, etc.) into a flat list of
:class:`SearchHit`.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Iterable

try:  # Optional in testing contexts
    from ollama import web_search as _ollama_web_search
except ImportError:  # pragma: no cover - fallback for test environments
    def _ollama_web_search(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for web_search at runtime")

from ..models import SearchHit


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


def normalise_ollama_payload(payload: Any) -> list[SearchHit]:
    """Convert any shape returned by ollama.web_search into a list of SearchHit."""

    seen: set[str] = set()
    hits: list[SearchHit] = []
    for raw in _iter_hit_candidates(payload):
        data = _coerce_hit(raw)
        url = data.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        hits.append(
            SearchHit(
                title=data.get("title") or url,
                url=url,
                snippet=data.get("snippet"),
            )
        )
    return hits


class OllamaSearchProvider:
    """Search provider backed by ``ollama.web_search``."""

    name: str = "ollama"

    def __init__(self, *, web_search=None) -> None:
        self._web_search = web_search or _ollama_web_search

    def search(self, query: str, max_results: int) -> list[SearchHit]:
        results = self._web_search(query=query, max_results=max_results)
        return normalise_ollama_payload(results)
