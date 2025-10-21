# NewsBot Output Improvement Recommendations

## Executive Summary

This document provides comprehensive recommendations to enhance NewsBot's ability to deliver useful and informative overviews of topics. The analysis covers content quality, presentation, user experience, and information architecture improvements.

**Current Strengths:**
- Solid technical architecture with clean separation of concerns
- Excellent citation system with source tracking
- Multiple output formats (Markdown, HTML, JSON)
- Good deduplication and diversity controls

**Key Areas for Improvement:**
1. Content organization and hierarchy
2. Information density and relevance
3. Visual presentation and scannability
4. Cross-topic insights and trend detection
5. User-facing guidance and context

---

## 1. Content Quality & Relevance Improvements

### 1.1 Add Executive Summary Section
**Problem:** Users must read through all topics to understand the day's key developments.

**Solution:** Add a cross-topic executive summary at the top of the digest.

**Implementation in `render.py`:**
```python
def _generate_executive_summary(digest: Digest, limit: int = 5) -> list[str]:
    """Extract top 5 most significant updates across all topics."""
    all_bullets = []
    for topic in digest.topics:
        if topic.stories:
            for story in topic.stories[:2]:  # Top 2 stories per topic
                all_bullets.append((
                    len(story.source_indices),  # Corroboration
                    story.updated,  # Recency indicator
                    topic.topic,
                    f"{story.headline} — {story.why}"
                ))

    all_bullets.sort(reverse=True)
    return [f"**{topic}:** {text}" for _, _, topic, text in all_bullets[:limit]]
```

Add to output after title:
```markdown
## Executive Summary
- **AI Policy:** New EU regulations announced — First comprehensive framework...
- **Climate:** Record temperatures recorded globally — Scientists warn of...
```

### 1.2 Enhance Prompt Engineering
**Current Issue:** Prompts in `prompts.py` don't emphasize what makes information valuable.

**Improvements for `JSON_SYSTEM_PROMPT`:**
```python
JSON_SYSTEM_PROMPT = (
    "You are a meticulous news editor for an expert audience. Use British English. "
    "You must respond with strict JSON that can be parsed without modification. "
    "Use only the supplied sources and cite them with their numeric indices. "
    "When in doubt, omit the item rather than speculate. "

    # ADD THESE GUIDELINES:
    "Prioritize stories by: "
    "(1) Novelty - new developments vs background information, "
    "(2) Impact - broad consequences vs niche updates, "
    "(3) Verifiability - multiple independent sources vs single claims. "
    "For 'why it matters', focus on concrete implications for the audience, "
    "not generic importance statements."
)
```

**Improvements for `JSON_USER_TEMPLATE`:**
```python
# Add after the Rules section:
"Ranking criteria:\n"
"- NEW > UPDATES > CONTEXT (favor breaking developments)\n"
"- VERIFIED > CLAIMED (prefer multi-source confirmation)\n"
"- ACTIONABLE > INFORMATIONAL (highlight decisions, changes, launches)\n"
"- Include dates prominently when stories have clear timelines.\n"
```

### 1.3 Fix Citation Redundancy
**Current Issue:** Example shows `[1][1][1]` - duplicate citations reduce readability.

**Fix in `utils.py`:**
```python
def ensure_citation_suffix(text: str, citations: Sequence[int]) -> str:
    """Append deduplicated citations to text."""
    # Add deduplication
    unique_citations = sorted(dict.fromkeys(citations))
    suffix = "".join(f"[{idx}]" for idx in unique_citations)
    # ... rest of function
```

### 1.4 Add Content Classification
**Problem:** No indication of whether content is breaking news, analysis, or background.

**Add to `Story` model in `models.py`:**
```python
@dataclass
class Story:
    # ... existing fields ...
    story_type: str = "update"  # "breaking" | "update" | "analysis" | "background"
    confidence: str = "verified"  # "verified" | "reported" | "claimed"
```

**Render with badges:**
```markdown
#### [Headline](url) 🔴 BREAKING _(Updated since last run)_
#### [Headline](url) ✓ VERIFIED
#### [Headline](url) 📊 ANALYSIS
```

---

## 2. Presentation & Readability Improvements

### 2.1 Improve "At a Glance" Selection
**Current Algorithm:** Prioritizes by domain count, then length (`render.py:74-112`)

**Enhanced Selection Criteria:**
```python
def _select_at_a_glance(
    topic: TopicSummary,
    sources_lookup: dict[int, tuple[str, str]],
    limit: int = 5,
    max_chars: int = 200,
) -> list[tuple[str, list[str], str]]:  # Add 'urgency' indicator

    if topic.stories:
        entries = []
        for story in topic.stories[:limit]:
            # Calculate relevance score
            recency_score = 10 if story.updated else 0
            corroboration_score = len(story.source_indices) * 2
            date_score = 5 if story.date else 0

            priority = recency_score + corroboration_score + date_score

            # Add urgency indicator
            if story.updated and len(story.source_indices) >= 3:
                urgency = "🔴"  # Breaking & verified
            elif story.updated:
                urgency = "🟡"  # Breaking, fewer sources
            else:
                urgency = "⚪"  # Standard

            base = strip_trailing_citations(f"{story.headline} — {story.why}")
            truncated = truncate_sentence(base, max_chars)
            truncated = ensure_citation_suffix(truncated, story.source_indices)
            domains = sorted_domains(citations_to_domains(story.source_indices, sources_lookup))

            entries.append((priority, truncated, domains, urgency))

        # Sort by priority descending
        entries.sort(reverse=True)
        return [(text, domains, urgency) for _, text, domains, urgency in entries[:limit]]

    # ... existing cluster-based logic with similar scoring
```

### 2.2 Enhanced Timeline Visualization
**Current Issue:** Timelines appear but don't show progression clearly.

**Improved Format:**
```markdown
### Timeline
**Recent developments:**
- 2025-10-15 — Tournament format expanded to 48 teams [1] 🆕
- 2025-09-20 — Host cities officially announced [2]
- 2025-08-10 — Ticket allocation process begins [3]

**Historical context:**
- 2023-05-09 — Joint bid accepted by FIFA [4]
```

**Implementation:** Add grouping logic in `_build_timeline()`:
```python
def _build_timeline(topic, sources_lookup, max_entries=8, max_chars=140):
    entries = sorted(seen_dates.items(), key=lambda item: item[0], reverse=True)

    recent_cutoff = dt.date.today() - dt.timedelta(days=30)
    recent = [(d, text) for d, text in entries if d >= recent_cutoff]
    historical = [(d, text) for d, text in entries if d < recent_cutoff]

    return {
        'recent': recent[:max_entries // 2],
        'historical': historical[:max_entries // 2]
    }
```

### 2.3 Improve Bullet Point Hierarchy
**Problem:** All bullets have equal visual weight, making scanning difficult.

**Solution:** Add importance levels to bullets.

**In `summarise.py`, enhance `ClusterBullet`:**
```python
@dataclass
class ClusterBullet:
    text: str
    citations: list[int]
    importance: int = 1  # 1=high, 2=medium, 3=low

    def __post_init__(self):
        # Auto-calculate importance
        if len(self.citations) >= 3:
            self.importance = 1  # Well-corroborated
        elif len(self.citations) == 2:
            self.importance = 2
        else:
            self.importance = 3  # Single source
```

**Render with visual hierarchy:**
```markdown
### Key Developments
- 🔹 **High priority**: Multi-source verified update [1][2][3]
  - 🔸 Supporting detail: Additional context [1]
    - ◦ Background: Historical context [2]
```

### 2.4 Enhanced Source Attribution
**Current:** Simple domain list after bullets.

**Improved:** Show source quality indicators.

```python
def _format_source_quality(domain: str, sources_lookup: dict) -> str:
    """Add quality indicators based on source type."""
    quality_tiers = {
        'reuters.com': '⭐',
        'bbc.co.uk': '⭐',
        'apnews.com': '⭐',
        # Official sources
        'gov': '🏛️',
        'edu': '🎓',
        # Others
    }

    for pattern, indicator in quality_tiers.items():
        if pattern in domain:
            return f"{indicator} {domain}"
    return domain
```

Render as:
```markdown
- Tournament expanded to 48 teams [1][2] — ⭐ reuters.com, 🏛️ fifa.gov
```

---

## 3. Information Architecture Improvements

### 3.1 Add "What Changed" Diff for Updates
**Problem:** When stories are marked "Updated since last run", users don't know what changed.

**Solution:** Store and display diffs in `cli.py` story tracking logic:

```python
def _compare_story_bullets(old_bullets: list[str], new_bullets: list[str]) -> str:
    """Generate human-readable diff."""
    old_set = {strip_trailing_citations(b) for b in old_bullets}
    new_set = {strip_trailing_citations(b) for b in new_bullets}

    added = new_set - old_set
    removed = old_set - new_set

    changes = []
    if added:
        changes.append(f"Added {len(added)} new bullet(s)")
    if removed:
        changes.append(f"Removed {len(removed)} bullet(s)")

    return "; ".join(changes) if changes else "Content refreshed"
```

**Display:**
```markdown
#### [Headline](url) _(Updated since last run)_
*What changed: Added 2 new bullets; Removed 1 outdated bullet*
```

### 3.2 Add Cross-Topic Connections
**Problem:** Related stories across topics aren't linked.

**Solution:** Add a "Related Topics" section:

```python
def _find_topic_connections(digest: Digest) -> dict[str, list[str]]:
    """Find topics with overlapping sources."""
    topic_sources = {}
    for topic in digest.topics:
        topic_sources[topic.topic] = set(topic.used_source_indices)

    connections = {}
    for topic, sources in topic_sources.items():
        related = []
        for other_topic, other_sources in topic_sources.items():
            if topic != other_topic:
                overlap = len(sources & other_sources)
                if overlap >= 2:  # At least 2 shared sources
                    related.append((other_topic, overlap))

        if related:
            related.sort(key=lambda x: x[1], reverse=True)
            connections[topic] = [t for t, _ in related[:3]]

    return connections
```

**Render:**
```markdown
## World Cup 2026
_Related topics: Sports Infrastructure (3 shared sources), Tourism Industry (2 shared sources)_
```

### 3.3 Add Summary Statistics Dashboard
**Problem:** No overview of content quality and coverage.

**Add after Table of Contents:**
```markdown
## Digest Overview
📊 **Coverage:** 5 topics · 47 sources · 23 unique domains
🔍 **Quality:** 85% corroboration rate · 3.2 sources/story avg
⏱️ **Recency:** 12 stories updated since last run
🌐 **Geographic spread:** US (15), UK (8), EU (7), Global (17)
```

**Implementation:**
```python
def _compute_digest_statistics(digest: Digest) -> dict:
    total_bullets = sum(t.total_bullets or 0 for t in digest.topics)
    total_corroborated = sum(t.corroborated_bullets for t in digest.topics)

    updated_stories = sum(
        len([s for s in t.stories if s.updated])
        for t in digest.topics
    )

    return {
        'topics': len(digest.topics),
        'sources': len(digest.sources),
        'domains': len({domain_of(url) for _, _, url in digest.sources}),
        'corroboration_rate': total_corroborated / total_bullets if total_bullets else 0,
        'avg_sources_per_story': len(digest.sources) / len(digest.topics),
        'updated_count': updated_stories,
    }
```

---

## 4. User Experience Enhancements

### 4.1 Add Reading Time Estimates
**Add to each section:**
```markdown
## World Cup 2026 _~3 min read_
```

```python
def _estimate_reading_time(topic: TopicSummary) -> int:
    """Estimate reading time in minutes (200 words/min)."""
    total_words = 0
    for cluster in topic.clusters:
        for bullet in cluster.bullets:
            total_words += len(bullet.text.split())

    for story in topic.stories:
        total_words += len(story.headline.split())
        total_words += len(story.why.split())
        for bullet in story.bullets:
            total_words += len(bullet.split())

    return max(1, total_words // 200)
```

### 4.2 Improve Further Reading Organization
**Current:** Flat list by domain.

**Enhanced:**
```markdown
### Further Reading

**Official sources:**
- 🏛️ fifa.com • Official tournament page — https://fifa.com/...
- 🏛️ ussoccer.com • US hosting details — https://ussoccer.com/...

**News analysis:**
- 📰 nytimes.com • Economic impact study — https://nytimes.com/...
- 📰 bbc.co.uk • Infrastructure challenges — https://bbc.co.uk/...

**Regional coverage:**
- 🌎 kansascityfwc26.com • Kansas City preparations — https://...
- 🌎 bostonfwc26.com • Boston venue details — https://...

_+ 15 more sources across 8 domains_
```

### 4.3 Add Confidence Indicators
**Problem:** All information appears equally certain.

**Add confidence levels to stories:**
```markdown
#### Headline _(Confidence: High - 5 independent sources)_
#### Headline _(Confidence: Medium - 2 sources, awaiting confirmation)_
#### Headline _(Confidence: Low - Single source report)_
```

**Automatically compute:**
```python
def _compute_confidence(story: Story) -> str:
    source_count = len(story.source_indices)
    if source_count >= 4:
        return f"High - {source_count} independent sources"
    elif source_count >= 2:
        return f"Medium - {source_count} sources"
    else:
        return "Low - Single source report"
```

### 4.4 Highlight Contradictions
**Problem:** When sources disagree, it's not highlighted.

**Add contradiction detection:**
```python
def _detect_contradictions(topic: TopicSummary, sources_lookup: dict) -> list[str]:
    """Find bullets that might contradict each other."""
    contradictions = []

    # Keywords that signal contradiction
    contradiction_markers = ['however', 'but', 'despite', 'contrary', 'although']

    all_bullets = []
    for cluster in topic.clusters:
        all_bullets.extend(cluster.bullets)

    for i, bullet1 in enumerate(all_bullets):
        for bullet2 in all_bullets[i+1:]:
            # Check for shared keywords but different citations
            if (set(bullet1.citations) != set(bullet2.citations) and
                any(marker in bullet1.text.lower() or marker in bullet2.text.lower()
                    for marker in contradiction_markers)):
                contradictions.append(f"Note: Different sources report varying details. "
                                    f"See [{bullet1.citations[0]}] vs [{bullet2.citations[0]}]")

    return contradictions
```

**Display:**
```markdown
### Potential Discrepancies
⚠️ Different sources report varying tournament dates. See [1] vs [3]
⚠️ Team qualification criteria disputed. See [2] vs [4]
```

---

## 5. Technical Implementation Improvements

### 5.1 Implement Importance Scoring
**Add to `models.py`:**
```python
@dataclass
class Story:
    # ... existing fields ...
    importance_score: float = 0.0

    def calculate_importance(self) -> float:
        """Calculate importance based on multiple factors."""
        score = 0.0

        # Corroboration (0-40 points)
        score += min(len(self.source_indices) * 10, 40)

        # Recency (0-30 points)
        if self.updated:
            score += 30
        elif self.date:
            try:
                date_obj = dt.date.fromisoformat(self.date)
                days_old = (dt.date.today() - date_obj).days
                if days_old <= 7:
                    score += 20
                elif days_old <= 30:
                    score += 10
            except ValueError:
                pass

        # Content depth (0-30 points)
        score += min(len(self.bullets) * 10, 30)

        return score
```

### 5.2 Add Semantic Clustering
**Problem:** Current clustering is based on LLM output without validation.

**Enhancement:** Add semantic similarity check for cluster coherence.

```python
# In summarise.py, add validation
def _validate_cluster_coherence(cluster: ClusterSummary) -> float:
    """Score cluster coherence (0-1) based on citation overlap."""
    if len(cluster.bullets) <= 1:
        return 1.0

    all_citations = [set(b.citations) for b in cluster.bullets]

    # Calculate pairwise Jaccard similarity
    similarities = []
    for i, cit1 in enumerate(all_citations):
        for cit2 in all_citations[i+1:]:
            if cit1 or cit2:
                similarity = len(cit1 & cit2) / len(cit1 | cit2)
                similarities.append(similarity)

    return sum(similarities) / len(similarities) if similarities else 0.0

# Flag low-coherence clusters
def _flag_fragmented_clusters(clusters: list[ClusterSummary]) -> list[ClusterSummary]:
    for cluster in clusters:
        coherence = _validate_cluster_coherence(cluster)
        if coherence < 0.3:
            cluster.heading += " (Loosely related)"
    return clusters
```

### 5.3 Enhanced Deduplication
**Current:** Basic URL deduplication in `triage.py`.

**Add content similarity check:**
```python
def _compute_content_similarity(page1: FetchedPage, page2: FetchedPage) -> float:
    """Compute rough similarity using character n-grams."""
    from collections import Counter

    def ngrams(text: str, n: int = 3) -> Counter:
        return Counter(text[i:i+n] for i in range(len(text) - n + 1))

    ng1 = ngrams(page1.content[:1000])  # First 1000 chars
    ng2 = ngrams(page2.content[:1000])

    common = sum((ng1 & ng2).values())
    total = sum((ng1 | ng2).values())

    return common / total if total > 0 else 0.0

# In triage logic, reject if similarity > 0.8
```

---

## 6. Quick Wins (Easy Implementation)

### Priority 1: Immediate Impact
1. **Fix duplicate citations** - `utils.py:ensure_citation_suffix()` ✅ Easy
2. **Add executive summary** - `render.py` ✅ Medium effort, high impact
3. **Improve "At a glance" scoring** - `render.py:_select_at_a_glance()` ✅ Medium
4. **Add reading time estimates** - `render.py` ✅ Easy
5. **Show "What changed" for updates** - `cli.py` ✅ Medium

### Priority 2: Enhanced Features
6. **Importance scoring for stories** - `models.py`, `summarise.py` ⚙️ Medium
7. **Confidence indicators** - `render.py` ⚙️ Easy
8. **Better timeline grouping** - `render.py:_build_timeline()` ⚙️ Medium
9. **Source quality badges** - `render.py` ⚙️ Easy
10. **Summary statistics dashboard** - `render.py` ⚙️ Medium

### Priority 3: Advanced Features
11. **Cross-topic connections** - New function in `render.py` 🔬 Complex
12. **Contradiction detection** - New function in `summarise.py` 🔬 Complex
13. **Semantic clustering validation** - `summarise.py` 🔬 Complex
14. **Enhanced content deduplication** - `triage.py` 🔬 Medium

---

## 7. Sample Improved Output

Here's what an enhanced digest would look like:

```markdown
# Daily Digest — 2025-10-21 (Europe/London)
Generated with gpt-oss:latest — Topics: 3; Sources: 47; Elapsed: 62.3s

## 📊 Digest Overview
**Coverage:** 3 topics · 47 sources · 23 unique domains
**Quality:** 85% corroboration rate · 3.2 sources/story avg
**Recency:** 12 stories updated since last run
**Reading time:** ~15 minutes

## ⚡ Executive Summary
- **World Cup 2026:** Tournament expanded to 48 teams — First expansion in World Cup history affects qualification...
- **AI Policy:** EU passes comprehensive AI regulation — New framework establishes global precedent...
- **Climate:** Arctic sea ice reaches record low — Scientists warn of accelerating feedback loops...

## Table of Contents
- [World Cup 2026](#world-cup-2026) _~3 min read_
  - [Tournament Structure](#tournament-structure)
  - [Host Cities](#host-cities)

---

<a id="world-cup-2026"></a>
## World Cup 2026
_Sources: 15 · Domains: 8 · Corroboration: 12/14_ ✅ Well-sourced
_Related topics: Sports Infrastructure (3 shared sources)_

### ⚡ At a glance
- 🔴 **2026 FIFA World Cup Expanded To 48 Teams** — Tournament structure fundamentally redesigned to include 16 more nations [1][2][3] — ⭐ reuters.com, ⭐ bbc.co.uk, 🏛️ fifa.com
- 🟡 **Host Cities Announce Infrastructure Plans** — 16 venues across North America prepare for increased capacity [4][5] — nytimes.com, guardian.com
- ⚪ **Ticket Allocation Process Begins** — Early registration opens for first allocation phase [6] — 🏛️ fifa.com

### 📰 Top Stories

#### [2026 FIFA World Cup Expanded To 48 Teams](https://fifa.com/...) 🔴 BREAKING _(Updated since last run)_
*2025-10-15 · Sources: 5 · Domains: ⭐ reuters.com, ⭐ bbc.co.uk, 🏛️ fifa.com, espn.com, apnews.com*
*Confidence: High - 5 independent sources*
*What changed: Added 2 new bullets about qualification structure*

_Why it matters:_ This represents the first major expansion since 1998 and will significantly increase developing nations' participation opportunities.

**Key developments:**
- 🔹 Tournament format redesigned with 16 groups of 3 teams each, replacing the traditional 8 groups of 4 [1][2][3] — ⭐ reuters.com, ⭐ bbc.co.uk, 🏛️ fifa.com
- 🔹 Total matches increase from 64 to 104, extending tournament duration by one week [1][4] — ⭐ reuters.com, nytimes.com
  - 🔸 UEFA allocation increased to 16 spots, CAF to 9, CONCACAF to 6 [2][3] — ⭐ bbc.co.uk, 🏛️ fifa.com
  - 🔸 Each host nation (US, Canada, Mexico) receives automatic qualification [3] — 🏛️ fifa.com

### 📅 Timeline

**Recent developments:**
- 2025-10-15 — New 48-team format officially confirmed by FIFA [1] 🆕
- 2025-09-20 — Final host city selections announced [4]
- 2025-08-10 — Ticket registration system launched [6]

**Historical context:**
- 2023-05-09 — United 2026 bid officially selected [7]
- 2018-06-13 — Joint bid submitted to FIFA [8]

### 🔍 Further Reading

**Official sources:**
- 🏛️ fifa.com • Official tournament page — https://fifa.com/...
- 🏛️ ussoccer.com • US hosting details — https://ussoccer.com/...

**News analysis:**
- 📰 nytimes.com • Economic impact study — https://nytimes.com/...
- 📰 bbc.co.uk • Infrastructure challenges — https://bbc.co.uk/...

**Regional coverage:**
- 🌎 kansascityfwc26.com • Kansas City preparations — https://...
- 🌎 bostonfwc26.com • Boston venue details — https://...

_+ 8 more sources_

[Back to top](#table-of-contents)

---

## 📚 Sources
- [1] ⭐ 2026 FIFA World Cup — https://en.wikipedia.org/wiki/2026_FIFA_World_Cup
- [2] ⭐ Reuters: FIFA confirms expansion — https://reuters.com/...
- [3] 🏛️ FIFA Official Announcement — https://fifa.com/...
...

---
Generated at 2025-10-21T10:30:00+01:00 (Europe/London) using gpt-oss:latest.
Summaries derived from Ollama web search with clustering, deduplication, and corroboration heuristics.
Elapsed: 62.3s · Quality score: 85% · Coverage: 23 domains
```

---

## 8. Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Fix duplicate citations bug
- [ ] Add importance scoring to Story model
- [ ] Enhance prompt engineering
- [ ] Add reading time estimates
- [ ] Implement digest statistics dashboard

### Phase 2: Content Quality (Week 2)
- [ ] Improve "At a glance" selection algorithm
- [ ] Add confidence indicators
- [ ] Implement "What changed" tracking for updates
- [ ] Add source quality badges
- [ ] Enhanced timeline grouping

### Phase 3: User Experience (Week 3)
- [ ] Add executive summary section
- [ ] Implement visual hierarchy for bullets
- [ ] Enhance further reading organization
- [ ] Add content classification (breaking/analysis/background)
- [ ] Improve HTML styling with new features

### Phase 4: Advanced Features (Week 4)
- [ ] Cross-topic connection detection
- [ ] Contradiction highlighting
- [ ] Semantic clustering validation
- [ ] Enhanced content deduplication
- [ ] Geographic spread analysis

---

## 9. Testing Recommendations

Add test coverage for new features:

```python
# tests/test_improvements.py

def test_executive_summary_generation():
    """Verify executive summary selects most important stories."""
    pass

def test_importance_scoring():
    """Verify importance scores rank stories correctly."""
    pass

def test_confidence_calculation():
    """Verify confidence levels match source counts."""
    pass

def test_citation_deduplication():
    """Verify [1][1][1] is reduced to [1]."""
    pass

def test_topic_connections():
    """Verify shared sources are detected across topics."""
    pass
```

---

## 10. Metrics to Track

Monitor these KPIs to measure improvement impact:

1. **Content Quality**
   - Average corroboration rate
   - Single-source story percentage
   - Stories with dates percentage

2. **User Engagement** (if tracking available)
   - Time spent reading
   - Section jump frequency
   - Further reading click-through rate

3. **Information Density**
   - Bullets per topic
   - Unique domains per topic
   - Average citations per bullet

4. **Output Quality**
   - Duplicate citation instances
   - Empty cluster count
   - Timeline coverage (% stories with dates)

---

## Conclusion

These improvements focus on making NewsBot's output more:

1. **Scannable** - Visual hierarchy, importance indicators, urgency flags
2. **Trustworthy** - Confidence levels, source quality, contradiction detection
3. **Actionable** - Executive summary, "what changed" tracking, classification
4. **Comprehensive** - Cross-topic links, statistics, enhanced timelines
5. **User-friendly** - Reading time, better organization, quality indicators

Start with the Quick Wins in Section 6 for immediate impact, then gradually implement advanced features based on user feedback.
