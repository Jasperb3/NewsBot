import time

import pytest

from newsbot.config import AppConfig
from newsbot.fetch import fetch_pages
from newsbot.models import SearchHit


class DummyLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, tuple]] = []

    def debug(self, msg: str, *args) -> None:
        self.records.append(("DEBUG", msg % args if args else msg))

    def info(self, msg: str, *args) -> None:
        self.records.append(("INFO", msg % args if args else msg))

    def warning(self, msg: str, *args) -> None:
        self.records.append(("WARNING", msg % args if args else msg))

    def error(self, msg: str, *args) -> None:
        self.records.append(("ERROR", msg % args if args else msg))


def _cfg() -> AppConfig:
    return AppConfig(
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


def _disable_trafilatura(monkeypatch):
    """Stub trafilatura so the snippet fallback is reached without network calls."""
    monkeypatch.setattr("newsbot.fetch._trafilatura_fetch", lambda url: None)
    monkeypatch.setattr("newsbot.fetch._trafilatura_extract", lambda payload: None)


def test_fetch_retry_success(monkeypatch):
    attempts = []

    def fake_fetch(url: str):
        attempts.append(url)
        if len(attempts) < 3:
            raise RuntimeError("temporary")
        return {"content": "A" * 500, "title": "Story"}

    monkeypatch.setattr("newsbot.fetch.web_fetch", fake_fetch)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="Snippet")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].is_snippet is False
    assert pages[0].fetcher == "ollama"
    assert len(attempts) == 3


def test_fetch_snippet_fallback(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("fail")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    _disable_trafilatura(monkeypatch)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="Short summary")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].is_snippet is True
    assert pages[0].fetcher == "snippet"
    assert pages[0].content == "Short summary"


def test_trafilatura_fallback_when_ollama_fails(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr("newsbot.fetch._trafilatura_fetch", lambda url: "<html>raw</html>")
    monkeypatch.setattr("newsbot.fetch._trafilatura_extract", lambda payload: "B" * 800)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="snippet")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].fetcher == "trafilatura"
    assert pages[0].is_snippet is False
    assert pages[0].content.startswith("B")


def test_trafilatura_fallback_when_ollama_returns_short_content(monkeypatch):
    def short_content(url: str):
        return {"content": "tiny", "title": "Story"}

    monkeypatch.setattr("newsbot.fetch.web_fetch", short_content)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr("newsbot.fetch._trafilatura_fetch", lambda url: "<html>raw</html>")
    monkeypatch.setattr("newsbot.fetch._trafilatura_extract", lambda payload: "C" * 500)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="snippet")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].fetcher == "trafilatura"
    assert pages[0].content.startswith("C")


def test_snippet_fallback_when_trafilatura_returns_short_content(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr("newsbot.fetch._trafilatura_fetch", lambda url: "<html>raw</html>")
    monkeypatch.setattr("newsbot.fetch._trafilatura_extract", lambda payload: "too short")

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="A snippet")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].fetcher == "snippet"
    assert pages[0].content == "A snippet"


def test_trafilatura_fetch_failure_falls_through_to_snippet(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("ollama down")

    def trafilatura_boom(url: str):
        raise RuntimeError("network")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setattr("newsbot.fetch._trafilatura_fetch", trafilatura_boom)
    monkeypatch.setattr("newsbot.fetch._trafilatura_extract", lambda payload: None)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="A snippet")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].fetcher == "snippet"


def test_no_page_returned_when_all_paths_fail_and_no_snippet(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("ollama down")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    _disable_trafilatura(monkeypatch)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet=None)
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert pages == []
