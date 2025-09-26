from newsbot.summarise import _sanitise_content


def test_sanitise_content_removes_telemetry_lines():
    raw = (
        "model=qwen created_at=2025-09-26T18:00:00Z latency=123ms\n"
        "assistant:thinking about something\n"
        "### Valid Heading\n"
        "- Useful insight [1]\n"
    )
    cleaned = _sanitise_content(raw)
    assert "model=" not in cleaned
    assert "assistant:" not in cleaned
    assert "Useful insight" in cleaned
