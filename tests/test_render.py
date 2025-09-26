import datetime as dt

from newsbot.models import ClusterBullet, ClusterSummary, Digest, TopicSummary
from newsbot.render import render_html, render_markdown, _build_timeline


def _base_topic() -> TopicSummary:
    cluster = ClusterSummary(
        heading="Latest Updates",
        bullets=[ClusterBullet(text="Tournament schedule confirmed [1]", citations=[1])],
    )
    topic = TopicSummary(topic="world cup", clusters=[cluster])
    topic.used_source_indices = [1]
    topic.unused_sources = [("Venue guide", "https://example.org/venues")]
    topic.coverage_domains = 1
    topic.corroborated_bullets = 0
    topic.total_bullets = 1
    return topic


def _make_digest(topic: TopicSummary) -> Digest:
    return Digest(
        run_id="test",
        run_time_iso="2025-09-26T18:54:56+01:00",
        timezone="Europe/London",
        model="test-model",
        topics=[topic],
        sources=[(1, "Official announcement", "https://fifa.example.com/news")],
    )


def test_topic_title_case_and_badges_markdown():
    digest = _make_digest(_base_topic())
    md = render_markdown(digest)
    assert "## World Cup" in md  # title-cased heading
    assert "_Sources: 1 · Domains: 1 · Corroboration: 0/1_" in md
    assert "— fifa.example.com" in md  # domain hint for bullet
    assert "[Back to top](#table-of-contents)" in md


def test_html_contains_badges_domains_and_toc():
    digest = _make_digest(_base_topic())
    html = render_html(digest)
    assert "class=\"badge\"" in html
    assert "class=\"domains\">· fifa.example.com" in html
    assert 'id="world-cup"' in html  # anchor preserved
    assert 'id="table-of-contents"' in html


def test_further_reading_group_cap():
    topic = _base_topic()
    topic.unused_sources = [
        (f"Source {idx}", f"https://{domain}/article/{idx}")
        for idx, domain in enumerate(
            [
                "example.com",
                "example.com",
                "news.org",
                "news.org",
                "news.org",
                "media.net",
                "media.net",
                "media.net",
                "media.net",
                "extra.info",
            ],
            start=1,
        )
    ]
    digest = _make_digest(topic)
    md = render_markdown(digest)
    assert "Further reading" in md
    assert "… and 2 more" in md


def test_timeline_is_terse():
    cluster = ClusterSummary(
        heading="Regulation",
        bullets=[
            ClusterBullet(
                text=(
                    "The council met on 2025-09-20 to finalise terms before another session. "
                    "Detailed analysis is pending [1][2]"
                ),
                citations=[1, 2],
            )
        ],
    )
    topic = TopicSummary(topic="policy", clusters=[cluster])
    topic.used_source_indices = [1, 2]
    topic.coverage_domains = 2
    topic.corroborated_bullets = 1
    topic.total_bullets = 1
    digest = Digest(
        run_id="test",
        run_time_iso="2025-09-26T18:54:56+01:00",
        timezone="Europe/London",
        model="test-model",
        topics=[topic],
        sources=[
            (1, "Gov release", "https://gov.example.com/doc"),
            (2, "Industry analysis", "https://analysis.example.net/post"),
        ],
    )
    sources_lookup = {idx: (title, url) for idx, title, url in digest.sources}
    timeline = _build_timeline(topic, sources_lookup)
    assert timeline[0][0] == dt.date(2025, 9, 20)
    assert "[1]" in timeline[0][1]
    assert "[2]" not in timeline[0][1]
    assert len(timeline[0][1]) <= 170  # terseness check

