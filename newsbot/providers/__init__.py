"""Search provider plugins."""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import SearchProvider
from .ollama_provider import OllamaSearchProvider

if TYPE_CHECKING:
    from ..config import AppConfig


def build_providers(cfg: "AppConfig", logger) -> list[SearchProvider]:
    """Instantiate the providers listed in ``cfg.search_providers``.

    Unknown names are logged and skipped. Providers that fail to initialise
    (e.g. missing API key, missing optional dependency) are also skipped with
    a warning so the run can degrade rather than crash.
    """

    providers: list[SearchProvider] = []
    for name in cfg.search_providers:
        normalised = name.strip().lower()
        if not normalised:
            continue
        if normalised == "ollama":
            providers.append(OllamaSearchProvider())
        elif normalised == "tavily":
            from .tavily import TavilySearchProvider

            if not cfg.tavily_api_key:
                logger.warning(
                    "Tavily provider requested but TAVILY_API_KEY is not set; skipping"
                )
                continue
            try:
                providers.append(
                    TavilySearchProvider(
                        api_key=cfg.tavily_api_key,
                        search_depth=cfg.tavily_search_depth,
                        topic=cfg.tavily_topic,
                        days=cfg.tavily_days,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to initialise Tavily provider: %s", exc)
        else:
            logger.warning("Unknown search provider '%s' — skipping", name)

    return providers


__all__ = ["SearchProvider", "OllamaSearchProvider", "build_providers"]
