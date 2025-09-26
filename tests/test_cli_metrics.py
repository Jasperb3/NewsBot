from newsbot.metrics import compute_topic_metrics
from newsbot.models import ClusterBullet, ClusterSummary, TopicSummary


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
