"""Search provider protocol."""
from __future__ import annotations

from typing import Protocol

from ..models import SearchHit


class SearchProvider(Protocol):
    """A pluggable source of search results.

    Implementations must expose a ``name`` attribute (used for logging and
    diagnostics) and a ``search`` method that returns a normalised list of
    :class:`SearchHit` for a single query. Filtering, deduplication, and
    domain preference are applied centrally by the orchestrator — providers
    should return what their backend gives them, ranked best-first.
    """

    name: str

    def search(self, query: str, max_results: int) -> list[SearchHit]: ...
