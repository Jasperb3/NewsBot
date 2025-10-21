"""Rendering utilities for digests."""
from __future__ import annotations

import datetime as dt
import re
from html import escape
from typing import Iterable, Sequence

from .models import ClusterBullet, Digest, Story, TopicSummary
from .utils import (
    citations_to_domains,
    domain_of,
    ensure_citation_suffix,
    extract_iso_dates,
    first_sentence,
    normalise_spaces,
    sorted_domains,
    strip_trailing_citations,
    to_title_case,
    truncate_sentence,
)

_MAX_AT_A_GLANCE_CHARS = 200
_MAX_TIMELINE_CHARS = 140
_MAX_STORY_BULLET_CHARS = 260
_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


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


def _topic_anchor(topic: TopicSummary) -> str:
    return _slugify(topic.topic)


def _cluster_anchor(topic_anchor: str, heading: str) -> str:
    return f"{topic_anchor}-{_slugify(heading)}"


def _truncate_with_citations(bullet: ClusterBullet, max_chars: int) -> str:
    body = strip_trailing_citations(bullet.text)
    truncated = truncate_sentence(body, max_chars)
    return ensure_citation_suffix(truncated, bullet.citations)


def _bullet_domains(bullet: ClusterBullet, sources_lookup: dict[int, tuple[str, str]]) -> list[str]:
    domains = citations_to_domains(bullet.citations, sources_lookup)
    return sorted_domains(domains)


def _extract_citations_from_text(text: str) -> list[int]:
    return [int(match.group(1)) for match in _CITATION_PATTERN.finditer(text or "")]


def _select_at_a_glance(
    topic: TopicSummary,
    sources_lookup: dict[int, tuple[str, str]],
    limit: int = 5,
    max_chars: int = 200,
) -> list[tuple[str, list[str]]]:
    if topic.stories:
        # Score stories by importance: updated > corroboration > date presence
        scored_entries: list[tuple[int, int, int, int, str, list[str]]] = []
        for idx, story in enumerate(topic.stories):
            # Calculate priority scores (negative for reverse sort)
            recency_score = -30 if story.updated else 0
            corroboration_score = -len(story.source_indices) * 5
            date_score = -10 if story.date else 0

            base = strip_trailing_citations(f"{story.headline} — {story.why}")
            truncated = truncate_sentence(base, max_chars)
            truncated = ensure_citation_suffix(truncated, story.source_indices)
            domains = sorted_domains(citations_to_domains(story.source_indices, sources_lookup))

            scored_entries.append((
                recency_score,
                corroboration_score,
                date_score,
                idx,  # Original order as tiebreaker
                truncated,
                domains,
            ))

        scored_entries.sort()
        selected = scored_entries[:limit]
        return [(entry[4], entry[5]) for entry in selected]

    # Cluster-based scoring when no stories exist
    pool: list[tuple[int, int, int, int, str, list[str]]] = []
    order = 0
    for cluster in topic.clusters:
        for bullet in cluster.bullets:
            domains = _bullet_domains(bullet, sources_lookup)
            # Prioritize by: more domains > more citations > original order
            domain_score = -len(domains) * 10
            citation_score = -len(bullet.citations) * 5
            truncated = _truncate_with_citations(bullet, max_chars)
            pool.append((
                domain_score,
                citation_score,
                order,
                order,  # Duplicate for compatibility
                truncated,
                domains,
            ))
            order += 1
    if not pool:
        return []
    pool.sort()
    selected = pool[:min(limit, len(pool))]
    return [(entry[4], entry[5]) for entry in selected]


def _format_story_bullet(text: str, sources_lookup: dict[int, tuple[str, str]]) -> tuple[str, list[str]]:
    citations = _extract_citations_from_text(text)
    truncated = truncate_sentence(strip_trailing_citations(text), _MAX_STORY_BULLET_CHARS)
    truncated = ensure_citation_suffix(truncated, citations)
    domains = sorted_domains(citations_to_domains(citations, sources_lookup))
    return truncated, domains


def _build_timeline(
    topic: TopicSummary,
    sources_lookup: dict[int, tuple[str, str]],
    max_entries: int = 8,
    max_chars: int = 140,
) -> dict[str, list[tuple[dt.date, str]]]:
    """Build timeline grouped into recent and historical sections."""
    seen_dates: dict[dt.date, str] = {}
    if topic.stories:
        for story in topic.stories:
            if not story.date:
                continue
            try:
                date_obj = dt.date.fromisoformat(story.date)
            except ValueError:
                continue
            if date_obj in seen_dates:
                continue
            base_text = story.bullets[0] if story.bullets else story.why or story.headline
            base_text = first_sentence(strip_trailing_citations(base_text))
            truncated = truncate_sentence(base_text, max_chars)
            first_citation = story.source_indices[0] if story.source_indices else None
            if first_citation:
                truncated = ensure_citation_suffix(truncated, [first_citation])
            seen_dates[date_obj] = truncated
    if not seen_dates:
        for cluster in topic.clusters:
            for bullet in cluster.bullets:
                citations = bullet.citations
                if not citations:
                    continue
                dates = extract_iso_dates(bullet.text)
                if not dates:
                    continue
                latest = max(dates)
                if latest in seen_dates:
                    continue
                sentence = first_sentence(strip_trailing_citations(bullet.text))
                truncated = truncate_sentence(sentence, max_chars)
                gist = ensure_citation_suffix(truncated, [citations[0]])
                seen_dates[latest] = gist

    # Group into recent and historical
    import datetime as dt_module
    recent_cutoff = dt_module.date.today() - dt_module.timedelta(days=30)
    all_entries = sorted(seen_dates.items(), key=lambda item: item[0], reverse=True)

    recent = [(d, text) for d, text in all_entries if d >= recent_cutoff]
    historical = [(d, text) for d, text in all_entries if d < recent_cutoff]

    return {
        'recent': recent[:max_entries // 2] if recent else [],
        'historical': historical[:max_entries // 2] if historical else [],
    }


def _estimate_reading_time(topic: TopicSummary) -> int:
    """Estimate reading time in minutes (assuming 200 words/min)."""
    total_words = 0

    # Count words in stories
    for story in topic.stories:
        total_words += len(story.headline.split())
        total_words += len(story.why.split())
        for bullet in story.bullets:
            total_words += len(strip_trailing_citations(bullet).split())

    # Count words in clusters
    for cluster in topic.clusters:
        total_words += len(cluster.heading.split())
        for bullet in cluster.bullets:
            total_words += len(strip_trailing_citations(bullet.text).split())

    # Account for "Further reading" section (estimated 5 words per entry)
    total_words += len(topic.unused_sources) * 5

    return max(1, total_words // 200)


def _topic_badge_texts(topic: TopicSummary) -> tuple[str, list[str]]:
    sources_count = len(topic.used_source_indices)
    domains_count = topic.coverage_domains
    total = topic.total_bullets or 0
    corroborated = topic.corroborated_bullets if total else 0
    base = f"Sources: {sources_count} · Domains: {domains_count} · Corroboration: {corroborated}/{total}"
    flags: list[str] = []
    if domains_count <= 1 or sources_count <= 1:
        flags.append("Single-source")
    if total and corroborated == 0:
        flags.append("Low corroboration")
    return base, flags


def _markdown_domain_suffix(domains: Sequence[str]) -> str:
    if not domains:
        return ""
    badged_domains = [_add_source_quality_badge(d) for d in domains]
    return f" — {', '.join(badged_domains)}"


def _html_domain_suffix(domains: Sequence[str]) -> str:
    if not domains:
        return ""
    badged_domains = [_add_source_quality_badge(d) for d in domains]
    return f"<span class=\"domains\">· {escape(', '.join(badged_domains))}</span>"


def _prepare_further_reading(topic: TopicSummary) -> tuple[list[tuple[str, str, str]], int]:
    grouped = [
        (domain_of(url), title, url)
        for title, url in topic.unused_sources
        if url
    ]
    grouped.sort(key=lambda item: (item[0], item[1].lower()))
    capped = grouped[:8]
    remaining = max(0, len(grouped) - len(capped))
    return capped, remaining


def _generate_executive_summary(digest: Digest, limit: int = 5) -> list[tuple[str, str]]:
    """Extract top stories across all topics for executive summary."""
    all_entries: list[tuple[int, int, int, str, str]] = []

    for topic in digest.topics:
        if topic.stories:
            # Use stories if available
            for story in topic.stories:
                # Score: updated=30, corroboration=5 per source, has_date=10
                recency_score = -30 if story.updated else 0
                corroboration_score = -len(story.source_indices) * 5
                date_score = -10 if story.date else 0
                score = recency_score + corroboration_score + date_score

                summary = strip_trailing_citations(f"{story.headline} — {story.why}")
                all_entries.append((
                    score,
                    recency_score,
                    corroboration_score,
                    to_title_case(topic.topic),
                    summary,
                ))
        else:
            # Fall back to top cluster bullets
            for cluster in topic.clusters[:1]:  # Only first cluster
                for bullet in cluster.bullets[:2]:  # Top 2 bullets
                    citation_score = -len(bullet.citations) * 5
                    all_entries.append((
                        citation_score,
                        0,
                        citation_score,
                        to_title_case(topic.topic),
                        strip_trailing_citations(bullet.text),
                    ))

    if not all_entries:
        return []

    # Sort by score (most important first)
    all_entries.sort()
    selected = all_entries[:limit]

    return [(topic, summary) for _, _, _, topic, summary in selected]


def _compute_confidence_level(source_count: int) -> str:
    """Compute confidence level based on number of independent sources."""
    if source_count >= 4:
        return f"High - {source_count} independent sources"
    elif source_count >= 2:
        return f"Medium - {source_count} sources"
    else:
        return "Low - Single source report"


def _add_source_quality_badge(domain: str) -> str:
    """Add quality indicator badge based on source type."""
    # Trusted news sources
    trusted_news = {
        'reuters.com', 'apnews.com', 'bbc.co.uk', 'bbc.com',
        'npr.org', 'pbs.org', 'theguardian.com', 'ft.com',
        'wsj.com', 'economist.com', 'nature.com', 'science.org'
    }

    # Check for trusted news
    if domain in trusted_news:
        return f"⭐ {domain}"

    # Check for official sources (.gov, .mil, international orgs)
    if any(domain.endswith(suffix) for suffix in ['.gov', '.mil', '.int']):
        return f"🏛️ {domain}"

    # Check for academic sources
    if domain.endswith('.edu') or domain.endswith('.ac.uk'):
        return f"🎓 {domain}"

    # Check for specific official organizations
    official_orgs = ['un.org', 'who.int', 'europa.eu', 'oecd.org', 'worldbank.org', 'imf.org']
    if any(org in domain for org in official_orgs):
        return f"🏛️ {domain}"

    # Default: no badge
    return domain


def _compute_digest_statistics(digest: Digest) -> dict[str, int | float]:
    """Compute summary statistics for the digest."""
    total_bullets = sum(t.total_bullets or 0 for t in digest.topics)
    total_corroborated = sum(t.corroborated_bullets for t in digest.topics)

    updated_stories = sum(
        len([s for s in t.stories if s.updated])
        for t in digest.topics
    )

    all_domains = {domain_of(url) for _, _, url in digest.sources}

    return {
        'topics': len(digest.topics),
        'sources': len(digest.sources),
        'domains': len(all_domains),
        'corroboration_rate': (total_corroborated / total_bullets * 100) if total_bullets else 0,
        'avg_sources_per_topic': len(digest.sources) / len(digest.topics) if digest.topics else 0,
        'updated_count': updated_stories,
        'total_bullets': total_bullets,
        'corroborated_bullets': total_corroborated,
    }


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

    # Add executive summary if there are multiple topics or stories
    if len(digest.topics) > 1 or any(topic.stories for topic in digest.topics):
        exec_summary = _generate_executive_summary(digest)
        if exec_summary:
            lines.append("")
            lines.append("## Executive Summary")
            for topic_name, summary_text in exec_summary:
                lines.append(f"- **{topic_name}:** {summary_text}")

    # Add digest statistics dashboard
    stats = _compute_digest_statistics(digest)
    lines.append("")
    lines.append("## Digest Overview")
    lines.append(f"📊 **Coverage:** {stats['topics']} topics · {stats['sources']} sources · {stats['domains']} unique domains")
    lines.append(f"🔍 **Quality:** {stats['corroboration_rate']:.0f}% corroboration rate · {stats['avg_sources_per_topic']:.1f} sources/topic avg")
    if stats['updated_count'] > 0:
        lines.append(f"⏱️ **Recency:** {stats['updated_count']} {'story' if stats['updated_count'] == 1 else 'stories'} updated since last run")

    lines.append("")
    lines.append("## Table of Contents")
    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        reading_time = _estimate_reading_time(topic)
        lines.append(f"- [{to_title_case(topic.topic)}](#{topic_anchor}) _~{reading_time} min read_")
        for cluster in topic.clusters:
            cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
            lines.append(f"  - [{cluster.heading}](#{cluster_anchor})")

    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        title = to_title_case(topic.topic)
        lines.append("")
        lines.append(f"<a id=\"{topic_anchor}\"></a>")
        lines.append(f"## {title}")

        base_badge, flags = _topic_badge_texts(topic)
        badge_line = f"_{base_badge}_"
        if flags:
            badge_line += " " + " ".join(f"_{flag}_" for flag in flags)
        lines.append(badge_line)

        at_a_glance = _select_at_a_glance(topic, sources_lookup)
        if at_a_glance:
            lines.append("### At a glance")
            for text, domains in at_a_glance:
                lines.append(f"- {text}{_markdown_domain_suffix(domains)}")

        if topic.stories:
            lines.append("### Top stories")
            for story in topic.stories:
                headline_text = story.headline
                if story.urls:
                    headline_text = f"[{headline_text}]({story.urls[0]})"
                if story.updated:
                    headline_text += " _(Updated since last run)_"
                lines.append(f"#### {headline_text}")
                story_domains = sorted_domains(citations_to_domains(story.source_indices, sources_lookup))
                badged_domains = [_add_source_quality_badge(d) for d in story_domains]
                meta_parts = [story.date or "date n/a", f"Sources: {len(story.source_indices)}"]
                meta_parts.append(
                    f"Domains: {', '.join(badged_domains)}" if badged_domains else "Domains: n/a"
                )
                lines.append(f"*{' · '.join(meta_parts)}*")
                # Add confidence indicator
                confidence = _compute_confidence_level(len(story.source_indices))
                lines.append(f"*Confidence: {confidence}*")
                if story.update_note:
                    lines.append(f"*{story.update_note}*")
                lines.append(f"_Why it matters:_ {story.why}")
                for bullet_text in story.bullets:
                    formatted, domains = _format_story_bullet(bullet_text, sources_lookup)
                    lines.append(f"- {formatted}{_markdown_domain_suffix(domains)}")

        timeline = _build_timeline(topic, sources_lookup)
        if timeline['recent'] or timeline['historical']:
            lines.append("### Timeline")
            if timeline['recent']:
                lines.append("**Recent developments:**")
                for date_obj, gist in timeline['recent']:
                    lines.append(f"- {date_obj.isoformat()} — {gist}")
            if timeline['historical']:
                if timeline['recent']:
                    lines.append("")
                lines.append("**Historical context:**")
                for date_obj, gist in timeline['historical']:
                    lines.append(f"- {date_obj.isoformat()} — {gist}")

        if topic.clusters:
            for cluster in topic.clusters:
                cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
                if topic.stories and cluster.heading.lower() == "top stories":
                    continue
                lines.append(f"<a id=\"{cluster_anchor}\"></a>")
                lines.append(f"### {cluster.heading}")
                for bullet in cluster.bullets:
                    domains = _bullet_domains(bullet, sources_lookup)
                    lines.append(f"- {bullet.text}{_markdown_domain_suffix(domains)}")
        else:
            lines.append("*No sufficiently reliable updates found.*")

        further_reading, remaining = _prepare_further_reading(topic)
        if further_reading:
            lines.append("### Further reading")
            for domain, title_fr, url_fr in further_reading:
                lines.append(f"- {domain} • {title_fr} — {url_fr}")
            if remaining:
                lines.append(f"- … and {remaining} more")

        lines.append("[Back to top](#table-of-contents)")

    if digest.sources:
        lines.append("")
        lines.append("## Sources")
        for idx, title, url in digest.sources:
            lines.append(f"- [{idx}] {title} — {url}")

    lines.append("")
    lines.append("---")
    footer = (
        f"Generated at {digest.run_time_iso} ({digest.timezone}) using {digest.model}. "
        "Summaries derived from Ollama web search with clustering, deduplication, and corroboration heuristics."
    )
    if digest.elapsed_seconds is not None:
        footer += f" Elapsed: {digest.elapsed_seconds:.1f}s."
    lines.append(footer)

    return "\n".join(lines).strip() + "\n"


def render_html(digest: Digest) -> str:
    """Render the digest to an HTML document with enhanced styling."""

    run_date = _format_run_date(digest.run_time_iso)
    sources_lookup = _sources_lookup(digest)

    head_css = (
        "body{font-family:'Segoe UI',Arial,sans-serif;margin:0;padding:0;background:var(--bg);color:var(--fg);}"
        "main{max-width:900px;margin:0 auto;padding:2rem;}"
        "nav{position:sticky;top:0;background:var(--bg);border-bottom:1px solid var(--border);padding:1rem 2rem;z-index:10;}"
        "nav ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:1rem;}"
        "nav a{text-decoration:none;color:var(--accent);}"
        "h1{font-size:2.2rem;margin-bottom:0.5rem;}h2{margin-top:2.5rem;}h3{margin-top:1.5rem;}"
        "section{margin-bottom:2rem;}ul{padding-left:1.2rem;}li{margin-bottom:0.4rem;}"
        "button.copy-link{background:none;border:1px solid var(--border);color:var(--accent);cursor:pointer;margin-left:0.4rem;font-size:0.85rem;padding:0.1rem 0.4rem;border-radius:0.4rem;}"
        "footer{margin-top:3rem;font-size:0.9rem;color:var(--muted);}"
        ".badge{display:inline-block;border:1px solid var(--border);padding:.15rem .4rem;border-radius:.5rem;margin-right:.4rem;font-size:.85rem;}"
        ".domains{opacity:.75;font-size:.9em;margin-left:.25rem;}"
        "p.meta{font-size:0.9rem;color:var(--muted);margin:0.2rem 0;}"
        ".back-to-top{margin-top:1rem;display:inline-block;}"
        "@media (prefers-color-scheme: dark){:root{--bg:#111;--fg:#f4f4f4;--accent:#9cc0ff;--border:#333;--muted:#bbb;}}"
        "@media (prefers-color-scheme: light){:root{--bg:#ffffff;--fg:#222;--accent:#3050a0;--border:#ddd;--muted:#666;}}"
        "@media print{nav{display:none;}body{background:#fff;color:#000;}a::after{content:' (' attr(href) ')';font-size:0.8em;color:#333;}main{padding:1rem;}}"
    )

    js_copy = "function copyLink(id){const url=window.location.origin+window.location.pathname+'#'+id;navigator.clipboard.writeText(url);}"

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

    parts.extend(["  <nav>", "    <ul>"])
    for topic in digest.topics:
        anchor = _topic_anchor(topic)
        reading_time = _estimate_reading_time(topic)
        parts.append(f"      <li><a href=\"#{escape(anchor)}\">{escape(to_title_case(topic.topic))} <span style=\"opacity:0.7;font-size:0.85em\">(~{reading_time} min)</span></a></li>")
    parts.extend(["    </ul>", "  </nav>"])

    parts.append("  <main>")
    parts.append(f"    <h1>Daily Digest — {escape(run_date)} ({escape(digest.timezone)})</h1>")
    parts.append(f"    <p>{escape(summary_line)}</p>")

    # Add executive summary if there are multiple topics or stories
    if len(digest.topics) > 1 or any(topic.stories for topic in digest.topics):
        exec_summary = _generate_executive_summary(digest)
        if exec_summary:
            parts.append("    <section>")
            parts.append("      <h2 id=\"executive-summary\">Executive Summary</h2>")
            parts.append("      <ul>")
            for topic_name, summary_text in exec_summary:
                parts.append(f"        <li><strong>{escape(topic_name)}:</strong> {escape(summary_text)}</li>")
            parts.append("      </ul>")
            parts.append("    </section>")

    # Add digest statistics dashboard
    stats = _compute_digest_statistics(digest)
    parts.append("    <section>")
    parts.append("      <h2 id=\"digest-overview\">Digest Overview</h2>")
    parts.append(f"      <p>📊 <strong>Coverage:</strong> {stats['topics']} topics · {stats['sources']} sources · {stats['domains']} unique domains</p>")
    parts.append(f"      <p>🔍 <strong>Quality:</strong> {stats['corroboration_rate']:.0f}% corroboration rate · {stats['avg_sources_per_topic']:.1f} sources/topic avg</p>")
    if stats['updated_count'] > 0:
        story_word = 'story' if stats['updated_count'] == 1 else 'stories'
        parts.append(f"      <p>⏱️ <strong>Recency:</strong> {stats['updated_count']} {story_word} updated since last run</p>")
    parts.append("    </section>")

    parts.append("    <section>")
    parts.append("      <h2 id=\"table-of-contents\">Table of Contents</h2>")
    parts.append("      <ul>")
    for topic in digest.topics:
        topic_anchor = _topic_anchor(topic)
        parts.append(f"        <li><a href=\"#{escape(topic_anchor)}\">{escape(to_title_case(topic.topic))}</a>")
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
        title = to_title_case(topic.topic)
        parts.append(f"    <section id=\"{escape(topic_anchor)}\">")
        parts.append(
            f"      <h2>{escape(title)}<button class=\"copy-link\" onclick=\"copyLink('{escape(topic_anchor)}')\">Copy link</button></h2>"
        )

        base_badge, flags = _topic_badge_texts(topic)
        badge_html = [f"<span class=\"badge\">{escape(base_badge)}</span>"]
        badge_html.extend(f"<span class=\"badge\">{escape(flag)}</span>" for flag in flags)
        parts.append(f"      <p>{''.join(badge_html)}</p>")

        at_a_glance = _select_at_a_glance(topic, sources_lookup)
        if at_a_glance:
            at_id = f"at-a-glance-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(at_id)}\">At a glance<button class=\"copy-link\" onclick=\"copyLink('{escape(at_id)}')\">Copy link</button></h3>"
            )
            parts.append("      <ul>")
            for text, domains in at_a_glance:
                parts.append(f"        <li>{escape(text)}{_html_domain_suffix(domains)}</li>")
            parts.append("      </ul>")

        if topic.stories:
            parts.append("      <h3>Top stories</h3>")
            for story in topic.stories:
                headline_html = escape(story.headline)
                if story.urls:
                    headline_html = f"<a href=\"{escape(story.urls[0])}\">{headline_html}</a>"
                if story.updated:
                    headline_html += " <span class=\"badge\">Updated since last run</span>"
                parts.append(f"      <h4>{headline_html}</h4>")
                story_domains = sorted_domains(citations_to_domains(story.source_indices, sources_lookup))
                badged_domains = [_add_source_quality_badge(d) for d in story_domains]
                meta_parts = [escape(story.date or "date n/a"), f"Sources: {len(story.source_indices)}"]
                meta_parts.append(
                    escape(", ".join(badged_domains)) if badged_domains else "Domains: n/a"
                )
                parts.append(f"      <p class=\"meta\">{' · '.join(meta_parts)}</p>")
                # Add confidence indicator
                confidence = _compute_confidence_level(len(story.source_indices))
                parts.append(f"      <p class=\"meta\">Confidence: {escape(confidence)}</p>")
                if story.update_note:
                    parts.append(f"      <p><em>{escape(story.update_note)}</em></p>")
                parts.append(f"      <p><strong>Why it matters:</strong> {escape(story.why)}</p>")
                parts.append("      <ul>")
                for bullet_text in story.bullets:
                    formatted, domains = _format_story_bullet(bullet_text, sources_lookup)
                    parts.append(
                        f"        <li>{escape(formatted)}{_html_domain_suffix(domains)}</li>"
                    )
                parts.append("      </ul>")

        timeline = _build_timeline(topic, sources_lookup)
        if timeline['recent'] or timeline['historical']:
            timeline_id = f"timeline-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(timeline_id)}\">Timeline<button class=\"copy-link\" onclick=\"copyLink('{escape(timeline_id)}')\">Copy link</button></h3>"
            )
            if timeline['recent']:
                parts.append("      <p><strong>Recent developments:</strong></p>")
                parts.append("      <ul>")
                for date_obj, gist in timeline['recent']:
                    parts.append(f"        <li>{escape(date_obj.isoformat())} — {escape(gist)}</li>")
                parts.append("      </ul>")
            if timeline['historical']:
                parts.append("      <p><strong>Historical context:</strong></p>")
                parts.append("      <ul>")
                for date_obj, gist in timeline['historical']:
                    parts.append(f"        <li>{escape(date_obj.isoformat())} — {escape(gist)}</li>")
                parts.append("      </ul>")

        if topic.clusters:
            for cluster in topic.clusters:
                cluster_anchor = _cluster_anchor(topic_anchor, cluster.heading)
                if topic.stories and cluster.heading.lower() == "top stories":
                    continue
                parts.append(
                    f"      <h3 id=\"{escape(cluster_anchor)}\">{escape(cluster.heading)}<button class=\"copy-link\" onclick=\"copyLink('{escape(cluster_anchor)}')\">Copy link</button></h3>"
                )
                parts.append("      <ul>")
                for bullet in cluster.bullets:
                    domains = _bullet_domains(bullet, sources_lookup)
                    parts.append(
                        f"        <li>{escape(bullet.text)}{_html_domain_suffix(domains)}</li>"
                    )
                parts.append("      </ul>")
        else:
            parts.append("      <p><em>No sufficiently reliable updates found.</em></p>")

        further_reading, remaining = _prepare_further_reading(topic)
        if further_reading:
            further_id = f"further-{topic_anchor}"
            parts.append(
                f"      <h3 id=\"{escape(further_id)}\">Further reading<button class=\"copy-link\" onclick=\"copyLink('{escape(further_id)}')\">Copy link</button></h3>"
            )
            parts.append("      <ul>")
            for domain, title_fr, url_fr in further_reading:
                parts.append(
                    f"        <li><span class=\"badge\">{escape(domain)}</span> <a href=\"{escape(url_fr)}\">{escape(title_fr)}</a></li>"
                )
            if remaining:
                parts.append(f"        <li>… and {remaining} more</li>")
            parts.append("      </ul>")

        parts.append("      <a class=\"back-to-top\" href=\"#table-of-contents\">Back to top</a>")
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
        "Summaries derived from Ollama web search with clustering, deduplication, and corroboration heuristics."
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
        timeline_entries = _build_timeline(topic, sources_lookup)
        further_reading, remaining = _prepare_further_reading(topic)
        badge_base, badge_flags = _topic_badge_texts(topic)
        topics_payload.append(
            {
                "topic": to_title_case(topic.topic),
                "anchor": _topic_anchor(topic),
                "coverage_domains": topic.coverage_domains,
                "corroborated_bullets": topic.corroborated_bullets,
                "total_bullets": topic.total_bullets,
                "badges": {"summary": badge_base, "flags": badge_flags},
                "at_a_glance": [
                    {"text": text, "domains": domains}
                    for text, domains in at_a_glance
                ],
                "timeline": {
                    "recent": [
                        {"date": date.isoformat(), "text": gist}
                        for date, gist in timeline_entries.get('recent', [])
                    ],
                    "historical": [
                        {"date": date.isoformat(), "text": gist}
                        for date, gist in timeline_entries.get('historical', [])
                    ],
                },
                "stories": [
                    {
                        "headline": story.headline,
                        "date": story.date,
                        "why": story.why,
                        "bullets": story.bullets,
                        "source_indices": story.source_indices,
                        "urls": story.urls,
                        "updated": story.updated,
                        "update_note": story.update_note,
                    }
                    for story in topic.stories
                ],
                "clusters": [
                    {
                        "heading": cluster.heading,
                        "bullets": [
                            {
                                "text": bullet.text,
                                "citations": bullet.citations,
                                "domains": _bullet_domains(bullet, sources_lookup),
                            }
                            for bullet in cluster.bullets
                        ],
                    }
                    for cluster in topic.clusters
                ],
                "further_reading": [
                    {"domain": domain, "title": title_fr, "url": url_fr}
                    for domain, title_fr, url_fr in further_reading
                ],
                "further_reading_overflow": remaining,
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
