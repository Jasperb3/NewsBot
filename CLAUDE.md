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
pytest                    # Run all 28 tests (should all pass)
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

### Not Yet Implemented (Priority 3)
- Cross-topic connection detection (shared sources across topics)
- Contradiction detection between bullets
- Semantic clustering validation (coherence scoring)
- n-gram content similarity for enhanced deduplication

## Testing Strategy
- 28 unit tests, all passing (`pytest` with no arguments)
- No live network calls — synthetic fixtures only
- Test files: `test_cli_metrics.py`, `test_fetch.py`, `test_render.py`, `test_search.py`, `test_summarise.py`, `test_triage.py`, `test_utils.py`
- `conftest.py` provides shared fixtures

## Content Limits and Batching
- Pages truncated at `MAX_CHARS_PER_PAGE` before summarisation
- Prompt batching respects `MAX_BATCH_CHARS` to stay within model context
- Results capped at 10 per topic maximum
