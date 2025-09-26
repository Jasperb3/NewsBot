"""Rendering utilities for digests."""
from __future__ import annotations

import datetime as dt
from html import escape
from typing import Iterable

from .models import Digest, TopicSummary
from .utils import citations_to_domains, extract_dates_from_bullets


def _format_run_date(run_time_iso: str) -> str:
    try:
        dt_obj = dt.datetime.fromisoformat(run_time_iso)
    except ValueError:
        try:
            dt_obj = dt.datetime.strptime(run_time_iso, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return run_time_iso
    return dt_obj.date().isoformat()


def _slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "section"


def _sources_lookup(digest: Digest) -> dict[int, tuple[str, str]]:
    return {idx: (title, url) for idx, title, url in digest.sources}


def _select_at_a_glance(topic: TopicSummary, sources_lookup: dict[int, tuple[str, str]], limit: int = 5) -> list[str]:
    pool = []
    for cluster in topic.clusters:
        for bullet in cluster.bullets:
            domains = citations_to_domains(bullet.citations, sources_lookup)
            pool.append(
                (
                    -len(domains),  # more domains (higher confidence)
                    len(bullet.text),
                    -len(bullet.citations),
                    bullet.text,
                )
            )

    if not pool:
        return []

    pool.sort()
    selected = [entry[3] for entry in pool[: max(3, min(limit, len(pool)))]]
    return selected


def _build_timeline(topic: TopicSummary) -> list[tuple[str, str]]:
    bullets = [bullet for cluster in topic.clusters for bullet in cluster.bullets]
    dated = extract_dates_from_bullets(bullets)
    seen: set[tuple[str, str]] = set()
    entries: list[tuple[str, str]] = []
    for date_obj, bullet in dated:
        key = (date_obj.isoformat(), bullet.text)
        if key in seen:
            continue
        seen.add(key)
        entries.append(key)
    return entries


def _topic_anchor(topic: TopicSummary) -> str:
    return _slugify(topic.topic)


def _cluster_anchor(topic_anchor: str, heading: str) -> str:
    return f"{topic_anchor}-{_slugify(heading)}"


def render_markdown(digest: Digest) -> str:
    """Render the digest to Markdown."""

    run_date = _format_run_date(digest.run_time_iso)
    sources_lookup = _sources_lookup(digest)

    lines: list[str] = [f"# Daily Digest — {run_date} ({digest.timezone})"]
    summary_line = (
        f"Generated with {digest.model} — Topics: {len(digest.topics)}; Sources: {len(digest.sources)}"
    )
    if digest.elapsed_seconds is not None:
        summary_line += f"; Elapsed: {digest.elapsed_seconds:.1f}s"
    lines.append(summary_line)

    lines.append("")
    lines.append("## Table of Contents")
    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        lines.append(f"- [{topic.topic}](#{topic_anchor})")
        for cluster in topic.clusters:
            cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
            lines.append(f"  - [{cluster.heading}](#{cluster_anchor})")

    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        lines.append("")
        lines.append(f"<a id=\"{topic_anchor}\"></a>")
        lines.append(f"## {topic.topic}")
        lines.append(
            f"Coverage: {topic.coverage_domains} domains | Corroboration: {topic.corroborated_bullets}/{topic.total_bullets} bullets"
        )

        at_a_glance = _select_at_a_glance(topic, sources_lookup)
        if at_a_glance:
            lines.append("### At a glance")
            for entry in at_a_glance[:5]:
                lines.append(f"- {entry}")

        timeline_entries = _build_timeline(topic)
        if timeline_entries:
            lines.append("### Timeline")
            for date_str, text in timeline_entries[:8]:
                lines.append(f"- {date_str} — {text}")

        for cluster in topic.clusters:
            cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
            lines.append(f"<a id=\"{cluster_anchor}\"></a>")
            lines.append(f"### {cluster.heading}")
            for bullet in cluster.bullets:
                lines.append(f"- {bullet.text}")

        if topic.unused_sources:
            lines.append("### Further reading")
            for title, url in topic.unused_sources:
                lines.append(f"- {title} — {url}")

    if digest.sources:
        lines.append("")
        lines.append("## Sources")
        for idx, title, url in digest.sources:
            lines.append(f"- [{idx}] {title} — {url}")

    lines.append("")
    lines.append("---")
    footer = (
        f"Generated at {digest.run_time_iso} ({digest.timezone}) using {digest.model}. "
        "Summaries derived from Ollama web search results with de-duplication and corroboration heuristics."
    )
    if digest.elapsed_seconds is not None:
        footer += f" Elapsed: {digest.elapsed_seconds:.1f}s."
    lines.append(footer)

    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    """Render the digest to an HTML document with TOC and anchors."""

    run_date = _format_run_date(digest.run_time_iso)
    sources_lookup = _sources_lookup(digest)

    head_css = """
body{font-family:"Segoe UI",Arial,sans-serif;margin:0;padding:0;background:var(--bg);color:var(--fg);}main{max-width:900px;margin:0 auto;padding:2rem;}nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--border);padding:1rem 2rem;z-index:10;}nav ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:1rem;}nav a{text-decoration:none;color:var(--accent);}h1{font-size:2.2rem;margin-bottom:0.5rem;}h2{margin-top:2.5rem;}h3{margin-top:1.5rem;}section{margin-bottom:2rem;}ul{padding-left:1.2rem;}li{margin-bottom:0.4rem;}button.copy-link{background:none;border:none;color:var(--accent);cursor:pointer;margin-left:0.4rem;font-size:0.9rem;}footer{margin-top:3rem;font-size:0.9rem;color:var(--muted);}pre,code{font-family:"Fira Code",monospace;}@media (prefers-color-scheme: dark){:root{--bg:#111;--fg:#f4f4f4;--accent:#9cc0ff;--border:#333;--muted:#bbb;}}@media (prefers-color-scheme: light){:root{--bg:#ffffff;--fg:#222;--accent:#3050a0;--border:#ddd;--muted:#666;}}@media print{nav{display:none;}body{background:#fff;color:#000;}a::after{content:" (" attr(href) ")";font-size:0.8em;color:#333;}main{padding:1rem;}}
"""

    js_copy = """
function copyLink(id){const url=window.location.origin+window.location.pathname+'#'+id;navigator.clipboard.writeText(url);}
"""

    parts: list[str] = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"utf-8\">",
        f"  <title>Daily Digest — {escape(run_date)}</title>",
        f"  <style>{head_css}</style>",
        f"  <script>{js_copy}</script>",
        "</head>",
        "<body>",
    ]

    summary_line = (
        f"Generated with {escape(digest.model)} — Topics: {len(digest.topics)}; Sources: {len(digest.sources)}"
    )
    if digest.elapsed_seconds is not None:
        summary_line += f"; Elapsed: {digest.elapsed_seconds:.1f}s"

    parts.extend(
        [
            "  <nav>",
            "    <ul>",
        ]
    )
    for topic in digest.topics:
        anchor = _topic_anchor(topic)
        parts.append(f"      <li><a href=\"#{escape(anchor)}\">{escape(topic.topic)}</a></li>")
    parts.extend(["    </ul>", "  </nav>"])

    parts.append("  <main>")
    parts.append(f"    <h1>Daily Digest — {escape(run_date)} ({escape(digest.timezone)})</h1>")
    parts.append(f"    <p>{escape(summary_line)}</p>")

    # In-body detailed TOC
    parts.append("    <section>")
    parts.append("      <h2 id=\"table-of-contents\">Table of Contents</h2>")
    parts.append("      <ul>")
    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        parts.append(f"        <li><a href=\"#{escape(topic_anchor)}\">{escape(topic.topic)}</a>")
        if topic.clusters:
            parts.append("          <ul>")
            for cluster in topic.clusters:
                cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
                parts.append(
                    f"            <li><a href=\"#{escape(cluster_anchor)}\">{escape(cluster.heading)}</a></li>"
                )
            parts.append("          </ul>")
        parts.append("        </li>")
    parts.append("      </ul>")
    parts.append("    </section>")

    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        parts.append(f"    <section id=\"{escape(topic_anchor)}\">")
        parts.append(
            f"      <h2>{escape(topic.topic)}<button class=\"copy-link\" onclick=\"copyLink('{escape(topic_anchor)}')\">Copy link</button></h2>"
        )
        parts.append(
            f"      <p>Coverage: {topic.coverage_domains} domains | Corroboration: {topic.corroborated_bullets}/{topic.total_bullets} bullets</p>"
        )

        at_a_glance = _select_at_a_glance(topic, sources_lookup)
        if at_a_glance:
            at_id = f"at-a-glance-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(at_id)}\">At a glance<button class=\"copy-link\" onclick=\"copyLink('{escape(at_id)}')\">Copy link</button></h3>"
            )
            parts.append(f"      <div id=\"{escape(at_id)}-content\">")
            parts.append("        <ul>")
            for entry in at_a_glance[:5]:
                parts.append(f"          <li>{escape(entry)}</li>")
            parts.append("        </ul>")
            parts.append("      </div>")

        timeline_entries = _build_timeline(topic)
        if timeline_entries:
            timeline_id = f"timeline-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(timeline_id)}\">Timeline<button class=\"copy-link\" onclick=\"copyLink('{escape(timeline_id)}')\">Copy link</button></h3>"
            )
            parts.append(f"      <div id=\"{escape(timeline_id)}-content\">")
            parts.append("        <ul>")
            for date_str, text in timeline_entries[:8]:
                parts.append(f"          <li>{escape(date_str)} — {escape(text)}</li>")
            parts.append("        </ul>")
            parts.append("      </div>")

        for cluster in topic.clusters:
            cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
            parts.append(
                f"      <h3 id=\"{escape(cluster_anchor)}\">{escape(cluster.heading)}<button class=\"copy-link\" onclick=\"copyLink('{escape(cluster_anchor)}')\">Copy link</button></h3>"
            )
            parts.append("      <ul>")
            for bullet in cluster.bullets:
                parts.append(f"        <li>{escape(bullet.text)}</li>")
            parts.append("      </ul>")

        if topic.unused_sources:
            further_id = f"further-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(further_id)}\">Further reading<button class=\"copy-link\" onclick=\"copyLink('{escape(further_id)}')\">Copy link</button></h3>"
            )
            parts.append(f"      <div id=\"{escape(further_id)}-content\">")
            parts.append("        <ul>")
            for title, url in topic.unused_sources:
                parts.append(
                    f"          <li><a href=\"{escape(url)}\">{escape(title)}</a></li>"
                )
            parts.append("        </ul>")
            parts.append("      </div>")

        parts.append("    </section>")

    if digest.sources:
        parts.append("    <section id=\"sources\">")
        parts.append("      <h2>Sources<button class=\"copy-link\" onclick=\"copyLink('sources')\">Copy link</button></h2>")
        parts.append("      <ul>")
        for idx, title, url in digest.sources:
            parts.append(
                f"        <li>[{idx}] <a href=\"{escape(url)}\">{escape(title)}</a></li>"
            )
        parts.append("      </ul>")
        parts.append("    </section>")

    footer_text = (
        f"Generated at {escape(digest.run_time_iso)} ({escape(digest.timezone)}) using {escape(digest.model)}. "
        "Summaries derived from Ollama web search results with de-duplication and corroboration heuristics."
    )
    if digest.elapsed_seconds is not None:
        footer_text += f" Elapsed: {digest.elapsed_seconds:.1f}s."

    parts.append(f"    <footer>{footer_text}</footer>")
    parts.append("  </main>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def render_json(digest: Digest) -> dict:
    """Return a JSON-serialisable representation of the digest."""

    sources_lookup = _sources_lookup(digest)

    topics_payload = []
    for topic in digest.topics:
        at_a_glance = _select_at_a_glance(topic, sources_lookup)
        timeline_entries = _build_timeline(topic)
        topics_payload.append(
            {
                "topic": topic.topic,
                "coverage_domains": topic.coverage_domains,
                "corroborated_bullets": topic.corroborated_bullets,
                "total_bullets": topic.total_bullets,
                "at_a_glance": at_a_glance,
                "timeline": [
                    {"date": date_str, "text": text}
                    for date_str, text in timeline_entries
                ],
                "clusters": [
                    {
                        "heading": cluster.heading,
                        "bullets": [
                            {"text": bullet.text, "citations": bullet.citations}
                            for bullet in cluster.bullets
                        ],
                    }
                    for cluster in topic.clusters
                ],
                "used_sources": [
                    {
                        "index": idx,
                        "title": sources_lookup[idx][0],
                        "url": sources_lookup[idx][1],
                    }
                    for idx in topic.used_source_indices
                    if idx in sources_lookup
                ],
                "further_reading": [
                    {"title": title, "url": url}
                    for title, url in topic.unused_sources
                ],
            }
        )

    payload = {
        "run_id": digest.run_id,
        "run_time_iso": digest.run_time_iso,
        "timezone": digest.timezone,
        "model": digest.model,
        "elapsed_seconds": digest.elapsed_seconds,
        "topics": topics_payload,
        "sources": [
            {"index": idx, "title": title, "url": url}
            for idx, title, url in digest.sources
        ],
    }

    return payload
