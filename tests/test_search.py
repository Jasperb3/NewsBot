from dataclasses import replace

from newsbot.config import AppConfig
from newsbot.search import _filter_hits


def make_config(**overrides):
    base = AppConfig(
        api_key=None,
        model="test-model",
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


def test_filter_hits_handles_tuple_with_dict():
    cfg = make_config()
    hits = [
        (0.9, {"url": "https://example.com/a", "title": "A", "snippet": "S"}),
    ]
    filtered = _filter_hits(hits, cfg)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/a"
    assert filtered[0].title == "A"


def test_filter_hits_handles_tuple_of_strings():
    cfg = make_config()
    hits = [
        ("https://example.com/b", "Title B", "Snippet"),
    ]
    filtered = _filter_hits(hits, cfg)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/b"
    assert filtered[0].title == "Title B"


def test_filter_hits_respects_exclude_domains():
    cfg = make_config(exclude_domains=["example.com"])
    hits = [
        {"url": "https://example.com/a", "title": "A"},
        {"url": "https://other.com/a", "title": "B"},
    ]
    filtered = _filter_hits(hits, cfg)
    assert len(filtered) == 1
    assert filtered[0].url == "https://other.com/a"


def test_filter_hits_handles_dict_with_results_key():
    cfg = make_config()
    hits = {
        "results": [
            {"url": "https://example.com/c", "title": "C"},
            {"url": "https://example.com/d", "title": "D"},
        ]
    }
    filtered = _filter_hits(hits, cfg)
    assert {hit.url for hit in filtered} == {
        "https://example.com/c",
        "https://example.com/d",
    }


def test_filter_hits_handles_tuple_with_list_and_metadata():
    cfg = make_config()
    hits = ([{"url": "https://example.com/e", "title": "E"}], {"meta": "value"})
    filtered = _filter_hits(hits, cfg)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/e"


class DummyResult:
    def __init__(self, entries):
        self.results = entries


def test_filter_hits_handles_object_with_results_attribute():
    cfg = make_config()
    hits = DummyResult([
        {"link": "https://example.com/f", "headline": "F"},
    ])
    filtered = _filter_hits(hits, cfg)
    assert len(filtered) == 1
    assert filtered[0].url == "https://example.com/f"
    assert filtered[0].title == "F"
