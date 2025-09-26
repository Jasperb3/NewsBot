"""Rendering utilities for digests."""
from __future__ import annotations

import datetime as dt
from html import escape

from .models import Digest


def _format_run_date(run_time_iso: str) -> str:
    try:
        dt_obj = dt.datetime.fromisoformat(run_time_iso)
    except ValueError:
        try:
            dt_obj = dt.datetime.strptime(run_time_iso, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return run_time_iso
    return dt_obj.date().isoformat()


def _ensure_citations(text: str, citations: list[int]) -> str:
    if not citations:
        return text
    required = [f"[{idx}]" for idx in citations]
    if all(marker in text for marker in required):
        return text
    return text.rstrip() + " " + "".join(required)


def render_markdown(digest: Digest) -> str:
    """Render the digest to Markdown."""
    run_date = _format_run_date(digest.run_time_iso)
    lines: list[str] = [f"# Daily Digest — {run_date} ({digest.timezone})"]

    for topic in digest.topics:
        lines.append("")
        lines.append(f"## {topic.topic}")
        for cluster in topic.clusters:
            lines.append(f"### {cluster.heading}")
            for bullet in cluster.bullets:
                text = _ensure_citations(bullet.text, bullet.citations)
                lines.append(f"- {text}")

    if digest.sources:
        lines.append("")
        lines.append("## Sources")
        for idx, title, url in digest.sources:
            lines.append(f"- [{idx}] {title} — {url}")

    footer_parts = [
        "",
        "---",
        (
            f"Generated at {digest.run_time_iso} ({digest.timezone}) using {digest.model}. "
            f"Topics: {len(digest.topics)}; sources: {len(digest.sources)}."
        ),
    ]
    if digest.elapsed_seconds is not None:
        footer_parts[-1] += f" Elapsed: {digest.elapsed_seconds:.1f}s."
    lines.extend(footer_parts)

    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    """Render the digest to a minimal HTML page."""
    run_date = _format_run_date(digest.run_time_iso)
    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"utf-8\">",
        f"  <title>Daily Digest — {escape(run_date)}</title>",
        "  <style>body{font-family:Arial,sans-serif;margin:2rem;color:#222;}"
        "h1{margin-bottom:1rem;}h2{margin-top:2rem;}h3{margin-top:1.5rem;}"
        "ul{padding-left:1.2rem;}li{margin-bottom:0.4rem;}footer{margin-top:2rem;font-size:0.9rem;color:#555;}"
        "</style>",
        "</head>",
        "<body>",
        f"  <h1>Daily Digest — {escape(run_date)} ({escape(digest.timezone)})</h1>",
    ]

    for topic in digest.topics:
        parts.append(f"  <h2>{escape(topic.topic)}</h2>")
        for cluster in topic.clusters:
            parts.append(f"  <h3>{escape(cluster.heading)}</h3>")
            parts.append("  <ul>")
            for bullet in cluster.bullets:
                text = escape(_ensure_citations(bullet.text, bullet.citations))
                parts.append(f"    <li>{text}</li>")
            parts.append("  </ul>")

    if digest.sources:
        parts.append("  <h2>Sources</h2>")
        parts.append("  <ul>")
        for idx, title, url in digest.sources:
            parts.append(
                f"    <li>[{idx}] <a href=\"{escape(url)}\">{escape(title)}</a></li>"
            )
        parts.append("  </ul>")

    footer_text = (
        f"Generated at {escape(digest.run_time_iso)} ({escape(digest.timezone)}) using {escape(digest.model)}. "
        f"Topics: {len(digest.topics)}; sources: {len(digest.sources)}."
    )
    if digest.elapsed_seconds is not None:
        footer_text += f" Elapsed: {digest.elapsed_seconds:.1f}s."

    parts.extend([
        f"  <footer>{footer_text}</footer>",
        "</body>",
        "</html>",
    ])

    return "\n".join(parts)
