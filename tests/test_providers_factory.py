"""Tests for newsbot.providers.build_providers factory."""
from dataclasses import replace

from newsbot.config import AppConfig
from newsbot.providers import build_providers
from newsbot.providers.ollama_provider import OllamaSearchProvider


class DummyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _record(self, level: str, msg: str, *args) -> None:
        self.records.append((level, msg % args if args else msg))

    debug = lambda self, msg, *a: self._record("DEBUG", msg, *a)
    info = lambda self, msg, *a: self._record("INFO", msg, *a)
    warning = lambda self, msg, *a: self._record("WARNING", msg, *a)
    error = lambda self, msg, *a: self._record("ERROR", msg, *a)


def _cfg(**overrides) -> AppConfig:
    base = AppConfig(
        api_key=None,
        model="test",
        max_results_per_topic=6,
        fetch_limit_per_topic=6,
        tz="Europe/London",
        output_format="md",
        prefer_domains=[],
        exclude_domains=[],
        max_chars_per_page=6000,
        max_batch_chars=18000,
    )
    return replace(base, **overrides) if overrides else base


def test_default_config_yields_ollama_only():
    providers = build_providers(_cfg(), DummyLogger())
    assert len(providers) == 1
    assert isinstance(providers[0], OllamaSearchProvider)
    assert providers[0].name == "ollama"


def test_unknown_provider_is_skipped_with_warning():
    logger = DummyLogger()
    providers = build_providers(_cfg(search_providers=["ollama", "bogus"]), logger)
    assert len(providers) == 1
    assert isinstance(providers[0], OllamaSearchProvider)
    assert any("bogus" in msg for level, msg in logger.records if level == "WARNING")


def test_tavily_skipped_when_api_key_missing():
    logger = DummyLogger()
    providers = build_providers(
        _cfg(search_providers=["ollama", "tavily"], tavily_api_key=None),
        logger,
    )
    assert len(providers) == 1
    assert providers[0].name == "ollama"
    warnings = [msg for level, msg in logger.records if level == "WARNING"]
    assert any("TAVILY_API_KEY" in msg for msg in warnings)


def test_empty_provider_names_are_ignored():
    providers = build_providers(_cfg(search_providers=["", "ollama", "  "]), DummyLogger())
    assert len(providers) == 1
    assert providers[0].name == "ollama"


def test_provider_names_are_case_insensitive():
    providers = build_providers(_cfg(search_providers=["OLLAMA"]), DummyLogger())
    assert len(providers) == 1
    assert providers[0].name == "ollama"
