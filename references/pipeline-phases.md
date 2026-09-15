# Pipeline Phases: Complete 5-Phase Skill Creation Reference

**Version:** 6.1
**Purpose:** Technical reference behind the guided-light skill creation journey.

This document contains the detailed instructions for each phase of skill creation, following the Agent Skills Open Standard (SKILL.md-first, `-skill` suffix on generated names, spec-compliant frontmatter, cross-platform support).

---

## Pipeline Overview

```
Phase 1: DISCOVERY       -> Research APIs, data sources, domain mapping
Phase 2: DESIGN          -> Define use cases, analyses, methodologies
Phase 3: ARCHITECTURE    -> Structure skill directory (standard-compliant)
Phase 4: DETECTION       -> Generate description + keywords for activation
Phase 5: IMPLEMENTATION  -> Create all files, validate, security scan
```

**Key principles:**

- SKILL.md is the **primary file**, created first in Phase 5
- Generated names use **kebab-case** and **must end with `-skill`**
- Name: 1-64 chars, lowercase letters, numbers, hyphens; must match directory
- Description: 1-1024 chars; this IS the activation mechanism
- Generated SKILL.md must be **<500 lines** (move detail to `references/`)
- Frontmatter must include: `name`, `description`, `license`, `metadata` (author, version)
- `install.sh` is generated for cross-platform support
- `.claude-plugin/` manifests are emitted for every skill (Step 6.5) — additive to SKILL.md activation, never a replacement
- Validation and security scan run at the end of Phase 5

---

# Phase 1: Discovery

## Objective

Research the environment, propose evidence-backed implementation choices, and expose
the business decisions that require human authority. Do not make the user translate
their workflow into a complete prompt or semantic schema.

## Detailed Process

### Step 0: Input Triage

Start the resumable interview before triage:

```bash
python3 scripts/structured_interview.py start interview.json \
  --problem "<user's words>" --created-by "<identified workflow expert>"
```

Read `references/structured-interview.md`. Inspect first, record agent findings as
`proposed` or `conflicting`, then ask the one `next_question` returned by `status`.
Only an identified human may confirm meaning, authority, consequences, or risk. Run
`gate` after discovery; exit 2 blocks Phase 2.

Before identifying the domain, classify what the user actually provided:

| Input Type | Strategy |
|---|---|
| Well-formed description | Proceed to Step 1 normally |
| Files only (Excel, PDF, code, CSV) | Reverse-engineer: open each file, reconstruct the workflow from structure. Tab names, column headers, formulas, and formatting ARE the specification |
| URLs only | Fetch each URL. Understand the data source. Infer what the user would do with this data based on their role/context |
| Screenshot/image | Read visually. Identify: what tool is shown? What data? What manual step is visible? What's the pain? |
| Email/forwarded chain | Extract: who asked for what, what was agreed, what's the actual request (ignore disclaimers, scheduling, CC lists) |
| Single word or phrase | Infer from context: user's desk/role, existing skills in their environment, databases available. Present the most likely interpretation and confirm |
| Mixed (files + sentence) | The files are the spec. The sentence is commentary. Cross-reference both |
| "here" + files | The files ARE the input. Process them all. Present your understanding. |
| Pasted reference material (guidelines, policies, wiki pages, style guides) | This IS the knowledge to codify. Read it all. Identify what it governs (writing, design, compliance, process). The user wants an active skill that enforces these rules, not a summary |

**After triage, present your evidence-backed understanding before proceeding:**

"From your [files/URLs/screenshot], I understand you [reconstructed workflow].
The output goes to [inferred recipient]. [Specific question if needed]. Right?"

Record the user's confirmation in `interview.json`. Then proceed to Step 1. If the
understanding contains several independent decisions, confirm them one at a time.

**Discovery check (before building):**
Before designing a new skill, verify:
- Is this data already in a database the user has access to?
- Has a colleague already built a skill for this?
- Is there a simpler solution (existing API, existing tool, existing infrastructure)?

The best outcome is sometimes: "You don't need a new skill — this data already exists in [database]. Let me show you how to query it."

### Step 0.5: Semantic Recon eligibility

After identifying the source, choose the Semantic Recon path before researching its
implementation details. It is required for every live or structured
`DATA_API`, `DATABASE`, `MCP_SERVER`, `CODEBASE`, or remotely served `DATA_FILE`
that the workflow needs. The `--semantic-recon` flag remains for compatibility.

The only exemption is a workflow with no external or structured source. Do not
downgrade a qualifying target merely to avoid the work. If the
operator cannot state the blast radius of misuse and out-of-scope boundary, or safe
access is unavailable, record `verification-blocked`; do not design a direct client.

For an eligible target:

1. Invoke `/semantic-recon` and complete its target profile, including blast radius
   and out-of-scope boundary.
2. Freeze its holdout questions before probing the target.
3. Complete the Semantic Recon gates through its clean-room audit.
4. In Phase 2, build on the registered `data_contract_<id>` rather than the raw
   source. Generated code calls the contract, runs `contract_health.report()`, routes
   requests through `validate_query()`, and preserves contract provenance.
5. Record the contract id, resolved path, target type, required operations, and
   freshness check in `discovery.json`; add a successful query and a refused unsafe
   query to the skill's evals.

Semantic Recon observes and tests system behavior. It never authorizes a business
definition, source-precedence policy, or risk acceptance; keep those decisions in the
structured interview and governed semantic contract.

### Step 1: Identify Domain

From user input, extract the main domain:

| User Input | Identified Domain |
|---|---|
| "US crop data" | Agriculture (US) |
| "stock market analysis" | Finance / Stock Market |
| "global climate data" | Climate / Meteorology |
| "economic indicators" | Economy / Macro |
| "commodity data" | Trading / Commodities |

### Step 2: Search Available APIs

For the identified domain, use WebSearch to find public APIs:

**Search queries:**
```
"[domain] API free public data"
"[domain] government API documentation"
"best API for [domain] historical data"
"[domain] open data sources"
```

**Example (US agriculture):**
```bash
WebSearch: "US agriculture API free historical data"
WebSearch: "USDA API documentation"
WebSearch: "agricultural statistics API United States"
```

**Typical result:** 5-10 candidate APIs.

### Step 3: Research Documentation

For each candidate API, use WebFetch to load:
- Homepage/overview
- Getting started guide
- API reference
- Rate limits and pricing

**Extract information per API:**

```markdown
## API: [Name]

**URL**: [base URL]
**Docs**: [docs URL]

**Authentication**:
- Type: API key / OAuth / None
- Cost: Free / Paid
- How to obtain: [steps]

**Available Data**:
- Temporal coverage: [from when to when]
- Geographic coverage: [countries, regions]
- Metrics: [list]
- Granularity: [daily, monthly, annual]

**Limitations**:
- Rate limit: [requests per day/hour]
- Max records: [per request]

**Quality**:
- Source: [official government / private]
- Reliability: [high/medium/low]
- Update frequency: [frequency]
- Documentation quality: [excellent/good/poor]

**Ease of Use**:
- Format: JSON / CSV / XML
- SDKs: [Python/R/None]
- Quirks: [any non-obvious behavior]
```

### Step 4: API Capability Inventory

Ensure the skill uses the maximum useful surface of the chosen API.

**Step 4.1: Complete Inventory**

For the chosen API, catalog ALL data types:

```markdown
## Complete Inventory - {API Name}

| Endpoint/Metric | Returns | Granularity | Coverage | Value |
|---|---|---|---|---|
| {metric1} | {description} | {daily/weekly} | {geo} | High |
| {metric2} | {description} | {monthly} | {geo} | High |
| {metric3} | {description} | {annual} | {geo} | Medium |
```

**Step 4.2: Coverage Decision**

- If metric has high value: implement in v1.0
- If API has 5 high-value metrics: implement all 5
- Never leave >50% of API unused without strong justification

**Step 4.3: Document Decision**

In `DECISIONS.md`:

```markdown
## API Coverage Decision

API {name} offers {N} types of metrics.

**Implemented in v1.0 ({X} of {N}):**
- {metric1} - {justification}
- {metric2} - {justification}

**Not implemented ({Y} of {N}):**
- {metricZ} - {why not} (planned for v2.0)

**Coverage:** {X/N * 100}%
```

**Output of this step:** Exact list of all `get_*()` methods to implement.

### Step 5: Compare Options

Create comparison table:

| API | Coverage | Cost | Rate Limit | Quality | Docs | Ease | Score |
|---|---|---|---|---|---|---|---|
| API 1 | 5/5 | Free | 1000/day | Official | 4/5 | 5/5 | 9.2/10 |
| API 2 | 4/5 | $49/mo | Unlimited | Private | 5/5 | 4/5 | 7.8/10 |

**Scoring criteria:**
- Coverage (fit with need): 30% weight
- Cost (prefer free): 20% weight
- Rate limit (sufficient?): 15% weight
- Quality (official > private): 15% weight
- Documentation (facilitates implementation): 10% weight
- Ease of use (format, structure): 10% weight

### Step 6: Propose and resolve

**Consider user constraints:**
- Mentioned "free"? Eliminate paid options
- Mentioned "10+ years historical data"? Check coverage
- Mentioned "real-time"? Prioritize streaming APIs

**Apply logic:**
1. Eliminate APIs that violate constraints
2. Of remaining, choose highest score
3. If tied, prefer: official > private, better docs, easier to use
4. Record the result as an evidence-backed proposal
5. Ask for human confirmation only when the choice establishes organizational
   authority, materially changes consequences, or accepts high/critical risk

**Document the final decision:**

```markdown
## Selected API: [API Name]

**Score**: X.X/10

**Justification**:
- Coverage: [specific details]
- Cost: [free/paid + details]
- Rate limit: [number] requests/day
- Quality: [official/private + reliability]
- Documentation: [quality + examples]

**Alternatives Considered**:
- API X: Score 7.5/10 - Rejected because [reason]
- API Y: Score 6.2/10 - Rejected because [reason]
```

### Step 7: Research Technical Details

After deciding, dive deep into documentation via WebFetch:
- Getting started guide
- Complete API reference
- Authentication guide
- Rate limiting details
- Best practices

**Extract for implementation:**

```markdown
## Technical Details - [API]

### Authentication
- Method: API key in header
- Header: `X-Api-Key: YOUR_KEY`
- Obtaining key: [step-by-step]

### Main Endpoints
- URL, parameters, response format, errors

### Rate Limiting
- Limit, response headers, behavior when exceeded

### Quirks and Gotchas
- Data formatting issues (e.g., values as strings with commas)
- Suppressed data markers
- Any non-obvious behavior

### Performance Tips
- What to cache and for how long
- Pagination
- Parallel requests
```

**Carry the gotchas forward.** Everything under "Quirks and Gotchas" is the single
highest-value thing this phase produces: it is the part a competent model cannot
derive on its own, because it contradicts what the API's own docs imply. These
entries do not stop at `references/api-guide.md` — they become the generated
skill's `## Gotchas` section (Phase 5, Step 2). Keep the list as you go; you will
be asked for it.

### Step 8: Document for Later Use

Save everything in `references/api-guide.md` of the skill to be created.

## Discovery Examples

### Example 1: US Agriculture

**Input**: "US crop data"

**Research**:
```
WebSearch: "USDA API agricultural data"
→ Found: NASS QuickStats, ERS, FAS

WebFetch: https://quickstats.nass.usda.gov/api
→ Free, data since 1866, 1000/day rate limit

WebFetch: https://www.ers.usda.gov/developer/
→ Free, economic focus, less granular

WebFetch: https://apps.fas.usda.gov/api
→ International focus, not domestic
```

**Comparison**:
| API | Coverage (US domestic) | Cost | Production Data | Score |
|-----|---------------------------|-------|-------------------|-------|
| NASS | ⭐⭐⭐⭐⭐ (excellent) | Free | ⭐⭐⭐⭐⭐ | 9.5/10 |
| ERS | ⭐⭐⭐⭐ (good) | Free | ⭐⭐⭐ (economic) | 7.0/10 |
| FAS | ⭐⭐ (international) | Free | ⭐⭐ (global) | 4.0/10 |

**DECISION**: NASS QuickStats API
- Best coverage for US domestic agriculture
- Free with reasonable rate limit
- Complete production, area, yield data

### Example 2: Stock Market

**Input**: "technical stock analysis"

**Research**:
```
WebSearch: "stock market API free historical data"
→ Alpha Vantage, Yahoo Finance, IEX Cloud, Polygon.io

WebFetch: Alpha Vantage docs
→ Free, 5 requests/min, 500/day

WebFetch: Yahoo Finance (yfinance)
→ Free, unlimited but unofficial

WebFetch: IEX Cloud
→ Freemium, good docs, 50k free credits/month
```

**Comparison**:
| API | Data | Cost | Rate Limit | Official | Score |
|-----|-------|-------|------------|---------|-------|
| Alpha Vantage | Complete | Free | 500/day | ⭐⭐⭐ | 8.0/10 |
| Yahoo Finance | Complete | Free | Unlimited | ❌ Unofficial | 7.5/10 |
| IEX Cloud | Excellent | Freemium | 50k/month | ⭐⭐⭐⭐ | 8.5/10 |

**DECISION**: IEX Cloud (free tier)
- Official and reliable
- 50k requests/month sufficient
- Excellent documentation
- Complete data (OHLCV + volume)

### Example 3: Global Climate

**Input**: "global climate data"

**Research**:
```
WebSearch: "weather API historical data global"
→ NOAA, OpenWeather, Weather.gov, Meteostat

[Research each one...]
```

**DECISION**: NOAA Climate Data Online (CDO) API
- Official (US government)
- Free
- Global and historical coverage (1900+)
- Rate limit: 1000/day

## Phase 1 Checklist

- [ ] `interview.json` started from the user's own problem statement
- [ ] Inspectable facts discovered before questions were asked
- [ ] Agent inferences recorded as `proposed`; disagreements as `conflicting`
- [ ] Human authority recorded for consequential confirmations
- [ ] Interview gate exits 0 and reports `READY`
- [ ] Research completed (WebSearch + WebFetch)
- [ ] Minimum 3 APIs compared
- [ ] Decision made with clear justification
- [ ] User constraints respected
- [ ] API capability inventory completed
- [ ] Technical details extracted
- [ ] DECISIONS.md content prepared
- [ ] Ready for analysis design

---

# Phase 2: Design

## Objective

**DEFINE** autonomously which analyses the skill will perform and how.

## Additional Steps

- **(new in v6.0)** Artifact Opportunity Assessment — call
  `artifact_detector.detect_artifact(description, domain)`. If a template
  is returned, inline it into the SKILL.md body along with emission
  instructions. See `phase2-artifact-assessment.md`.
- **(new)** Eval Criteria Definition — derive 3–6 binary checks (each graded
  by a shell `command` or flagged `llm-judge`) plus ≥3 golden cases that define
  the skill's loss function. Written to `evals/<name>.eval.md` in Phase 5; on by
  default, `--no-eval` opts out. See `phase2-eval-assessment.md`.

## Detailed Process

### Step 1: Brainstorm Use Cases

From the workflow described by the user, think of typical questions they will ask.

**Technique:** "If I were this user, what would I ask?"

**Example (US agriculture):**

User said: "download crop data, compare year vs year, make rankings"

Typical questions:
1. "What's the corn production in 2023?"
2. "How's soybean compared to last year?"
3. "Did production grow or fall?"
4. "Does growth come from area or productivity?"
5. "Which states produce most wheat?"
6. "Top 5 soybean producers"
7. "Production trend last 5 years?"
8. "Average US yield"
9. "Compare Midwest vs South"
10. "Production by region"

**Goal:** List 15-20 typical questions.

### Step 2: Group by Analysis Type

Group similar questions:

**Group 1: Simple Queries** (fetching + formatting)
- Required analysis: **Data Retrieval**
- Complexity: Low

**Group 2: Temporal Comparisons** (YoY)
- Required analysis: **YoY Comparison + Decomposition**
- Complexity: Medium

**Group 3: Rankings** (sorting + share)
- Required analysis: **State/Entity Ranking**
- Complexity: Medium

**Group 4: Trends** (time series)
- Required analysis: **Trend Analysis**
- Complexity: Medium-High

**Group 5: Projections** (forecasting)
- Required analysis: **Forecasting**
- Complexity: High

**Group 6: Geographic Aggregations**
- Required analysis: **Regional Aggregation**
- Complexity: Medium

### Step 3: Prioritize Analyses

**Prioritization criteria:**
1. **Frequency of use** (based on described workflow)
2. **Analytical value** (insight vs effort)
3. **Implementation complexity** (easier first)
4. **Dependencies** (does one analysis depend on another?)

Score each analysis on these criteria and implement the top 4-6 that cover 80% of use cases. Always include a **comprehensive report function** that combines multiple analyses into a single summary.

### Step 4: Specify Each Analysis

For each selected analysis, document:

```markdown
## Analysis: [Name]

**Objective**: [What it does in 1 sentence]
**When to use**: [Types of questions that trigger it]

**Required inputs**:
- Input 1: [type, description]
- Input 2: [type, description]

**Expected outputs**:
- Output 1: [type, description]

**Methodology**: [Explanation in natural language]

**Formulas**:
- Formula 1 = ...

**Validations**:
- Validation 1: [criteria]

**Interpretation**:
- If result > X: [interpretation]
- If result < Y: [interpretation]

**Concrete example**:
- Input: [specific values]
- Processing: [step by step calculation]
- Output: [JSON with result]
- Response to user: [formatted answer]
```

### Step 5: Specify Methodologies

For quantitative analyses, detail methodology with formulas.

**Example: YoY Decomposition**

```
Production = Area x Yield

Change_Production ~ Change_Area x Yield(t-1) + Area(t-1) x Change_Yield

Contrib_Area = (Change_Area% / Change_Production%) x 100
Contrib_Yield = (Change_Yield% / Change_Production%) x 100
```

**Interpretation:**
- Contrib_Area > 60%: Extensive growth (area expansion is main driver)
- Contrib_Yield > 60%: Intensive growth (technology improvement is main driver)
- Both ~50%: Balanced growth

**Validation:**
- Production(t) approximately equals Area(t) x Yield(t) (margin 1%)
- Contrib_Area + Contrib_Yield approximately equals 100% (margin 5%)

### Step 6: Comprehensive Report Function

Always design a comprehensive report function that:
- Combines data from multiple analyses
- Provides an executive summary
- Includes key metrics, comparisons, and trends
- Is the single most useful output of the skill

### Step 7: Document Analyses

Save all specifications in `references/analysis-methods.md` of the skill.

## Phase 2 Checklist

- [ ] 15+ typical questions listed
- [ ] Questions grouped by analysis type
- [ ] 4-6 analyses prioritized (with scoring)
- [ ] Each analysis specified (objective, inputs, outputs, methodology)
- [ ] Methodologies detailed with formulas
- [ ] Validations defined
- [ ] Interpretations specified
- [ ] Concrete examples included
- [ ] Comprehensive report function designed

---

# Phase 3: Architecture

## Objective

**STRUCTURE** the skill using the Agent Skills Open Standard: directory layout, files, responsibilities, cache, performance.

## Detailed Process

### Step 1: Define Skill Name

**Format:** `{domain}-{objective}-skill` — kebab-case per the Agent Skills Open Standard.

**Rules:**
- 1-64 characters
- Lowercase letters, numbers, and hyphens only
- Must not start or end with hyphen
- Must not contain consecutive hyphens
- Must match parent directory name
- **Must end with `-skill`**

**Examples:**
- `stock-analyzer-skill`
- `csv-data-cleaner-skill`
- `weekly-report-generator-skill`
- `nass-agriculture-monitor-skill`
- `noaa-climate-analysis-skill`

### Step 2: Directory Structure

All skills follow the Agent Skills Open Standard structure:

**Simple Skill (1-2 workflows, <1000 lines):**

```
skill-name/
├── SKILL.md              # Primary file, <500 lines
├── scripts/
│   └── main.py
├── references/
│   └── guide.md
├── assets/
│   └── config.json
├── .claude-plugin/       # plugin.json + marketplace.json (Claude Code plugin install)
├── install.sh            # Cross-platform installer
└── README.md             # Multi-platform install instructions
```

**Organized Skill (3-5 scripts, medium complexity):**

```
skill-name/
├── SKILL.md
├── scripts/
│   ├── fetch.py
│   ├── parse.py
│   ├── analyze.py
│   └── utils/
│       ├── cache.py
│       └── validators.py
├── references/
│   ├── api-guide.md
│   └── analysis-methods.md
├── assets/
│   └── config.json
├── .claude-plugin/
├── install.sh
└── README.md
```

**Complex Skill (6+ scripts, large scope):**

```
skill-name/
├── SKILL.md
├── scripts/
│   ├── core/
│   │   ├── fetch_source.py
│   │   ├── parse_source.py
│   │   └── analyze_source.py
│   ├── models/
│   │   └── forecasting.py
│   └── utils/
│       ├── cache_manager.py
│       ├── rate_limiter.py
│       └── validators.py
├── references/
│   ├── api-guide.md
│   ├── analysis-methods.md
│   └── troubleshooting.md
├── assets/
│   ├── config.json
│   └── metadata.json
├── .claude-plugin/
├── install.sh
└── README.md
```

**Important:** The SKILL.md file with its frontmatter is what activates the skill on all platforms. The `.claude-plugin/` manifests (Step 6.5) are additive: they make the same skill installable through Claude Code's native plugin system (`/plugin marketplace add`), which brings in-tool install, updates, and enable/disable. Because the skill has no `skills/` subdirectory, Claude Code discovers the root SKILL.md automatically (root-fallback). Do NOT add a `.claude/` directory inside a skill — it can shadow plugin skill discovery.

### Step 3: Simple vs Complex Suite Decision

| Factor | Simple Skill | Complex Suite |
|---|---|---|
| Workflows | 1-2 | 3+ distinct |
| Code size | <1000 lines | >2000 lines |
| Maintenance | Single developer | Team |
| Structure | Single SKILL.md | Multiple component SKILL.md files |
| marketplace.json | Shipped by default (`.claude-plugin/`, Step 6.5) | Shipped by default (official fields only) |

**Default:** Start with simple skill. Upgrade to complex suite only when warranted.

### Step 4: Define Script Responsibilities

**Principle:** Separation of Concerns.

**Typical scripts:**

| Script | Responsibility | Does NOT | Size |
|---|---|---|---|
| `fetch_source.py` | API requests, auth, rate limiting | Parse, transform, analyze | 200-300 lines |
| `parse_source.py` | Parsing, cleaning, validation | Fetch, analyze | 150-200 lines |
| `analyze_source.py` | All analyses (YoY, ranking, etc.) | Fetch, parse | 300-500 lines |

**Typical utils:**

| Util | Responsibility | Size |
|---|---|---|
| `cache_manager.py` | Response cache, differentiated TTL | 100-150 lines |
| `rate_limiter.py` | Rate limit control, persistent counter | 100-150 lines |
| `validators.py` | Data validations, consistency checks | 100-150 lines |

### Step 5: Plan References

Detailed documentation files loaded on demand:

| File | Content | Size |
|---|---|---|
| `api-guide.md` | How to get API key, endpoints, parameters, response format, quirks | ~1500 words |
| `analysis-methods.md` | Each analysis explained, formulas, interpretations, examples | ~2000 words |
| `troubleshooting.md` | Common problems, step-by-step solutions, FAQs | ~1000 words |

### Step 6: Plan Assets

**config.json** structure:

```json
{
  "api": {
    "base_url": "https://api.example.com/v1",
    "api_key_env": "API_KEY_VAR",
    "_instructions": "Get free key from: https://example.com/register",
    "rate_limit_per_day": 1000,
    "timeout_seconds": 30
  },
  "cache": {
    "enabled": true,
    "ttl_historical_days": 365,
    "ttl_current_days": 7
  },
  "defaults": {
    "param1": "value1"
  }
}
```

### Step 7: Cache and Rate Limiting Strategy

**Cache rules:**
- Historical data (year < current): Permanent cache (365+ days)
- Current year data: Short cache (7 days, may be revised)
- Metadata (lists, mappings): Permanent cache

**Rate limiting:**
- Persistent counter (file-based)
- Pre-request verification
- Alerts when near limit (>90%)
- Blocking when limit reached

### Step 8: Document Architecture

Prepare content for `DECISIONS.md`:
- Chosen directory structure and justification
- Script responsibilities
- Cache strategy and TTLs
- Rate limiting approach

## Phase 3 Checklist

- [ ] Skill name defined (kebab-case, ends with `-skill`, 1-64 chars)
- [ ] Directory structure chosen
- [ ] Responsibilities of each script defined
- [ ] References planned (which files, content)
- [ ] Assets planned (which configs, structure)
- [ ] Cache strategy defined (what, TTL)
- [ ] Rate limiting strategy defined
- [ ] Architecture documented

---

# Phase 4: Detection

## Objective

Generate a **description** (<=1024 characters) with domain keywords for agent discovery. The description in the SKILL.md frontmatter IS the primary activation mechanism across all platforms.

**Key v4.0 change:** There are NO `activation.keywords` or `activation.patterns` fields in marketplace.json. The `description` field in SKILL.md frontmatter is the single activation mechanism. All keywords must be embedded in the description itself.

## Detailed Process

### Step 1: List Domain Entities

Identify all relevant entities users may mention:

**Entity categories:**

1. **Organizations/Sources**: Names, acronyms, full names (USDA, NASS, NOAA)
2. **Main Objects**: Domain-specific items (commodities, instruments, metrics)
3. **Geography**: Countries, regions, states
4. **Metrics**: production, area, yield, price, revenue, temperature
5. **Temporality**: years, seasons, current, historical, YoY

### Step 2: List Actions/Verbs

Which verbs does the user use to request analyses?

**Categories:**
- **Query**: what is, how much, show me, get, tell me, find
- **Compare**: compare, versus, vs, difference, change, growth
- **Rank**: top, best, leading, biggest, rank, ranking, list
- **Analyze**: analyze, trend, pattern, evolution, breakdown
- **Forecast**: predict, project, forecast, outlook, estimate
- **Report**: report, dashboard, summary, overview

### Step 3: Generate Comprehensive Keywords

For EACH metric/capability the skill implements, generate keywords:

```markdown
Metric 1: [metric name]
Primary keywords: [3-5 keywords]
Secondary keywords: [3-5 synonyms]
Action keywords: [2-3 verbs specific to this metric]
Total: ~10-15 keywords per metric
```

**Goal:** 50-80 unique keywords total across all metrics.

### Step 4: List Question Variations

For each analysis type, enumerate how users might ask:

**YoY Comparison:**
- "Compare X this year vs last year"
- "How does X compare to last year"
- "X growth rate"
- "X change YoY"
- "Did X increase or decrease"

**Ranking:**
- "Top states for X"
- "Which states produce most X"
- "Leading X producers"
- "Ranking of X"

**Trend:**
- "X trend last N years"
- "How has X changed over time"
- "Historical X data"

### Step 5: Define Negative Scope

What should NOT activate the skill? Avoid false positives.

```markdown
## Skill Scope

### WITHIN scope:
- [specific capability 1]
- [specific capability 2]

### OUT of scope:
- [related but unsupported topic 1]
- [related but unsupported topic 2]
```

### Step 6: Create the Description

The description must be <=1024 characters and serve as the sole activation mechanism. Pack it with the most important keywords.

**Template:**

```yaml
description: >-
  [What the skill does]. Activates when users ask to [primary use case],
  [secondary use case], or [tertiary use case]. Triggers on phrases like
  [keyword phrase 1], [keyword phrase 2], [keyword phrase 3], [keyword
  phrase 4]. Supports [capability 1], [capability 2], [capability 3].
  Uses [technology/API] to [what it does with real data].
```

**Mandatory components:**
1. Domain with specific entities (not just "crops" but "corn, soybeans, wheat")
2. Each major API metric explicitly mentioned
3. Action verbs covered (compare, rank, analyze, report)
4. Temporal context (current, historical, year-over-year)
5. Geographic context if relevant (states, regions, national)
6. Data source name (USDA NASS, Alpha Vantage, etc.)

**Constraints:**
- Must be 1-1024 characters
- Must be a single string (use `>-` for YAML folding)
- No line breaks in the final output

**Real example:**

```yaml
description: >-
  Analyze US agricultural production using official USDA NASS data.
  Activates when users ask about crop production, area planted, yield,
  harvest progress, or crop conditions for corn, soybeans, wheat, and
  other commodities. Triggers on phrases like compare corn production,
  top soybean states, wheat yield trend, crop condition report, harvest
  progress update. Supports year-over-year comparisons, state rankings,
  trend analyses, growth decomposition, regional aggregations, and
  comprehensive crop reports. Uses Python with NASS QuickStats API to
  fetch real data on production, area, yield, conditions, and progress.
```

### Step 7: Mental Testing

For each example question from Phase 2, verify:
- Does the description contain relevant keywords?
- Would an LLM reading the description match this query?

If any use case would NOT be detected, add missing keywords to the description.

### Step 8: Document Keywords in SKILL.md Body

In the SKILL.md body (not frontmatter), include a keywords section for transparency:

```markdown
## Keywords for Automatic Detection

This skill is activated when user mentions:

**Entities**: [list]
**Geography**: [list]
**Metrics**: [list]
**Actions**: [list]

**Activation examples:**
- "[example 1]"
- "[example 2]"
- "[example 3]"

**Does NOT activate for:**
- "[out of scope 1]"
- "[out of scope 2]"
```

## Phase 4 Checklist

- [ ] Domain entities listed (organizations, objects, geography)
- [ ] Actions/verbs listed
- [ ] 50+ keywords generated across all metrics
- [ ] Question variations mapped
- [ ] Negative scope defined
- [ ] Description created (<=1024 chars, packed with keywords)
- [ ] Keywords documented in SKILL.md body
- [ ] Activation examples (positive and negative)
- [ ] Mental detection simulation (all use cases covered)

---

# Phase 5: Implementation

## Objective

**IMPLEMENT** everything with functional code, useful documentation, and real configs. Then **validate** against the spec and run a **security scan**.

## Quality Rules (Non-Negotiable)

### NEVER:

```python
# FORBIDDEN: placeholder code
def analyze():
    # TODO: implement this function
    pass
```

```markdown
<!-- FORBIDDEN: empty reference -->
For more details, consult the official documentation at [external link].
```

```json
// FORBIDDEN: placeholder config
{ "api_key": "YOUR_API_KEY_HERE" }
```

### ALWAYS:

- Complete, functional code in every function
- Detailed docstrings with Args, Returns, Raises, Example
- Type hints on all public functions
- Robust error handling with specific exceptions
- Input and output validations
- Real values in configs with instructions for user-provided values
- Self-contained content in references (not just links)

## Implementation Order

Execute these 10 steps in order:

### Step 1: Create Directory Structure

```bash
mkdir -p skill-name/{scripts,references,assets}
```

Every skill also gets a `.claude-plugin/` directory (see Step 6.5) so Claude Code can install it as a plugin.

### Step 2: Write SKILL.md (PRIMARY FILE - CREATE FIRST)

The SKILL.md is the most important file. It must have spec-compliant frontmatter and be <500 lines.

**Required frontmatter:**

```yaml
---
name: skill-name
description: >-
  Description here, <=1024 chars, packed with activation keywords.
license: MIT
metadata:
  author: Author Name
  version: 1.0.0
  created: 2026-02-27
  last_reviewed: 2026-02-27
  review_interval_days: 90
  dependencies:
    - url: https://api.example.com/v1
      name: Example API
      type: api
---
```

**Frontmatter field rules:**
- `name`: 1-64 chars, lowercase + hyphens, must match directory name
- `description`: 1-1024 chars, the activation mechanism
- `license`: Required (MIT, Apache-2.0, etc.)
- `metadata.author`: Required
- `metadata.version`: Required, semver format

**Body structure (must be <500 lines total including frontmatter):**

```markdown
# Skill Name

[Introduction: 2-3 paragraphs]

## When to Use This Skill

[Activation triggers with examples]

## Data Source

[API summary, link to references/api-guide.md for details]

## Workflows

### Workflow 1: [Name]
[Step-by-step with commands and examples]

### Workflow 2: [Name]
[Step-by-step with commands and examples]

## Available Scripts

[Each script: the command that RUNS it, then inputs and outputs. Lead with the
verb — "Run `python3 scripts/x.py --input <f>`" — never a bare path, so the agent
never has to guess whether to execute the file or read it.]

## Available Analyses

[Brief description of each analysis, link to references/ for details]

## Error Handling

[Common errors and how the skill handles them]

## Gotchas

[Environment-specific facts that defy reasonable assumptions]

## Keywords for Detection

[Organized keyword list]

## Usage Examples

[3-5 complete examples with question, flow, and answer]

## References

[Table of reference files with a "when to read this" column — these are READ on
demand, never executed]
```

**Keeping under 500 lines:** Move detailed content to `references/`:
- Detailed API docs go to `references/api-guide.md`
- Detailed methodologies go to `references/analysis-methods.md`
- Troubleshooting goes to `references/troubleshooting.md`

The cheapest way under the limit is not to move content but to delete the lines
that restate what the model already knows. See "Non-Obvious, Not Restated" in
`quality-standards.md`. Cut those first, then move what remains.

**Writing the `## Gotchas` section:**

This is the highest-value section in the body, and the one no model can write for
you. It holds the environment-specific facts that defy reasonable assumptions —
every place where doing the obvious thing produces the wrong result.

Sources, in order:

1. The "Quirks and Gotchas" list from Phase 1 Step 7.
2. Every correction made while verifying the skill in this phase. If a script had
   to be fixed because the real system behaved differently than expected, that
   difference is a gotcha. Write it down now, or make the same correction again
   next month.
3. Anything the user said in the form "oh, and you have to..." — those are gotchas
   the user did not think to put in the spec because they live in muscle memory.

Sources 1 and 2 are yours to find. Source 3 mostly **will not arrive at creation
time**, and you should not stall trying to extract it. A person cannot describe a
process they run from muscle memory — that is the premise this whole factory is
built on. What they can do is recognize a wrong output the moment they see one.

So ship the skill with the gotchas you have, and tell the user how to add the rest
as they surface:

```bash
python3 scripts/evolve.py --correct "the West region files late, so Friday exports are short"
```

That writes the sentence verbatim to `EVOLUTION.md` and appends it to `## Gotchas`,
so the next run already knows. A skill's gotchas should grow over its life; an
empty section on day one is honest, and a section that never grows means nobody
ever told it anything.

Format each entry as the wrong assumption followed by the real behavior:

```markdown
## Gotchas

- **Yields come back as strings with thousands separators** (`"1,234"`), not numbers.
  `int()` raises on them. `parse_value()` in `scripts/fetch.py` strips separators —
  use it rather than casting.
- **The `/summary` endpoint returns HTTP 200 with an empty `data` array** when the
  requested year has not been published yet, instead of 404. Check `len(data)`, not
  the status code.
- **County-level records are suppressed** (`(D)`) when fewer than three operations
  report. These rows must be dropped before aggregating or state totals come out low.
```

Rules:

- `None known` is a valid value. Write it when the skill genuinely has no gotchas.
- **Never invent gotchas to fill the section.** A fabricated gotcha is worse than
  an empty one: it teaches the agent a false constraint it will then work around.
  If it did not come from a real correction or a real observation, it does not go in.
- Do not put generic advice here ("APIs can be slow", "always validate input").
  That is the section with the content removed.

### Step 2.5: Write AGENTS.md (Companion Instruction File)

Generate an AGENTS.md alongside SKILL.md to maximize cross-tool reach. ~15 tools read AGENTS.md (AAIF-governed format), including some that don't read SKILL.md (Augment, Continue.dev, Zed).

**Template:**

```markdown
# skill-name

> [One-line description from SKILL.md frontmatter]

## Purpose

[2-3 sentences explaining what this skill does and when to use it]

## Activation

This skill activates when users ask about [domain keywords]. Invoke with `/skill-name` on platforms that support slash commands, or ask naturally.

**Example queries:**
- "[example 1]"
- "[example 2]"
- "[example 3]"

## Usage

[Brief usage instructions — what to provide, what to expect back]

## Gotchas

[Copy the SKILL.md `## Gotchas` entries verbatim, or `None known`]

## Implementation

Full skill definition, scripts, and references are in the SKILL.md file and accompanying directories. See SKILL.md for complete instructions.

## Files

- `SKILL.md` — Full skill definition (agentskills.io format), including the `## Gotchas` section
- `scripts/` — Executable code (`run_pipeline.py` orchestrator for multi-script skills, `run_evals.py` eval runner)
- `references/` — Detailed documentation
- `assets/` — Templates, configs
- `evals/` — Bundled eval spec: binary checks + golden cases; `evals/caliper/` holds the agent-run (Caliper) spec
- `install.sh` — Cross-platform installer
```

**Rules:**
- Keep AGENTS.md concise (~50-100 lines). It is a pointer and summary, not a duplicate of SKILL.md.
- Include enough context for tools that ONLY read AGENTS.md (they will not see SKILL.md).
- Include activation keywords so description-based matching works.
- **`## Gotchas` is the one section worth duplicating in full.** Augment, Continue.dev
  and Zed read AGENTS.md and never open SKILL.md; a pointer to gotchas they cannot
  follow leaves them running on assumptions the gotchas exist to correct.

### Step 3: Implement Python Scripts

Every script must follow this quality standard:

```python
#!/usr/bin/env python3
"""
Script title in 1 line.

Detailed description: what it does, how it works,
when to use, inputs and outputs.

Example:
    $ python script.py --param1 value1
"""

# 1. Standard library imports
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# 2. Third-party imports
import requests

# 3. Local imports
from utils.cache_manager import CacheManager


# Constants
API_BASE_URL = "https://..."
DEFAULT_TIMEOUT = 30


class MainClass:
    """
    Class description.

    Attributes:
        attr1: description
        attr2: description

    Example:
        >>> obj = MainClass(param)
        >>> result = obj.method()
    """

    def __init__(self, param1: str, param2: int = 10):
        """
        Initialize MainClass.

        Args:
            param1: detailed description
            param2: detailed description. Defaults to 10.

        Raises:
            ValueError: If param1 is invalid
        """
        if not param1:
            raise ValueError("param1 cannot be empty")
        self.param1 = param1
        self.param2 = param2

    def main_method(self, input_val: str) -> Dict:
        """
        What the method does.

        Args:
            input_val: description

        Returns:
            Dict with keys:
                - key1: description
                - key2: description

        Raises:
            APIError: If API request fails

        Example:
            >>> obj.main_method("value")
            {'key1': 123, 'key2': 'abc'}
        """
        if not self._validate_input(input_val):
            raise ValueError(f"Invalid input: {input_val}")

        try:
            result = self._do_work(input_val)
            return result
        except Exception as e:
            print(f"Error: {e}")
            raise


def main():
    """Main function with argparse."""
    import argparse

    parser = argparse.ArgumentParser(description="Script description")
    parser.add_argument('--param1', required=True, help="Parameter description")
    parser.add_argument('--output', default='output.json', help="Output file path")

    args = parser.parse_args()
    obj = MainClass(args.param1)
    result = obj.main_method(args.param1)

    import json
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
```

**Checklist per script:**
- Correct shebang (`#!/usr/bin/env python3`)
- Complete module docstring
- Organized imports (stdlib, third-party, local)
- Type hints on all public functions
- Docstrings with Args, Returns, Raises, Example
- Error handling for risky operations
- Input and output validations
- Main function with argparse
- `if __name__ == "__main__"` guard
- No TODO, no `pass`, no `NotImplementedError`

**Script patterns by type:**

**fetch_source.py** (200-300 lines):
- API client class with authentication
- Rate limiting integration
- Request retry with exponential backoff
- Response validation
- Cache integration (check cache before API call)

**parse_source.py** (150-200 lines):
- Parse raw API JSON to structured data
- Clean data (remove formatting, handle nulls)
- Transform data (standardize names, convert units)
- Validate data (required fields, ranges, no duplicates)

**analyze_source.py** (300-500 lines):
- All analysis functions (YoY, ranking, trend, etc.)
- Comprehensive report function
- Each function: validate inputs, compute, interpret, return structured result

**run_pipeline.py** (orchestrator — required when 2+ scripts run in sequence):
- Single entry-point that imports each step's function and calls them in order
- Wires each step's output into the next step's input **in code** (never via the agent)
- Lets the SKILL.md give the agent ONE happy-path command instead of N prose steps
- Skip for genuinely interactive/branching skills. See `phase5-orchestration.md`

### Step 4: Write References

Detailed documentation files. Each must be self-contained with real content.

**api-guide.md** (~1500 words):
- How to get API key (step-by-step)
- Main endpoints with example requests and responses
- Parameter details with types and valid values
- Response format with field descriptions
- Rate limits and how to handle them
- Known quirks and workarounds

**analysis-methods.md** (~2000 words):
- Each analysis explained with objective and methodology
- Mathematical formulas
- Interpretation guidelines
- Validation criteria
- Complete numerical examples with real values

**troubleshooting.md** (~1000 words):
- Common problems with symptoms, causes, and solutions
- Error messages and what they mean
- Step-by-step debugging procedures

### Step 5: Write Assets

**config.json**: Real API URLs, env var names for keys, rate limits, cache TTLs, default parameters. Always include `_instructions` or `_note` fields explaining user-provided values.

**metadata.json** (if needed): Domain-specific mappings, aliases, conversions, groupings.

### Step 5.5: Emit Eval Spec (skip if `--no-eval`)

Write the skill's loss function so it ships with the skill and doubles as a
regression test:

1. Write `evals/<skill-name>.eval.md` — prose plus a fenced ` ```json ` block
   carrying the `criteria` (binary; each `command` with a `cmd`, or `llm-judge`)
   and the `golden` cases derived in Phase 2. Place golden inputs/expected files
   under `evals/golden/<case-id>/`.
2. Copy the runner verbatim:
   ```bash
   cp scripts/run_evals_template.py <skill>/scripts/run_evals.py
   chmod +x <skill>/scripts/run_evals.py
   ```
3. Golden cases: seed from the user's artifacts when available; otherwise
   synthesize input-only cases marked `expected_status: "pending-first-green"`.
4. If the skill runs from one command, add a `run` field
   (`"run": "python3 scripts/run_pipeline.py --input {input} --output {output}"`)
   so `run_evals.py --rollout` can execute the skill end-to-end on each golden
   input and score the real output (post-delivery; not a gate). Omit `run` for
   interactive/branching skills.
5. Write `evals/caliper/<skill-name>.eval.yaml` from
   `references/templates/caliper-eval-template.yaml`: three tasks (happy path, edge
   case, silence probe) whose `assert:` blocks mirror the criteria above and whose
   `activates:` names the skill. This is the agent-run counterpart of the file-level
   spec: the marketplace operator's agent runs it inside a real agent per declared
   platform (`team_marketplace.py reliability`) and certifies what passes. Never run
   it at delivery; only validate the syntax when `caliper` is installed
   (`caliper validate <spec>`). See `docs/CALIPER.md`.

See `phase2-eval-assessment.md` for the full format, criteria rules, the rollout
`run` field, and the `autoresearch-universal` handoff (its rule 18 consumes this
spec directly). On by default; `--no-eval` skips this step and emits no `evals/`
directory.

### Step 6: Generate install.sh

Generate the installer from `scripts/install-template.sh` — the canonical template. Replace `{{SKILL_NAME}}` with the actual skill name and `chmod +x`:

```bash
# During skill generation:
sed "s/{{SKILL_NAME}}/skill-name/g" scripts/install-template.sh > skill-name/install.sh
chmod +x skill-name/install.sh
```

The template handles:
- POSIX-compatible shell (`set -eu`, no bashisms)
- 17 platforms (see `scripts/platforms.py`, the single source of truth): claude-code, github-copilot, cursor, windsurf, cline, codex, gemini, kiro, kilo-code, factory, junie, trae, goose, opencode, roo-code, antigravity, universal
- Corrected paths: Codex → `~/.agents/skills/`, Windsurf → `.windsurf/rules/` (project) / `global_rules.md` (global)
- Format adapters: auto-generates `.mdc` for Cursor, `.md` rules for Windsurf, plain `.md` for Cline/Roo/Trae
- Universal `.agents/skills/` secondary symlink after every install
- `--all` flag to install to every detected tool at once
- `--dry-run` for preview without changes

### Step 6.5: Generate Claude Code plugin manifests

Generate `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` from
the canonical templates in `scripts/claude-plugin-template/`. This makes the
skill installable through Claude Code's native plugin system — in-tool install,
updates, and enable/disable — with two commands:

```
/plugin marketplace add <github-owner>/<repo>     # or a local path: /plugin marketplace add ./skill-name
/plugin install <skill-name>@<skill-name>
```

Fill the placeholders from the SKILL.md frontmatter:

| Placeholder | Source |
|---|---|
| `{{SKILL_NAME}}` | frontmatter `name` (must match exactly) |
| `{{SKILL_VERSION}}` | frontmatter `metadata.version` |
| `{{SKILL_AUTHOR}}` | frontmatter `metadata.author` |
| `{{SKILL_DESCRIPTION}}` | one-line summary derived from `description` — single line, no double quotes, so the JSON stays valid |

```bash
# During skill generation (repeat for marketplace.json):
sed -e "s/{{SKILL_NAME}}/skill-name/g" \
    -e "s/{{SKILL_VERSION}}/1.0.0/g" \
    -e "s/{{SKILL_AUTHOR}}/Author Name/g" \
    -e "s/{{SKILL_DESCRIPTION}}/One-line description/g" \
    scripts/claude-plugin-template/plugin.json > skill-name/.claude-plugin/plugin.json
```

After generation, verify both files parse (`python3 -c "import json,sys; json.load(open(sys.argv[1]))" ...`)
and that the `name` fields match the SKILL.md `name`. Claude Code discovers the
skill's root SKILL.md automatically (root-fallback — no `skills/` subdirectory
needed). Never create a `.claude/` directory inside a generated skill; it can
shadow plugin skill discovery.

### Step 6.6: Ship the evolution toolkit

Copy the maintenance loop into the skill so it can check itself after delivery
— no creator repo needed:

```bash
cp scripts/evolve_template.py <skill>/scripts/evolve.py
cp scripts/skill_document.py scripts/review_staleness.py scripts/dependency_health.py \
   scripts/schema_drift.py scripts/staleness_check.py scripts/success_ledger.py \
   <skill>/scripts/
chmod +x <skill>/scripts/evolve.py
```

`python3 scripts/evolve.py` runs staleness/dependency/drift checks plus the
eval rollout (with `--judge` to grade llm-judge criteria). Any failure appends
the raw evidence to the skill's `EVOLUTION.md` — that file is the input for a
regenerate pass (`/agent-skills-platform <skill> using EVOLUTION.md`).

### Step 6.7: Emit verification evidence

After the graph gates and the representative or live run complete, generate the
release artifact from their actual results:

```bash
python3 scripts/generate_verification.py <skill> \
  --run-kind representative --environment <current-platform>
```

Use `--run-kind live` only when the skill successfully called its real external
system. The generated `VERIFICATION.md` records exact eval counts, gate states,
installed environments, and declared platform coverage. It must also state that one
run is not certification of every future data source or every platform.

The ledger records only fixed lifecycle metadata with a locally salted skill ID.
It contains no workflow content and has no network transport. Read
`product-success.md` for the event schema, instrumentation contract, opt-out, and
metric formulas. Instrument a deterministic `run_pipeline.py` so a successful run
records `os.environ.get("ASC_RUN_EVENT", "skill_run")`, uses `ASC_RUN_ID` when
present, and treats ledger errors as non-fatal.

### Step 7: Write README.md

Multi-platform installation instructions:

```markdown
# Skill Name

Brief description.

## Installation

### Universal Path (works with 6+ tools)

```bash
git clone <repo-url> ~/.agents/skills/skill-name
```

Works with Codex CLI, Gemini CLI, Kiro, Antigravity, and other tools that read `~/.agents/skills/`.

### Claude Code (plugin — recommended)

```
/plugin marketplace add <github-owner>/<repo>    # or local: /plugin marketplace add ./skill-name
/plugin install skill-name@skill-name
```

### Using install.sh (Recommended for other tools)

```bash
chmod +x install.sh
./install.sh                          # Auto-detect platform
./install.sh --platform claude-code   # Claude Code
./install.sh --platform cursor        # Cursor (auto-generates .mdc)
./install.sh --all                    # All detected platforms
./install.sh --dry-run                # Preview without installing
```

### Alternative: npx

```bash
npx skills add <repo-url>
```

### Manual Installation

| Platform | Copy to |
|---|---|
| Universal | `~/.agents/skills/skill-name/` |
| Claude Code | `~/.claude/skills/skill-name/` or `.claude/skills/skill-name/` |
| GitHub Copilot | `.github/skills/skill-name/` |
| Cursor | `.cursor/rules/skill-name/` |
| Windsurf | `.windsurf/rules/skill-name/` |
| Cline | `.clinerules/skill-name/` |
| Codex CLI | `~/.agents/skills/skill-name/` |
| Gemini CLI | `~/.gemini/skills/skill-name/` |
| Kiro | `.kiro/skills/skill-name/` |
| Trae | `.trae/rules/skill-name/` |
| Goose | `~/.config/goose/skills/skill-name/` |
| OpenCode | `~/.config/opencode/skills/skill-name/` |
| Roo Code | `.roo/rules/skill-name/` |
| Antigravity | `.agents/skills/skill-name/` |

## Prerequisites

[API key instructions, dependencies]

## Usage Examples

[3-5 examples]

## Troubleshooting

[Common issues and solutions]
```

### Step 7b: Generate Harness Patterns (mandatory)

Every skill must include these harness patterns as executable code, not as markdown instructions.

**a. Self-bootstrapping wrappers at the repo root:**
- `./skill-name` (bash) — auto-creates venv, installs uv if missing, installs deps on first run. Bootstrap messages to stderr.
- `.\skill-name.ps1` (PowerShell) — same behavior for Windows users.

**b. Input validation module (`scripts/validate_inputs.py` or integrated into main script):**
- Validate all user-facing inputs before computation: reject negatives where nonsensical, reject out-of-bounds values, validate enum inputs against known values
- On validation failure: print JSON to stderr with `{"error": "...", "error_type": "validation", "details": [{"field": "...", "error": "..."}]}` and exit 1
- If the skill brief contains `harness_requirements.input_validation`, implement those specific rules

**c. Output sanity checks:**
- After computation, check results against domain-specific bounds
- Attach `_warnings` array to JSON output when values are unusual but not invalid
- If the skill brief contains `harness_requirements.output_sanity`, implement those specific bounds

**d. `--check-prereqs` command (or flag on the main command):**
- Check Python version, required packages (try import), API keys (check env vars exist without printing values), network access (optional, with timeout)
- Output: `{"ready": true/false, "checks": [{"check": "...", "required": "...", "found": "...", "ok": true/false}]}`

**e. `--diagnostics` command (or flag):**
- Output: `{"skill": "...", "version": "...", "harness_level": "...", "commands": [...], "harness_features": {"input_validation": true, ...}}`

**f. SKILL.md frontmatter must include:**
- `activation: /{skill-name}` — unique namespace prefix
- `provenance:` block — if cliskill provides provenance metadata in the skill brief, pass it through. If standalone, generate minimal: `maintainer: unknown, version: 1.0.0, created: {today}`

**g. SKILL.md body must include:**
- `## Prerequisites` section listing runtime, deps, API keys, network requirements
- Anti-activation in anti-goals: "Do NOT activate on general queries — wait for explicit `/{skill-name}` invocation"

**h. Structured error handling throughout:**
- All errors as JSON to stderr: `{"error": "message", "error_type": "validation|runtime|network", "hint": "..."}`
- Exit code 1 on all errors. Never expose stack traces.

### Step 8: Build the Normalized Skill Graph and Run Gates

After creating all files, emit the normalized artifact/dependency IR:

```bash
python3 scripts/skill_graph.py build path/to/skill/ --output path/to/skill/skill.graph.json
```

Then run the constraint system and all independent gates through one entry point:

```bash
python3 scripts/skill_graph.py run path/to/skill/ --jobs 4
```

It must report no graph-constraint or gate errors. The graph blocks unreachable
expected outputs and deterministic multi-step workflows without an orchestrator.
The spec, security, pipeline, and eval-schema gates run concurrently; unchanged
gate results are reused by content hash. Read `skill-graph.md` for the complete IR
contract. Run an individual validator only to diagnose its corresponding gate.

**What it checks:**
- Frontmatter fields present and valid (name, description, license, metadata)
- Name matches directory name
- Name format: 1-64 chars, lowercase + hyphens, no leading/trailing hyphens, no consecutive hyphens
- Description: 1-1024 chars
- SKILL.md under 500 lines
- Required files present

**If validation fails:** Fix the issues and re-run. Do not proceed until validation passes.

### Step 9: Repair Any Gate Failure

Use the failed gate's stdout/stderr and the graph constraint's exact repair. Fix
the named artifact, rebuild `skill.graph.json`, and rerun Step 8. Do not proceed
while any gate or constraint fails.

### Step 10: Install, Try, and Report

After the gates pass, auto-install the skill as described in
`distribution-guide.md`. Then run one representative use case before using success
wording.

Prefer a user-supplied artifact. Otherwise use a local golden fixture. Verification
must not send email or messages, publish, purchase, modify production data, or perform
another consequential action. Use a documented `--dry-run`, sandbox destination, or
local fixture. If no safe path exists, do not execute the side effect.

Use one state in the handoff:

| State | Required evidence |
|---|---|
| `verified` | Gates passed, installed, representative run produced an inspectable result |
| `verification-blocked` | Build passed, but credentials, data, or authority prevent a safe run |
| `installed` | User explicitly declined representative execution |
| `failed` | A build, gate, install, or representative run failed |

For `verified`, use this order:

```
[Concrete result] now works.

Result: [path or short preview]
Use it: /skill-name [representative request]

Checks: validation passed · pipeline passed · security scan clean · representative run passed
Security note: clean means no known scanner pattern matched; it is not proof of safety.

If the result is wrong:
  python3 <skill>/scripts/evolve.py --correct "what it got wrong"
```

For `verification-blocked`, name the missing prerequisite and give one exact setup
action. Do not print `SKILL CREATED SUCCESSFULLY`. File counts, architecture decisions,
eval optimization, and registry commands belong under `Advanced details`, not in the
primary handoff.

## File Creation Order Summary

| Order | File | Notes |
|---|---|---|
| 1 | Directory structure | `mkdir -p skill-name/{scripts,references,assets}` |
| 2 | `SKILL.md` | PRIMARY file, <500 lines, spec-compliant frontmatter, `## Gotchas` section |
| 3 | `scripts/*.py` | Functional code; `run_pipeline.py` orchestrator for multi-script skills |
| 4 | `references/*.md` | Detailed documentation, self-contained |
| 5 | `assets/*.json` | Real values, validated JSON |
| 5.5 | `evals/*.eval.md` + `scripts/run_evals.py` | Bundled loss function; skip if `--no-eval` |
| 5.6 | `evals/caliper/<name>.eval.yaml` | Agent-run reliability spec from `references/templates/caliper-eval-template.yaml`; skip if `--no-eval` |
| 6 | `install.sh` | Cross-platform installer, `chmod +x` |
| 6.5 | `.claude-plugin/*.json` | Plugin manifests from `scripts/claude-plugin-template/`; names match SKILL.md |
| 6.6 | `scripts/evolve.py` + maintenance modules + `success_ledger.py` | Self-maintenance plus private local lifecycle measurement |
| 6.7 | `interview.json` | Ready evidence, conflict, confirmation, and authority trail |
| 7 | `README.md` | Multi-platform install instructions |
| 7.5 | `skill.graph.json` | Normalized typed IR; build with `scripts/skill_graph.py` |
| 8 | Run `skill_graph.py run` | Constraints + spec/security/pipeline/eval gates must pass |
| 9 | Repair failed graph node | Rebuild the IR and rerun until green |
| 10 | Report results | Summary to user |

## Phase 5 Checklist

- [ ] Directory structure created
- [ ] SKILL.md created FIRST with spec-compliant frontmatter
- [ ] SKILL.md is <500 lines
- [ ] Frontmatter has: name, description (<=1024 chars), license, metadata (author, version)
- [ ] Frontmatter has: `activation: /{skill-name}`
- [ ] Frontmatter has: `provenance:` block (full if from cliskill, minimal if standalone)
- [ ] Temporal metadata included (metadata.created, metadata.last_reviewed, metadata.review_interval_days)
- [ ] Name is kebab-case, ends with `-skill`, matches directory
- [ ] SKILL.md body has `## Prerequisites` section
- [ ] SKILL.md body has `## Gotchas` section, carrying the Phase 1 quirks list plus every correction made during this phase (`None known` is valid; invented gotchas are not)
- [ ] AGENTS.md repeats the `## Gotchas` entries in full (AGENTS.md-only tools never see SKILL.md)
- [ ] Nothing in the SKILL.md body restates what the model already knows
- [ ] SKILL.md anti-goals include anti-activation instruction
- [ ] All Python scripts implemented with functional code
- [ ] No TODO, no `pass`, no `NotImplementedError`, no placeholders
- [ ] All scripts have: shebang, docstrings, type hints, error handling
- [ ] Multi-script skill has one `scripts/run_pipeline.py` orchestrator (steps wired in code, one happy-path command)
- [ ] Every `scripts/` mention says to RUN it and every `references/` mention says to READ it — no bare paths (`validate.py` warns on unlabeled mentions)
- [ ] `check_pipeline.py` reports no errors (scripts compile, third-party deps declared)
- [ ] Input validation implemented (reject bad inputs with structured JSON errors)
- [ ] Output sanity checks implemented (warn on extreme values)
- [ ] `--check-prereqs` command returns structured JSON
- [ ] `--diagnostics` command returns skill metadata
- [ ] Self-bootstrapping wrappers: `./skill-name` (bash) + `.\skill-name.ps1` (PowerShell)
- [ ] All errors as JSON to stderr with error_type classification
- [ ] References written with real, self-contained content
- [ ] Assets created with valid JSON and real values
- [ ] Eval spec emitted (`evals/<name>.eval.md` + `scripts/run_evals.py`) unless `--no-eval`
- [ ] Eval spec validates (`python3 scripts/run_evals.py --validate` → VALID)
- [ ] Agent-run spec emitted (`evals/caliper/<name>.eval.yaml`: happy path, edge case, silence probe) unless `--no-eval`
- [ ] At least one golden case marked `"split": "test"` (holdout — skipped by default, scored only with `--include-holdout`, never fed to an optimization loop)
- [ ] `install.sh` generated with cross-platform support
- [ ] `.claude-plugin/plugin.json` + `marketplace.json` generated (valid JSON, `name` fields match SKILL.md)
- [ ] Evolution toolkit shipped (`scripts/evolve.py` + staleness/drift/dep-health modules; `python3 scripts/evolve.py` exits 0)
- [ ] Eval spec has a `judge` block with a pinned model + known-bad canary when any criterion is `llm-judge`
- [ ] `interview.json` preserved and `structured_interview.py gate` exits 0 (`READY`)
- [ ] `README.md` written with multi-platform install instructions (including `/plugin marketplace add`)
- [ ] `requirements.txt` created (if third-party dependencies used)
- [ ] Spec validation passed (`scripts/validate.py`)
- [ ] Security scan passed (`scripts/security_scan.py`)
- [ ] Staleness check passed (`scripts/staleness_check.py`)
- [ ] Results reported to user

---

# Quality Standards Reminders

These standards apply across ALL phases and ALL generated files.

## Code Quality

**Every function must be:**
- Complete and functional (no stubs)
- Documented with docstrings (Args, Returns, Raises, Example)
- Type-hinted on all public interfaces
- Protected by error handling
- Validated on inputs and outputs

**Every script must have:**
- `#!/usr/bin/env python3` shebang
- Module-level docstring
- Organized imports (stdlib, third-party, local)
- Constants at top level
- `main()` function with argparse
- `if __name__ == "__main__"` guard

## Documentation Quality

**References must be:**
- Self-contained (not just links to external docs)
- Concrete (real values, executable examples)
- Load-bearing (carry knowledge the model could not supply on its own — length is not the measure)
- Well-structured (headings, lists, code blocks)

**SKILL.md must be:**
- Under 500 lines (cut what the model already knows first, then move detail to references)
- Frontmatter-compliant (name, description, license, metadata)
- Carrying a `## Gotchas` section (`None known` is valid; invented gotchas are not)
- Actionable (workflows with specific commands)

## Configuration Quality

**JSON configs must be:**
- Syntactically valid (always validate with `python -c "import json; ..."`)
- Populated with real values (real API URLs, real rate limits)
- Annotated with `_instructions` or `_note` fields for user-provided values
- Never contain hardcoded secrets

## Naming Quality

- Skill names: kebab-case, 1-64 chars, must end with `-skill`
- Python files: snake_case
- Classes: PascalCase
- Functions/methods: snake_case
- Constants: UPPER_SNAKE_CASE

## Anti-Patterns to Avoid

| Anti-Pattern | Correct Approach |
|---|---|
| `def analyze(): pass` | Complete implementation with real logic |
| `# TODO: implement` | Implement it now |
| `api_key: YOUR_KEY_HERE` | `api_key_env: "ENV_VAR_NAME"` with instructions |
| `See official docs at [link]` | Include the relevant information directly |
| SKILL.md over 500 lines | Cut what the model already knows, then move detail to `references/` |
| `Handle errors appropriately` / `Validate inputs` | Name the actual failure and the actual fix, or delete the line — the model already knows the generic advice |
| No `## Gotchas` section | Carry the Phase 1 quirks list and every correction made while verifying (`None known` if there genuinely are none) |
| Inventing gotchas to fill the section | Only real, observed behavior — a fabricated gotcha teaches a false constraint the agent will work around |
| Installing an imported skill unscanned | `--audit` it first; registry installs re-scan rather than trusting the cached verdict |
| `` `scripts/fetch.py` handles auth `` | **Run** `python3 scripts/fetch.py` — a bare path leaves the agent guessing whether to execute it or read it |
| `` `references/api-guide.md` has the endpoints `` | **Read** `references/api-guide.md` for the endpoints |
| marketplace.json as step 0 | SKILL.md is the primary file, created first |
| Name missing `-skill` suffix | End every skill name with `-skill`: `stock-analyzer-skill` |
| Description over 1024 chars | Trim to essential keywords within limit |
