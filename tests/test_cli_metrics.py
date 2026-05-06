from newsbot.cli import _index_previous_stories, _mark_story_updates, _reindex_citations
from newsbot.metrics import compute_topic_metrics
from newsbot.models import ClusterBullet, ClusterSummary, Story, TopicSummary


class StubLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warning(self, message: str, *args, **kwargs) -> None:  # pragma: no cover - simple recorder
        self.messages.append(message % args if args else message)


def test_confidence_metrics():
    cluster = ClusterSummary(
        heading="Updates",
        bullets=[
            ClusterBullet(text="Policy agreed [1][2]", citations=[1, 2]),
            ClusterBullet(text="Schedule draft [3]", citations=[3]),
        ],
    )
    summary = TopicSummary(topic="Energy", clusters=[cluster])
    summary.used_source_indices = [1, 2, 3]

    sources_lookup = {
        1: ("Gov release", "https://gov.example.com/doc"),
        2: ("Industry blog", "https://energy.example.net/news"),
        3: ("Gov stats", "https://gov.example.com/stats"),
    }

    logger = StubLogger()
    coverage, corroborated, total = compute_topic_metrics(summary, sources_lookup, logger)

    assert coverage == 2
    assert corroborated == 1
    assert total == 2
    assert summary.coverage_domains == 2
    assert summary.corroborated_bullets == 1
    assert summary.total_bullets == 2
    assert not logger.messages


def test_reindex_citations_updates_story_source_indices():
    # Simulates second topic: local source [1] = OBR, but global should be [2]
    story = Story(
        headline="OBR Forecast",
        date=None,
        why="It matters.",
        bullets=["GDP growth expected [1]", "Inflation forecast revised [1]"],
        source_indices=[1],
        urls=["https://obr.uk/forecast"],
    )
    cluster = ClusterSummary(
        heading="Economy",
        bullets=[ClusterBullet(text="OBR forecasts GDP [1]", citations=[1])],
    )
    summary = TopicSummary(topic="UK economy", clusters=[cluster], stories=[story])
    mapping = {1: 2}  # local 1 → global 2

    _reindex_citations(summary, mapping)

    # Cluster bullets must be updated
    assert summary.clusters[0].bullets[0].citations == [2]
    assert "[2]" in summary.clusters[0].bullets[0].text

    # Stories must ALSO be updated — this is what was broken
    assert summary.stories[0].source_indices == [2], (
        "story.source_indices not remapped: still has local index, causing cross-topic contamination"
    )
    assert "[2]" in summary.stories[0].bullets[0]
    assert "[1]" not in summary.stories[0].bullets[0]


def test_story_tracking_updated_badge():
    story = Story(
        headline="Energy Policy Shifts",
        date="2025-09-20",
        why="New incentives announced",
        bullets=["Government outlined incentives [1]"],
        source_indices=[1],
        urls=["https://example.com/update"],
    )
    summary = TopicSummary(topic="Energy", clusters=[], stories=[story])

    previous_digest = {
        "topics": [
            {
                "topic": "Energy",
                "stories": [
                    {
                        "headline": "Energy Policy Shifts",
                        "date": "2025-09-15",
                        "bullets": ["Earlier information [1]"],
                        "urls": ["https://example.com/update"],
                    }
                ],
            }
        ]
    }

    index = _index_previous_stories(previous_digest)
    _mark_story_updates([summary], index)

    assert summary.stories[0].updated is True
