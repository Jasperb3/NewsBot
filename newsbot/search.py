"""Search orchestration across multiple pluggable providers."""
from __future__ import annotations

from typing import Any, Iterable

from .config import AppConfig
from .models import SearchHit
from .providers import SearchProvider, build_providers
from .providers.ollama_provider import normalise_ollama_payload
from .utils import canonicalise_url, domain_of


def _interleave(provider_hits: list[list[SearchHit]]) -> list[SearchHit]:
    """Round-robin interleave so each provider's top hit is reached early.

    This prevents a single provider's full top-N from monopolising the merged
    list before another provider gets a chance — important when a downstream
    fetch cap means only the first M hits are actually retrieved.
    """

    if not provider_hits:
        return []

    interleaved: list[SearchHit] = []
    max_len = max(len(hits) for hits in provider_hits)
    for i in range(max_len):
        for hits in provider_hits:
            if i < len(hits):
                interleaved.append(hits[i])
    return interleaved


def _filter_hits(hits: Iterable[Any], cfg: AppConfig) -> list[SearchHit]:
    """Dedupe by canonical URL, drop excluded domains, prefer-domain sort, truncate.

    Accepts either a flat list of :class:`SearchHit` *or* a raw payload from
    ``ollama.web_search`` (for backwards compatibility with existing callers
    and tests). Raw payloads are normalised via the Ollama provider helper.
    """

    normalised: list[SearchHit]
    if isinstance(hits, list) and all(isinstance(h, SearchHit) for h in hits):
        normalised = hits
    else:
        normalised = normalise_ollama_payload(hits)

    exclude = set(cfg.exclude_domains)
    prefer = set(cfg.prefer_domains)

    seen: set[str] = set()
    filtered: list[SearchHit] = []
    for hit in normalised:
        if not hit.url:
            continue
        canonical = canonicalise_url(hit.url)
        if canonical in seen:
            continue
        if exclude and domain_of(canonical) in exclude:
            continue
        seen.add(canonical)
        filtered.append(SearchHit(title=hit.title, url=canonical, snippet=hit.snippet))

    if prefer:
        filtered.sort(key=lambda hit: domain_of(hit.url) not in prefer)

    return filtered[: cfg.max_results_per_topic]


def _run_providers(
    providers: list[SearchProvider],
    topic: str,
    cfg: AppConfig,
    logger,
) -> list[list[SearchHit]]:
    """Run each provider, returning per-provider hit lists. Failures are logged and skipped."""

    out: list[list[SearchHit]] = []
    for provider in providers:
        try:
            hits = provider.search(topic, cfg.max_results_per_topic)
        except Exception as exc:  # pragma: no cover - network failure path
            logger.warning(
                "Provider '%s' failed for topic '%s': %s",
                provider.name,
                topic,
                exc,
            )
            continue
        logger.info(
            "Provider '%s' returned %d hits for '%s'",
            provider.name,
            len(hits),
            topic,
        )
        out.append(hits)
    return out


def search_topic(topic: str, cfg: AppConfig, logger) -> list[SearchHit]:
    """Run a multi-provider web search for the given topic."""

    logger.info("Searching topic '%s' …", topic)
    providers = build_providers(cfg, logger)
    if not providers:
        logger.error(
            "No search providers available for '%s' — check SEARCH_PROVIDERS and API keys",
            topic,
        )
        return []

    provider_hits = _run_providers(providers, topic, cfg, logger)
    if not provider_hits:
        logger.warning("All providers returned no results for '%s'", topic)
        return []

    interleaved = _interleave(provider_hits)
    filtered = _filter_hits(interleaved, cfg)

    logger.info(
        "Found %d unique hits for '%s' across %d provider(s)",
        len(filtered),
        topic,
        len(provider_hits),
    )
    return filtered
