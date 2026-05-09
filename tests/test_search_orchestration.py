"""Tests for multi-provider search orchestration in newsbot.search."""
from dataclasses import replace

from newsbot.config import AppConfig
from newsbot.models import SearchHit
from newsbot.search import _interleave, search_topic


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


class _StubProvider:
    def __init__(self, name: str, hits: list[SearchHit], *, raises: Exception | None = None):
        self.name = name
        self._hits = hits
        self._raises = raises
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, max_results: int) -> list[SearchHit]:
        self.calls.append((query, max_results))
        if self._raises is not None:
            raise self._raises
        return list(self._hits)


def test_interleave_round_robin():
    a = [SearchHit("A1", "https://a/1"), SearchHit("A2", "https://a/2")]
    b = [SearchHit("B1", "https://b/1")]
    c = [SearchHit("C1", "https://c/1"), SearchHit("C2", "https://c/2"), SearchHit("C3", "https://c/3")]

    merged = _interleave([a, b, c])

    assert [h.url for h in merged] == [
        "https://a/1",
        "https://b/1",
        "https://c/1",
        "https://a/2",
        "https://c/2",
        "https://c/3",
    ]


def test_interleave_handles_empty_input():
    assert _interleave([]) == []
    assert _interleave([[]]) == []


def test_search_topic_combines_providers(monkeypatch):
    ollama = _StubProvider(
        "ollama",
        [SearchHit("Ollama1", "https://example.com/o1"), SearchHit("Ollama2", "https://example.com/o2")],
    )
    tavily = _StubProvider(
        "tavily",
        [SearchHit("Tavily1", "https://news.com/t1"), SearchHit("Tavily2", "https://news.com/t2")],
    )
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [ollama, tavily])

    cfg = _cfg(search_providers=["ollama", "tavily"])
    hits = search_topic("AI", cfg, DummyLogger())

    # Round-robin: o1, t1, o2, t2
    urls = [h.url for h in hits]
    assert urls == [
        "https://example.com/o1",
        "https://news.com/t1",
        "https://example.com/o2",
        "https://news.com/t2",
    ]
    assert ollama.calls == [("AI", cfg.max_results_per_topic)]
    assert tavily.calls == [("AI", cfg.max_results_per_topic)]


def test_search_topic_dedupes_across_providers(monkeypatch):
    shared_url = "https://reuters.com/article-123"
    ollama = _StubProvider("ollama", [SearchHit("Story (Ollama)", shared_url)])
    tavily = _StubProvider(
        "tavily",
        [
            SearchHit("Story (Tavily)", shared_url, snippet="Curated summary"),
            SearchHit("Other", "https://ft.com/x"),
        ],
    )
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [ollama, tavily])

    hits = search_topic("markets", _cfg(), DummyLogger())

    urls = [h.url for h in hits]
    assert urls.count(shared_url) == 1, "Duplicate URL across providers must be deduped"
    assert "https://ft.com/x" in urls
    # First-seen wins, so we keep the Ollama title (round-robin places ollama hit first)
    shared_hit = next(h for h in hits if h.url == shared_url)
    assert shared_hit.title == "Story (Ollama)"


def test_search_topic_continues_when_one_provider_fails(monkeypatch):
    failing = _StubProvider("tavily", [], raises=RuntimeError("API down"))
    working = _StubProvider("ollama", [SearchHit("Title", "https://example.com/a")])
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [failing, working])

    logger = DummyLogger()
    hits = search_topic("topic", _cfg(), logger)

    assert len(hits) == 1
    assert hits[0].url == "https://example.com/a"
    warnings = [msg for level, msg in logger.records if level == "WARNING"]
    assert any("tavily" in msg.lower() for msg in warnings)


def test_search_topic_returns_empty_when_no_providers(monkeypatch):
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [])

    logger = DummyLogger()
    hits = search_topic("topic", _cfg(), logger)

    assert hits == []
    errors = [msg for level, msg in logger.records if level == "ERROR"]
    assert any("no search providers" in msg.lower() for msg in errors)


def test_search_topic_respects_exclude_and_truncates(monkeypatch):
    provider = _StubProvider(
        "ollama",
        [
            SearchHit(f"Story {i}", f"https://reddit.com/r/x/{i}") for i in range(3)
        ]
        + [SearchHit(f"News {i}", f"https://reuters.com/{i}") for i in range(8)],
    )
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [provider])

    cfg = _cfg(exclude_domains=["reddit.com"], max_results_per_topic=4)
    hits = search_topic("topic", cfg, DummyLogger())

    assert len(hits) == 4
    assert all("reddit.com" not in h.url for h in hits)
    assert all("reuters.com" in h.url for h in hits)


def test_search_topic_promotes_preferred_domains(monkeypatch):
    provider = _StubProvider(
        "ollama",
        [
            SearchHit("Blog", "https://random-blog.com/post"),
            SearchHit("Reuters", "https://reuters.com/story"),
            SearchHit("Other", "https://other.com/x"),
            SearchHit("BBC", "https://bbc.co.uk/news/story"),
        ],
    )
    monkeypatch.setattr("newsbot.search.build_providers", lambda cfg, logger: [provider])

    cfg = _cfg(prefer_domains=["reuters.com", "bbc.co.uk"])
    hits = search_topic("topic", cfg, DummyLogger())

    # Preferred domains come first, preserving relative order otherwise
    domains = [h.url for h in hits]
    assert domains[0].startswith("https://reuters.com")
    assert domains[1].startswith("https://bbc.co.uk")
