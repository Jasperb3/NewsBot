from newsbot.models import ClusterBullet, ClusterSummary, Digest, TopicSummary
from newsbot.render import render_html, render_markdown


def make_topic() -> TopicSummary:
    cluster = ClusterSummary(
        heading="Latest Updates",
        bullets=[ClusterBullet(text="Tournament schedule confirmed [1]", citations=[1])],
    )
    topic = TopicSummary(topic="World Cup", clusters=[cluster])
    topic.used_source_indices = [1]
    topic.unused_sources = [("Venue guide", "https://example.org/venues")]
    topic.coverage_domains = 1
    topic.corroborated_bullets = 0
    topic.total_bullets = 1
    return topic


def make_digest() -> Digest:
    topic = make_topic()
    return Digest(
        run_id="test",
        run_time_iso="2025-09-26T18:54:56+01:00",
        timezone="Europe/London",
        model="test-model",
        topics=[topic],
        sources=[(1, "Official announcement", "https://fifa.example.com/news")],
    )


def test_prune_unused_sources():
    digest = make_digest()
    md = render_markdown(digest)
    assert "Further reading" in md
    assert "Venue guide" in md
    sources_section = md.split("## Sources", 1)[-1]
    assert "Official announcement" in sources_section
    assert "Venue guide" not in sources_section


def test_html_contains_anchors_and_toc():
    digest = make_digest()
    html = render_html(digest)
    assert '<nav>' in html
    assert 'id="world-cup"' in html
    assert 'Copy link' in html
    assert 'Table of Contents' in html
