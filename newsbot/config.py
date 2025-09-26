"""Configuration loading for news-digest-bot."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Mapping, MutableMapping

from .log import get_logger
from .utils import split_and_strip_csv

LOGGER = get_logger(__name__)

try:  # Optional dependency
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional path
    load_dotenv = None  # type: ignore


@dataclass
class AppConfig:
    """Runtime configuration for the application."""

    api_key: str | None
    model: str
    max_results_per_topic: int
    fetch_limit_per_topic: int
    tz: str
    output_format: str
    prefer_domains: list[str]
    exclude_domains: list[str]
    max_chars_per_page: int
    max_batch_chars: int


def _parse_int(env: Mapping[str, str], key: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    raw = env.get(key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        LOGGER.warning("Invalid integer for %s, using default %s", key, default)
        return default
    if value < minimum:
        LOGGER.warning("%s below minimum (%s), clamping", key, minimum)
        value = minimum
    if maximum is not None and value > maximum:
        LOGGER.warning("%s above maximum (%s), clamping", key, maximum)
        value = maximum
    return value


def _normalise_format(fmt: str) -> str:
    fmt_lower = fmt.lower().strip()
    if fmt_lower not in {"md", "html"}:
        LOGGER.warning("Unsupported OUTPUT_FORMAT '%s', falling back to 'md'", fmt)
        return "md"
    return fmt_lower


def load_config(env: MutableMapping[str, str] | Mapping[str, str] | None = None) -> AppConfig:
    """Load configuration from environment variables.

    Parameters
    ----------
    env:
        Environment mapping to read configuration from. Defaults to ``os.environ``.
    """

    if env is None:
        if load_dotenv is not None:
            load_dotenv()
        env = os.environ

    api_key = env.get("OLLAMA_API_KEY")
    if not api_key:
        LOGGER.warning("OLLAMA_API_KEY missing; relying on local Ollama authentication")

    model = env.get("MODEL", "qwen3:4b")

    max_results = _parse_int(env, "MAX_RESULTS_PER_TOPIC", default=6, minimum=1, maximum=10)
    fetch_limit = _parse_int(env, "FETCH_LIMIT_PER_TOPIC", default=max_results, minimum=1, maximum=10)

    max_chars_per_page = _parse_int(env, "MAX_CHARS_PER_PAGE", default=6000, minimum=500)
    max_batch_chars = _parse_int(env, "MAX_BATCH_CHARS", default=18000, minimum=1000)

    output_format = _normalise_format(env.get("OUTPUT_FORMAT", "md"))

    prefer_domains = split_and_strip_csv(env.get("PREFER_DOMAINS"))
    exclude_domains = split_and_strip_csv(env.get("EXCLUDE_DOMAINS"))

    config = AppConfig(
        api_key=api_key,
        model=model,
        max_results_per_topic=max_results,
        fetch_limit_per_topic=fetch_limit,
        tz=env.get("TZ", "Europe/London"),
        output_format=output_format,
        prefer_domains=prefer_domains,
        exclude_domains=exclude_domains,
        max_chars_per_page=max_chars_per_page,
        max_batch_chars=max_batch_chars,
    )

    LOGGER.debug("Loaded configuration: %s", config)
    return config
