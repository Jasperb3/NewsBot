import datetime as dt

from newsbot.utils import (
    canonicalise_url,
    chunk_texts_by_char_limit,
    domain_of,
    extract_iso_dates,
    split_and_strip_csv,
)


def test_canonicalise_url_strips_tracking_and_fragment():
    url = "https://www.Example.com/news?id=123&utm_source=test#section"
    expected = "https://example.com/news?id=123"
    assert canonicalise_url(url) == expected


def test_domain_of_handles_www_and_case():
    url = "HTTPS://WWW.BBC.CO.UK/news/article"
    assert domain_of(url) == "bbc.co.uk"


def test_split_and_strip_csv_removes_empty_items():
    csv = "alpha, beta , , gamma"
    assert split_and_strip_csv(csv) == ["alpha", "beta", "gamma"]


def test_extract_iso_dates_picks_valid_dates():
    text = "Report updated on 2024-05-30 and again 2023/12/01."
    assert extract_iso_dates(text) == [dt.date(2024, 5, 30), dt.date(2023, 12, 1)]


def test_chunk_texts_by_char_limit_batches_sequences():
    texts = ["a" * 5, "b" * 4, "c" * 9]
    assert chunk_texts_by_char_limit(texts, max_chars=10) == [["aaaaa", "bbbb"], ["ccccccccc"]]


def test_chunk_texts_by_char_limit_splits_large_entry():
    texts = ["x" * 15]
    assert chunk_texts_by_char_limit(texts, max_chars=10) == [["xxxxxxxxxx"], ["xxxxx"]]
