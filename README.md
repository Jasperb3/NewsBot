# NewsBot — AI-Powered News Digest Generator

Turn any set of topics into a structured, cited, quality-scored news briefing — fully local, powered by [Ollama](https://ollama.com).

NewsBot searches the web, fetches and deduplicates articles, runs them through a local LLM, and produces a polished Markdown (or HTML) digest with numbered citations, corroboration metrics, source quality badges, and cross-topic analysis. Every run is reproducible: raw inputs, outputs, and a manifest are archived in a timestamped directory.

---

## What it produces

A daily digest with:

- **Executive Summary** — top stories across all topics ranked by importance (corroboration, recency, update status)
- **Digest Overview** — coverage stats, corroboration rate, and count of stories that changed since the last run
- **Per-topic sections** with:
  - *At a Glance* — highest-priority bullets, scored and sorted automatically
  - *Top Stories* — structured headlines with `why it matters`, dated bullets, confidence levels (High / Medium / Low), and source quality badges (⭐ trusted news, 🏛️ official, 🎓 academic)
  - *Timeline* — dated events split into "Recent developments" and "Historical context"
  - *Potential Discrepancies* — flags when sources with different citations use adversative language (`however`, `but`, `despite`…)
  - *Related Topics* — links topics that share ≥2 sources
  - *Further Reading* — unused sources not summarised in the main body
- **Full source appendix** — every URL cited, globally reindexed across topics
- **HTML output** (optional) — responsive, dark-mode-aware, with sticky navigation and copy-link buttons

### Example output

```markdown
# Daily Digest — 2026-05-06 (Europe/London)
Generated with gemma4:e4b — Topics: 3; Sources: 14; Elapsed: 142.1s

## Executive Summary
- **AI Regulation:** EU AI Act enters enforcement phase — first binding obligations apply to prohibited-use systems...
- **UK Economy:** OBR revises growth forecast downward — GDP growth cut to 1.0% for 2026...
- **Climate:** Arctic sea ice extent hits record April low — scientists warn of accelerating feedback loops...

## Digest Overview
📊 **Coverage:** 3 topics · 14 sources · 11 unique domains
🔍 **Quality:** 71% corroboration rate · 4.7 sources/topic avg
⏱️ **Recency:** 3 stories updated since last run

## Table of Contents
- [AI Regulation](#ai-regulation) _~4 min read_
- [UK Economy](#uk-economy) _~3 min read_
- [Climate](#climate) _~2 min read_

---

<a id="ai-regulation"></a>
## AI Regulation
_Sources: 6 · Domains: 5 · Corroboration: 8/10_ ✅ Well-sourced
_Related topics: UK Economy (2 shared sources)_

### At a glance
- EU AI Act enforcement begins — prohibited AI systems must be removed from market by August 2025 [1][2][3] — ⭐ reuters.com, 🏛️ eur-lex.europa.eu

### Top stories

#### [EU AI Act: Prohibited Systems Deadline Passes](https://example.com)
*2026-02-02 · Sources: 4 · Domains: ⭐ reuters.com, 🏛️ eur-lex.europa.eu, ⭐ bbc.co.uk, 🎓 ox.ac.uk*
*Confidence: High - 4 independent sources*
_Why it matters:_ The first enforcement milestone affects providers of biometric categorisation and social scoring systems across the EU.

- Providers must discontinue or retrofit prohibited AI systems by the August deadline or face fines up to €35 million [1][2] — ⭐ reuters.com, 🏛️ eur-lex.europa.eu
- National market surveillance authorities are activating enforcement mechanisms across all 27 member states [2][3] — 🏛️ eur-lex.europa.eu, ⭐ bbc.co.uk
```

---

## Architecture

```
Topics (CLI) → Search → Fetch → Triage → Distill → Summarise → Render → Output
                                                                        ↓
                                                  digest.md / digest.html / digest.json
                                                  runs/YYYYMMDD_HHMMSS/ (archived)
```

| Stage | File | What it does |
|---|---|---|
| Search | `newsbot/search.py` | Multi-provider orchestrator: round-robin interleave, URL dedup, domain filtering |
| Fetch | `newsbot/fetch.py` | `ollama.web_fetch` → `trafilatura` → snippet fallback chain; `fetcher` field on every page |
| Triage | `newsbot/triage.py` | Title dedup, n-gram content-similarity dedup (>80% Jaccard), domain diversity, recency ordering |
| Distill | `newsbot/distill.py` | (Optional) Per-article LLM compression: long bodies → dense fact-preserving prose. Off by default |
| Summarise | `newsbot/summarise.py` | JSON-mode LLM summarisation → Stories + fallback cluster parsing; cluster coherence validation |
| Render | `newsbot/render.py` | Markdown + HTML + JSON; all quality-analysis features |
| CLI | `newsbot/cli.py` | Orchestration, global citation reindexing, cross-run story tracking, importance scoring |

---

## Installation

Requires Python 3.10+ and a running [Ollama](https://ollama.com) instance.

```bash
git clone https://github.com/Jasperb3/NewsBot.git
cd NewsBot

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install (with dev dependencies for testing)
pip install -e .[dev]
```

---

## Configuration

Create a `.env` file in the project root (see variables below). All settings have sensible defaults for local Ollama.

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_API_KEY` | — | API key for remote Ollama instances; omit for local daemon |
| `MODEL` | `qwen3:4b` | Ollama model alias |
| `MAX_RESULTS_PER_TOPIC` | `6` | Search hits per topic (max 10) |
| `FETCH_LIMIT_PER_TOPIC` | `6` | Pages to fetch per topic (max 10) |
| `MAX_CHARS_PER_PAGE` | `6000` | Content truncation per page before summarisation |
| `MAX_BATCH_CHARS` | `18000` | Total prompt size cap across all pages |
| `PREFER_DOMAINS` | — | Comma-separated domains to prioritise |
| `EXCLUDE_DOMAINS` | — | Comma-separated domains to exclude |
| `OUTPUT_FORMAT` | `md` | `md` or `html` |
| `TZ` | `Europe/London` | Timezone for timestamps |
| `SEARCH_PROVIDERS` | `ollama` | Comma-separated list of search providers to combine. Currently supported: `ollama`, `tavily` |
| `TAVILY_API_KEY` | — | Required when `tavily` is in `SEARCH_PROVIDERS`. Get one at [tavily.com](https://tavily.com); free tier covers ~1k searches/mo |
| `TAVILY_SEARCH_DEPTH` | `basic` | `basic` (1 credit) or `advanced` (2 credits, deeper crawl) |
| `TAVILY_TOPIC` | `news` | `news` (recency-biased, mainstream outlets) or `general` |
| `TAVILY_DAYS` | `7` | When `TAVILY_TOPIC=news`, only return results from the last N days |
| `DISTILL_ENABLED` | `false` | When `true`, run a per-article distillation pass that compresses long article bodies into dense, fact-preserving prose before they reach the topic summariser |
| `DISTILL_THRESHOLD_CHARS` | `4000` | Articles shorter than this skip distillation |
| `DISTILL_TARGET_CHARS` | `1500` | Approximate target length of each distilled summary |

**Suggested preferred domains:** reuters.com, ft.com, apnews.com, bbc.co.uk, theguardian.com, cnbc.com, techcrunch.com, wired.com — set these via `PREFER_DOMAINS` to bias the merged result list toward trusted news sources.

### Search providers

Each provider runs independently and their results are round-robin interleaved, then deduplicated by canonical URL. A provider that fails (network error, missing API key) is logged and skipped — the run continues with whatever providers succeeded.

| Provider | What it adds | Cost | When to enable |
|---|---|---|---|
| `ollama` (default) | Broad, model-friendly search via the local Ollama daemon | Free | Always |
| `tavily` | News-curated results with recency window; high-quality snippets that survive even if fetch fails | Free tier ~1k/mo | When you need wider source variety and stronger snippet fallbacks |

To enable Tavily, set both:

```bash
SEARCH_PROVIDERS=ollama,tavily
TAVILY_API_KEY=tvly-...
```

and install the optional dependency:

```bash
pip install -e .[tavily]
```

### Per-article distillation

By default, the topic summariser sees the raw fetched article body (up to `MAX_CHARS_PER_PAGE` per page). For long, noisy articles this dilutes the signal — the summariser has to find the citation-worthy facts inside ad-laced, multi-section pages.

Set `DISTILL_ENABLED=true` to insert a per-article condensation pass between fetch and summarisation. Each article above `DISTILL_THRESHOLD_CHARS` is rewritten by the local Ollama model into ~`DISTILL_TARGET_CHARS` of dense prose with hard rules:

- All proper nouns, dates, numbers, and direct quotes preserved verbatim
- Web boilerplate (nav, ads, "related articles", paywall notices) stripped
- No commentary added — flowing factual prose, no bullets or markdown

**Trade-off:** doubles model calls per run (one per long article + one per topic), so expect ~2× wall-clock time. In return, the topic summariser gets cleaner, denser inputs — which is the largest single lever on output quality. Snippet-fallback pages and short articles are skipped automatically (no wasted calls). Distillation failures degrade gracefully: the original content is kept and a warning is logged.

Watch for the per-run log line:

```
Distilled 4/6 pages: 28432 -> 6184 chars (saved 22248, 78% reduction)
```

---

## Usage

```bash
# Basic: two topics, 6 results each, output to digest.md
newsbot --topics "AI regulation, UK economy" --out digest.md

# More results, HTML output, exclude noisy domains
newsbot --topics "climate policy" --max-results 8 --html --exclude "reddit.com,medium.com"

# Prefer specific sources
newsbot --topics "financial markets" --prefer "ft.com,bloomberg.com,reuters.com"

# Dry run: search only, no fetch or summarise
newsbot --topics "AI" --dry-run

# Verbose logging
newsbot --topics "UK politics" --verbose
```

### CLI reference

| Flag | Description |
|---|---|
| `--topics` | Comma-separated list of topics (required) |
| `--max-results N` | Results per topic, 1–10 (overrides env) |
| `--out PATH` | Copy final Markdown here (default: `digest.md`) |
| `--html` | Also render an HTML digest |
| `--prefer DOMAINS` | Comma-separated domain priority list |
| `--exclude DOMAINS` | Comma-separated domain blocklist |
| `--corroborate` | Allow LLM to call web tools during summarisation |
| `--dry-run` | Search only; skip fetch and summarise |
| `--verbose` | Enable DEBUG-level logging |

---

## Output files

Each run creates `runs/YYYYMMDD_HHMMSS/`:

```
runs/
└── 20260506_162441/
    ├── search_ai-regulation.jsonl    # Raw search hits
    ├── fetch_ai-regulation.jsonl     # Triaged fetched pages
    ├── search_uk-economy.jsonl
    ├── fetch_uk-economy.jsonl
    ├── digest.md                     # Markdown output
    ├── digest.html                   # HTML output (if --html)
    ├── digest.json                   # Machine-readable digest
    └── manifest.json                 # Run metadata & file refs
```

`runs/latest.json` is updated after each run and used for cross-run story tracking (detecting updated stories).

---

## Quality features

### Citation integrity
- Every bullet includes `[n]` markers tied to the source appendix
- Citations are globally reindexed across topics to prevent collisions
- Unused sources are pruned; duplicates are deduplicated

### Story importance scoring
Stories are ranked before rendering using a 0–100 score:
- Corroboration: up to 40 pts (10 per independent source)
- Updated since last run: 30 pts
- Has a date: 10 pts; very recent (≤7 days): +10 pts; recent (≤30 days): +5 pts
- Content depth: up to 20 pts (5 per bullet)

### Cross-run story tracking
On each run, the previous digest is compared and stories are flagged `Updated since last run` with a note describing what changed (e.g., *"Content updated: 2 new bullets, 1 removed"*).

### Cluster coherence validation
After summarisation, clusters whose bullets draw from entirely different sources (Jaccard similarity < 0.3) are labelled *(Loosely related)* to signal LLM fragmentation.

### Content-similarity deduplication
Beyond title deduplication, pages with >80% 3-gram overlap are dropped before summarisation, preventing the LLM from citing syndicated copies as independent sources.

### Fetch resilience
Each URL goes through a three-stage fallback chain: `ollama.web_fetch` (3 retries) → `trafilatura` HTML extraction → search snippet. A per-source breakdown is logged after each topic fetch so you can see how often each tier fires. The `trafilatura` dependency is optional; the pipeline degrades gracefully if it is absent.

---

## Development

```bash
# Run the full test suite (126 tests, no network calls)
pytest

# Run with coverage
pytest --cov=newsbot

# Lint
ruff check newsbot
```

Tests use only synthetic fixtures — no live network calls. The suite covers all pipeline stages and quality-analysis functions.

---

## Ethical use

- Respect publishers' terms of service and robots directives
- Attribute sources clearly — every claim in the digest has a numbered citation
- Use digests to assist expert judgement, not replace it; verify contentious claims before redistribution
- The bot is rate-limited by design: at most 10 fetches per topic
