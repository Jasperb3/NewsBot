"""Tests for the Tavily search provider."""
import pytest

from newsbot.providers.tavily import TavilySearchProvider


class _StubClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_tavily_provider_normalises_results():
    client = _StubClient({
        "results": [
            {"title": "Story", "url": "https://reuters.com/story", "content": "Snippet"},
            {"title": "Other", "url": "https://bbc.co.uk/news/x", "content": "Body"},
        ]
    })
    provider = TavilySearchProvider(api_key="dummy", client=client)

    hits = provider.search("AI regulation", max_results=5)

    assert [h.url for h in hits] == [
        "https://reuters.com/story",
        "https://bbc.co.uk/news/x",
    ]
    assert hits[0].title == "Story"
    assert hits[0].snippet == "Snippet"


def test_tavily_provider_passes_news_topic_and_days():
    client = _StubClient({"results": []})
    provider = TavilySearchProvider(
        api_key="dummy",
        search_depth="advanced",
        topic="news",
        days=14,
        client=client,
    )

    provider.search("query", max_results=8)

    assert client.calls == [
        {
            "query": "query",
            "max_results": 8,
            "search_depth": "advanced",
            "topic": "news",
            "days": 14,
        }
    ]


def test_tavily_provider_omits_days_for_general_topic():
    client = _StubClient({"results": []})
    provider = TavilySearchProvider(api_key="dummy", topic="general", client=client)

    provider.search("q", max_results=3)

    assert "days" not in client.calls[0]


def test_tavily_provider_clamps_max_results():
    client = _StubClient({"results": []})
    provider = TavilySearchProvider(api_key="dummy", client=client)

    provider.search("q", max_results=999)
    assert client.calls[0]["max_results"] == 10

    provider.search("q", max_results=0)
    assert client.calls[1]["max_results"] == 1


def test_tavily_provider_falls_back_to_basic_for_invalid_depth():
    client = _StubClient({"results": []})
    provider = TavilySearchProvider(
        api_key="dummy", search_depth="ludicrous", client=client
    )
    provider.search("q", max_results=1)
    assert client.calls[0]["search_depth"] == "basic"


def test_tavily_provider_skips_malformed_entries():
    client = _StubClient({
        "results": [
            {"title": "Good", "url": "https://example.com/a", "content": "ok"},
            {"title": "Bad — no URL"},
            "not even a dict",
            {"url": "https://example.com/a", "title": "Dup"},  # duplicate URL
            {"url": "https://example.com/b", "title": "Also good"},
        ]
    })
    provider = TavilySearchProvider(api_key="dummy", client=client)

    hits = provider.search("q", max_results=10)

    assert [h.url for h in hits] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_tavily_provider_handles_empty_response():
    client = _StubClient({})
    provider = TavilySearchProvider(api_key="dummy", client=client)
    assert provider.search("q", max_results=5) == []


def test_tavily_provider_requires_api_key():
    with pytest.raises(ValueError):
        TavilySearchProvider(api_key="")
