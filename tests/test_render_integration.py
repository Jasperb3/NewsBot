"""Integration tests for render.py feature functions added in Priority 1, 2 & 3 improvements."""
import datetime as dt

import pytest

from newsbot.models import ClusterBullet, ClusterSummary, Digest, Story, TopicSummary
from newsbot.render import (
    _add_source_quality_badge,
    _build_timeline,
    _compute_confidence_level,
    _detect_contradictions,
    _find_topic_connections,
    _compute_digest_statistics,
    _estimate_reading_time,
    _generate_executive_summary,
    _select_at_a_glance,
    render_markdown,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _story(
    headline: str,
    why: str = "It matters.",
    source_indices: list[int] | None = None,
    bullets: list[str] | None = None,
    updated: bool = False,
    update_note: str | None = None,
    date: str | None = None,
    urls: list[str] | None = None,
) -> Story:
    return Story(
        headline=headline,
        date=date,
        why=why,
        bullets=bullets or [f"Detail about {headline} [1]"],
        source_indices=source_indices or [1],
        urls=urls or [f"https://example.com/{headline.lower().replace(' ', '-')}"],
        updated=updated,
        update_note=update_note,
    )


def _cluster(heading: str = "Updates", bullets: list[ClusterBullet] | None = None) -> ClusterSummary:
    return ClusterSummary(
        heading=heading,
        bullets=bullets or [ClusterBullet(text="A thing happened [1]", citations=[1])],
    )


def _topic(
    name: str = "test topic",
    stories: list[Story] | None = None,
    clusters: list[ClusterSummary] | None = None,
    used_indices: list[int] | None = None,
    domains: int = 2,
    corroborated: int = 1,
    total: int = 1,
) -> TopicSummary:
    t = TopicSummary(
        topic=name,
        clusters=clusters or [_cluster()],
        stories=stories or [],
    )
    t.used_source_indices = used_indices or [1]
    t.coverage_domains = domains
    t.corroborated_bullets = corroborated
    t.total_bullets = total
    t.unused_sources = []
    return t


def _digest(topics: list[TopicSummary], sources: list[tuple] | None = None) -> Digest:
    return Digest(
        run_id="test",
        run_time_iso="2025-10-21T10:30:00+01:00",
        timezone="Europe/London",
        model="test-model",
        topics=topics,
        sources=sources or [(1, "Reuters report", "https://reuters.com/article/1")],
    )


# ---------------------------------------------------------------------------
# _compute_confidence_level
# ---------------------------------------------------------------------------

def test_confidence_high_with_four_or_more_sources():
    level = _compute_confidence_level(4)
    assert level.startswith("High")
    assert "4" in level


def test_confidence_medium_with_two_or_three_sources():
    assert _compute_confidence_level(2).startswith("Medium")
    assert _compute_confidence_level(3).startswith("Medium")


def test_confidence_low_with_single_source():
    assert _compute_confidence_level(1).startswith("Low")


def test_confidence_low_with_zero_sources():
    assert _compute_confidence_level(0).startswith("Low")


# ---------------------------------------------------------------------------
# _add_source_quality_badge
# ---------------------------------------------------------------------------

def test_trusted_news_domain_gets_star_badge():
    assert _add_source_quality_badge("reuters.com").startswith("⭐")
    assert _add_source_quality_badge("bbc.co.uk").startswith("⭐")
    assert _add_source_quality_badge("apnews.com").startswith("⭐")


def test_gov_domain_gets_official_badge():
    assert _add_source_quality_badge("justice.gov").startswith("🏛️")


def test_edu_domain_gets_academic_badge():
    assert _add_source_quality_badge("mit.edu").startswith("🎓")


def test_ac_uk_domain_gets_academic_badge():
    assert _add_source_quality_badge("ox.ac.uk").startswith("🎓")


def test_unknown_domain_has_no_badge():
    badge = _add_source_quality_badge("randomnews.io")
    assert badge == "randomnews.io"


def test_official_org_gets_official_badge():
    assert _add_source_quality_badge("who.int").startswith("🏛️")
    assert _add_source_quality_badge("europa.eu").startswith("🏛️")


# ---------------------------------------------------------------------------
# _estimate_reading_time
# ---------------------------------------------------------------------------

def test_reading_time_is_at_least_one_minute():
    topic = _topic(stories=[_story("Brief")])
    assert _estimate_reading_time(topic) >= 1


def test_reading_time_grows_with_more_content():
    few_bullets = [ClusterBullet(text="Short [1]", citations=[1])]
    many_bullets = [ClusterBullet(text=" ".join(["word"] * 50) + " [1]", citations=[1]) for _ in range(20)]
    short_topic = _topic(clusters=[ClusterSummary(heading="A", bullets=few_bullets)])
    long_topic = _topic(clusters=[ClusterSummary(heading="A", bullets=many_bullets)])
    assert _estimate_reading_time(long_topic) > _estimate_reading_time(short_topic)


def test_reading_time_counts_story_words():
    # Need >400 words across headline + why + bullets to exceed the 1-minute minimum
    story = _story(
        "Headline word count",
        why=" ".join(["important"] * 200),
        bullets=[" ".join(["detail"] * 200) + " [1]"],
    )
    topic_with_story = _topic(stories=[story], clusters=[])
    topic_without = _topic(stories=[], clusters=[_cluster()])
    assert _estimate_reading_time(topic_with_story) > _estimate_reading_time(topic_without)


# ---------------------------------------------------------------------------
# _compute_digest_statistics
# ---------------------------------------------------------------------------

def test_statistics_counts_topics_and_sources():
    t1 = _topic("topic a")
    t2 = _topic("topic b")
    digest = _digest(
        [t1, t2],
        sources=[(1, "Reuters", "https://reuters.com/a"), (2, "BBC", "https://bbc.co.uk/b")],
    )
    stats = _compute_digest_statistics(digest)
    assert stats["topics"] == 2
    assert stats["sources"] == 2


def test_statistics_counts_unique_domains():
    digest = _digest(
        [_topic()],
        sources=[
            (1, "Reuters article 1", "https://reuters.com/a"),
            (2, "Reuters article 2", "https://reuters.com/b"),
            (3, "BBC", "https://bbc.co.uk/c"),
        ],
    )
    stats = _compute_digest_statistics(digest)
    assert stats["domains"] == 2  # reuters.com and bbc.co.uk


def test_statistics_corroboration_rate_is_percentage():
    topic = _topic(corroborated=3, total=4)
    digest = _digest([topic])
    stats = _compute_digest_statistics(digest)
    assert stats["corroboration_rate"] == pytest.approx(75.0)


def test_statistics_updated_count_reflects_story_flags():
    updated = _story("Breaking", updated=True)
    not_updated = _story("Background")
    topic = _topic(stories=[updated, not_updated])
    digest = _digest([topic])
    stats = _compute_digest_statistics(digest)
    assert stats["updated_count"] == 1


def test_statistics_zero_total_bullets_does_not_divide_by_zero():
    topic = _topic(corroborated=0, total=0)
    digest = _digest([topic])
    stats = _compute_digest_statistics(digest)
    assert stats["corroboration_rate"] == 0


# ---------------------------------------------------------------------------
# _generate_executive_summary
# ---------------------------------------------------------------------------

def test_executive_summary_returns_topic_and_text_pairs():
    story = _story("Major Event", why="It has wide impact.")
    topic = _topic("geopolitics", stories=[story])
    digest = _digest([topic])
    summary = _generate_executive_summary(digest)
    assert len(summary) >= 1
    topic_name, text = summary[0]
    assert "Geopolitics" in topic_name or "geopolitics" in topic_name.lower()
    assert "Major Event" in text


def test_executive_summary_respects_limit():
    stories = [_story(f"Story {i}", source_indices=[i + 1]) for i in range(10)]
    topic = _topic("big topic", stories=stories)
    digest = _digest([topic], sources=[(i + 1, f"Source {i}", f"https://src.com/{i}") for i in range(10)])
    summary = _generate_executive_summary(digest, limit=3)
    assert len(summary) <= 3


def test_executive_summary_prefers_updated_stories():
    stale = _story("Old news", source_indices=[1])
    fresh = _story("Breaking", updated=True, source_indices=[2])
    topic = _topic("news", stories=[stale, fresh])
    digest = _digest([topic], sources=[(1, "Old", "https://old.com"), (2, "New", "https://new.com")])
    summary = _generate_executive_summary(digest)
    # First entry should be the updated story
    first_text = summary[0][1]
    assert "Breaking" in first_text


def test_executive_summary_falls_back_to_clusters_when_no_stories():
    cluster = ClusterSummary(
        heading="Context",
        bullets=[ClusterBullet(text="Something noteworthy happened [1]", citations=[1])],
    )
    topic = _topic("background", clusters=[cluster], stories=[])
    digest = _digest([topic])
    summary = _generate_executive_summary(digest)
    assert len(summary) >= 1


# ---------------------------------------------------------------------------
# _select_at_a_glance
# ---------------------------------------------------------------------------

def test_at_a_glance_returns_up_to_limit_entries():
    stories = [_story(f"Story {i}") for i in range(10)]
    topic = _topic(stories=stories)
    sources_lookup = {1: ("Reuters", "https://reuters.com")}
    results = _select_at_a_glance(topic, sources_lookup, limit=5)
    assert len(results) <= 5


def test_at_a_glance_updated_story_ranks_first():
    old = _story("Background info", source_indices=[1])
    breaking = _story("Breaking news", updated=True, source_indices=[2])
    topic = _topic(stories=[old, breaking])
    sources_lookup = {
        1: ("Old", "https://old.com"),
        2: ("New", "https://new.com"),
    }
    results = _select_at_a_glance(topic, sources_lookup)
    assert len(results) >= 2
    first_text = results[0][0]
    assert "Breaking news" in first_text


def test_at_a_glance_entry_includes_domain():
    story = _story("Key development", source_indices=[1])
    topic = _topic(stories=[story])
    sources_lookup = {1: ("BBC Report", "https://bbc.co.uk/story")}
    results = _select_at_a_glance(topic, sources_lookup)
    assert len(results) >= 1
    _, domains = results[0]
    assert "bbc.co.uk" in domains


def test_at_a_glance_falls_back_to_clusters_when_no_stories():
    cluster = ClusterSummary(
        heading="Summary",
        bullets=[
            ClusterBullet(text="Cluster item [1]", citations=[1]),
            ClusterBullet(text="Another item [1]", citations=[1]),
        ],
    )
    topic = _topic(clusters=[cluster], stories=[])
    sources_lookup = {1: ("Source", "https://example.com")}
    results = _select_at_a_glance(topic, sources_lookup)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# _build_timeline — grouping behaviour
# ---------------------------------------------------------------------------

def test_timeline_recent_vs_historical_split():
    recent_date = dt.date.today() - dt.timedelta(days=10)
    old_date = dt.date.today() - dt.timedelta(days=90)
    cluster = ClusterSummary(
        heading="Events",
        bullets=[
            ClusterBullet(
                text=f"Recent event on {recent_date.isoformat()} [1]",
                citations=[1],
            ),
            ClusterBullet(
                text=f"Old event on {old_date.isoformat()} [2]",
                citations=[2],
            ),
        ],
    )
    topic = _topic(clusters=[cluster], stories=[])
    sources_lookup = {
        1: ("Source A", "https://a.com"),
        2: ("Source B", "https://b.com"),
    }
    timeline = _build_timeline(topic, sources_lookup)
    recent_dates = [d for d, _ in timeline["recent"]]
    historical_dates = [d for d, _ in timeline["historical"]]
    assert recent_date in recent_dates
    assert old_date in historical_dates


def test_timeline_returns_dict_with_recent_and_historical_keys():
    topic = _topic(stories=[], clusters=[])
    timeline = _build_timeline(topic, {})
    assert "recent" in timeline
    assert "historical" in timeline


def test_timeline_story_date_takes_priority_over_cluster_extraction():
    story = _story(
        "Dated story",
        date="2025-01-15",
        source_indices=[1],
        bullets=["Some detail [1]"],
    )
    topic = _topic(stories=[story], clusters=[])
    sources_lookup = {1: ("Source", "https://example.com")}
    timeline = _build_timeline(topic, sources_lookup)
    all_dates = [d for d, _ in timeline["recent"]] + [d for d, _ in timeline["historical"]]
    assert dt.date(2025, 1, 15) in all_dates


# ---------------------------------------------------------------------------
# render_markdown — end-to-end integration
# ---------------------------------------------------------------------------

def test_markdown_contains_executive_summary_section():
    story = _story("Key development")
    topic = _topic("AI policy", stories=[story])
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "## Executive Summary" in md


def test_markdown_contains_digest_overview_section():
    topic = _topic("climate")
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "## Digest Overview" in md
    assert "Coverage" in md


def test_markdown_shows_confidence_for_stories():
    story = _story("Multi-source story", source_indices=[1, 2, 3, 4])
    topic = _topic("technology", stories=[story])
    digest = _digest(
        [topic],
        sources=[
            (1, "S1", "https://reuters.com/1"),
            (2, "S2", "https://bbc.co.uk/2"),
            (3, "S3", "https://apnews.com/3"),
            (4, "S4", "https://ft.com/4"),
        ],
    )
    md = render_markdown(digest)
    assert "Confidence: High" in md


def test_markdown_shows_update_note_for_updated_story():
    story = _story(
        "Updated story",
        updated=True,
        update_note="Content updated: 2 new bullets",
    )
    topic = _topic("news", stories=[story])
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "Updated since last run" in md
    assert "Content updated: 2 new bullets" in md


def test_markdown_shows_reading_time_in_toc():
    topic = _topic("health")
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "min read" in md


def test_markdown_source_badges_appear_in_story_domains():
    story = _story("Reuters story", source_indices=[1])
    topic = _topic("finance", stories=[story])
    digest = _digest([topic], sources=[(1, "Reuters", "https://reuters.com/story")])
    md = render_markdown(digest)
    assert "⭐" in md


def test_markdown_digest_overview_shows_corroboration_rate():
    topic = _topic(corroborated=2, total=4)
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "corroboration rate" in md.lower()


def test_markdown_digest_overview_shows_updated_count_when_nonzero():
    updated = _story("Breaking", updated=True)
    topic = _topic(stories=[updated])
    digest = _digest([topic])
    md = render_markdown(digest)
    assert "updated since last run" in md.lower()


# ---------------------------------------------------------------------------
# Priority 3 — _find_topic_connections
# ---------------------------------------------------------------------------

def _topic_with_sources(name: str, indices: list[int]) -> TopicSummary:
    t = _topic(name)
    t.used_source_indices = indices
    return t


def test_topics_with_two_shared_sources_are_connected():
    t1 = _topic_with_sources("AI policy", [1, 2, 3])
    t2 = _topic_with_sources("Technology", [2, 3, 4])  # shares 2, 3
    digest = _digest(
        [t1, t2],
        sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 5)],
    )
    connections = _find_topic_connections(digest)
    assert "AI policy" in connections
    related_names = [name for name, _ in connections["AI policy"]]
    assert "Technology" in related_names


def test_topics_with_only_one_shared_source_are_not_connected():
    t1 = _topic_with_sources("Finance", [1, 2])
    t2 = _topic_with_sources("Sports", [2, 3])  # only shares 2
    digest = _digest(
        [t1, t2],
        sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 4)],
    )
    connections = _find_topic_connections(digest)
    assert "Finance" not in connections


def test_topic_connections_capped_at_three():
    topics = [_topic_with_sources(f"Topic {i}", [1, 2, i + 3]) for i in range(6)]
    # All share sources 1 and 2
    digest = _digest(topics, sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 10)])
    connections = _find_topic_connections(digest)
    for related in connections.values():
        assert len(related) <= 3


def test_no_self_connections():
    t1 = _topic_with_sources("Solo", [1, 2, 3])
    digest = _digest([t1], sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 4)])
    connections = _find_topic_connections(digest)
    # Solo topic has no other topics to connect to
    assert connections.get("Solo", []) == []


def test_connection_overlap_count_is_correct():
    t1 = _topic_with_sources("Climate", [1, 2, 3, 4])
    t2 = _topic_with_sources("Energy", [2, 3, 4, 5])  # 3 shared: 2, 3, 4
    digest = _digest(
        [t1, t2],
        sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 6)],
    )
    connections = _find_topic_connections(digest)
    energy_overlap = next(count for name, count in connections["Climate"] if name == "Energy")
    assert energy_overlap == 3


def test_related_topics_appear_in_markdown():
    t1 = _topic_with_sources("Climate", [1, 2, 3])
    t2 = _topic_with_sources("Energy", [2, 3, 4])
    digest = _digest(
        [t1, t2],
        sources=[(i, f"S{i}", f"https://s{i}.com") for i in range(1, 5)],
    )
    md = render_markdown(digest)
    assert "Related topics" in md
    assert "Energy" in md


# ---------------------------------------------------------------------------
# Priority 3 — _detect_contradictions
# ---------------------------------------------------------------------------

def test_contradiction_detected_with_marker_and_different_citations():
    cluster = ClusterSummary(
        heading="Analysis",
        bullets=[
            ClusterBullet(text="Costs will rise however analysts disagree [1]", citations=[1]),
            ClusterBullet(text="Markets stable despite the concerns [2]", citations=[2]),
        ],
    )
    topic = _topic(clusters=[cluster])
    contradictions = _detect_contradictions(topic)
    assert len(contradictions) >= 1


def test_no_contradiction_when_same_citations():
    cluster = ClusterSummary(
        heading="Analysis",
        bullets=[
            ClusterBullet(text="Although costs rose last month [1]", citations=[1]),
            ClusterBullet(text="However prices stabilised this week [1]", citations=[1]),
        ],
    )
    topic = _topic(clusters=[cluster])
    contradictions = _detect_contradictions(topic)
    assert len(contradictions) == 0


def test_no_contradiction_without_adversative_markers():
    cluster = ClusterSummary(
        heading="Analysis",
        bullets=[
            ClusterBullet(text="Markets rose steadily in Q3 [1]", citations=[1]),
            ClusterBullet(text="Employment increased by 2% [2]", citations=[2]),
        ],
    )
    topic = _topic(clusters=[cluster])
    contradictions = _detect_contradictions(topic)
    assert len(contradictions) == 0


def test_contradictions_capped_at_three():
    # 5 bullets all with contradiction markers, each citing a different source
    bullets = [
        ClusterBullet(text=f"Despite earlier reports source {i} says the opposite [{i}]", citations=[i])
        for i in range(1, 6)
    ]
    cluster = ClusterSummary(heading="Conflicts", bullets=bullets)
    topic = _topic(clusters=[cluster])
    contradictions = _detect_contradictions(topic)
    assert len(contradictions) <= 3


def test_contradictions_section_appears_in_markdown_when_present():
    cluster = ClusterSummary(
        heading="Analysis",
        bullets=[
            ClusterBullet(text="Growth expected however headwinds remain [1]", citations=[1]),
            ClusterBullet(text="But contrary signals from regulators [2]", citations=[2]),
        ],
    )
    t = _topic("economics", clusters=[cluster], stories=[])
    digest = _digest([t], sources=[(1, "A", "https://a.com"), (2, "B", "https://b.com")])
    md = render_markdown(digest)
    assert "Potential Discrepancies" in md
