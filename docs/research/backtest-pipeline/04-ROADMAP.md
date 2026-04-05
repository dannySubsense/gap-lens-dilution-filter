# Roadmap: Backtest Pipeline

**Feature name:** backtest-pipeline
**Document version:** 1.0
**Date:** 2026-04-05
**Author:** @planner
**Hypotheses covered:** H1a, H1b, H1e, H1f, H1g

---

## Important: Script Location

All pipeline scripts, components, tests, and caches live under `research/` at the project root — not under `app/`. Output data files live under `docs/research/data/`. No production app code is modified at any point.

---

## Dependency Map

| Component | Depends On |
|-----------|------------|
| `research/pipeline/trading_calendar.py` | `market_data.duckdb` (read-only) |
| `research/pipeline/discovery.py` | nothing (pure HTTP + disk) |
| `research/pipeline/cik_resolver.py` | `market_data.duckdb` (read-only) |
| `research/pipeline/fetcher.py` | nothing (pure HTTP + disk) |
| `research/pipeline/bt_classifier.py` | `app.services.classifier.rule_based`, `app.services.classifier.protocol` |
| `research/pipeline/underwriter_extractor.py` | `research/config/underwriter_normalization.json` |
| `research/pipeline/market_data_joiner.py` | `trading_calendar.py`, `market_data.duckdb` (read-only) |
| `research/pipeline/bt_filter_engine.py` | `app.services.filter_engine` (constants only), `MarketSnapshot` (from market_data_joiner) |
| `research/pipeline/bt_scorer.py` | `app.services.scorer`, `MarketSnapshot` (from market_data_joiner) |
| `research/pipeline/outcome_computer.py` | `MarketSnapshot` (from market_data_joiner) |
| `research/pipeline/output_writer.py` | `BacktestRow`, `ParticipantRecord`, `RunMetadata` dataclasses |
| `research/pipeline/run_manifest.py` | nothing (pure dataclass) |
| `research/run_backtest.py` | all pipeline components above |
| Research Contract validation | all pipeline components + `research/run_backtest.py` |

---

## Slice Overview

| Slice | Name | Depends On | New Files |
|-------|------|------------|-----------|
| 1 | Directory Scaffold and Shared Dataclasses | — | `research/pipeline/__init__.py`, `research/pipeline/dataclasses.py`, `research/pipeline/config.py`, `research/config/underwriter_normalization.json` |
| 2 | TradingCalendar | Slice 1 | `research/pipeline/trading_calendar.py`, `research/tests/test_trading_calendar.py` |
| 3 | FilingDiscovery | Slice 1 | `research/pipeline/discovery.py`, `research/tests/test_discovery.py` |
| 4 | CIKResolver | Slice 1, 2 | `research/pipeline/cik_resolver.py`, `research/tests/test_cik_resolver.py` |
| 5 | FilingTextFetcher | Slice 1 | `research/pipeline/fetcher.py`, `research/tests/test_fetcher.py` |
| 6 | BacktestClassifier | Slice 1, 5 | `research/pipeline/bt_classifier.py`, `research/tests/test_bt_classifier.py` |
| 7 | UnderwriterExtractor | Slice 1 | `research/pipeline/underwriter_extractor.py`, `research/tests/test_underwriter_extractor.py` |
| 8 | MarketDataJoiner | Slice 1, 2 | `research/pipeline/market_data_joiner.py`, `research/tests/test_market_data_joiner.py` |
| 9 | BacktestFilterEngine | Slice 1, 8 | `research/pipeline/bt_filter_engine.py`, `research/tests/test_bt_filter_engine.py` |
| 10 | BacktestScorer | Slice 1, 8 | `research/pipeline/bt_scorer.py`, `research/tests/test_bt_scorer.py` |
| 11 | OutcomeComputer | Slice 1, 8 | `research/pipeline/outcome_computer.py`, `research/tests/test_outcome_computer.py` |
| 12 | OutputWriter and RunManifest | Slice 1 | `research/pipeline/output_writer.py`, `research/pipeline/run_manifest.py`, `research/tests/test_output_writer.py` |
| 13 | PipelineOrchestrator | Slices 1–12 | `research/run_backtest.py` |
| 14 | Research Contract Validation | Slice 13 | `research/tests/test_research_contract.py` |

---

## Detailed Slices

---

### Slice 1: Directory Scaffold and Shared Dataclasses

**Goal:** Create the `research/` directory tree, all shared dataclass types, and the static underwriter normalization config so every subsequent slice has a stable foundation to import from.

**Depends On:** —

**Files:**
- `research/__init__.py` — create (empty)
- `research/pipeline/__init__.py` — create (empty)
- `research/tests/__init__.py` — create (empty)
- `research/config/underwriter_normalization.json` — create (seed with empty object `{}` as a valid placeholder; researcher populates before full run)
- `research/cache/.gitkeep` — create (so git tracks the directory)
- `research/cache/master_gz/.gitkeep` — create
- `research/cache/filing_text/.gitkeep` — create
- `docs/research/data/.gitkeep` — create (if directory does not already exist)
- `research/pipeline/dataclasses.py` — create; contains: `DiscoveredFiling`, `ResolvedFiling`, `FetchedFiling`, `MarketSnapshot`, `ParticipantRecord`, `BacktestRow`, `BacktestMarketData`, `FilterOutcome` (stub), `ScorerResult` (stub)
- `research/pipeline/config.py` — create; contains: `BacktestConfig` dataclass with hardcoded defaults (`FLOAT_DATA_START_DATE = date(2020, 3, 4)`, `MARKET_DATA_DB_PATH`, `PIPELINE_VERSION`, filter thresholds, `filing_text_max_bytes = 512_000`)

**Implementation Notes:**
- `dataclasses.py` is the single source of truth for all inter-component data contracts in the research pipeline. No component defines its own ad-hoc dicts.
- `MarketSnapshot.forward_prices` is `dict[int, float | None]` with keys 1, 3, 5, 20.
- `MarketSnapshot.delisted_before` is `dict[int, bool]` with keys 1, 3, 5, 20.
- `BacktestConfig` imports `app.core.config.settings` to read `default_borrow_cost`, `score_normalization_ceiling`, and `setup_quality` — these three fields only.
- The `research/` directory must NOT contain any `app/` production code; it only imports from `app/`.

**Tests:**
- `research/tests/test_dataclasses.py` — create
- [ ] Instantiate each dataclass with valid field values; assert no `TypeError`
- [ ] Assert `MarketSnapshot.forward_prices` accepts `{1: None, 3: 0.95, 5: None, 20: 0.80}`
- [ ] Assert `BacktestConfig` loads without error and `FLOAT_DATA_START_DATE` equals `date(2020, 3, 4)`

**Done When:**
- [ ] `research/` directory tree matches the structure in `02-ARCHITECTURE.md` Section 4
- [ ] `from research.pipeline.dataclasses import MarketSnapshot` succeeds in a Python shell from the project root
- [ ] `from research.pipeline.config import BacktestConfig` succeeds
- [ ] All slice tests pass

---

### Slice 2: TradingCalendar

**Goal:** Implement `TradingCalendar` — a component that derives all trading days from `daily_prices` and resolves any date to the most recent trading day on or before it.

**Depends On:** Slice 1

**Files:**
- `research/pipeline/trading_calendar.py` — create
- `research/tests/test_trading_calendar.py` — create

**Implementation Notes:**
- Opens `market_data.duckdb` with `duckdb.connect(path, read_only=True)`.
- Executes `SELECT DISTINCT trade_date FROM daily_prices ORDER BY trade_date` once at construction.
- Stores as a sorted `list[date]` in memory.
- `prior_or_equal(d: date) -> date` uses `bisect.bisect_right` to find the floor.
- If the calendar is empty (zero rows), raise `RuntimeError("daily_prices is empty — cannot build trading calendar")`.
- The component does not cache to disk — it is re-derived on each pipeline startup from the live DB.

**Tests:**
- [ ] `TradingCalendar.prior_or_equal(date(2022, 7, 4))` returns `date(2022, 7, 1)` (July 4 is a US holiday; July 1 is a Friday)
- [ ] `TradingCalendar.prior_or_equal(date(2022, 7, 2))` returns `date(2022, 7, 1)` (Saturday)
- [ ] `TradingCalendar.prior_or_equal(date(2022, 7, 1))` returns `date(2022, 7, 1)` (trading day itself)
- [ ] A calendar constructed from a mock DB with zero rows raises `RuntimeError`
- [ ] The calendar contains no weekends (assert `all(d.weekday() < 5 for d in calendar.dates)`)

**Done When:**
- [ ] All tests pass against the real `market_data.duckdb` (or a mock that mirrors its structure)
- [ ] `prior_or_equal` returns a value for any date in the 2017-2025 range

---

### Slice 3: FilingDiscovery

**Goal:** Implement `FilingDiscovery` — downloads EDGAR quarterly master.gz files, caches them to disk, and yields `DiscoveredFiling` objects filtered to the in-scope form types.

**Depends On:** Slice 1

**Files:**
- `research/pipeline/discovery.py` — create
- `research/tests/test_discovery.py` — create

**Implementation Notes:**
- Downloads from `https://www.sec.gov/Archives/edgar/full-index/{YYYY}/QTR{N}/master.gz`.
- Cache path: `research/cache/master_gz/{YYYY}_QTR{N}.gz`. Cache hit skips download.
- Parses pipe-delimited format: `CIK|CompanyName|FormType|DateFiled|Filename`.
- Filters to `form_type in {S-1, S-1/A, S-3, 424B2, 424B4, 8-K, 13D/A}` and `DateFiled` within requested range.
- Derives `accession_number` from `Filename` (basename, strip `.txt`, normalize dashes).
- On HTTP failure: log the quarter to `RunManifest.quarters_failed` and continue.
- Use 30-second timeout per download. No per-request rate limit needed (32 files total).

**Tests:**
- [ ] `parse_master_line` correctly extracts all five fields from a sample pipe-delimited line
- [ ] Only form types in the allowed set are yielded (assert `13D/A` is included; assert `DEF 14A` is excluded)
- [ ] `accession_number` is correctly derived from a sample Filename string (e.g., `edgar/data/1234567/0001234567-22-000123.txt` yields `0001234567-22-000123`)
- [ ] A filing with `DateFiled = "2016-12-31"` is excluded when date range starts `2017-01-01`
- [ ] A filing with `DateFiled = "2026-01-01"` is excluded when date range ends `2025-12-31`
- [ ] Cache hit: if master.gz file already exists on disk, no HTTP request is made (mock the HTTP layer)
- [ ] On HTTP 500 during download, the quarter is skipped (not raised) and the failure is returned in the quarters_failed list

**Done When:**
- [ ] All tests pass (using mock HTTP — no live SEC calls in tests)
- [ ] `FilingDiscovery(start_date=date(2021,1,1), end_date=date(2021,3,31))` yields only Q1 2021 filings from the in-scope form types

---

### Slice 4: CIKResolver

**Goal:** Implement `CIKResolver` — resolves a `DiscoveredFiling.cik` to a ticker using `market_data.duckdb`, handling multi-ticker CIKs via date-range disambiguation and share-class preference.

**Depends On:** Slice 1, Slice 2

**Files:**
- `research/pipeline/cik_resolver.py` — create
- `research/tests/test_cik_resolver.py` — create

**Implementation Notes:**
- Uses `duckdb.connect(path, read_only=True)`.
- Primary lookup: `raw_symbols_massive` joined with `symbol_history` using the SQL specified in `02-ARCHITECTURE.md` Section 6.2.
- Multi-ticker tie-break: prefer rows where `security_type` does not contain `WARRANT`, `RIGHT`, `UNIT`.
- If still ambiguous after share-class preference: `resolution_status = "AMBIGUOUS_SKIPPED"`, `ticker = None`.
- Fallback (last resort only): fuzzy match on entity name against `raw_symbols_fmp` if primary lookup returns zero rows and the entity name is an exact string.
- `UNRESOLVABLE`: no ticker found after both steps.
- **Anti-survivorship invariant:** The query must return results for both active and inactive symbols. The `active` column is used only for tie-breaking (ORDER BY), not for exclusion.

**Tests:**
- [ ] A known CIK that resolves to a single active ticker returns `resolution_status = "RESOLVED"` with the correct ticker
- [ ] A CIK that has no entry in `raw_symbols_massive` returns `resolution_status = "UNRESOLVABLE"` and `ticker = None`
- [ ] A CIK for a known-delisted symbol (where `symbol_history.end_date` is in the past) is resolved successfully — the filing is NOT excluded due to delisting (anti-survivorship test)
- [ ] A CIK with two tickers (common share + warrant) returns the common share ticker, not the warrant
- [ ] The `filing_date` parameter is used in the date-range filter: a CIK for a symbol that was only active in 2019 does not resolve for a filing dated 2023

**Done When:**
- [ ] All tests pass (may require a fixture DuckDB or known-good CIKs from the real DB)
- [ ] `CIKResolver` does not write to `market_data.duckdb` (read-only connection confirmed)

---

### Slice 5: FilingTextFetcher

**Goal:** Implement `FilingTextFetcher` — fetches filing HTML from SEC Archives with rate limiting, retry, and disk caching; strips HTML to plain text; handles all error conditions.

**Depends On:** Slice 1

**Files:**
- `research/pipeline/fetcher.py` — create
- `research/tests/test_fetcher.py` — create

**Implementation Notes:**
- Cache path: `research/cache/filing_text/{accession_number}.txt`. Cache hit returns cached text, skips HTTP.
- HTTP client: `httpx.AsyncClient` with `User-Agent: gap-lens-dilution-filter contact@yourdomain.com`.
- Rate limiter: `TokenBucketRateLimiter(rate=10, capacity=10)` singleton; one token acquired before each HTTP call.
- Concurrency: `asyncio.Semaphore(value=8)`.
- HTTP 404: `fetch_status = "FETCH_FAILED"`, `fetch_error = "HTTP_404"`. No retry.
- HTTP 429/503: back off 1s, 2s, 4s (maximum 3 attempts). After all fail: `fetch_status = "FETCH_FAILED"`.
- XBRL/binary detection: Content-Type `application/xml` or `xbrl` in Content-Type or body starts with `<?xml`: `fetch_status = "FETCH_FAILED"`, `fetch_error = "BINARY_CONTENT"`.
- HTML stripping: BeautifulSoup with `get_text(separator=" ")` and `lxml` parser.
- Truncate at `BacktestConfig.filing_text_max_bytes` (512,000 bytes).
- Empty text after stripping: `fetch_status = "EMPTY_TEXT"`, `plain_text = None`.
- Cache write is atomic: write to `{accession_number}.txt.tmp` then `os.rename()`.
- Skip fetch entirely if `ResolvedFiling.resolution_status != "RESOLVED"`.

**Tests:**
- [ ] Cache hit: when `{accession_number}.txt` exists on disk, no HTTP request is issued (mock HTTP layer)
- [ ] HTTP 404: `FetchedFiling.fetch_status == "FETCH_FAILED"` and `fetch_error == "HTTP_404"`; no retry
- [ ] HTTP 429: retried exactly 3 times with delays; after 3 failures `fetch_status == "FETCH_FAILED"`
- [ ] XBRL body detection: a response body starting with `<?xml` returns `fetch_status = "FETCH_FAILED"` with reason `BINARY_CONTENT`
- [ ] HTML stripping: a response containing `<html><body><p>Hello world</p></body></html>` returns `plain_text = "Hello world"` (or equivalent whitespace-trimmed form)
- [ ] Text truncation: a 700,000-byte text is truncated to 512,000 bytes in the output
- [ ] Empty text: a response whose HTML strips to whitespace-only returns `fetch_status = "EMPTY_TEXT"`
- [ ] Skip rule: a `ResolvedFiling` with `resolution_status = "UNRESOLVABLE"` returns a `FetchedFiling` with `fetch_status = "FETCH_FAILED"` without making any HTTP call

**Done When:**
- [ ] All tests pass (all HTTP mocked — no live SEC calls in tests)
- [ ] Cache write is atomic (verified by test that simulates interrupted write)

---

### Slice 6: BacktestClassifier

**Goal:** Implement `BacktestClassifier` — a thin wrapper that calls `RuleBasedClassifier.classify()` unchanged and returns a `ClassificationResult` for each fetched filing.

**Depends On:** Slice 1, Slice 5

**Files:**
- `research/pipeline/bt_classifier.py` — create
- `research/tests/test_bt_classifier.py` — create

**Implementation Notes:**
- Import: `from app.services.classifier.rule_based import RuleBasedClassifier`.
- Import: `from app.services.classifier.protocol import ClassificationResult`.
- A single shared `RuleBasedClassifier` instance is created at pipeline startup and reused.
- If `FetchedFiling.fetch_status != "OK"` or `plain_text is None`: return a stub `ClassificationResult` with `setup_type = None`, `confidence = 0.0`, `reasoning` set to the fetch error reason.
- Otherwise: call `classifier.classify(filing.plain_text, filing.form_type)` (the async method; await it).
- No modifications to `RuleBasedClassifier` are permitted. No fork or copy.
- `pipeline_version` in `BacktestRow` must be set to a string containing `"rule-based-v1"`.

**Tests:**
- [ ] A `FetchedFiling` with `fetch_status = "FETCH_FAILED"` returns `ClassificationResult` with `setup_type = None` and no exception raised
- [ ] A `FetchedFiling` with `plain_text = None` returns a stub result (same as above)
- [ ] A sample filing text that matches a known 424B4 setup rule returns the expected `setup_type` (uses the real `RuleBasedClassifier` in this integration-level test)
- [ ] `BacktestClassifier` does not modify any fields on the `RuleBasedClassifier` instance between calls

**Done When:**
- [ ] All tests pass
- [ ] `import app.services.classifier.rule_based` succeeds from within the `research/` package (confirming the import path is correct)

---

### Slice 7: UnderwriterExtractor

**Goal:** Implement `UnderwriterExtractor` — extracts named financial intermediaries and their roles from filing plain text using regex patterns, normalizes names against the static config, and returns `list[ParticipantRecord]`.

**Depends On:** Slice 1

**Files:**
- `research/pipeline/underwriter_extractor.py` — create
- `research/tests/test_underwriter_extractor.py` — create

**Implementation Notes:**
- Loads `research/config/underwriter_normalization.json` at instantiation (`dict[str, str]`). If file is missing: logs a warning, operates with empty normalization table (all names stored verbatim as `is_normalized = False`).
- Section isolation strategy per form type as specified in `02-ARCHITECTURE.md` Section 6.5.
- Applies `LEAD_UW_PATTERNS`, `CO_MANAGER_PATTERNS`, `SALES_AGENT_PATTERNS` regex patterns from the architecture spec.
- Multi co-manager handling: split comma-separated list after `co-manager[s]` header.
- Normalization: strip trailing legal suffixes (`", LLC"`, `", Inc."`, `"& Co."`) before table lookup. If matched: `is_normalized = True`. If not: store verbatim.
- `raw_text_snippet`: up to 300 chars of surrounding context.
- Zero patterns matched: return `[]` (not an error).
- This component receives only `FetchedFiling.plain_text` and `form_type` — no market data or return values.

**Tests:**
- [ ] A sample 424B4 plain text containing `"lead underwriter, Maxim Group LLC"` returns exactly one `ParticipantRecord` with `role = "lead_underwriter"` and `firm_name = "Maxim Group LLC"` (or canonical if in normalization table)
- [ ] A sample 8-K containing `"equity distribution agreement with H.C. Wainwright & Co., LLC"` returns one record with `role = "sales_agent"`
- [ ] A text containing `"co-managers: Oppenheimer & Co., Roth Capital Partners"` returns two `ParticipantRecord` objects with `role = "co_manager"`
- [ ] `"H.C. Wainwright & Co., LLC"` normalizes to `"H.C. Wainwright & Co."` when that mapping exists in the normalization config; `is_normalized = True`
- [ ] An unrecognized firm name stores the raw string verbatim; `is_normalized = False`
- [ ] A filing text with no matching patterns returns `[]`
- [ ] An S-3 filing returns `[]` (S-3 is excluded from extraction per architecture spec)
- [ ] Missing normalization config file: extractor instantiates without raising; all names stored as `is_normalized = False`

**Done When:**
- [ ] All tests pass using hardcoded sample filing text strings (no live HTTP)
- [ ] Section isolation correctly limits 8-K extraction to the first 5,000 characters in a test with a long mock body

---

### Slice 8: MarketDataJoiner

**Goal:** Implement `MarketDataJoiner` — executes all point-in-time market data joins against `market_data.duckdb` and assembles a `MarketSnapshot` for each resolved filing.

**Depends On:** Slice 1, Slice 2

**Files:**
- `research/pipeline/market_data_joiner.py` — create
- `research/tests/test_market_data_joiner.py` — create

**Implementation Notes:**
- Opens a single `duckdb.connect(path, read_only=True)` connection at pipeline startup. DuckDB read-only connections are thread-safe for concurrent reads.
- `effective_trade_date = TradingCalendar.prior_or_equal(filing.date_filed)` — computed once and used for ALL joins in one call. Never re-derived per join.
- `FLOAT_DATA_START_DATE = date(2020, 3, 4)` is the named constant (from `BacktestConfig`) controlling the AS-OF float query skip.
- All five join SQL queries as specified in `02-ARCHITECTURE.md` Section 6.7.
- Forward prices query uses `ROW_NUMBER() OVER (ORDER BY trade_date)` keyed on rows with `trade_date > effective_trade_date`; returns rows for `rn IN (1, 3, 5, 20)`.
- `delisted_before[N]` is derived: if fewer than N forward rows exist, `delisted_before[N] = True`.
- For short interest: pre-2021 filing will return no rows; `short_interest_at_T = None`, `borrow_cost_source = "DEFAULT"`.
- Does NOT read or return `filter_status`, scores, or returns — only market snapshot data.

**Tests (critical — these are the look-ahead bias canary tests required by the Research Contract):**
- [ ] **Look-ahead canary — float:** A mock DB with `historical_float` rows dated `2022-06-10` and `2022-06-20` for symbol `TEST`; filing dated `2022-06-15` returns the `2022-06-10` row (not `2022-06-20`)
- [ ] **Look-ahead canary — short interest:** A mock DB with `short_interest` rows dated `2022-02-15` and `2022-03-15`; filing dated `2022-03-01` returns the `2022-02-15` row
- [ ] **Look-ahead canary — ADV:** A filing dated `2022-06-15`; adding a price row for `2022-06-16` to the mock DB does not change the computed ADV value
- [ ] Float AS-OF query is skipped entirely for a filing dated `2020-03-03`; `float_at_T = None`, `float_available = False`
- [ ] Float AS-OF query runs for a filing dated `2020-03-04`; `float_available = True`
- [ ] Short interest returns `None` and `borrow_cost_source = "DEFAULT"` for a filing dated `2020-01-01` (pre-2021, short_interest table covers 2021+)
- [ ] `forward_prices[1]` is `None` and `delisted_before[1] = True` when the symbol has zero price rows after `effective_trade_date`
- [ ] Weekend filing date: filing dated `2022-06-04` (Saturday) resolves `effective_trade_date` to `2022-06-03` (Friday) and all joins use `2022-06-03`

**Done When:**
- [ ] All tests pass (may use an in-memory DuckDB fixture with synthetic data for the canary tests)
- [ ] The component never writes to `market_data.duckdb` (confirmed by using read-only connection — write attempt raises an exception)

---

### Slice 9: BacktestFilterEngine

**Goal:** Implement `BacktestFilterEngine` — a pure-function port of `FilterEngine.evaluate()` that takes a `MarketSnapshot` and `ClassificationResult` and returns a `FilterOutcome`; no async, no DB writes.

**Depends On:** Slice 1, Slice 8

**Files:**
- `research/pipeline/bt_filter_engine.py` — create
- `research/tests/test_bt_filter_engine.py` — create

**Implementation Notes:**
- Import filter constants: `from app.services.filter_engine import ALLOWED_FORM_TYPES, OFFERING_KEYWORDS`. Do not duplicate these constants.
- Filter order: universe check (NOT_IN_UNIVERSE gating) → Filter 1 (form type + keyword) → Filter 2 (market cap) → Filter 3 (float, skipped if `float_available=False`) → Filter 4 (dilution %, skipped if float unavailable) → Filter 5 (price) → Filter 6 (ADV).
- `dilution_severity = shares_offered_raw / float_at_T`. If `float_at_T` is None or zero: `dilution_severity = None`, `dilution_extractable = False`.
- Float skip rule: if `float_available = False`, Filter 3 and Filter 4 are skipped (not failed). `filter_fail_reason = "FLOAT_NOT_AVAILABLE"` is only set if the filing would otherwise pass but these filters cannot be evaluated.
- Universe check: `if snapshot.in_smallcap_universe is False or None: return FilterOutcome(passed=False, fail_criterion="NOT_IN_UNIVERSE")`.
- This component must NOT accept or use `MarketSnapshot.forward_prices` — see canary test below.

**Tests:**
- [ ] A `MarketSnapshot` where all filters pass returns `FilterOutcome(passed=True, fail_criterion=None)`
- [ ] A `MarketSnapshot` with `market_cap_at_T = 3_000_000_000` fails Filter 2 with `fail_criterion = "MARKET_CAP"`
- [ ] A `MarketSnapshot` with `float_available = False` skips Filter 3 and Filter 4; does not fail on these criteria
- [ ] A `MarketSnapshot` with `in_smallcap_universe = False` returns `fail_criterion = "NOT_IN_UNIVERSE"` without evaluating any other filter
- [ ] **Look-ahead canary (Research Contract required):** `BacktestFilterEngine.evaluate()` on a `MarketSnapshot` with `forward_prices = {1: 0.95, 3: 0.88, 5: 0.82, 20: 0.70}` produces the identical `FilterOutcome` as the same snapshot with `forward_prices = {1: None, 3: None, 5: None, 20: None}`
- [ ] A filing with `form_type = "DEF 14A"` fails Filter 1 (not in ALLOWED_FORM_TYPES)
- [ ] `dilution_extractable = False` when `float_at_T = None` and `float_available = True`

**Done When:**
- [ ] All tests pass
- [ ] No `await` or `async` keywords appear in `bt_filter_engine.py` (pure synchronous function)
- [ ] No `duckdb`, `httpx`, or any DB/HTTP import appears in `bt_filter_engine.py`

---

### Slice 10: BacktestScorer

**Goal:** Implement `BacktestScorer` — an adapter that calls `Scorer.score()` by constructing a `BacktestMarketData` adapter from `MarketSnapshot` fields; returns a score and rank; handles borrow cost derivation.

**Depends On:** Slice 1, Slice 8

**Files:**
- `research/pipeline/bt_scorer.py` — create
- `research/tests/test_bt_scorer.py` — create

**Implementation Notes:**
- Import: `from app.services.scorer import Scorer`.
- `BacktestMarketData` dataclass with fields: `adv_dollar: float`, `float_shares: float`, `price: float`, `market_cap: float` — exactly four fields, none forward-looking.
- Borrow cost derivation: if `short_interest_at_T` is not None and `float_at_T` is not None and `float_at_T > 0`: `borrow_cost = short_interest_at_T / float_at_T`. Otherwise: `borrow_cost = 0.0` (Scorer internally substitutes `settings.default_borrow_cost`).
- Two-tier flag: scorer does NOT alter behavior for 2017-2019 filings. If `float_at_T = None`, `dilution_severity = 0.0` and the scorer returns score = 0. The `float_available` flag in the output row is the downstream signal.
- `BacktestMarketData` must contain only the four fields listed. It must NOT include `forward_prices`, `return_1d`, or any outcome field.

**Tests:**
- [ ] A `MarketSnapshot` with valid price, market cap, float, adv, and short interest returns `score` in [0, 100] and `rank` in `{"A", "B", "C", "D"}`
- [ ] A `MarketSnapshot` with `short_interest_at_T = None` returns `borrow_cost_source = "DEFAULT"` and score matches what `Scorer.score()` produces with `borrow_cost = settings.default_borrow_cost`
- [ ] A `MarketSnapshot` with `float_at_T = None` returns `score = 0` and `dilution_extractable = False`
- [ ] **Look-ahead canary (Research Contract required):** `BacktestScorer.score()` on a `MarketSnapshot` with `forward_prices = {1: 0.95, 3: 0.88, 5: 0.82, 20: 0.70}` produces an identical `ScorerResult` as the same snapshot with `forward_prices = {1: None, 3: None, 5: None, 20: None}`
- [ ] `BacktestMarketData` raises `TypeError` if constructed with a fifth field (structural guard)

**Done When:**
- [ ] All tests pass
- [ ] `BacktestMarketData` is confirmed to have exactly four fields with no forward price data (checked via `dataclasses.fields()` in a test)

---

### Slice 11: OutcomeComputer

**Goal:** Implement `OutcomeComputer` — computes T+1, T+3, T+5, T+20 price returns from `MarketSnapshot.forward_prices`; sets delisting flags; handles NULL and zero price-at-T cases.

**Depends On:** Slice 1, Slice 8

**Files:**
- `research/pipeline/outcome_computer.py` — create
- `research/tests/test_outcome_computer.py` — create

**Implementation Notes:**
- Input: `price_at_T` (from `MarketSnapshot`) and `MarketSnapshot.forward_prices`.
- If `price_at_T` is None or `price_at_T == 0.0`: set `outcome_computable = False`; all return fields are `None`; all `delisted_before_TN` flags are `False` (default, not True — delisting is undefined when price_at_T itself is absent).
- For each horizon N in [1, 3, 5, 20]:
  - If `forward_prices[N]` is None: `return_N = None`, `delisted_before_TN = True`.
  - Otherwise: `return_N = (forward_prices[N] / price_at_T) - 1.0`, `delisted_before_TN = False`.
- `outcome_computable = True` if `price_at_T` is valid (even if all returns are NULL due to delistings).
- Horizon counting is strictly trading-day based (row-number-forward in `daily_prices`), not calendar-day. This counting is done in `MarketDataJoiner`; `OutcomeComputer` only divides.

**Tests:**
- [ ] `price_at_T = 10.00`, `forward_prices = {1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00}` → `return_1d = -0.05`, `return_3d = -0.08`, `return_5d = -0.10`, `return_20d = -0.20`; all `delisted_before_TN = False`; `outcome_computable = True`
- [ ] `price_at_T = 10.00`, `forward_prices = {1: 9.50, 3: None, 5: None, 20: None}` → `return_1d = -0.05`; `delisted_before_T3 = True`, `delisted_before_T5 = True`, `delisted_before_T20 = True`; `outcome_computable = True`
- [ ] `price_at_T = None` → `outcome_computable = False`; all return fields are `None`
- [ ] `price_at_T = 0.0` → `outcome_computable = False`; all return fields are `None`
- [ ] All four return values are stored as Python `float` (not integer)

**Done When:**
- [ ] All tests pass
- [ ] No DB or HTTP calls appear in `outcome_computer.py`

---

### Slice 12: OutputWriter and RunManifest

**Goal:** Implement `OutputWriter` and `RunManifest` — assembles all `BacktestRow` and `ParticipantRecord` objects into the final output files (Parquet, CSV, JSON metadata); enforces schema; computes SHA-256.

**Depends On:** Slice 1

**Files:**
- `research/pipeline/output_writer.py` — create
- `research/pipeline/run_manifest.py` — create
- `research/tests/test_output_writer.py` — create

**Implementation Notes:**
- `RunManifest` is a mutable dataclass that accumulates run statistics across the pipeline and is finalized before writing.
- `OutputWriter.write(rows, participants, manifest)` outputs three files to `docs/research/data/`:
  - `backtest_results.parquet` (pyarrow, explicit schema, sorted by `(cik, filed_at, accession_number)`, snappy compression, fixed row group size 128MB)
  - `backtest_results.csv` (pandas, `index=False`, UTF-8, Unix line endings)
  - `backtest_run_metadata.json` (json.dumps, indent=2, with `parquet_sha256` field computed after writing the Parquet file)
- Additionally writes `backtest_participants.parquet` and `backtest_participants.csv`.
- Schema enforcement: use `pyarrow.schema(...)` declared explicitly; do not infer schema from the DataFrame. All column names and types must match `01-REQUIREMENTS.md` Output Schema exactly.
- `processed_at` is set to the pipeline run start time (a single constant for all rows).
- SHA-256: computed via `hashlib.sha256` over the raw bytes of the written Parquet file.
- `docs/research/data/` directory is created if it does not exist.

**Tests:**
- [ ] `OutputWriter.write()` with a list of 3 synthetic `BacktestRow` objects produces a readable Parquet file (`pyarrow.parquet.read_table()` succeeds)
- [ ] The written Parquet file contains exactly the columns listed in the output schema (no extra, no missing columns)
- [ ] Rows are sorted by `(cik, filed_at, accession_number)` in the output Parquet
- [ ] `processed_at` is identical across all rows in the output
- [ ] `pipeline_version` is identical across all rows and matches the value in the metadata JSON
- [ ] The SHA-256 in `backtest_run_metadata.json` matches `hashlib.sha256` of the written Parquet file
- [ ] `RunManifest` with zero `quarters_failed` writes `"quarters_failed": []` in the JSON
- [ ] Writing `backtest_participants` with zero rows produces a valid empty Parquet file (not an error)

**Done When:**
- [ ] All tests pass
- [ ] `docs/research/data/backtest_results.parquet` can be read by pandas and pyarrow after the test run
- [ ] The metadata JSON contains all fields listed in `02-ARCHITECTURE.md` Section 5.7

---

### Slice 13: PipelineOrchestrator

**Goal:** Implement `research/run_backtest.py` — the top-level entry point that sequences all pipeline stages, handles startup checks, resume logic, per-filing error isolation, and produces the final output.

**Depends On:** Slices 1 through 12

**Files:**
- `research/run_backtest.py` — create

**Implementation Notes:**
- CLI with argparse: `--start-date`, `--end-date`, `--resume`, `--dry-run N`.
- Startup checks (in order, HALT on failure):
  1. `market_data.duckdb` exists and is readable.
  2. `SELECT COUNT(*) FROM daily_universe` returns > 0; if 0, HALT.
  3. `SELECT COUNT(*) FROM daily_prices` returns > 0; if 0, HALT.
  4. Build `TradingCalendar` from `daily_prices`.
  5. Load `research/config/underwriter_normalization.json`.
- Stage sequencing: single linear pass — `FilingDiscovery` → `CIKResolver` → `FilingTextFetcher` → `BacktestClassifier` → `UnderwriterExtractor` → `MarketDataJoiner` → `BacktestFilterEngine` → `BacktestScorer` → `OutcomeComputer`. Accumulate `BacktestRow` and `ParticipantRecord` objects in memory. After all filings are processed, call `OutputWriter.write()`.
- Resume logic: `--resume` passes to `FilingDiscovery` (skip cached master.gz files) and `FilingTextFetcher` (skip cached filing texts). Classification, join, filter, score, and outcome always re-run from cache.
- Per-filing error isolation: each filing is wrapped in a try/except block. Exceptions are logged with `accession_number`; `filter_status = "PIPELINE_ERROR"` is set on the row. Pipeline continues.
- `--dry-run N`: process the first N filings discovered then stop. Useful for smoke testing.
- `pipeline_version` string must embed `"rule-based-v1"` to satisfy the Research Contract `classifier_version` field.

**Tests (smoke-level integration — not full run):**
- [ ] `python research/run_backtest.py --help` exits 0 and prints all arguments
- [ ] `python research/run_backtest.py --dry-run 0` exits 0 without error (no filings processed, empty output written)
- [ ] Startup check: if `market_data.duckdb` path does not exist, the script exits with a non-zero exit code and a clear error message
- [ ] `--dry-run 1` with cached master.gz and filing text fixtures completes without exception and writes all three output files

**Done When:**
- [ ] All tests pass
- [ ] `python research/run_backtest.py --dry-run 0` runs end-to-end from the project root without import errors
- [ ] Output files are created at `docs/research/data/` with the correct names

---

### Slice 14: Research Contract Validation

**Goal:** Implement a standalone test suite that programmatically verifies all structural integrity checks, canary tests, and required manifest fields from the Research Contract against actual pipeline output. This slice is the final gate before any finding document can cite the pipeline output.

**Depends On:** Slice 13

**Files:**
- `research/tests/test_research_contract.py` — create

**Implementation Notes:**
- This is a separate test module from the component-level tests. It operates against the actual output files produced by a pipeline run (or a synthetic mini-run produced by the `--dry-run` mode).
- It does NOT re-run the full pipeline; it asserts properties of the output files that already exist.
- Each assertion maps to a numbered Research Contract criterion (RC-01 through RC-18 where testable in code).
- The canary test `test_canary_no_lookahead` is also run here (as specified in `RESEARCH-CONTRACT.md` Section 2.8), in addition to its per-component tests in Slices 9 and 10.

**Tests (one-to-one with Research Contract criteria that are programmatically verifiable):**
- [ ] **RC-01 (Structural integrity, all 11 checks):**
  - [ ] `backtest_results.parquet` is readable by `pyarrow.parquet.read_table()` without error
  - [ ] Zero rows have `filter_status = "PASSED"` and `score IS NULL`
  - [ ] Zero rows have `filter_status = "PASSED"` and `rank IS NULL`
  - [ ] Zero rows have `outcome_computable = True` and `price_at_T IS NULL`
  - [ ] Zero rows have `delisted_before_T1 = False` and `return_1d IS NULL` and `outcome_computable = True` (and equivalents for T3, T5, T20)
  - [ ] Zero rows have `float_available = True` and `filed_at < 2020-03-04`
  - [ ] Zero rows have `float_available = False` and `filed_at >= 2020-03-04`
  - [ ] Every `accession_number` in `backtest_participants` has a row in `backtest_results`
  - [ ] `processed_at` is identical across all rows
  - [ ] `pipeline_version` is identical across all rows and matches metadata JSON
  - [ ] SHA-256 of `backtest_results.parquet` matches `backtest_run_metadata.json.parquet_sha256`
- [ ] **RC-02:** `backtest_run_metadata.json` contains all required fields from `RESEARCH-CONTRACT.md` Section 7.2
- [ ] **RC-03:** `canary_no_lookahead` field in manifest is `"PASS"`
- [ ] **RC-16:** `classifier_version` in manifest equals `"rule-based-v1"`
- [ ] **RC-17:** Zero rows in `backtest_results` have `|return_20d| > 500%` without a corresponding `corporate_action_flag` note in findings (pipeline check: log count of such rows to run manifest)
- [ ] **RC-18:** If `normalization_config_entry_count = 0` in manifest, test asserts that no H1e/H1f/H1g findings citations are possible (enforced by manifest field, not by blocking the run)
- [ ] **Canary test (Section 2.8, standalone):** `test_canary_no_lookahead` — constructs two `MarketSnapshot` objects (one with populated `forward_prices`, one with all `forward_prices = None`) and asserts that `BacktestFilterEngine.evaluate()` and `BacktestScorer.score()` produce identical results for both
- [ ] **Schema completeness:** All columns defined in `01-REQUIREMENTS.md` Output Schema are present in the Parquet file with the correct data types
- [ ] **Two-tier flag invariant:** `float_available` column contains no NULL values (it is required non-nullable)
- [ ] **Participants FK integrity:** `backtest_participants.parquet` contains no `accession_number` values absent from `backtest_results.parquet`

**Done When:**
- [ ] All assertions in `test_research_contract.py` pass against the output of a `--dry-run` pipeline execution
- [ ] `canary_no_lookahead` assertion passes (no forward data leaks into filter or scoring)
- [ ] The test file can be run in isolation: `python -m pytest research/tests/test_research_contract.py -v`
- [ ] Every passing assertion maps to a named RC criterion in a comment in the test code

---

## Sequence Rules

1. Complete each slice fully before starting the next. No partial slice work.
2. Slices 2 through 7 may be developed in parallel (they have no mutual dependencies within that group), but each must have all its own tests passing before it is declared done.
3. Slices 8, 9, and 10 depend on Slice 2 (via `MarketSnapshot`'s `effective_trade_date`) and Slice 1. They may also be developed in parallel once Slices 1 and 2 are done.
4. Slice 13 (Orchestrator) must not begin until all of Slices 1-12 are done. It is the integration point.
5. Slice 14 (Research Contract Validation) must not begin until Slice 13 is done and its smoke tests pass.
6. If any slice is blocked by an unresolved dependency (missing data fixture, missing app-side API), HALT and report — do not skip ahead.
7. No new slices without human approval.

---

## Deferred (Not This Roadmap)

- Teacher labeling (Claude LLM classification) — Phase R2; depends on Phase R1 findings from this pipeline.
- Student model training (Llama 1B LoRA) — Phase R3.
- H1c validation (rule-based vs teacher agreement rate) — requires teacher labels not yet produced.
- H1d validation (student model F1) — requires student model not yet trained.
- `UNDERWRITER_FACTOR` scoring multiplier — win rates needed as input are an output of this pipeline; cannot be computed until after a full run is complete.
- Borrow cost data from IBKR API — deferred to Phase R4 per `METHODOLOGY.md`.
- FMP MCP server as a discovery source — EDGAR quarterly master.gz is the required historical discovery method.
- 424B3 underwriter extraction beyond sales agent identification — Phase R2 enhancement.
- Position sizing, P&L simulation, execution cost modeling — out of scope for signal validation.
- Automated finding document generation — findings are written by the researcher after reviewing the output dataset.
- Parallelism beyond the async fetch semaphore — single-threaded classification/join/scoring is sufficient per architecture.
- UnderwriterExtractor human-review validation (50-filing sample) — this is a researcher task after a full run; it is not a code slice. Its gate (RC-10) is documented in the Research Contract.
