from newsbot.models import FetchedPage
from newsbot.triage import (
    dedupe_by_content_similarity,
    dedupe_by_title,
    ensure_domain_diversity,
    order_by_recency_hint,
    triage_pages,
)


def make_page(url: str, title: str, content: str) -> FetchedPage:
    return FetchedPage(url=url, title=title, content=content, links=[], topic="test")


def test_dedupe_by_title_removes_near_duplicates():
    pages = [
        make_page("https://example.com/a", "Breaking News: Update", "content"),
        make_page("https://mirror.com/a", "Breaking News - Update", "content"),
        make_page("https://example.com/b", "Different Story", "content"),
    ]
    deduped = dedupe_by_title(pages)
    assert len(deduped) == 2
    assert deduped[0].url == "https://example.com/a"


def test_ensure_domain_diversity_prioritises_unique_domains():
    pages = [
        make_page("https://a.com/1", "A1", "content"),
        make_page("https://a.com/2", "A2", "content"),
        make_page("https://b.com/1", "B1", "content"),
    ]
    diverse = ensure_domain_diversity(pages, min_domains=2)
    domains = {page.url.split('/')[2] for page in diverse}
    assert domains == {"a.com", "b.com"}


def test_order_by_recency_hint_sorts_by_recent_date():
    pages = [
        make_page("https://a.com/old", "Title", "Updated on 2023-01-01."),
        make_page("https://a.com/new", "Title", "Updated on 2024-05-30."),
        make_page("https://a.com/none", "Title", "No dates here"),
    ]
    ordered = order_by_recency_hint(pages)
    assert ordered[0].url == "https://a.com/new"
    assert ordered[1].url == "https://a.com/old"


def test_triage_pages_runs_all_steps():
    pages = [
        make_page("https://a.com/1", "Breaking News", "Updated 2024-05-30"),
        make_page("https://b.com/1", "Breaking News", "Updated 2024-05-29"),
        make_page("https://c.com/1", "Other Story", "Updated 2024-05-28"),
    ]
    triaged = triage_pages(pages)
    assert len(triaged) == 2
    assert triaged[0].url == "https://a.com/1"


# ---------------------------------------------------------------------------
# Priority 3 — content-similarity deduplication
# ---------------------------------------------------------------------------

def test_near_identical_content_is_deduplicated():
    # Pages sharing 95%+ of 3-gram content (large repeated block)
    common = "breaking news update latest report " * 200
    page1 = make_page("https://a.com/1", "Story A", common + " exclusive angle")
    page2 = make_page("https://b.com/1", "Story B", common + " different ending")
    result = dedupe_by_content_similarity([page1, page2])
    assert len(result) == 1


def test_distinct_content_both_kept():
    page1 = make_page("https://a.com/1", "Story A", "climate policy research greenhouse gases " * 40)
    page2 = make_page("https://b.com/1", "Story B", "football league championship scores goals " * 40)
    result = dedupe_by_content_similarity([page1, page2])
    assert len(result) == 2


def test_first_page_kept_when_near_duplicate():
    common = "policy reform announced government statement " * 200
    page1 = make_page("https://first.com/1", "First", common)
    page2 = make_page("https://second.com/1", "Second", common)
    result = dedupe_by_content_similarity([page1, page2])
    assert result[0].url == "https://first.com/1"


def test_single_page_unchanged():
    page = make_page("https://a.com/1", "Solo", "single article content " * 30)
    result = dedupe_by_content_similarity([page])
    assert result == [page]


def test_empty_list_returns_empty():
    assert dedupe_by_content_similarity([]) == []


def test_triage_pipeline_deduplicates_similar_content():
    # Full pipeline: near-duplicate content pages with different titles should be reduced
    common = "parliament vote debate legislation amendment bill " * 200
    pages = [
        make_page("https://a.com/1", "Story A on 2024-05-30", common + " angle a"),
        make_page("https://b.com/1", "Story B on 2024-05-29", common + " angle b"),
        make_page("https://c.com/1", "Unrelated Story on 2024-05-28", "entirely different content topic " * 40),
    ]
    triaged = triage_pages(pages)
    # Near-duplicates consolidated; unrelated story kept
    assert len(triaged) < 3
