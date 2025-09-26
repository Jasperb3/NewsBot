import json
from types import SimpleNamespace

import pytest

from newsbot.config import AppConfig
from newsbot.models import FetchedPage
from newsbot.summarise import (
    _extract_message_content,
    _parse_json_stories,
    _sanitise_content,
    _stories_to_clusters,
    summarise_topic,
)


class DummyLogger:
    def __init__(self) -> None:
        self.messages: list[tuple[str, tuple]] = []

    def warning(self, msg: str, *args) -> None:
        self.messages.append((msg, args))

    def info(self, msg: str, *args) -> None:  # pragma: no cover - informational
        self.messages.append((msg, args))

    def debug(self, msg: str, *args) -> None:
        self.messages.append((msg, args))


def _app_config() -> AppConfig:
    return AppConfig(
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


def test_sanitise_content_removes_telemetry_lines():
    raw = (
        "model=qwen created_at=2025-09-26T18:00:00Z latency=123ms\n"
        "assistant:thinking about something\n"
        "tool_calls=[] images=[] total_duration=0.12s eval_count=128\n"
        "### Valid Heading\n"
        "- Useful insight [1]\n"
    )
    cleaned = _sanitise_content(raw)
    assert "model=" not in cleaned
    assert "assistant:" not in cleaned
    assert "tool_calls" not in cleaned
    assert "created_at" not in cleaned
    assert "Useful insight" in cleaned


def test_chat_response_handling_object():
    response = SimpleNamespace(message=SimpleNamespace(content="Structured copy", thinking="meta"))
    assert _extract_message_content(response) == "Structured copy"


def test_json_mode_validates_and_renders(monkeypatch):
    payload = {
        "stories": [
            {
                "headline": "energy policy shifts",
                "date": "2025-09-20",
                "why": "New measures impact industry",
                "bullets": [
                    "Government outlined incentives [1]",
                    "Analysts expect growth [2]",
                ],
                "source_indices": [1, 2],
            }
        ]
    }

    responses = []

    def fake_chat(*args, **kwargs):
        responses.append(kwargs.get("tools"))
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))

    monkeypatch.setattr("newsbot.summarise.chat", fake_chat)
    monkeypatch.setattr("newsbot.summarise.web_search", lambda *args, **kwargs: None)
    monkeypatch.setattr("newsbot.summarise.web_fetch", lambda *args, **kwargs: None)

    pages = [
        FetchedPage(
            url="https://example.com/a",
            title="Gov update",
            content="On 2025-09-20 the government announced incentives.",
            links=[],
            topic="energy",
        ),
        FetchedPage(
            url="https://news.example.net/b",
            title="Analysis",
            content="Analysts responded to the incentives the same day.",
            links=[],
            topic="energy",
        ),
    ]

    summary, sources_table = summarise_topic(
        "energy", pages, _app_config(), DummyLogger(), corroborate=False
    )

    assert responses == [None]
    assert summary.stories
    story = summary.stories[0]
    assert story.headline == "Energy Policy Shifts"
    assert story.source_indices == [1, 2]
    assert summary.clusters and summary.clusters[0].heading == "Top Stories"

    # Validate story parsing helper independently
    parsed = _parse_json_stories(json.dumps(payload), sources_table, DummyLogger())
    clusters = _stories_to_clusters(parsed)
    assert clusters[0].bullets


def test_tools_flag(monkeypatch):
    payload = {
        "stories": [
            {
                "headline": "supply chain",
                "date": None,
                "why": "Suppliers face pressures",
                "bullets": [
                    "Logistics firms report delays [1]",
                    "Manufacturers adjust schedules [1]",
                ],
                "source_indices": [1],
            }
        ]
    }

    captured_tools: list = []

    def fake_chat(*args, **kwargs):
        captured_tools.append(kwargs.get("tools"))
        return SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))

    sentinel_search = lambda *args, **kwargs: None  # noqa: E731
    sentinel_fetch = lambda *args, **kwargs: None  # noqa: E731

    monkeypatch.setattr("newsbot.summarise.chat", fake_chat)
    monkeypatch.setattr("newsbot.summarise.web_search", sentinel_search)
    monkeypatch.setattr("newsbot.summarise.web_fetch", sentinel_fetch)

    page = FetchedPage(
        url="https://updates.example.com/a",
        title="Logistics",
        content="Report cites new delays.",
        links=[],
        topic="supply",
    )

    summarise_topic("supply", [page], _app_config(), DummyLogger(), corroborate=True)
    assert len(captured_tools) == 1
    tools = captured_tools[0]
    assert isinstance(tools, list)
    assert tools[0] is sentinel_search and tools[1] is sentinel_fetch
