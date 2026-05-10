"""Per-article distillation.

Compresses long, noisy article bodies into dense fact-preserving prose so the
topic-level summariser sees clean inputs. Designed to keep every citation-worthy
fact (proper nouns, dates, numbers, direct quotes) and strip web boilerplate.

Disabled by default; opt in via ``DISTILL_ENABLED=true``.
"""
from __future__ import annotations

import time
from typing import Any

try:  # Optional during offline testing
    from ollama import chat as _ollama_chat
except ImportError:  # pragma: no cover - fallback stub
    def _ollama_chat(*args, **kwargs):  # type: ignore
        raise RuntimeError("ollama package is required for chat at runtime")

from .config import AppConfig
from .models import FetchedPage


_DISTILL_SYSTEM_PROMPT = """\
You are a news-article condenser. Your job is to compress a long article into a \
dense, fact-preserving summary that another AI will use to write a citation-grade \
news digest.

HARD RULES — follow exactly:
- Preserve ALL proper nouns (people, organisations, places, products, legislation) \
verbatim.
- Preserve ALL dates, numbers, currency amounts, and percentages verbatim.
- Preserve direct quotes verbatim, with attribution where given.
- Remove navigation text, advertisements, "related articles", paywall notices, \
cookie banners, social-media share prompts, and editorial boilerplate.
- Do NOT add commentary, analysis, opinion, or context not present in the article.
- Do NOT use bullet points, headings, or markdown — output flowing prose only.
- Do NOT introduce yourself or the article ("This article discusses..."); start \
directly with the first fact.
- If the article is already short or sparse, return what is there with boilerplate \
removed.

LENGTH: Aim for roughly {target_chars} characters of dense, factual prose, in 2–4 \
short paragraphs. It is fine to be shorter — never pad."""


_USER_TEMPLATE = """\
ARTICLE TITLE: {title}
ARTICLE URL: {url}

ARTICLE BODY:
{body}"""


def _extract_message_content(response: Any) -> str:
    """Decode an Ollama chat response across the SDK's response shapes."""
    if hasattr(response, "message"):
        message = getattr(response, "message")
        if message is not None:
            content = getattr(message, "content", None)
            if content:
                return content
            if isinstance(message, dict):
                content = message.get("content")
                if content:
                    return content
    if isinstance(response, dict):
        message = response.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if content:
                return content
        content = response.get("content")
        if content:
            return content
    return ""


_MIN_DISTILLED_CHARS = 100


def _distill_one(
    page: FetchedPage,
    cfg: AppConfig,
    logger,
    *,
    chat=None,
) -> FetchedPage:
    """Distill a single page. Returns the page unchanged on any failure."""

    chat_fn = chat or _ollama_chat
    target = cfg.distill_target_chars

    messages = [
        {
            "role": "system",
            "content": _DISTILL_SYSTEM_PROMPT.format(target_chars=target),
        },
        {
            "role": "user",
            "content": _USER_TEMPLATE.format(
                title=page.title, url=page.url, body=page.content
            ),
        },
    ]

    started = time.perf_counter()
    try:
        response = chat_fn(model=cfg.model, messages=messages)
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("Distillation failed for %s (model error): %s", page.url, exc)
        return page

    distilled = _extract_message_content(response).strip()
    elapsed = time.perf_counter() - started

    if not distilled or len(distilled) < _MIN_DISTILLED_CHARS:
        logger.warning(
            "Distillation produced empty/tiny output for %s (%d chars in %.1fs); keeping original",
            page.url,
            len(distilled),
            elapsed,
        )
        return page

    if len(distilled) >= len(page.content):
        logger.info(
            "Distillation did not shrink content for %s (%d -> %d in %.1fs); keeping original",
            page.url,
            len(page.content),
            len(distilled),
            elapsed,
        )
        return page

    logger.info(
        "Distilled %s: %d -> %d chars in %.1fs",
        page.url,
        len(page.content),
        len(distilled),
        elapsed,
    )

    return FetchedPage(
        url=page.url,
        title=page.title,
        content=distilled,
        links=page.links,
        topic=page.topic,
        is_snippet=page.is_snippet,
        fetcher=page.fetcher,
        distilled=True,
    )


def distill_pages(
    pages: list[FetchedPage],
    cfg: AppConfig,
    logger,
    *,
    chat=None,
) -> list[FetchedPage]:
    """Distill any pages whose content exceeds ``cfg.distill_threshold_chars``.

    Returns a new list with distilled copies replacing originals where successful;
    short pages, snippet-fallback pages, and any distillation failures pass through
    unchanged. No-op when ``cfg.distill_enabled`` is False.
    """

    if not cfg.distill_enabled or not pages:
        return list(pages)

    threshold = cfg.distill_threshold_chars
    out: list[FetchedPage] = []
    distilled_count = 0
    chars_before_total = 0
    chars_after_total = 0

    for page in pages:
        if page.is_snippet or len(page.content) < threshold:
            out.append(page)
            continue

        chars_before_total += len(page.content)
        new_page = _distill_one(page, cfg, logger, chat=chat)
        chars_after_total += len(new_page.content)
        if new_page.distilled:
            distilled_count += 1
        out.append(new_page)

    if distilled_count > 0 and chars_before_total > 0:
        savings = chars_before_total - chars_after_total
        pct = savings / chars_before_total * 100
        logger.info(
            "Distilled %d/%d pages: %d -> %d chars (saved %d, %.0f%% reduction)",
            distilled_count,
            len(pages),
            chars_before_total,
            chars_after_total,
            savings,
            pct,
        )

    return out
