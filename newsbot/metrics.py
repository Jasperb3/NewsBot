"""Metrics and validation helpers for topic summaries."""
from __future__ import annotations

from typing import Dict, Tuple

from .models import TopicSummary
from .utils import citations_to_domains


def compute_topic_metrics(
    summary: TopicSummary,
    sources_lookup: Dict[int, tuple[str, str]],
    logger,
) -> Tuple[int, int, int]:
    """Calculate coverage and corroboration metrics for a topic.

    Returns a tuple of (coverage_domains, corroborated_bullets, total_bullets).
    """

    total_bullets = 0
    corroborated = 0
    for cluster in summary.clusters:
        for bullet in cluster.bullets:
            total_bullets += 1
            domains = citations_to_domains(bullet.citations, sources_lookup)
            if len(domains) >= 2:
                corroborated += 1
            if not bullet.citations:
                logger.warning(
                    "Bullet without citations after mapping in topic '%s': %s",
                    summary.topic,
                    bullet.text,
                )

    coverage_domains = len(citations_to_domains(summary.used_source_indices, sources_lookup))
    summary.coverage_domains = coverage_domains
    summary.corroborated_bullets = corroborated
    summary.total_bullets = total_bullets
    return coverage_domains, corroborated, total_bullets
