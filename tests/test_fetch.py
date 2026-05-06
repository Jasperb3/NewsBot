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
    assert len(attempts) == 3


def test_fetch_snippet_fallback(monkeypatch):
    def always_fail(url: str):
        raise RuntimeError("fail")

    monkeypatch.setattr("newsbot.fetch.web_fetch", always_fail)
    monkeypatch.setattr("time.sleep", lambda *_: None)

    hit = SearchHit(title="Story", url="https://example.com/a", snippet="Short summary")
    pages = fetch_pages([hit], _cfg(), DummyLogger(), topic="news")

    assert len(pages) == 1
    assert pages[0].is_snippet is True
    assert pages[0].content == "Short summary"
