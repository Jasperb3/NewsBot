"""Tests for configuration loading."""
from newsbot.config import load_config


def test_default_search_providers_is_ollama_only():
    cfg = load_config(env={})
    assert cfg.search_providers == ["ollama"]
    assert cfg.tavily_api_key is None


def test_search_providers_parsed_from_csv():
    cfg = load_config(env={"SEARCH_PROVIDERS": "ollama, tavily"})
    assert cfg.search_providers == ["ollama", "tavily"]


def test_tavily_options_parsed():
    env = {
        "SEARCH_PROVIDERS": "tavily",
        "TAVILY_API_KEY": "tvly-secret",
        "TAVILY_SEARCH_DEPTH": "advanced",
        "TAVILY_TOPIC": "news",
        "TAVILY_DAYS": "14",
    }
    cfg = load_config(env=env)
    assert cfg.tavily_api_key == "tvly-secret"
    assert cfg.tavily_search_depth == "advanced"
    assert cfg.tavily_topic == "news"
    assert cfg.tavily_days == 14


def test_invalid_tavily_depth_falls_back_to_basic():
    cfg = load_config(env={"TAVILY_SEARCH_DEPTH": "ludicrous"})
    assert cfg.tavily_search_depth == "basic"


def test_invalid_tavily_topic_falls_back_to_news():
    cfg = load_config(env={"TAVILY_TOPIC": "weather"})
    assert cfg.tavily_topic == "news"


def test_tavily_days_clamped_to_range():
    cfg = load_config(env={"TAVILY_DAYS": "9999"})
    assert cfg.tavily_days == 365

    cfg = load_config(env={"TAVILY_DAYS": "0"})
    assert cfg.tavily_days == 1


def test_empty_tavily_api_key_normalises_to_none():
    cfg = load_config(env={"TAVILY_API_KEY": ""})
    assert cfg.tavily_api_key is None


def test_distill_disabled_by_default():
    cfg = load_config(env={})
    assert cfg.distill_enabled is False
    assert cfg.distill_threshold_chars == 4000
    assert cfg.distill_target_chars == 1500


def test_distill_enabled_via_env():
    cfg = load_config(env={"DISTILL_ENABLED": "true"})
    assert cfg.distill_enabled is True


def test_distill_bool_accepts_common_truthy_values():
    for truthy in ["1", "true", "TRUE", "yes", "on", "y"]:
        cfg = load_config(env={"DISTILL_ENABLED": truthy})
        assert cfg.distill_enabled is True, f"Expected '{truthy}' to be truthy"


def test_distill_bool_accepts_common_falsy_values():
    for falsy in ["0", "false", "no", "off", "n"]:
        cfg = load_config(env={"DISTILL_ENABLED": falsy})
        assert cfg.distill_enabled is False, f"Expected '{falsy}' to be falsy"


def test_distill_threshold_and_target_parsed():
    cfg = load_config(
        env={
            "DISTILL_ENABLED": "true",
            "DISTILL_THRESHOLD_CHARS": "6000",
            "DISTILL_TARGET_CHARS": "2000",
        }
    )
    assert cfg.distill_threshold_chars == 6000
    assert cfg.distill_target_chars == 2000


def test_distill_threshold_clamped_to_minimum():
    cfg = load_config(env={"DISTILL_THRESHOLD_CHARS": "100"})
    assert cfg.distill_threshold_chars == 500
