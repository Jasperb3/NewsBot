# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

news-digest-bot is a Python package that generates topic-based news digests using Ollama's web search and fetch capabilities. The system follows a multi-stage pipeline: search → fetch → triage → summarise → render.

## Core Architecture

### Data Flow Pipeline
1. **Search**: Uses `ollama.web_search` to find relevant articles per topic (`newsbot/search.py`)
2. **Fetch**: Retrieves full content via `ollama.web_fetch` with 3-attempt retry and snippet fallback (`newsbot/fetch.py`)
3. **Triage**: Filters content for duplicates, diversity, and recency (`newsbot/triage.py`)
4. **Summarise**: Uses LLM to create structured summaries with citations (`newsbot/summarise.py`)
5. **Render**: Outputs Markdown/HTML/JSON with numbered citations, executive summary, and quality metrics (`newsbot/render.py`)

### Key Components
- **CLI Entry Point**: `newsbot/cli.py` — Main orchestrator with argument parsing, pipeline execution, cross-run story tracking, and importance-based story sorting
- **Configuration**: `newsbot/config.py` — Environment-based config with sensible defaults
- **Data Models**: `newsbot/models.py` — Structured dataclasses; `Story.calculate_importance()` scores stories 0–100
- **Storage**: `newsbot/store.py` — Timestamped run directories with manifest tracking
- **Metrics**: `newsbot/metrics.py` — Coverage and corroboration analytics
- **Prompts**: `newsbot/prompts.py` — LLM prompt templates
- **Logging**: `newsbot/log.py` — Shared logger configuration
- **Utilities**: `newsbot/utils.py` — URL canonicalisation, citation helpers, text processing

### Run Directory Structure
Each execution creates `runs/YYYYMMDD_HHMMSS/` containing:
- `search_<topic>.jsonl` — Raw search results per topic
- `fetch_<topic>.jsonl` — Triaged fetch payloads
- `digest.md` — Final Markdown output
- `digest.html` — Optional HTML output
- `digest.json` — Machine-readable digest data (symlinked as `runs/latest.json`)
- `manifest.json` — Run metadata and file references

## Development Commands

### Installation
```bash
pip install -e .          # Standard
pip install -e .[dev]     # With dev dependencies
```

### Testing
```bash
pytest                    # Run all 89 tests (should all pass)
make test
```

### Linting
```bash
ruff check newsbot
make lint
```

### Running the Bot
```bash
newsbot --topics "AI policy, renewable energy" --max-results 6 --out digest.md
newsbot --topics "UK politics" --html --exclude "reddit.com,medium.com"
newsbot --topics "AI" --dry-run      # search only
make run
```

## Configuration

Reads `.env` (if present) then `os.environ`.

### Required
- `OLLAMA_API_KEY` — For remote Ollama instances (local daemon may not need it)

### Key Settings
- `MODEL` — Ollama model alias (default: `qwen3:4b`)
- `MAX_RESULTS_PER_TOPIC` / `FETCH_LIMIT_PER_TOPIC` — Per-topic limits (≤10)
- `PREFER_DOMAINS` / `EXCLUDE_DOMAINS` — Comma-separated domain filters
- `MAX_CHARS_PER_PAGE` / `MAX_BATCH_CHARS` — Content processing limits
- `OUTPUT_FORMAT` — `md` or `html` (CLI `--html` flag also enables HTML)
- `TZ` — Timezone for timestamps (default: `Europe/London`)

### Default Domain Preferences
- **Preferred**: reuters.com, ft.com, apnews.com, bbc.co.uk, theguardian.com, cnbc.com, techcrunch.com, wired.com, espn.com
- **Excluded**: wikipedia.org (overridable with `--no-wiki`)

## Key Patterns & Behaviours

### Fetch Resilience
`fetch.py` retries each URL up to 3 times (with `time.sleep` between attempts). If all retries fail and the `SearchHit` has a snippet, it falls back to the snippet (`FetchedPage.is_snippet = True`). Pages with content shorter than 200 chars are skipped without retrying.

### Citation System
- All bullets include numeric markers `[n]` linking to sources
- Citations are reindexed globally across topics (`_compact_sources` in `cli.py`)
- Unused sources are pruned from final output
- `ensure_citation_suffix` in `utils.py` deduplicates repeated markers

### Story Importance Scoring
`Story.calculate_importance()` returns 0–100:
- Corroboration: up to 40 pts (10 per source)
- Updated flag: 30 pts
- Date present: 10 pts; very recent (≤7 days): +10 pts; recent (≤30 days): +5 pts
- Bullet depth: up to 20 pts (5 per bullet)

Stories are sorted by this score before rendering.

### Cross-Run Story Tracking
On each run, `cli.py` loads `runs/latest.json` and flags stories with `updated=True` and `update_note` strings (e.g., "Content updated: 2 new bullets, 1 removed") when bullet content changes vs the previous run.

### Render Enhancements (Priority 1 & 2 from IMPROVEMENTS.md — all implemented)
- **Executive Summary**: Top stories across all topics, scored by importance
- **Digest Overview**: Coverage stats, corroboration rate, updated story count
- **Reading Time**: Estimated per-topic in Table of Contents
- **At a Glance**: Scored by updated/corroboration/date (not just domain count)
- **Timeline**: Grouped into "Recent developments" (≤30 days) and "Historical context"
- **Confidence Levels**: Per-story (High/Medium/Low based on source count)
- **Source Quality Badges**: ⭐ trusted news, 🏛️ official (.gov/.int), 🎓 academic (.edu/.ac.uk)
- **Update Notes**: "What changed" shown inline under updated stories

### Priority 3 Features (all implemented)

**Cross-topic connections** (`render.py:_find_topic_connections`)
- Links topics sharing ≥2 source indices; sorted by overlap count, capped at 3
- Renders `_Related topics: Energy (3 shared sources)_` below each topic header

**Contradiction detection** (`render.py:_detect_contradictions`)
- Flags bullet pairs from *different* source sets that contain adversative markers (`however`, `but`, `despite`, `contrary`, `although`)
- Renders a `### Potential Discrepancies` section with `⚠️` notes per topic; capped at 3

**Semantic clustering validation** (`summarise.py:_validate_cluster_coherence`, `flag_fragmented_clusters`)
- `_validate_cluster_coherence(cluster)` → 0–1 pairwise Jaccard similarity of citation sets across bullets
- `flag_fragmented_clusters(clusters)` → appends `(Loosely related)` to cluster headings where coherence < 0.3
- Call `flag_fragmented_clusters` in `cli.py` on a topic's clusters after `summarise_topic` returns to label fragmentary LLM output

**Content-similarity deduplication** (`triage.py:dedupe_by_content_similarity`)
- `_content_similarity(p1, p2)` → 3-gram Jaccard on first 1000 characters
- `dedupe_by_content_similarity(pages)` → drops pages with >80% overlap to any already-kept page; first-seen wins
- Wired into `triage_pages()` as a step after title dedup

## Testing Strategy
- 89 tests, all passing (`pytest` with no arguments)
- No live network calls — synthetic fixtures only
- Test files:
  - `test_cli_metrics.py` — story tracking and confidence metrics
  - `test_fetch.py` — retry logic and snippet fallback
  - `test_render.py` — core rendering correctness
  - `test_render_integration.py` — all Priority 1/2/3 render functions (61 tests)
  - `test_search.py` — search result parsing variants
  - `test_summarise.py` — JSON parsing, cluster coherence validation
  - `test_triage.py` — deduplication, diversity, content similarity
  - `test_utils.py` — URL canonicalisation, citation helpers
- `conftest.py` provides shared fixtures

## Content Limits and Batching
- Pages truncated at `MAX_CHARS_PER_PAGE` before summarisation
- Prompt batching respects `MAX_BATCH_CHARS` to stay within model context
- Results capped at 10 per topic maximum
