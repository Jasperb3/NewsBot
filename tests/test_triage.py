from newsbot.models import FetchedPage
from newsbot.triage import (
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
