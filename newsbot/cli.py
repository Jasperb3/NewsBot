"""Command-line interface for news-digest-bot."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import AppConfig, load_config
from .fetch import fetch_pages
from .log import get_logger
from .models import Digest, TopicSummary
from .metrics import compute_topic_metrics
from .render import render_html, render_json, render_markdown
from .search import search_topic
from .store import save_manifest, start_run_dir, update_latest_digest, write_json, write_jsonl, write_text
from .summarise import summarise_topic
from .utils import (
    canonicalise_url,
    collect_used_citations,
    ensure_citation_suffix,
    split_and_strip_csv,
    strip_trailing_citations,
)
from .triage import triage_pages

TZ_LONDON = ZoneInfo("Europe/London")


def _slugify(text: str) -> str:
    cleaned = [ch.lower() if ch.isalnum() else "-" for ch in text]
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")
    return slug or "topic"


def _prepare_config(cfg: AppConfig, args: argparse.Namespace) -> AppConfig:
    updated = cfg
    if args.max_results is not None:
        max_results = max(1, min(10, args.max_results))
        updated = replace(updated, max_results_per_topic=max_results, fetch_limit_per_topic=max_results)
    if args.prefer:
        prefer = split_and_strip_csv(args.prefer)
        updated = replace(updated, prefer_domains=prefer)
    if args.exclude:
        exclude = split_and_strip_csv(args.exclude)
        updated = replace(updated, exclude_domains=exclude)
    return updated


def _topics_from_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [topic.strip() for topic in value.split(",") if topic.strip()]


_MARKER_PATTERN = re.compile(r"\[(\d+)\]")
_CITATION_RE = re.compile(r"\[(\d+)\]")


def _reindex_citations(summary: TopicSummary, mapping: dict[int, int]) -> None:
    """Update bullet citations to global indices, pruning unmapped markers."""

    for cluster in summary.clusters:
        for bullet in cluster.bullets:
            mapped = [mapping[idx] for idx in bullet.citations if idx in mapping]

            def _replace(match: re.Match[str]) -> str:
                idx = int(match.group(1))
                if idx in mapping:
                    return f"[{mapping[idx]}]"
                return ""

            bullet.text = _MARKER_PATTERN.sub(_replace, bullet.text)
            bullet.citations = mapped
            bullet.text = ensure_citation_suffix(bullet.text, bullet.citations)


def _prune_empty_bullets(summary: TopicSummary, logger) -> None:
    """Remove bullets without citations, logging a warning."""

    new_clusters: list = []
    for cluster in summary.clusters:
        retained = []
        for bullet in cluster.bullets:
            if bullet.citations:
                retained.append(bullet)
            else:
                logger.warning(
                    "Dropping citation-free bullet in topic '%s': %s",
                    summary.topic,
                    bullet.text,
                )
        if retained:
            cluster.bullets = retained
            new_clusters.append(cluster)
    summary.clusters = new_clusters


def _compact_sources(
    topics: list[TopicSummary],
    sources: list[tuple[int, str, str]],
    logger,
) -> tuple[list[tuple[int, str, str]], dict[int, tuple[str, str]]]:
    """Prune unused sources and reindex citations across topics."""

    used_indices: set[int] = set()
    for summary in topics:
        for cluster in summary.clusters:
            for bullet in cluster.bullets:
                used_indices.update(bullet.citations)

    new_sources: list[tuple[int, str, str]] = []
    index_mapping: dict[int, int] = {}
    next_idx = 1
    for idx, title, url in sources:
        if idx in used_indices:
            index_mapping[idx] = next_idx
            new_sources.append((next_idx, title, url))
            next_idx += 1

    for summary in topics:
        for cluster in summary.clusters:
            updated_bullets = []
            for bullet in cluster.bullets:
                mapped = [index_mapping[c] for c in bullet.citations if c in index_mapping]
                if not mapped:
                    logger.warning(
                        "Dropping citation-free bullet in topic '%s' after source compaction: %s",
                        summary.topic,
                        bullet.text,
                    )
                    continue
                bullet.citations = mapped
                bullet.text = ensure_citation_suffix(strip_trailing_citations(bullet.text), bullet.citations)
                updated_bullets.append(bullet)
            cluster.bullets = updated_bullets
        summary.clusters = [cluster for cluster in summary.clusters if cluster.bullets]
        if summary.stories:
            retained_stories = []
            for story in summary.stories:
                mapped_sources = [index_mapping[c] for c in story.source_indices if c in index_mapping]
                new_bullets: list[str] = []
                for bullet_text in story.bullets:
                    citations = [index_mapping[int(match.group(1))] for match in _CITATION_RE.finditer(bullet_text) if int(match.group(1)) in index_mapping]
                    if not citations:
                        logger.warning(
                            "Dropping story bullet without citations in topic '%s': %s",
                            summary.topic,
                            bullet_text,
                        )
                        continue
                    refreshed = ensure_citation_suffix(strip_trailing_citations(bullet_text), citations)
                    new_bullets.append(refreshed)
                if mapped_sources and new_bullets:
                    story.source_indices = mapped_sources
                    story.bullets = new_bullets
                    retained_stories.append(story)
            summary.stories = retained_stories
        summary.used_source_indices = sorted(
            {
                cite
                for cluster in summary.clusters
                for bullet in cluster.bullets
                for cite in bullet.citations
            }
        )

    sources_lookup = {idx: (title, url) for idx, title, url in new_sources}
    return new_sources, sources_lookup


def _story_key(headline: str, urls: Sequence[str]) -> str:
    for url in urls:
        try:
            canon = canonicalise_url(url)
        except Exception:  # pragma: no cover - defensive
            continue
        if canon:
            return f"url::{canon}"
    slug = re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")
    return f"title::{slug}"


def _load_previous_digest(logger) -> dict | None:
    latest_path = Path("runs/latest.json")
    if not latest_path.exists():
        return None
    try:
        return json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to read previous digest: %s", exc)
        return None


def _index_previous_stories(previous: dict | None) -> dict[str, dict[str, dict]]:
    index: dict[str, dict[str, dict]] = {}
    if not previous:
        return index
    topics = previous.get("topics") if isinstance(previous, dict) else None
    if not isinstance(topics, list):
        return index
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        name = topic.get("topic")
        if not name:
            continue
        key = _slugify(str(name))
        stories = topic.get("stories")
        if not isinstance(stories, list):
            continue
        story_map: dict[str, dict] = {}
        for story in stories:
            if not isinstance(story, dict):
                continue
            headline = story.get("headline")
            urls = story.get("urls") if isinstance(story.get("urls"), list) else story.get("urls", [])
            urls = urls or story.get("used_sources")
            if not isinstance(urls, list):
                urls = []
            story_key = _story_key(str(headline or ""), urls)
            story_map[story_key] = story
        index[key] = story_map
    return index


def _mark_story_updates(topics: list[TopicSummary], previous_index: dict[str, dict[str, dict]]) -> None:
    for summary in topics:
        if not summary.stories:
            continue
        topic_key = _slugify(summary.topic)
        prev_stories = previous_index.get(topic_key, {})
        for story in summary.stories:
            story_key = _story_key(story.headline, story.urls)
            previous_story = prev_stories.get(story_key)
            if not previous_story:
                continue
            changed = False
            notes: list[str] = []

            # Check date changes
            prev_date = previous_story.get("date")
            if prev_date != story.date and (story.date or prev_date):
                changed = True
                if story.date and prev_date:
                    notes.append(f"Date updated from {prev_date} to {story.date}")
                elif story.date:
                    notes.append(f"Date added ({story.date})")
                else:
                    notes.append("Date removed")

            # Check bullet changes with detailed diff
            prev_bullets = previous_story.get("bullets")
            if isinstance(prev_bullets, list):
                # Normalize bullets for comparison (strip citations)
                prev_set = {strip_trailing_citations(b) for b in prev_bullets}
                curr_set = {strip_trailing_citations(b) for b in story.bullets}

                added = curr_set - prev_set
                removed = prev_set - curr_set

                if added or removed:
                    changed = True
                    change_parts = []
                    if added:
                        change_parts.append(f"{len(added)} new bullet{'s' if len(added) > 1 else ''}")
                    if removed:
                        change_parts.append(f"{len(removed)} removed")
                    notes.append("Content updated: " + ", ".join(change_parts))
                elif len(prev_bullets) != len(story.bullets):
                    # Bullet count changed but no content diff (citation updates only)
                    changed = True
                    notes.append("Content refreshed")

            if changed:
                story.updated = True
                if notes:
                    story.update_note = "; ".join(notes)


def _log_summary(logger, digest: Digest, run_dir: Path) -> None:
    logger.info(
        "Completed run %s: topics=%s sources=%s output=%s",
        digest.run_id,
        len(digest.topics),
        len(digest.sources),
        run_dir,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate topic-based news digests using Ollama search.")
    parser.add_argument("--topics", required=True, help="Comma-separated list of topics to cover.")
    parser.add_argument("--max-results", type=int, help="Override maximum results per topic (<=10).")
    parser.add_argument("--out", default="digest.md", help="Path to copy the final Markdown digest to.")
    parser.add_argument("--html", action="store_true", help="Render an HTML digest alongside Markdown.")
    parser.add_argument("--prefer", help="Comma-separated domains to prioritise.")
    parser.add_argument("--exclude", help="Comma-separated domains to exclude.")
    parser.add_argument("--corroborate", action="store_true", help="Allow model to call web tools during summarisation.")
    parser.add_argument("--dry-run", action="store_true", help="Search only; skip fetch and summarise steps.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (DEBUG level).")
    return parser




def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    topics = _topics_from_arg(args.topics)
    if not topics:
        parser.error("At least one topic is required via --topics")

    cfg = load_config()

    logger = get_logger("newsbot")
    if args.verbose:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in root_logger.handlers:
            handler.setLevel(logging.DEBUG)

    cfg = _prepare_config(cfg, args)

    previous_digest = _load_previous_digest(logger)
    previous_story_index = _index_previous_stories(previous_digest)

    start_dt = datetime.now(TZ_LONDON)
    run_dir = start_run_dir()
    run_id = run_dir.name

    manifest: dict = {
        "run_id": run_id,
        "run_time_iso": start_dt.isoformat(),
        "timezone": cfg.tz,
        "model": cfg.model,
        "topics": topics,
        "dry_run": args.dry_run,
    }

    aggregated_topics: list[TopicSummary] = []
    aggregated_sources: list[tuple[int, str, str]] = []
    sources_lookup: dict[int, tuple[str, str]] = {}
    elapsed: float | None = None

    start_time = time.perf_counter()

    try:
        for topic in topics:
            hits = search_topic(topic, cfg, logger)
            slug = _slugify(topic)
            search_file = run_dir / f"search_{slug}.jsonl"
            write_jsonl(search_file, (asdict(hit) for hit in hits))

            if args.dry_run:
                continue

            pages = fetch_pages(hits, cfg, logger, topic=topic)
            triaged = triage_pages(pages)
            fetch_file = run_dir / f"fetch_{slug}.jsonl"
            write_jsonl(fetch_file, (asdict(page) for page in triaged))

            summary, sources_table = summarise_topic(topic, triaged, cfg, logger, args.corroborate)

            used_local = sorted(collect_used_citations(summary.clusters))
            used_sources_local = [entry for entry in sources_table if entry[0] in used_local]
            unused_sources_local = [
                (title, url) for idx, title, url in sources_table if idx not in used_local
            ]

            index_mapping: dict[int, int] = {}
            for local_idx, title, url in used_sources_local:
                global_idx = len(aggregated_sources) + 1
                aggregated_sources.append((global_idx, title, url))
                sources_lookup[global_idx] = (title, url)
                index_mapping[local_idx] = global_idx

            _reindex_citations(summary, index_mapping)

            _prune_empty_bullets(summary, logger)

            summary.unused_sources = unused_sources_local
            summary.used_source_indices = sorted(
                idx for idx in collect_used_citations(summary.clusters) if idx in sources_lookup
            )

            aggregated_topics.append(summary)

        elapsed = time.perf_counter() - start_time

        if args.dry_run:
            manifest.update({"status": "dry-run", "search_files": sorted(p.name for p in run_dir.glob("search_*.jsonl"))})
            save_manifest(run_dir / "manifest.json", manifest)
            logger.info("Dry run complete. Search data stored in %s", run_dir)
            return 0

        aggregated_sources, sources_lookup = _compact_sources(aggregated_topics, aggregated_sources, logger)

        _mark_story_updates(aggregated_topics, previous_story_index)

        for summary in aggregated_topics:
            compute_topic_metrics(summary, sources_lookup, logger)

        digest = Digest(
            run_id=run_id,
            run_time_iso=start_dt.isoformat(),
            timezone=cfg.tz,
            model=cfg.model,
            topics=aggregated_topics,
            sources=aggregated_sources,
            elapsed_seconds=elapsed,
        )

        if not digest.topics:
            logger.error("No summaries were produced; aborting")
            return 1

        markdown = render_markdown(digest)
        digest_path = run_dir / "digest.md"
        write_text(digest_path, markdown)

        out_path = Path(args.out)
        if out_path != digest_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(markdown, encoding="utf-8")

        html_path: Path | None = None
        if args.html:
            html = render_html(digest)
            html_path = run_dir / "digest.html"
            write_text(html_path, html)

        manifest.update(
            {
                "status": "completed",
                "elapsed_seconds": elapsed,
                "outputs": {
                    "markdown": str(digest_path),
                    "html": str(html_path) if html_path else None,
                    "json": str(run_dir / "digest.json"),
                },
                "sources": len(aggregated_sources),
            }
        )
        save_manifest(run_dir / "manifest.json", manifest)

        json_payload = render_json(digest)
        write_json(run_dir / "digest.json", json_payload)
        update_latest_digest(run_dir / "digest.json")

        _log_summary(logger, digest, run_dir)
        logger.info("Markdown digest copied to %s", out_path.resolve())
        return 0
    except Exception as exc:  # pragma: no cover - top-level safety
        logger.exception("Run failed: %s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
