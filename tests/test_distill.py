"""Tests for per-article distillation."""
from dataclasses import replace

from newsbot.config import AppConfig
from newsbot.distill import distill_pages
from newsbot.models import FetchedPage


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
        distill_enabled=True,
        distill_threshold_chars=4000,
        distill_target_chars=1500,
    )
    return replace(base, **overrides) if overrides else base


def _page(content: str, *, url: str = "https://example.com/a", **kwargs) -> FetchedPage:
    return FetchedPage(
        url=url,
        title=kwargs.pop("title", "Story"),
        content=content,
        links=[],
        topic=kwargs.pop("topic", "news"),
        is_snippet=kwargs.pop("is_snippet", False),
        fetcher=kwargs.pop("fetcher", "ollama"),
    )


def _chat_returning(text: str):
    """Build a fake ollama.chat that returns text in the SDK's dict shape."""
    calls: list[dict] = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return {"message": {"content": text}}

    fake_chat.calls = calls  # type: ignore[attr-defined]
    return fake_chat


def test_distill_disabled_passes_pages_through_unchanged():
    pages = [_page("A" * 8000)]
    chat = _chat_returning("should not be called")
    out = distill_pages(pages, _cfg(distill_enabled=False), DummyLogger(), chat=chat)
    assert out == pages
    assert chat.calls == []


def test_distill_skips_pages_below_threshold():
    pages = [_page("A" * 1000)]  # below 4000-char threshold
    chat = _chat_returning("ignored")
    out = distill_pages(pages, _cfg(), DummyLogger(), chat=chat)
    assert out[0].content == pages[0].content
    assert out[0].distilled is False
    assert chat.calls == []


def test_distill_skips_snippet_pages_even_when_long():
    pages = [_page("X" * 8000, is_snippet=True)]
    chat = _chat_returning("ignored")
    out = distill_pages(pages, _cfg(), DummyLogger(), chat=chat)
    assert chat.calls == [], "Snippet pages must not consume model calls"
    assert out[0].distilled is False


def test_distill_replaces_long_content_with_summary():
    pages = [_page("A" * 8000)]
    summary = "Dense summary preserving Reuters and 42% and other facts. " * 10
    chat = _chat_returning(summary)

    logger = DummyLogger()
    out = distill_pages(pages, _cfg(), logger, chat=chat)

    assert out[0].distilled is True
    assert out[0].content == summary.strip()
    assert len(out[0].content) < len(pages[0].content)
    assert len(chat.calls) == 1
    # Original metadata is preserved
    assert out[0].url == pages[0].url
    assert out[0].title == pages[0].title
    assert out[0].fetcher == pages[0].fetcher


def test_distill_keeps_original_when_chat_raises():
    pages = [_page("A" * 8000)]

    def boom(**kwargs):
        raise RuntimeError("model unavailable")

    out = distill_pages(pages, _cfg(), DummyLogger(), chat=boom)

    assert out[0].content == pages[0].content
    assert out[0].distilled is False


def test_distill_keeps_original_when_output_too_short():
    pages = [_page("A" * 8000)]
    chat = _chat_returning("tiny")  # below 100-char minimum

    out = distill_pages(pages, _cfg(), DummyLogger(), chat=chat)

    assert out[0].content == pages[0].content
    assert out[0].distilled is False


def test_distill_keeps_original_when_output_not_smaller():
    original = "A" * 8000
    pages = [_page(original)]
    # Distilled output is the same length — no benefit, keep original
    chat = _chat_returning("B" * 8000)

    out = distill_pages(pages, _cfg(), DummyLogger(), chat=chat)

    assert out[0].content == original
    assert out[0].distilled is False


def test_distill_handles_mix_of_short_and_long():
    pages = [
        _page("short " * 100, url="https://a.com/1"),  # ~600 chars, skip
        _page("long " * 2000, url="https://b.com/2"),  # ~10000 chars, distill
        _page("X" * 5000, url="https://c.com/3", is_snippet=True),  # snippet, skip
    ]
    chat = _chat_returning("Distilled prose with names like Reuters and dates like 2026. " * 10)

    out = distill_pages(pages, _cfg(), DummyLogger(), chat=chat)

    assert len(out) == 3
    assert out[0].distilled is False  # short
    assert out[1].distilled is True   # long
    assert out[2].distilled is False  # snippet
    assert len(chat.calls) == 1


def test_distill_uses_configured_model_and_target():
    pages = [_page("A" * 8000)]
    summary = "Dense Reuters summary. " * 30
    chat = _chat_returning(summary)

    cfg = _cfg(model="qwen3:14b", distill_target_chars=2500)
    distill_pages(pages, cfg, DummyLogger(), chat=chat)

    assert chat.calls[0]["model"] == "qwen3:14b"
    system_msg = chat.calls[0]["messages"][0]["content"]
    assert "2500" in system_msg, "Target length should appear in the system prompt"


def test_distill_logs_per_run_summary():
    pages = [_page("long " * 2000), _page("more " * 2000, url="https://x.com/y")]
    summary = "Distilled output preserving facts and entities and numbers. " * 5
    chat = _chat_returning(summary)

    logger = DummyLogger()
    distill_pages(pages, _cfg(), logger, chat=chat)

    summary_lines = [msg for level, msg in logger.records if "Distilled 2/" in msg]
    assert summary_lines, "Expected an aggregate summary log line"


def test_distill_returns_empty_for_empty_input():
    assert distill_pages([], _cfg(), DummyLogger()) == []


def test_distill_extracts_content_from_object_response_shape():
    """Some Ollama SDK versions return objects rather than dicts."""

    class _Msg:
        content = "Distilled prose with names and dates and more facts. " * 5

    class _Resp:
        message = _Msg()

    def fake_chat(**kwargs):
        return _Resp()

    pages = [_page("A" * 8000)]
    out = distill_pages(pages, _cfg(), DummyLogger(), chat=fake_chat)
    assert out[0].distilled is True
    assert "Distilled" in out[0].content
