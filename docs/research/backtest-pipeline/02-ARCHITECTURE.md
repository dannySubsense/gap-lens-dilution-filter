# Architecture: Backtest Pipeline

**Feature name:** backtest-pipeline
**Document version:** 1.0
**Date:** 2026-04-05
**Author:** @architect
**Hypotheses covered:** H1a, H1b, H1e, H1f, H1g

---

## 1. Overview

The backtest pipeline is a standalone, offline batch system that discovers all in-scope SEC dilution filings from 2017-2025, classifies them using the existing rule-based classifier extended with underwriter extraction, joins each filing against certified market data using strict point-in-time rules, and writes a labeled dataset for hypothesis testing.

The pipeline is isolated from the production application. It reads `market_data.duckdb` in read-only mode and writes to a dedicated research output file. The production DuckDB (`filter.duckdb`) is never touched.

---

## 2. System Context

```
EDGAR quarterly full-index (HTTPS, public)
    │
    ▼
[Discovery Stage]  →  raw_filings_cache/ (disk, idempotent)
    │
    ▼
[CIK Resolution]  →  market_data.duckdb (read-only) raw_symbols_massive + symbol_history
    │
    ▼
[Text Fetch Stage]  →  filing_text_cache/ (disk, idempotent)
    │
    ▼
[Classification Stage]  →  RuleBasedClassifier (rule-based-v1, no modifications)
    │
    ▼
[Underwriter Extraction Stage]  →  UnderwriterExtractor (new component, additive)
    │
    ▼
[Market Data Join Stage]  →  market_data.duckdb (read-only)
    │   daily_prices, daily_market_cap, daily_universe
    │   historical_float (AS-OF), short_interest (AS-OF)
    │
    ▼
[Filter Stage]  →  BacktestFilterEngine (adapted from FilterEngine, no live DB writes)
    │
    ▼
[Scoring Stage]  →  BacktestScorer (adapted from Scorer, no live DB writes)
    │
    ▼
[Outcome Stage]  →  OutcomeComputer (new component)
    │
    ▼
[Output Stage]  →  docs/research/data/backtest_results.parquet
                    docs/research/data/backtest_results.csv
                    docs/research/data/backtest_run_metadata.json
```

---

## 3. Components

| Component | Responsibility | Location |
|-----------|----------------|----------|
| `FilingDiscovery` | Downloads EDGAR quarterly master.gz files and filters to in-scope form types | `research/pipeline/discovery.py` |
| `CIKResolver` | Resolves CIK to ticker using market_data.duckdb; handles symbol_history date-range selection | `research/pipeline/cik_resolver.py` |
| `FilingTextFetcher` | Fetches filing HTML from SEC Archives with rate limiting and retry; caches to disk | `research/pipeline/fetcher.py` |
| `BacktestClassifier` | Thin wrapper: calls `RuleBasedClassifier.classify()` unchanged; extracts `_shares_offered_raw` | `research/pipeline/bt_classifier.py` |
| `UnderwriterExtractor` | Parses "Plan of Distribution" and ATM sections for named firms; normalizes against config table | `research/pipeline/underwriter_extractor.py` |
| `MarketDataJoiner` | Executes all point-in-time joins against market_data.duckdb; assembles `MarketSnapshot` | `research/pipeline/market_data_joiner.py` |
| `TradingCalendar` | Determines the most recent trading day on or before a given date | `research/pipeline/trading_calendar.py` |
| `BacktestFilterEngine` | Pure-function port of `FilterEngine`; takes `MarketSnapshot`; returns `FilterOutcome`; no DB writes | `research/pipeline/bt_filter_engine.py` |
| `BacktestScorer` | Pure-function port of `Scorer`; takes `ClassificationResult` + `MarketSnapshot`; returns `ScorerResult` | `research/pipeline/bt_scorer.py` |
| `OutcomeComputer` | Computes T+1, T+3, T+5, T+20 returns from `daily_prices`; handles delistings via NULL | `research/pipeline/outcome_computer.py` |
| `OutputWriter` | Assembles final rows, writes Parquet + CSV + metadata JSON; computes SHA-256 | `research/pipeline/output_writer.py` |
| `RunManifest` | Accumulates pipeline parameters and run statistics; written with output | `research/pipeline/run_manifest.py` |
| `PipelineOrchestrator` | Top-level runner; controls stage sequencing, resume logic, error accumulation | `research/run_backtest.py` |
| `underwriter_normalization.json` | Static config: canonical firm name → list of known variant strings | `research/config/underwriter_normalization.json` |

---

## 4. Directory Structure

```
research/
├── run_backtest.py                 # Entry point; CLI with --start-date, --end-date, --resume
├── config/
│   └── underwriter_normalization.json
├── pipeline/
│   ├── __init__.py
│   ├── discovery.py
│   ├── cik_resolver.py
│   ├── fetcher.py
│   ├── bt_classifier.py
│   ├── underwriter_extractor.py
│   ├── market_data_joiner.py
│   ├── trading_calendar.py
│   ├── bt_filter_engine.py
│   ├── bt_scorer.py
│   ├── outcome_computer.py
│   ├── output_writer.py
│   └── run_manifest.py
├── cache/
│   ├── master_gz/                  # Quarterly master.gz files (keyed by YYYY_QTRN.gz)
│   └── filing_text/                # Filing plain text (keyed by accession_number.txt)
└── tests/
    ├── test_discovery.py
    ├── test_cik_resolver.py
    ├── test_fetcher.py
    ├── test_underwriter_extractor.py
    ├── test_market_data_joiner.py
    ├── test_bt_filter_engine.py
    ├── test_bt_scorer.py
    ├── test_outcome_computer.py
    └── test_output_writer.py
docs/research/data/
├── backtest_results.parquet
├── backtest_results.csv
├── backtest_participants.parquet
├── backtest_participants.csv
└── backtest_run_metadata.json
```

---

## 5. Data Schemas

### 5.1 Internal: DiscoveredFiling

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class DiscoveredFiling:
    cik: str                    # Zero-padded to 10 digits as stored in master.gz
    entity_name: str
    form_type: str              # S-1, 424B4, 8-K, etc.
    date_filed: date            # From master.gz DateFiled column
    filename: str               # Relative path segment from master.gz
    accession_number: str       # Derived from filename: last 20 chars, dashes normalized
    quarter_key: str            # "2021_QTR2" — source quarter for resume tracking
```

### 5.2 Internal: ResolvedFiling

```python
@dataclass
class ResolvedFiling(DiscoveredFiling):
    ticker: str | None          # None means UNRESOLVABLE
    resolution_status: str      # "RESOLVED", "UNRESOLVABLE", "AMBIGUOUS_SKIPPED"
    permanent_id: str | None    # From symbol_history if resolution succeeded
```

### 5.3 Internal: FetchedFiling

```python
@dataclass
class FetchedFiling(ResolvedFiling):
    plain_text: str | None      # Stripped, truncated at filing_text_max_bytes
    fetch_status: str           # "OK", "FETCH_FAILED", "BINARY_CONTENT", "EMPTY_TEXT"
    fetch_error: str | None     # Error detail if fetch_status != "OK"
```

### 5.4 Internal: MarketSnapshot

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class MarketSnapshot:
    symbol: str
    effective_trade_date: date  # The prior-trading-day-adjusted date used for all T joins
    price_at_T: float | None
    market_cap_at_T: float | None
    float_at_T: float | None    # None if float unavailable (pre-2020 or no row found)
    float_available: bool
    float_effective_date: date | None    # Actual date of the AS-OF float row used
    short_interest_at_T: float | None
    short_interest_effective_date: date | None
    borrow_cost_source: str     # "SHORT_INTEREST", "DEFAULT"
    adv_at_T: float | None      # 20-day dollar volume ADV
    in_smallcap_universe: bool | None
    # Forward price rows for outcome computation
    # Key: N (1, 3, 5, 20), Value: adjusted_close or None
    forward_prices: dict[int, float | None]
    # Delistings flags
    delisted_before: dict[int, bool]    # Key: N (1, 3, 5, 20)
```

### 5.5 Internal: ParticipantRecord

```python
@dataclass
class ParticipantRecord:
    accession_number: str
    firm_name: str              # Canonical name after normalization
    role: str                   # "lead_underwriter", "co_manager", "sales_agent", "placement_agent"
    is_normalized: bool
    raw_text_snippet: str | None  # Up to 300 chars
```

### 5.6 Internal: BacktestRow

This is the in-memory representation of one row in the final output, assembled from all stages before writing:

```python
@dataclass
class BacktestRow:
    accession_number: str
    cik: str
    ticker: str | None
    entity_name: str | None
    form_type: str
    filed_at: datetime          # UTC timestamp; time component set to 00:00:00 if only date known
    setup_type: str | None
    confidence: float | None
    shares_offered_raw: int | None
    dilution_severity: float | None
    price_discount: float | None
    immediate_pressure: bool | None
    key_excerpt: str | None
    filter_status: str          # "PASSED", "FORM_TYPE_FAIL", "MARKET_CAP_FAIL", "FLOAT_FAIL", "DILUTION_FAIL", "PRICE_FAIL", "ADV_FAIL", "NOT_IN_UNIVERSE", "PIPELINE_ERROR", "UNRESOLVABLE", "FETCH_FAILED"
    filter_fail_reason: str | None
    float_available: bool
    in_smallcap_universe: bool | None
    price_at_T: float | None
    market_cap_at_T: float | None
    float_at_T: float | None
    adv_at_T: float | None
    short_interest_at_T: float | None
    borrow_cost_source: str | None
    score: int | None
    rank: str | None
    dilution_extractable: bool | None
    outcome_computable: bool
    return_1d: float | None
    return_3d: float | None
    return_5d: float | None
    return_20d: float | None
    delisted_before_T1: bool
    delisted_before_T3: bool
    delisted_before_T5: bool
    delisted_before_T20: bool
    pipeline_version: str
    processed_at: datetime
```

### 5.7 Output: RunMetadata (backtest_run_metadata.json)

```python
@dataclass
class RunMetadata:
    run_date: str                       # ISO 8601 UTC timestamp of pipeline run start
    pipeline_version: str               # e.g. "backtest-v1.0.0"
    classifier_version: str             # Always "rule-based-v1"
    scoring_formula_version: str        # e.g. "v1.0" — references the exact formula used
    date_range_start: str               # "2017-01-01"
    date_range_end: str                 # "2025-12-31"
    form_types: list[str]
    market_cap_threshold: int
    float_threshold: int
    dilution_pct_threshold: float
    price_threshold: float
    adv_threshold: float
    float_data_start: str               # Must be "2020-03-04" (FLOAT_DATA_START_DATE constant)
    market_data_db_path: str            # Absolute path to market_data.duckdb used
    market_data_db_certification: str   # e.g. "v1.0.0 (certified 2026-02-19)"
    total_filings_discovered: int
    total_cik_resolved: int
    total_fetch_ok: int
    total_classified: int
    total_passed_filters: int
    total_with_outcomes: int
    quarters_failed: list[str]          # Quarters where master.gz download failed
    parquet_sha256: str
    parquet_row_count: int
    execution_timestamp: str            # ISO 8601 UTC; same value as run_date
    canary_no_lookahead: str            # "PASS" or "FAIL" — result of Section 2.8 canary test
    total_unresolvable_count: int       # Count of filings where CIK not found in raw_symbols_massive
    normalization_config_loaded: bool   # True if underwriter_normalization.json was loaded and non-empty
    normalization_config_entry_count: int  # Number of normalization mappings loaded (0 if config missing)
```

---

## 6. Component Specifications

### 6.1 FilingDiscovery

**Input:** date range (start_date, end_date), target form_type set

**Output:** iterator of `DiscoveredFiling`

**Logic:**
1. Enumerate all (YYYY, QTR) combinations covering the date range.
2. For each quarter, attempt to download `https://www.sec.gov/Archives/edgar/full-index/{YYYY}/QTR{N}/master.gz`.
3. Cache the downloaded file at `research/cache/master_gz/{YYYY}_QTR{N}.gz`. If cache hit, skip download.
4. Decompress and parse the pipe-delimited format: `CIK|CompanyName|FormType|DateFiled|Filename`.
5. Filter rows: FormType must be in `{S-1, S-1/A, S-3, 424B2, 424B4, 8-K, 13D/A}` and DateFiled must be within the requested range.
6. Derive `accession_number` from the Filename field: take the basename, strip the `.txt` extension, replace hyphens with dashes to normalize.
7. On download failure (HTTP error or timeout): log the quarter to the run manifest as failed, skip it, continue.

**Rate limiting:** master.gz downloads are one file per quarter (36 total for 2017-2025); no rate limit needed. Use a 30-second timeout per download.

### 6.2 CIKResolver

**Input:** `DiscoveredFiling`

**Output:** `ResolvedFiling`

**Logic:**

This component executes against `market_data.duckdb` (read-only connection, separate from any production DB).

Step 1 — Primary lookup: join on `raw_symbols_massive.cik = filing.cik` (string comparison; CIK stored as VARCHAR in both).

Step 2 — Date-range disambiguation: if multiple tickers match the same CIK, filter by `symbol_history.start_date <= filing.date_filed AND (symbol_history.end_date >= filing.date_filed OR symbol_history.end_date IS NULL)`. If still multiple, prefer `raw_symbols_massive` rows where the data implies a common share class (type field not containing "WARRANT", "RIGHT", "UNIT"). If still ambiguous after this, log as `AMBIGUOUS_SKIPPED` and return `ticker=None`.

Step 3 — Fallback: if `raw_symbols_massive` yields no result, attempt lookup against `raw_symbols_fmp` by entity name fuzzy match (only if entity name is an exact-match string, to avoid false positives). Treat as last resort; do not use unless the CIK lookup produced zero rows.

Step 4 — UNRESOLVABLE: if no ticker found, set `resolution_status = "UNRESOLVABLE"`, `ticker = None`.

**SQL for Step 1-2 (parameterized):**
```sql
SELECT rsm.ticker, sh.permanent_id
FROM raw_symbols_massive rsm
JOIN symbol_history sh ON sh.symbol = rsm.ticker
WHERE rsm.cik = ?
  AND sh.start_date <= ?
  AND (sh.end_date >= ? OR sh.end_date IS NULL)
ORDER BY
    CASE WHEN rsm.active THEN 0 ELSE 1 END,
    sh.start_date ASC
LIMIT 5
```
If this returns exactly one row: resolved. If it returns multiple rows with different tickers, apply the share-class preference rule.

### 6.3 FilingTextFetcher

**Input:** `ResolvedFiling`

**Output:** `FetchedFiling`

**Logic:**
1. Skip fetch if `resolution_status != "RESOLVED"` (no ticker, no need to fetch).
2. Construct SEC Archives URL from the `filename` field:
   `https://www.sec.gov/Archives/edgar/{filename}` (filename already includes path segments).
3. Check disk cache at `research/cache/filing_text/{accession_number}.txt`. If hit, read from disk and skip HTTP.
4. Issue GET request with `User-Agent: gap-lens-dilution-filter contact@yourdomain.com` and `Accept: text/html, text/plain`.
5. On HTTP 404: set `fetch_status = "FETCH_FAILED"`, `fetch_error = "HTTP_404"`. Do not retry.
6. On HTTP 429 or 503: back off and retry up to 3 times (delays: 1s, 2s, 4s). After 3 failures: `fetch_status = "FETCH_FAILED"`.
7. Content-type check: if response Content-Type is `application/xml` or contains `xbrl` or body starts with `<?xml`: set `fetch_status = "FETCH_FAILED"`, `fetch_error = "BINARY_CONTENT"`.
8. Strip HTML to plain text using `_TextExtractor` logic (reuse `app/services/classifier/rule_based.py` text cleaning if present, otherwise BeautifulSoup with `get_text(separator=" ")`).
9. Truncate at `settings.filing_text_max_bytes` (512,000 bytes).
10. If plain text is empty after stripping: set `fetch_status = "EMPTY_TEXT"`, `plain_text = None`.
11. Write plain text to disk cache atomically (write to `.tmp` then rename).

**Rate limiting:** The global rate limiter enforces a maximum of 10 requests per second across all concurrent fetchers. Implementation: a `TokenBucketRateLimiter(rate=10, capacity=10)` shared singleton. The fetcher acquires one token before each HTTP call.

**Concurrency:** The fetch stage uses `asyncio.Semaphore(value=8)` to bound concurrent in-flight requests. With 8 concurrent fetchers at 10 req/s ceiling, wall-clock fetch time for ~200K filings is approximately 5-6 hours (dominated by network latency). This is acceptable for an offline batch run.

### 6.4 BacktestClassifier

**Input:** `FetchedFiling`

**Output:** `ClassificationResult` (from `app.services.classifier.protocol`)

**Logic:**
- Instantiate a single shared `RuleBasedClassifier` instance.
- If `fetch_status != "OK"` or `plain_text is None`: return a stub `ClassificationResult` with `setup_type="NULL"`, `confidence=0.0`, `reasoning` set to the fetch failure reason.
- Otherwise: call `await classifier.classify(filing.plain_text, filing.form_type)`.
- After receiving the result, apply the NULL sentinel mapping: if `result["setup_type"] == "NULL"`, set `backtest_row.setup_type = None`. This is required because `RuleBasedClassifier` uses the string `"NULL"` as a sentinel on no-match, while the output schema (`BacktestRow.setup_type: str | None`) requires a true Python `None`. Propagating the string `"NULL"` to Parquet would cause `WHERE setup_type IS NULL` queries to return zero rows.
- The classifier version tag `"rule-based-v1"` is written to the output via `pipeline_version`. No modifications to `RuleBasedClassifier` are permitted.

**Async calling convention:** `RuleBasedClassifier.classify()` is an async method. The classification stage must run inside a single shared async context — do not call `asyncio.run()` per filing, as that creates a new event loop per call and is prohibitively expensive at 200K+ iterations. The `PipelineOrchestrator` must enter an async context once for the entire classification batch (see Section 6.12).

**Reuse:** `app.services.classifier.rule_based.RuleBasedClassifier` is imported directly. The backtest pipeline adds it as a dependency; it does not copy or fork the code.

### 6.5 UnderwriterExtractor

**Input:** `FetchedFiling`, `ClassificationResult`

**Output:** `list[ParticipantRecord]`

**Logic:**

This is a new component. It runs after classification as an additive step that does not modify `setup_type` or any classifier output.

**Section isolation strategy:**
- For 424B4 and S-1: locate the "Plan of Distribution" section by scanning for the header pattern `(?i)plan\s+of\s+distribution`. Extract text from that header until the next all-caps section header (regex: `\n[A-Z][A-Z\s]{3,}\n`). Also scan the first 3,000 characters of plain text (cover page region).
- For 8-K: scan the full body. The equity distribution agreement is usually referenced within the first 5,000 characters.
- For 424B3: not in the Phase R1 discovery form_type set — this branch will never execute; 424B3 extraction is deferred to a future phase.
- For 424B2: scan cover page region (first 3,000 characters).
- For 13D/A: scan full body (best-effort only, as specified in requirements).
- For S-3: no extraction (form type does not typically name specific underwriters at registration stage; extraction is deferred to the 424B-series prospectus supplement).

**Extraction patterns (applied to the isolated text region):**

```python
LEAD_UW_PATTERNS = [
    r"(?:lead|sole|book-running)\s+(?:managing\s+)?underwriter[,\s]+([A-Z][^,\n]{3,60})",
    r"([A-Z][^,\n]{3,60})\s+is\s+(?:acting\s+as\s+)?(?:the\s+)?(?:sole\s+)?(?:book-running\s+)?managing\s+underwriter",
    r"([A-Z][^,\n]{3,60}),?\s+as\s+(?:the\s+)?(?:sole\s+)?(?:lead\s+)?(?:book-running\s+)?underwriter",
]

CO_MANAGER_PATTERNS = [
    r"co-(?:managers?|leads?)[:\s]+([A-Z][^\n]{3,120})",  # allows dots so "Oppenheimer & Co." is not truncated
    r"([A-Z][^,\n]{3,60}),?\s+as\s+co-manager",
]

SALES_AGENT_PATTERNS = [
    r"(?:sales\s+agent|placement\s+agent)[,\s]+([A-Z][^,\n]{3,60})",
    r"([A-Z][^,\n]{3,60}),?\s+as\s+(?:our\s+)?(?:sales|placement)\s+agent",
    r"equity\s+distribution\s+agreement\s+with\s+([A-Z][^,\n]{3,60})",
]
```

Multiple co-managers may appear in a comma-separated list after the co-manager header; split on commas and extract each as a separate `ParticipantRecord` with `role = "co_manager"`.

**Normalization:**
1. Load `research/config/underwriter_normalization.json` at startup as `dict[str, str]` (variant → canonical).
2. For each extracted raw name: strip trailing legal suffixes for lookup (`", LLC"`, `", Inc."`, `"& Co."` etc.) before table lookup.
3. If a match is found in the normalization table: set `firm_name = canonical`, `is_normalized = True`.
4. If no match: set `firm_name = raw_extracted_string`, `is_normalized = False`.
5. Store up to 300 chars of surrounding context as `raw_text_snippet`.

**Zero-result contract:** If no patterns match, return an empty list. This is not an error condition.

### 6.6 TradingCalendar

**Input:** a date (DATE type)

**Output:** the most recent trading day on or before that date

**Implementation:** Derive the trading calendar by querying `daily_prices` once at pipeline startup:

```sql
SELECT DISTINCT trade_date
FROM daily_prices
ORDER BY trade_date
```

Store as a sorted `list[date]` in memory (~2,200 dates for 2017-2025). Use binary search (`bisect.bisect_right`) to find the largest `trade_date <= requested_date`.

This approach is accurate because `daily_prices` already excludes weekends and US market holidays (no-weekend invariant confirmed in market_data audit). No external holiday calendar file is needed.

**HALT condition:** If the calendar contains zero dates, raise `RuntimeError("daily_prices is empty — cannot build trading calendar")` which propagates to an orchestrator-level HALT.

### 6.7 MarketDataJoiner

**Input:** `ResolvedFiling` (with ticker and date), `TradingCalendar`

**Output:** `MarketSnapshot`

**Database connection:** A single `duckdb.connect(market_data_db_path, read_only=True)` connection opened once for the pipeline run. DuckDB read-only connections are thread-safe for concurrent reads.

**All joins use `effective_trade_date = TradingCalendar.prior_or_equal(filing.date_filed)`.**

**Price at T (daily_prices):**
```sql
SELECT adjusted_close
FROM daily_prices
WHERE symbol = ? AND trade_date = ?
```
Returns `None` if no row (symbol not trading on that date after calendar adjustment).

**Market cap at T (daily_market_cap):**
```sql
SELECT market_cap
FROM daily_market_cap
WHERE symbol = ? AND trade_date = ?
```

**ADV at T (20-day dollar-volume average):**
```sql
SELECT AVG(close * volume) AS adv
FROM daily_prices
WHERE symbol = ?
  AND trade_date <= ?
  AND trade_date >= (
      SELECT trade_date FROM daily_prices
      WHERE symbol = ? AND trade_date <= ?
      ORDER BY trade_date DESC
      LIMIT 1 OFFSET 19
  )
```
This selects the 20 most recent trading days up to and including T, then averages `close * volume`. The `close` column is the raw (unadjusted) closing price, not `adjusted_close`. Using raw close is correct for ADV because it reflects the actual dollar volume traded; using `adjusted_close` would distort ADV when stock splits occur. If `daily_prices` does not store a separate raw close column and only has `adjusted_close`, split effects on ADV are accepted as a known approximation and must be documented in the run metadata. Returns `None` if fewer than 20 rows available.

**Universe check (daily_universe):**
```sql
SELECT in_smallcap_universe
FROM daily_universe
WHERE symbol = ? AND trade_date = ?
```
If no row: `in_smallcap_universe = None` (treated as NOT_IN_UNIVERSE in the filter stage).

**Float AS-OF join (historical_float) — point-in-time:**
```sql
SELECT float_shares, trade_date AS float_effective_date
FROM historical_float
WHERE symbol = ?
  AND trade_date <= ?
ORDER BY trade_date DESC
LIMIT 1
```
- If `filing.date_filed < 2020-03-04`: skip this query entirely. Set `float_at_T = None`, `float_available = False`.
- If query returns no row for a post-2020 filing: set `float_at_T = None`, `float_available = True` (data should exist; absence is a data gap, not a pre-2020 flag).

**Short interest AS-OF join (short_interest) — point-in-time:**
```sql
SELECT short_position, settlement_date AS si_effective_date
FROM short_interest
WHERE symbol = ?
  AND settlement_date <= ?
ORDER BY settlement_date DESC
LIMIT 1
```
- `short_interest` covers 2021+. For pre-2021 filings: query will return no rows; set `short_interest_at_T = None`.
- `borrow_cost_source`: if `short_interest_at_T` is not None, set to `"SHORT_INTEREST"`; otherwise `"DEFAULT"`.

**Forward price rows for outcome computation:**
```sql
SELECT trade_date, adjusted_close
FROM (
    SELECT trade_date, adjusted_close,
           ROW_NUMBER() OVER (ORDER BY trade_date) AS rn
    FROM daily_prices
    WHERE symbol = ? AND trade_date > ?
)
WHERE rn IN (1, 3, 5, 20)
```
Returns up to 4 rows. Missing rows (symbol delisted before that horizon) are `None`. The `delisted_before` flags are derived: if fewer than N rows exist for symbol after T, the symbol was delisted before T+N.

### 6.8 BacktestFilterEngine

**Input:** `ResolvedFiling`, `ClassificationResult`, `MarketSnapshot`

**Output:** `FilterOutcome` (from `app.services.filter_engine`)

**Design:** Pure function — no async, no DB writes. This is a port of `FilterEngine.evaluate()` with all DuckDB write calls removed. Accepts pre-fetched `MarketSnapshot` data instead of `FMPMarketData`.

**Filter mapping:**

| Filter | Criterion | MarketSnapshot field |
|--------|-----------|----------------------|
| 1 | form_type in ALLOWED_FORM_TYPES AND keyword in text | `filing.form_type`, `filing.plain_text` |
| 2 | market_cap < 2,000,000,000 | `snapshot.market_cap_at_T` |
| 3 | float < 50,000,000 (skip if `float_available=False`) | `snapshot.float_at_T`, `snapshot.float_available` |
| 4 | dilution_pct > 0.10 | `classification._shares_offered_raw / snapshot.float_at_T` |
| 5 | price > 1.00 | `snapshot.price_at_T` |
| 6 | adv > 500,000 | `snapshot.adv_at_T` |

**Float skip rule:** For filings where `snapshot.float_available = False`, Filter 3 is skipped (not failed). Filter 4 is also skipped (cannot compute dilution without float). The `filter_fail_reason` for these filings must be `"FLOAT_NOT_AVAILABLE"` only if they would fail exclusively due to lack of float data; if they fail an earlier filter, that filter's reason takes precedence.

**Universe check:** Before Filter 1, check `snapshot.in_smallcap_universe`. If `False` or `None`: return `FilterOutcome(passed=False, fail_criterion="NOT_IN_UNIVERSE")`. This maps to `filter_status = "NOT_IN_UNIVERSE"` in the output row (which is a sub-case of `FILTERED_OUT`).

**Dilution severity computation:** `dilution_severity = shares_offered_raw / float_at_T`. This is the value stored in `BacktestRow.dilution_severity` and passed to the scorer. If `float_at_T` is None or zero, `dilution_severity = None` and `dilution_extractable = False`.

**`shares_offered_raw` source:** Use `classification["_shares_offered_raw"]` (transient field on `ClassificationResult`). If zero: `dilution_extractable = False`.

**ALLOWED_FORM_TYPES and OFFERING_KEYWORDS:** Import directly from `app.services.filter_engine` — do not duplicate constants.

### 6.9 BacktestScorer

**Input:** `ClassificationResult`, `MarketSnapshot`

**Output:** `ScorerResult` (from `app.services.scorer`)

**Design:** Adapter that calls `Scorer.score()` by constructing a compatible `FMPMarketData`-like object from `MarketSnapshot`. Specifically:

```python
@dataclass
class BacktestMarketData:
    """Adapter: satisfies Scorer's FMPMarketData interface using MarketSnapshot fields."""
    adv_dollar: float
    float_shares: float
    price: float
    market_cap: float
```

The `Scorer.score()` static method is imported directly and called with this adapter. This avoids any modification of `Scorer`.

**Dilution severity patching (mirrors live pipeline "step 7.5"):** `RuleBasedClassifier` always returns `dilution_severity=0.0` (the field is a placeholder; see `rule_based.py` line 108). The live pipeline has a "step 7.5" that patches the computed dilution_severity into the `ClassificationResult` before calling `Scorer.score()`. The backtest must replicate this step. Before calling `Scorer.score()`, create a patched copy of the `ClassificationResult` dict:

```python
patched_classification = dict(classification)
patched_classification["dilution_severity"] = (
    backtest_row.dilution_severity  # computed by BacktestFilterEngine as shares_offered_raw / float_at_T
    if backtest_row.dilution_severity is not None
    else 0.0  # matches live pipeline fallback when float is unavailable
)
```

Without this step, every filing scores 0 because `dilution_severity=0.0` produces `raw_score=0` regardless of other factors.

**`setup_type` check:** Before calling `Scorer.score()`, check that `patched_classification["setup_type"]` is not `None`. If `setup_type` is `None` (i.e., the no-match sentinel was already mapped to `None` per Section 6.4), do not call the scorer — set `score = None`, `rank = None`. Note: the scorer internally guards against the string `"NULL"`, but the backtest pipeline stores `None` (not `"NULL"`) as the sentinel, so this guard must check for `None`.

**`float_illiquidity` input:** `Scorer.score()` computes `float_illiquidity = settings.adv_min_threshold / fmp_data.adv_dollar` internally. The `BacktestMarketData` adapter must supply `adv_dollar = snapshot.adv_at_T` (not `snapshot.float_at_T`). If `snapshot.adv_at_T` is None or zero, do not call the scorer — set `score = None`, `rank = None`. Note: despite its name, `float_illiquidity` is an ADV-based ratio (`adv_min_threshold / adv_dollar`); float data does not enter this computation.

**Borrow cost:** Always pass `borrow_cost=0.0` to `Scorer.score()`. This matches the live pipeline exactly — IBKR is disabled (`ibkr_borrow_cost_enabled = False` in `config.py`) and the live pipeline always passes `borrow_cost=0.0`, which causes `Scorer.score()` to substitute `settings.default_borrow_cost = 0.30`. Using any other proxy formula (such as `short_interest_at_T / float_at_T`) would produce scores incomparable to the live pipeline. Short interest data is preserved in `BacktestRow.short_interest_at_T` for Phase R4 borrow cost sensitivity analysis but is not used in Phase R1 scoring.

**Two-tier flag:** `BacktestScorer` does not alter scoring behavior for the 2017-2019 tier. The `float_available` flag in the output row is the signal to downstream analysis that those rows should be excluded from H1a full-fidelity analysis. The scorer runs normally; if `float_at_T` is None, `dilution_severity` will be 0.0 (live fallback) and the score will reflect only `setup_quality` and the ADV floor.

### 6.10 OutcomeComputer

**Input:** `BacktestRow` (partially populated, with `price_at_T` and `MarketSnapshot.forward_prices`)

**Output:** Updated `BacktestRow` with return fields populated

**Logic:**
1. If `price_at_T` is None or `price_at_T == 0.0`: set `outcome_computable = False`, all return fields and delisted flags remain at defaults.
2. For each horizon N in [1, 3, 5, 20]:
   - If `forward_prices[N]` is None: `return_N = None`, `delisted_before_TN = True`.
   - Otherwise: `return_N = (forward_prices[N] / price_at_T) - 1.0`, `delisted_before_TN = False`.
3. `outcome_computable = True` if `price_at_T` is valid (even if all returns end up NULL due to delisting).

**Horizon counting:** The `forward_prices` dictionary is pre-populated by `MarketDataJoiner` using row-number ordering on `daily_prices` for the symbol. "T+1" means the first row in `daily_prices` for that symbol with `trade_date > effective_trade_date`. This is strictly trading-day counting, not calendar-day counting.

### 6.11 OutputWriter

**Input:** `list[BacktestRow]`, `list[ParticipantRecord]`, `RunMetadata`

**Output:** Five files:
- `docs/research/data/backtest_results.parquet`
- `docs/research/data/backtest_results.csv`
- `docs/research/data/backtest_participants.parquet`
- `docs/research/data/backtest_participants.csv`
- `docs/research/data/backtest_run_metadata.json`

**Parquet column ordering and types:** Match the output schema tables in `01-REQUIREMENTS.md` exactly. Use `pyarrow` for schema enforcement and `pandas` for DataFrame construction.

**Determinism:** Sort the results DataFrame by `(cik, filed_at, accession_number)` before writing. Sort the participants DataFrame by `(accession_number, firm_name, role)`. Use fixed Parquet row group size (128MB). Do not use Parquet compression with non-deterministic codecs; use `snappy` (deterministic) or `none`.

**CSV:** Write with `index=False`, `encoding="utf-8"`, Unix line endings.

**Metadata JSON:** Compute SHA-256 of the results Parquet file after writing using `hashlib.sha256`. Write metadata with `json.dumps(indent=2)`.

### 6.12 PipelineOrchestrator (run_backtest.py)

**Entry point signature:**
```
python research/run_backtest.py \
    [--start-date YYYY-MM-DD] \
    [--end-date YYYY-MM-DD] \
    [--resume] \
    [--dry-run N]      # process first N filings then stop
```

**Startup checks:**
1. Verify `market_data.duckdb` exists and is readable.
2. Execute `SELECT COUNT(*) FROM daily_universe` — if result is 0, HALT with error message: "daily_universe is empty. Cannot run backtest. Populate market_data.duckdb first."
3. Execute `SELECT COUNT(*) FROM daily_prices` — if result is 0, HALT.
4. Build `TradingCalendar` from `daily_prices`.
5. Load normalization config from `research/config/underwriter_normalization.json`.

**Stage sequencing:** The pipeline runs in a single linear pass over all discovered filings. There is no intermediate persistence to a staging database — all state is accumulated in memory as `BacktestRow` objects and written at the end. For a full 2017-2025 run expected to produce ~200K-500K rows (most will be FILTERED_OUT or NO_MATCH), memory usage is manageable (approximately 1-2GB for the full row list).

**Async context for classification:** `RuleBasedClassifier.classify()` is async. The classification batch must execute inside a single `asyncio.run()` call, not one per filing. The recommended pattern is:

```python
async def _classify_batch(filings):
    results = []
    for filing in filings:
        result = await classifier.classify(filing.plain_text, filing.form_type)
        results.append(result)
    return results

classified = asyncio.run(_classify_batch(fetched_filings))
```

This enters the event loop once for the entire batch. Creating a new event loop per filing via per-call `asyncio.run()` is prohibited — it is prohibitively expensive at 200K+ iterations.

**Resume logic:**
- Discovery cache and fetch cache are on disk.
- If `--resume` is passed: FilingDiscovery skips downloading master.gz files already in cache; FilingTextFetcher skips fetching texts already in cache.
- The in-memory row accumulation does not resume — the full classification, join, filter, score, outcome pass always re-runs from the cache. This is acceptable because those stages are CPU-bound (no I/O) and fast.

**Error handling per filing:** Each filing is processed in a try/except wrapper. Unexpected exceptions per filing are logged with the accession_number and set `filter_status = "PIPELINE_ERROR"`. The pipeline never aborts due to a single filing error.

---

## 7. Look-Ahead Bias Controls

This section explicitly states each point-in-time rule and which component enforces it.

| Data | Anti-look-ahead rule | Component responsible |
|------|----------------------|-----------------------|
| Price at T | `trade_date = TradingCalendar.prior_or_equal(filing.date_filed)` | MarketDataJoiner |
| Market cap at T | Same as price | MarketDataJoiner |
| ADV at T | 20-day window ending at T inclusive | MarketDataJoiner |
| Universe membership | `daily_universe.trade_date = effective_trade_date` (the same adjusted T date) | MarketDataJoiner |
| Float at T | `MAX(trade_date) WHERE trade_date <= filing.date_filed` (AS-OF join) | MarketDataJoiner |
| Short interest at T | `MAX(settlement_date) WHERE settlement_date <= filing.date_filed` (AS-OF join) | MarketDataJoiner |
| Outcome returns T+1..T+20 | Row-number forward in daily_prices; not used in filter or scoring decision | OutcomeComputer |
| Underwriter normalization table | Static config, fixed at pipeline build time; no future data | UnderwriterExtractor |

**Critical invariant:** The `effective_trade_date` (prior-trading-day-adjusted filing date) is computed once by `TradingCalendar` and passed consistently to all join operations in `MarketDataJoiner`. It is never re-derived per join.

---

## 8. Survivorship Bias Controls

| Rule | Implementation |
|------|----------------|
| Include filings for subsequently-delisted symbols | Inclusion is gated on `daily_universe.in_smallcap_universe` at the filing date, not at run time. Symbols delisted after the filing date are included if in-universe on the filing date. |
| Do not filter to currently-active symbols | `CIKResolver` queries `raw_symbols_massive` (which contains both active and inactive symbols via the `active` column) and `symbol_history` (which covers symbol lifecycle 2006-2025 regardless of current active status). |
| NULL returns for delisted symbols | `OutcomeComputer` writes `return_N = None` and `delisted_before_TN = True` when `daily_prices` has no row at the forward horizon. This does NOT exclude the filing — it remains in the output with NULL outcome fields. |

---

## 9. Two-Tier Coverage Design

| Tier | Date range | Float | Scoring | Filter 3 | dilution_severity component |
|------|------------|-------|---------|----------|-----------------------------|
| Full fidelity | 2020-03-04 to 2025-12-31 | Available | Complete formula | Applied | Computed as `shares_offered / float_at_T` |
| Partial fidelity | 2017-01-01 to 2020-03-03 | Not available | Partial (`dilution_severity=0.0` because float unavailable; `setup_quality` and ADV floor apply) | Skipped | Cannot be computed; falls back to 0.0 |

**Output flag:** `float_available` column in `backtest_results` is `False` for all filings with `filed_at < 2020-03-04`. Finding documents testing H1a must include a filter: `WHERE float_available = True`.

**Partial fidelity rationale:** For 2017-2019 filings, `float_at_T` is unavailable (historical_float data begins 2020-03-04). As a result, `dilution_severity` cannot be computed (`shares_offered / float_at_T` requires float). The `float_illiquidity` term in the scoring formula is unaffected — it is computed as `adv_min_threshold / adv_dollar` (an ADV ratio) and does not depend on float data.

**Implementation in `MarketDataJoiner`:** The float-cutoff date `2020-03-04` is a named constant `FLOAT_DATA_START_DATE = date(2020, 3, 4)` in `research/pipeline/market_data_joiner.py`. The AS-OF float query is only executed when `filing.date_filed >= FLOAT_DATA_START_DATE`.

---

## 10. Isolation from Production System

| Constraint | Implementation |
|------------|----------------|
| No writes to filter.duckdb | The pipeline never imports `app.services.db` or `get_db()`. The production DuckDB is not opened. |
| Read-only market_data.duckdb | `duckdb.connect(path, read_only=True)` is used exclusively. |
| Separate output path | All output written to `docs/research/data/`, never to `data/` (production path). |
| No FMP API calls | Market data is read from the certified DuckDB; no live API calls during the backtest. |
| Settings isolation | Backtest configuration is in `research/pipeline/config.py` (a simple dataclass with hardcoded defaults). `app.core.config.Settings` is imported only to read `default_borrow_cost`, `score_normalization_ceiling`, and `setup_quality` values for scorer compatibility. |

---

## 11. Reuse vs. Extension of Existing Components

| Existing component | Reuse approach |
|--------------------|----------------|
| `app.services.classifier.rule_based.RuleBasedClassifier` | Imported directly, called unchanged. No fork or copy. |
| `app.services.classifier.protocol.ClassificationResult` | Imported directly as the shared type contract. |
| `app.services.scorer.Scorer` | Imported directly, called via `BacktestScorer` adapter. |
| `app.services.filter_engine.ALLOWED_FORM_TYPES`, `OFFERING_KEYWORDS` | Constants imported directly. |
| `app.services.filter_engine.FilterEngine` | NOT reused. `BacktestFilterEngine` is a pure-function port that removes all async DB write calls. |
| `app.core.config.settings` | Three fields imported: `default_borrow_cost`, `score_normalization_ceiling`, `setup_quality`. |
| `app.utils.ticker_resolver.TickerResolver` | NOT reused. `CIKResolver` is a new component using `market_data.duckdb` directly (which has `raw_symbols_massive` with CIK data). The production `TickerResolver` uses `filter.duckdb`'s `cik_ticker_map`. |

---

## 12. Reproducibility Design

All parameters affecting output are recorded in `RunMetadata` and embedded in `backtest_run_metadata.json`. The following determinism invariants are enforced:

1. **Filing discovery order:** Master.gz files are processed in chronological quarter order. Within each quarter, filings are processed in the order they appear in master.gz (no sorting by the pipeline).
2. **Output sort:** The final DataFrame is sorted by `(cik, filed_at, accession_number)` before writing. This makes the row order deterministic even if processing order varies with resume.
3. **Parquet metadata:** Row group size is fixed at 128MB. Schema is declared explicitly via `pyarrow.schema(...)` before writing — no inference.
4. **No timestamps in data rows:** `processed_at` is set to the pipeline run start time (a single constant for all rows in one run), not per-row wall clock. This prevents per-row timestamp drift from breaking determinism.
5. **Float tie-breaking:** If `historical_float` has multiple rows for `(symbol, date)`, the AS-OF query uses `ORDER BY trade_date DESC LIMIT 1`, which will consistently pick the same row since `(symbol, trade_date)` is the primary key (unique). No tie possible.

---

## 13. Error Handling and Partial Failure

| Failure mode | Handling |
|--------------|----------|
| quarterly master.gz download fails | Log to `RunMetadata.quarters_failed`; continue with remaining quarters |
| Filing fetch returns HTTP 429 after 3 retries | `fetch_status = "FETCH_FAILED"`, row written to output with that status |
| Filing fetch returns HTTP 404 | `fetch_status = "FETCH_FAILED"`, reason `"HTTP_404"`, no retry |
| CIK not in raw_symbols_massive | `resolution_status = "UNRESOLVABLE"`, `ticker = None`, `filter_status = "UNRESOLVABLE"` |
| Symbol not in daily_universe on filing date | `filter_fail_reason = "NOT_IN_UNIVERSE"`, `filter_status = "NOT_IN_UNIVERSE"` |
| price_at_T is None | `outcome_computable = False`; row still written with classification and filter data |
| Unexpected Python exception per filing | Caught, logged with accession_number; `filter_status = "PIPELINE_ERROR"`; pipeline continues |
| market_data.duckdb not found at startup | HALT immediately with clear error message before any processing starts |
| daily_universe is empty | HALT immediately (per requirements constraint) |
| KeyboardInterrupt mid-run | Disk caches are intact; re-run with `--resume` to reuse cached downloads |

---

## 14. Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `duckdb` | `>=0.10.0` | Read market_data.duckdb; already in project |
| `pyarrow` | `>=14.0.0` | Write Parquet output with explicit schema |
| `pandas` | `>=2.0.0` | DataFrame construction for output writing |
| `httpx` | `>=0.27.0` | HTTP client for SEC Archives fetches; already in project |
| `beautifulsoup4` | `>=4.12.0` | HTML stripping for filing text; already used in project |
| `lxml` | `>=4.9.0` | Fast HTML parser backend for BeautifulSoup |

No new non-standard dependencies are introduced. All libraries are already in the project or are standard for this stack.

---

## 15. Integration Points

| Existing system | Integration point |
|-----------------|-------------------|
| `app/services/classifier/rule_based.py` | Imported by `BacktestClassifier`; no modification permitted |
| `app/services/scorer.py` | Imported by `BacktestScorer`; called via adapter |
| `app/services/filter_engine.py` | Constants `ALLOWED_FORM_TYPES`, `OFFERING_KEYWORDS` imported; `FilterEngine` class not used |
| `app/core/config.py` | Three config values read; no new settings added to `Settings` class |
| `market_data.duckdb` at `/home/d-tuned/market_data/duckdb/market_data.duckdb` | Read-only DuckDB connection; tables: `daily_prices`, `daily_market_cap`, `daily_universe`, `historical_float`, `short_interest`, `raw_symbols_massive`, `symbol_history` |

---

## 16. Open Questions Resolved

| # | Resolution |
|---|-----------|
| OQ-1 | historical_float schema confirmed: `(symbol VARCHAR, trade_date DATE, float_shares DOUBLE, outstanding_shares DOUBLE, free_float_pct DOUBLE, source_url VARCHAR, pipeline_version VARCHAR, created_at TIMESTAMP)`. short_interest schema confirmed: `(symbol VARCHAR, settlement_date DATE, short_position DOUBLE, prev_short_position DOUBLE, avg_daily_volume DOUBLE, days_to_cover DOUBLE, revision_flag VARCHAR, pipeline_version VARCHAR, created_at TIMESTAMP)`. Both tables are in market_data.duckdb. |
| OQ-2 | Read-only connection confirmed: `duckdb.connect(path, read_only=True)`. No copy needed. |
| OQ-3 | Estimated wall-clock runtime: fetch phase ~5-6 hours (network-bound, 8 concurrent fetchers at 10 req/s ceiling); classification + join + scoring phase ~1-2 hours (CPU-bound, single-threaded DuckDB reads). Total: approximately 7-8 hours for a full 2017-2025 first run. Subsequent runs with cache: ~1-2 hours (classify + join only). No parallelism required beyond the fetch concurrency already specified. |
| OQ-4 | Normalization table provided as static config file by researcher before pipeline build. `UnderwriterExtractor` fails gracefully if file is missing (logs warning, stores all names as `is_normalized=False`). |

---

## 17. Patterns and Rationale

| Pattern | Usage | Rationale |
|---------|-------|-----------|
| Disk cache for idempotency | master.gz and filing text caches | Allows pipeline resume after interruption without re-hitting SEC rate limits; SEC explicitly allows caching of public filings |
| Pure-function ports for existing services | `BacktestFilterEngine`, `BacktestScorer` | Preserves production code integrity (no modifications); makes backtest components independently testable |
| AS-OF join in SQL (ORDER BY date DESC LIMIT 1) | Float and short interest joins | Simple, correct, and performant for DuckDB; avoids complex window function or subquery approaches; maintains point-in-time correctness |
| Trading calendar derived from daily_prices | `TradingCalendar` | Certified dataset already excludes weekends/holidays; no external calendar dependency; one source of truth |
| Single read-only DuckDB connection | MarketDataJoiner | DuckDB read-only mode is safe for concurrent reads; single connection avoids connection pool complexity |
| In-memory row accumulation | PipelineOrchestrator | Simplifies output determinism (sort once at end); feasible given estimated row count (~200K-500K rows, ~2GB RAM max) |
| Token bucket rate limiter for SEC fetches | FilingTextFetcher | SEC published limit is 10 req/s; token bucket is the standard pattern for burst-safe rate limiting |
| Additive underwriter extraction (after classification) | UnderwriterExtractor | Keeps classifier untouched (required by constraints); separates concerns cleanly |

---

## 18. Anti-Patterns Rejected

| Anti-pattern | Reason rejected |
|--------------|----------------|
| Modifying RuleBasedClassifier to add underwriter extraction inline | Violates requirements constraint: "no modifications to the core classification logic are permitted" |
| Using filter.duckdb for intermediate backtest state | Violates isolation constraint; would mix research and production data |
| Using AskEdgar API for historical discovery | Explicitly out of scope per requirements; EDGAR quarterly master.gz is required |
| Imputing or estimating float pre-2020 | Explicitly prohibited by requirements: "must never be imputed or estimated" |
| Deduplicating overlapping filing windows | Explicitly prohibited by requirements (AC-08 last bullet) |
| Writing to market_data.duckdb | Violates read-only constraint on certified dataset |
