"""Tavily-backed search provider.

Tavily is an AI-curated search API designed for LLM consumption. We use the
``news`` topic with a recency window so results are biased toward fresh,
mainstream reporting — complementing Ollama's broader, less-curated results.
"""
from __future__ import annotations

from typing import Any

try:  # Optional dependency; only required when this provider is enabled
    from tavily import TavilyClient as _TavilyClient
except ImportError:  # pragma: no cover - optional path
    _TavilyClient = None  # type: ignore

from ..models import SearchHit


_VALID_DEPTHS = {"basic", "advanced"}
_VALID_TOPICS = {"news", "general"}


class TavilySearchProvider:
    """Search provider backed by the Tavily API."""

    name: str = "tavily"

    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = "basic",
        topic: str = "news",
        days: int = 7,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("TavilySearchProvider requires a non-empty api_key")

        if client is None:
            if _TavilyClient is None:
                raise RuntimeError(
                    "tavily-python package is required for TavilySearchProvider; "
                    "install with `pip install tavily-python`"
                )
            client = _TavilyClient(api_key=api_key)

        self._client = client
        self._search_depth = search_depth if search_depth in _VALID_DEPTHS else "basic"
        self._topic = topic if topic in _VALID_TOPICS else "news"
        self._days = max(1, int(days))

    def search(self, query: str, max_results: int) -> list[SearchHit]:
        params: dict[str, Any] = {
            "query": query,
            "max_results": max(1, min(int(max_results), 10)),
            "search_depth": self._search_depth,
            "topic": self._topic,
        }
        # The `days` parameter is only meaningful for the news topic.
        if self._topic == "news":
            params["days"] = self._days

        response = self._client.search(**params)
        results = response.get("results", []) if isinstance(response, dict) else []

        hits: list[SearchHit] = []
        seen: set[str] = set()
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            hits.append(
                SearchHit(
                    title=item.get("title") or url,
                    url=url,
                    snippet=item.get("content"),
                )
            )
        return hits
