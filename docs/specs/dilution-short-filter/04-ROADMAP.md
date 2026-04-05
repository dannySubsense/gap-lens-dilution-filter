# Implementation Roadmap: dilution-short-filter

- **Document**: 04-ROADMAP.md
- **Project**: gap-lens-dilution-filter
- **Phase**: Phase 1 (Rule-Based Pipeline)
- **Status**: APPROVED FOR IMPLEMENTATION
- **Date**: 2026-04-04
- **Author**: @planner
- **Based On**: 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, 03-UI-SPEC.md

---

## Overview

This roadmap breaks the dilution-short-filter Phase 1 system into 17 ordered, independently testable slices. Each slice has a single deliverable, concrete file list, acceptance test, and blocking dependencies. No slice may begin until all listed dependencies are complete and their acceptance tests pass.

The implementation starts from a copy of gap-lens-dilution, builds the data spine (DuckDB + config) before any services, orders services by pipeline data flow (ingest → filter → classify → score → signal), and places all frontend work after the API is stable and testable.

---

## Dependency Map

| Slice | Name | Depends On |
|-------|------|------------|
| 1 | Project Scaffold | — |
| 2 | DuckDB Foundation | 1 |
| 3 | Config Extension | 1 |
| 4 | Pydantic Models | 2, 3 |
| 5 | FMP Client | 3 |
| 6 | Filing Fetcher | 2, 3 |
| 7 | EDGAR Poller | 2, 3, 6 |
| 8 | Filter Engine | 2, 3, 4, 5 |
| 9 | Classifier Protocol + Rule-Based | 3, 4 |
| 10 | Scorer | 3, 4, 9 |
| 11 | Signal Manager | 2, 4, 10 |
| 12 | Pipeline Integration | 2, 3, 5, 6, 7, 8, 9, 10, 11 |
| 13 | API Routes | 2, 4, 11, 12 |
| 14 | Frontend Shell | 1, 13 |
| 15 | Signal Rows + Auto-Refresh | 14 |
| 16 | Setup Detail + Position Tracking | 15 |
| 17 | End-to-End Smoke Test | 12, 13, 16 |

---

## Sequence Rules

1. Complete each slice fully before starting the next.
2. No partial slice work — the acceptance test must pass before moving on.
3. If blocked at any slice, HALT and report; do not skip ahead.
4. No new slices added without human approval.
5. The original `/home/d-tuned/projects/gap-lens-dilution/` repository must not be modified at any point.

---

## Slice Detail

---

### Slice 1: Project Scaffold

**Goal**: Create the gap-lens-dilution-filter project by copying the reusable files from gap-lens-dilution, stripping the ticker-lookup frontend, initializing git, and setting up the `.env` file.

**Depends On**: —

**Files Created or Modified**:

Backend (copied from `/home/d-tuned/projects/gap-lens-dilution/`):
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/__init__.py` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/core/__init__.py` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/core/config.py` — copy (will be extended in Slice 3)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/models/__init__.py` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/models/responses.py` — copy unchanged
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/__init__.py` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/dilution.py` — copy unchanged (DilutionService, never modified)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/utils/__init__.py` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/utils/errors.py` — copy unchanged
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/utils/formatting.py` — copy unchanged
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/utils/validation.py` — copy unchanged
- `/home/d-tuned/projects/gap-lens-dilution-filter/requirements.txt` — copy (will be extended in Slice 3)

Frontend scaffold (Next.js, copied from gap-lens-dilution):
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/package.json` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/tsconfig.json` — copy
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/app/globals.css` — copy (preserves dark theme vars; dashboard-specific CSS added in Slice 14)

New files created:
- `/home/d-tuned/projects/gap-lens-dilution-filter/.env` — new, populated with placeholder values for all env vars (see Section 9 of 02-ARCHITECTURE.md); FMP_API_KEY and ASKEDGAR_API_KEY left blank
- `/home/d-tuned/projects/gap-lens-dilution-filter/.gitignore` — new, excludes `.env`, `__pycache__`, `venv/`, `data/`, `.next/`, `node_modules/`
- `/home/d-tuned/projects/gap-lens-dilution-filter/data/.gitkeep` — new, creates `data/` directory for DuckDB file

**Implementation Notes**:
- Delete or do not copy: `app/static/js/`, `app/static/index.html`, any ticker-lookup frontend files.
- The `app/main.py` is NOT copied in this slice; it will be created in Slice 12 (it requires lifespan setup with all services).
- The `frontend/src/app/layout.tsx` is NOT copied in this slice; it is created in Slice 14 (it needs the new page title).
- After copying, run `pip install -r requirements.txt` in a fresh venv to confirm all existing dependencies resolve.
- Run `npm install` in `frontend/` to confirm the Next.js scaffold installs cleanly.

**Done When**:
- [ ] All listed files are present at their target paths.
- [ ] `pip install -r requirements.txt` exits 0 in a fresh virtual environment.
- [ ] `npm install` in `frontend/` exits 0.
- [ ] `python -c "from app.services.dilution import DilutionService; print('ok')"` prints `ok` (confirms DilutionService import chain is intact).
- [ ] No file in `/home/d-tuned/projects/gap-lens-dilution/` has been modified (verify with `git status` in that repo — it should be clean).

---

### Slice 2: DuckDB Foundation

**Goal**: Implement `db.py` with the singleton DuckDB connection, all five `CREATE TABLE IF NOT EXISTS` statements, the `poll_state` seed row, `init_db()`, and `get_db()`. Verify schema is created on first call.

**Depends On**: Slice 1

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/db.py` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/requirements.txt` — add `duckdb` if not already present

**Implementation Notes**:
- Uses `duckdb.connect(settings.duckdb_path)` as a module-level singleton opened once at import time. `init_db()` executes all CREATE TABLE statements against this connection.
- All five tables: `filings`, `filter_results`, `market_data`, `labels`, `signals`. Plus `poll_state` with the `INSERT OR IGNORE` seed row.
- Full DDL is specified verbatim in Section 6 of 02-ARCHITECTURE.md; copy it exactly.
- `get_db()` returns the module-level connection instance (not a factory — DuckDB single-writer model).
- `init_db()` must be idempotent: calling it twice must not error or duplicate data.

**Done When**:
- [ ] `python -c "from app.services.db import init_db, get_db; init_db(); db = get_db(); print(db.execute('SHOW TABLES').fetchall())"` prints all five domain table names plus `poll_state` and `cik_ticker_map` without error.
- [ ] Running `init_db()` a second time does not raise an exception or alter existing rows.
- [ ] The `poll_state` table contains exactly one row with `id=1` after init.
- [ ] A `data/filter.duckdb` file exists on disk after calling `init_db()` (with default path from config).

---

### Slice 3: Config Extension

**Goal**: Extend `app/core/config.py` with all new environment variables defined in Section 9 of 02-ARCHITECTURE.md, and extend `requirements.txt` with all new Python dependencies.

**Depends On**: Slice 1

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/core/config.py` — extend (add all new Settings fields from 02-ARCHITECTURE.md Section 9)
- `/home/d-tuned/projects/gap-lens-dilution-filter/requirements.txt` — extend (add: `duckdb`, `lxml`, `aiofiles`, `httpx` if not present)

**Implementation Notes**:
- Add the following new fields to the existing `Settings` class (all with defaults matching the spec):
  - `classifier_name: str = "rule-based-v1"`
  - `edgar_poll_interval: int = 90`
  - `edgar_efts_url: str = "https://efts.sec.gov/LATEST/search-index"` — base URL only; the `forms`, `startdt`, `enddt`, and `from` query parameters are appended dynamically at runtime by `EdgarPoller._poll_once()`. The config stores only the base URL.
  - `duckdb_path: str = "./data/filter.duckdb"`
  - `filing_text_max_bytes: int = 512_000`
  - `default_borrow_cost: float = 0.30`
  - `adv_min_threshold: float = 500_000` — ADV threshold used in FLOAT_ILLIQUIDITY numerator and in Filter 6.
  - `score_normalization_ceiling: float = 1.0`
  - `setup_quality_a` through `setup_quality_e` (floats, values per spec)
  - `lifecycle_check_interval: int = 300`
  - `ibkr_borrow_cost_enabled: bool = False`
  - `setup_quality` computed property returning a `dict[str, float]`
- The `fmp_api_key: str = ""` field likely already exists in the inherited config; confirm and do not duplicate it.
- Do not remove any existing fields from the original config.

**Done When**:
- [ ] `python -c "from app.core.config import settings; print(settings.edgar_poll_interval, settings.setup_quality)"` prints `90` and the setup quality dict without error.
- [ ] `python -c "from app.core.config import settings; assert settings.setup_quality['A'] == 0.65"` passes.
- [ ] `python -c "from app.core.config import settings; assert settings.edgar_efts_url.startswith('https://efts.sec.gov')"` passes.
- [ ] `pip install -r requirements.txt` exits 0 with `duckdb` and `lxml` in the installed set.
- [ ] Existing DilutionService imports still succeed after config modification.

---

### Slice 4: Pydantic Models

**Goal**: Define all Pydantic response models and the TypeScript type interfaces used by the API and frontend.

**Depends On**: Slices 2, 3

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/models/signals.py` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/types/signals.ts` — new

**Implementation Notes**:
- `app/models/signals.py` must define exactly: `SignalRow`, `ClassificationDetail`, `SignalDetailResponse`, `SignalListResponse`, `PositionRequest`, `PositionResponse`, `HealthResponse`. The canonical field definitions are in Section 5 of 02-ARCHITECTURE.md.
- `PositionRequest` must include validators: `entry_price` must be `> 0` if provided; `cover_price` must be `> 0.01` if provided. Use Pydantic `@field_validator` or `model_validator`.
- `frontend/src/types/signals.ts` must define: `SignalRow`, `ClassificationDetail`, `SignalDetailResponse`, `SignalListResponse`, `HealthResponse`, `PositionRequest`, `ApiResult<T>`. Canonical definitions are in Section 7 of 02-ARCHITECTURE.md.
- No import cycles: `signals.py` must not import from any service file.

**Done When**:
- [ ] `python -c "from app.models.signals import SignalRow, HealthResponse, PositionRequest; print('ok')"` prints `ok`.
- [ ] A `PositionRequest(cover_price=0.005)` raises a `ValidationError` (cover price below $0.01 threshold).
- [ ] A `PositionRequest(entry_price=5.20)` validates successfully.
- [ ] TypeScript compilation of `frontend/src/types/signals.ts` succeeds via `npx tsc --noEmit` from the `frontend/` directory.

---

### Slice 5: FMP Client

**Goal**: Implement `FMPClient` in `app/services/fmp_client.py` with the correct FMP endpoints (quote, shares_float, historical volume), retry/backoff logic, and the `FMPMarketData` dataclass.

**Depends On**: Slice 3

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/fmp_client.py` — new

**Implementation Notes**:
- `FMPMarketData` is a dataclass: `price: float`, `market_cap: float`, `float_shares: float`, `adv_dollar: float`, `fetched_at: datetime`.
- Three async methods calling:
  - `/v3/quote/{ticker}?apikey={key}` for `price` (field: `price`) and `market_cap` (field: `marketCap`).
  - `/v4/shares_float?symbol={ticker}&apikey={key}` for `float_shares` (field: `floatShares`). Note: NOT `/v3/profile` — that endpoint does not reliably return float shares.
  - `/v3/historical-price-full/{ticker}?timeseries=20&apikey={key}` for 20-day ADV computation (sum of `volume * close` / 20).
- Retry: up to 3 attempts on HTTP 429 or 5xx, with exponential backoff (1s, 2s, 4s).
- If `settings.fmp_api_key == ""` at call time: log a warning and raise `FMPDataUnavailableError` immediately (do not attempt the call).
- Raise `FMPDataUnavailableError` (custom exception in `app/utils/errors.py`) after all retries exhausted.
- Match the retry/cache pattern of `DilutionService` for consistency.

**Done When**:
- [ ] Unit test with `httpx` mocked: `FMPClient().get_market_data("AAPL")` with a mocked 200 response returns a populated `FMPMarketData` instance.
- [ ] Unit test: calling `get_market_data` with `fmp_api_key=""` raises `FMPDataUnavailableError` without making any HTTP request.
- [ ] Unit test: a 429 response on first attempt causes a retry; on the third 429, `FMPDataUnavailableError` is raised.
- [ ] `FMPDataUnavailableError` is importable from `app.utils.errors`.

---

### Slice 6: Filing Fetcher + Ticker Resolver

**Goal**: Implement `FilingFetcher` in `app/services/filing_fetcher.py` to fetch and plain-text-strip EDGAR filing documents, and implement `TickerResolver` in `app/utils/ticker_resolver.py` to resolve EDGAR CIKs to ticker symbols.

**Depends On**: Slices 2, 3

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/filing_fetcher.py` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/utils/ticker_resolver.py` — new

**Implementation Notes**:

FilingFetcher:
- Single async method: `fetch(filing_url: str) -> str`.
- Uses `httpx.AsyncClient` to GET the filing URL.
- Strips HTML tags using `html.parser` (stdlib) or `lxml`; preserve whitespace structure.
- Truncates to `settings.filing_text_max_bytes` bytes before returning.
- Retries up to 3 times on network failure with exponential backoff.
- Raises `FilingFetchError` (new custom exception added to `app/utils/errors.py`) after 3 failures.

TickerResolver:
- On startup, `TickerResolver.refresh()` is called from the FastAPI lifespan handler in `app/main.py`, after `init_db()` completes. It downloads `https://www.sec.gov/files/company_tickers_exchange.json` and upserts into DuckDB `cik_ticker_map` table (`cik INTEGER`, `ticker TEXT`, `name TEXT`, `exchange TEXT`). Refreshes once per day.
- `resolve(cik: str, efts_ticker: str | None, entity_name: str | None) -> str | None` — four-step fallback chain:
  1. Query `cik_ticker_map` by CIK (normalize to integer, stripping leading zeros).
  2. Use `efts_ticker` if present in the EFTS response.
  3. Query FMP `/v3/search?query={entity_name}&limit=1` if entity_name is provided.
  4. Return `None` (caller marks filing as UNRESOLVABLE).

**Done When**:
- [ ] Unit test: `FilingFetcher().fetch(url)` with mocked HTML response returns stripped plain text.
- [ ] Unit test: a response larger than `settings.filing_text_max_bytes` is truncated to that length exactly.
- [ ] Unit test: 3 consecutive network failures raise `FilingFetchError`.
- [ ] `FilingFetchError` is importable from `app.utils.errors`.
- [ ] `TickerResolver().resolve("320193", None, None)` returns `"AAPL"` (resolved from cik_ticker_map after init).
- [ ] `TickerResolver().resolve("9999999", "XYZ", None)` returns `"XYZ"` (resolved from EFTS ticker fallback when CIK not in map).
- [ ] `TickerResolver().resolve("9999999", None, None)` returns `None` (UNRESOLVABLE).
- [ ] `cik_ticker_map` table schema exists in DuckDB after `init_db()` is called (the CREATE TABLE IF NOT EXISTS runs in init_db).
- [ ] `cik_ticker_map` table is populated with data after `TickerResolver.refresh()` is called from the lifespan handler.

---

### Slice 7: EDGAR Poller

**Goal**: Implement `EdgarPoller` in `app/services/edgar_poller.py` to continuously poll the EDGAR EFTS JSON endpoint, parse new accession numbers, deduplicate against DuckDB, and hand each new filing off for processing.

**Depends On**: Slices 2, 3, 6

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/edgar_poller.py` — new

**Implementation Notes**:
- Public interface: `run_forever()` coroutine (infinite loop), `last_poll_at: datetime | None` property, `last_success_at: datetime | None` property.
- `_poll_once()` method: fetch EDGAR EFTS JSON endpoint (see 02-ARCHITECTURE.md Section 3.1 for full URL and parameters), parse JSON response, extract per-hit fields (`accessionNo`, `cik`, `formType`, `filedAt`, `entityName`, `ticker`), deduplicate by querying `filings` table on `accession_number`, call `process_filing(...)` for each new entry. Handles pagination via `from=` offset if `total.value > 100`.
- Retry: up to 3 attempts on EDGAR unreachable (1s, 2s, 4s backoff).
- On malformed or unexpected JSON response: log the raw excerpt (first 500 bytes), skip the poll cycle, do not crash.
- Updates `poll_state` table in DuckDB on each successful poll cycle.
- `process_filing` is a stub method at this slice that only writes a PENDING record to the `filings` table and calls `FilingFetcher.fetch(filing_url)`. Full pipeline wiring is Slice 12.
- The `run_forever` loop follows the pattern from 02-ARCHITECTURE.md Section 8 exactly.

**Done When**:
- [ ] Unit test: calling `_poll_once()` with mocked EDGAR EFTS JSON response containing 3 hits writes 3 rows to `filings` with `processing_status = PENDING`.
- [ ] Unit test: calling `_poll_once()` twice with the same JSON (same accession numbers) results in exactly 3 rows total — no duplicates.
- [ ] Unit test: malformed JSON (non-parseable string) does not raise; it logs the excerpt and returns normally.
- [ ] Unit test: EDGAR unreachable (3 consecutive connection errors) logs a failure and returns without crashing.
- [ ] After a successful `_poll_once()`, `poll_state` row has an updated `last_success_at` value.
- [ ] `last_poll_at` and `last_success_at` properties return `None` before any poll runs.

---

### Slice 8: Filter Engine

**Goal**: Implement `FilterEngine` in `app/services/filter_engine.py` with all six filter criteria applied in order, stop-on-fail behavior, and `filter_results` table writes.

**Depends On**: Slices 2, 3, 4, 5

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/filter_engine.py` — new

**Implementation Notes**:
- Single async method: `evaluate(accession_number, form_type, filing_text, ticker, fmp_data, ask_edgar_dilution_pct) -> FilterOutcome`.
- `FilterOutcome` is a dataclass: `passed: bool`, `fail_criterion: str | None`.
- Filter 1 (filing type + keyword): evaluated from `form_type` and `filing_text` — no API call. Offering keywords: `'offering'`, `'shares'`, `'prospectus'`, `'at-the-market'`, `'sales agent'`, `'underwritten'`, `'priced'` (from requirements AC-02).
- Filters 2, 3, 5, 6 use fields from `fmp_data: FMPMarketData | None`. If `fmp_data is None`, these fail immediately with `fail_criterion = "DATA_UNAVAILABLE"`.
- Filter 4 (dilution %): computed as `ask_edgar_dilution_pct` if available; else attempt keyword extraction of shares_offered from `filing_text` divided by `fmp_data.float_shares`. If neither is extractable, fail conservatively with `fail_criterion = "DILUTION_PCT"`.
- Each evaluated criterion writes one row to `filter_results` (via `asyncio.to_thread` for DuckDB write). Stops writing after first failure.
- Thresholds from spec: market_cap < 2e9, float_shares < 50e6, dilution_pct > 0.10, price > 1.00, adv_dollar > 500_000.
- If ticker is None (unresolvable): update `filings.filter_status = UNRESOLVABLE`; return `FilterOutcome(passed=False, fail_criterion="UNRESOLVABLE")`.

**Done When**:
- [ ] Unit test: a filing with all-passing values (mocked FMP data within thresholds, valid form type, extractable dilution) returns `FilterOutcome(passed=True, fail_criterion=None)` and writes 6 `filter_results` rows all with `passed=True`.
- [ ] Unit test: a filing with market_cap = 3e9 returns `FilterOutcome(passed=False, fail_criterion="MARKET_CAP")` and writes exactly 2 `filter_results` rows (Filter 1 passed, Filter 2 failed — evaluation stopped).
- [ ] Unit test: `fmp_data=None` causes Filter 2 to fail with `fail_criterion="DATA_UNAVAILABLE"`.
- [ ] Unit test: `ticker=None` returns `FilterOutcome(passed=False, fail_criterion="UNRESOLVABLE")` and updates `filings.filter_status`.
- [ ] The `filings` table record for a passing filing has `filter_status = PASSED` after `evaluate()` returns.

---

### Slice 9: Classifier Protocol + Rule-Based Classifier

**Goal**: Define `ClassifierProtocol` and `ClassificationResult` in `protocol.py`, implement `RuleBasedClassifier` in `rule_based.py`, and expose `get_classifier` factory in `__init__.py`.

**Depends On**: Slices 3, 4

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/classifier/__init__.py` — new (get_classifier factory)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/classifier/protocol.py` — new (ClassifierProtocol, ClassificationResult)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/classifier/rule_based.py` — new (RuleBasedClassifier)

**Implementation Notes**:
- `protocol.py` defines `ClassificationResult` TypedDict and `ClassifierProtocol` Protocol exactly as specified in Section 4 of 02-ARCHITECTURE.md. These are the canonical definitions; do not deviate.
- `RuleBasedClassifier` implements `ClassifierProtocol`. Rules applied in precedence order A > E > B > C > D (spec Section 3.5.3). All keyword matching is case-insensitive.
- On a match: `confidence = 1.0`. On NULL: `confidence = 0.0`.
- `immediate_pressure = True` for setup types B and C only.
- `key_excerpt`: first 500-character window containing the matched keyword, truncated to 500 chars before return.
- `dilution_severity`: keyword-regex extraction of "X,XXX,XXX shares" near offering language, divided by float. Returns `0.0` if not extractable.
- `price_discount`: regex for `"\$\d+\.\d+"` near "at" or "priced at" language. Returns `None` if not extractable.
- `__init__.py` provides `get_classifier(name: str | None = None) -> ClassifierProtocol` using the registry pattern from Section 3.5.2. Pipeline code must only import `get_classifier`, never `RuleBasedClassifier` directly.
- If multiple rules match, first in precedence order wins; all matched pattern labels logged to `filings.all_matched_patterns` as a JSON array.

**Done When**:
- [ ] Unit test: `get_classifier("rule-based-v1")` returns an instance that satisfies `isinstance(obj, ClassifierProtocol)` (use `runtime_checkable` on Protocol, or verify via duck-typing test).
- [ ] Unit test: filing text `"S-1"` + text containing `"commence offering"` returns `ClassificationResult` with `setup_type="A"`, `confidence=1.0`.
- [ ] Unit test: filing text with no matching pattern returns `setup_type="NULL"`, `confidence=0.0`.
- [ ] Unit test: filing text with both `"commence offering"` (A pattern) and `"cashless exercise"` (E pattern) returns `setup_type="A"` (A takes precedence).
- [ ] Unit test: `get_classifier("unknown-classifier")` raises `ValueError`.
- [ ] Unit test: a stub class implementing `classify(self, filing_text: str, form_type: str) -> ClassificationResult` can be passed to any pipeline function that accepts `ClassifierProtocol` without modification to that function. (Verifies the abstraction seam.)
- [ ] `key_excerpt` is never longer than 500 characters in any returned result.

---

### Slice 10: Scorer

**Goal**: Implement `Scorer` in `app/services/scorer.py` with the SCORE formula, normalization, clamping, and rank assignment.

**Depends On**: Slices 3, 4, 9

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/scorer.py` — new

**Implementation Notes**:
- Single method: `score(classification: ClassificationResult, fmp_data: FMPMarketData, borrow_cost: float) -> ScorerResult`.
- `ScorerResult` is a dataclass: `score: int`, `rank: str`.
- Formula (exact, from Section 3.6 of 02-ARCHITECTURE.md):
  ```python
  DILUTION_SEVERITY  = classification["dilution_severity"]
  FLOAT_ILLIQUIDITY  = settings.adv_min_threshold / fmp_data.adv_dollar
  SETUP_QUALITY      = settings.setup_quality[classification["setup_type"]]
  raw_score = (DILUTION_SEVERITY * FLOAT_ILLIQUIDITY * SETUP_QUALITY) / borrow_cost
  score = clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)
  ```
- If `borrow_cost == 0.0`: substitute `settings.default_borrow_cost`, log warning.
- If `classification["dilution_severity"] == 0.0`: log a data quality note (conservative — scorer returns a low score, not an error).
- If normalized value exceeds 100 before clamping: log a data quality warning with the raw pre-normalization value.
- Rank thresholds: score > 80 → "A", 60 <= score <= 80 → "B", 40 <= score < 60 → "C", score < 40 → "D".
- `setup_type = "NULL"` should not reach the scorer (filtered before this stage); if it does, return `ScorerResult(score=0, rank="D")`.

**Done When**:
- [ ] Unit test: known inputs produce the expected score consistent with the Architecture Section 3.6 worked examples. Use `DILUTION_SEVERITY`, `FLOAT_ILLIQUIDITY`, `SETUP_QUALITY`, and `borrow_cost` values drawn directly from the spec's worked example to verify the formula produces the documented integer output.
- [ ] Unit test: `borrow_cost=0.0` substitutes `settings.default_borrow_cost` and does not raise.
- [ ] Unit test: a raw score producing a normalized value of 120 is clamped to 100.
- [ ] Unit test: score > 80 → rank "A"; score 70 → rank "B"; score 50 → rank "C"; score 30 → rank "D".
- [ ] `ScorerResult` is importable from `app.services.scorer`.

---

### Slice 11: Signal Manager

**Goal**: Implement `SignalManager` in `app/services/signal_manager.py` for alert emission, SETUP_UPDATE detection, status transitions, and the lifecycle checker loop.

**Depends On**: Slices 2, 4, 10

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/signal_manager.py` — new

**Implementation Notes**:
- `emit(scorer_result, classification, fmp_data, accession_number, ticker) -> int | None`:
  - Rank A: INSERT into `signals` with `status="LIVE"`, `alert_type="NEW_SETUP"`. Returns `signal_id`.
  - Rank B: INSERT with `status="WATCHLIST"`, `alert_type="NEW_SETUP"`. Returns `signal_id`.
  - Rank C/D: no `signals` insert. Returns `None`.
  - Always writes to `labels` table (all ranks). Sets `classifier_version = settings.classifier_name`.
  - SETUP_UPDATE: before inserting, query `signals` for an existing row with matching `ticker` and `alerted_at` within 24 hours. If found: UPDATE in-place, set `alert_type="SETUP_UPDATE"`. Return the existing `signal_id`.
- `close(signal_id: int, close_reason: str)`: sets `status="CLOSED"`, `closed_at=now()`, `close_reason=close_reason` on the signals row.
- `record_position(signal_id: int, entry_price: float | None, cover_price: float | None)`: updates `entry_price` and/or `cover_price` on the signals row. If both are set: computes `pnl_pct = (entry_price - cover_price) / entry_price * 100` (short P&L formula) and calls `close(signal_id, "MANUAL")`.
- `run_lifecycle_loop()` coroutine: wakes every `settings.lifecycle_check_interval` seconds, queries `signals` for LIVE/WATCHLIST rows where `alerted_at + hold_time[setup_type] < now()`, calls `close(id, "TIME_EXCEEDED")` for each. Hold times: A=3 days, B=2 days, C=1 day, D=None (skip), E=1 day.
- All DuckDB writes use `asyncio.to_thread(db.execute, ...)`.

**Done When**:
- [ ] Unit test: `emit()` with Rank A scorer result inserts one row in `signals` with `status="LIVE"` and one row in `labels`.
- [ ] Unit test: `emit()` with Rank C scorer result inserts zero rows in `signals` but one row in `labels`.
- [ ] Unit test: calling `emit()` twice with same ticker within 24 hours produces one `signals` row with `alert_type="SETUP_UPDATE"`, not two rows.
- [ ] Unit test: `record_position(id, entry_price=5.20, cover_price=4.26)` computes `pnl_pct ≈ 18.08` and sets `status="CLOSED"`.
- [ ] Unit test: `record_position(id, entry_price=5.20, cover_price=None)` updates `entry_price` but does not close the signal.
- [ ] Unit test: lifecycle checker transitions a LIVE Setup A signal with `alerted_at` > 3 days ago to `status="TIME_EXCEEDED"`.
- [ ] Unit test: lifecycle checker does NOT auto-close a Setup D signal regardless of elapsed time.

---

### Slice 12: Pipeline Integration

**Goal**: Wire all backend services into a single `process_filing()` pipeline function and register it with FastAPI's asyncio lifespan in `app/main.py`.

**Depends On**: Slices 2, 3, 5, 6, 7, 8, 9, 10, 11

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/main.py` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/services/edgar_poller.py` — modify: replace the stub `process_filing` with a call to the full pipeline function

**Implementation Notes**:
- `app/main.py` defines the `lifespan` context manager (per 02-ARCHITECTURE.md Section 8): calls `init_db()`, instantiates `EdgarPoller`, creates `asyncio.create_task(poller.run_forever())`, and creates `asyncio.create_task(signal_manager.run_lifecycle_loop())`.
- `process_filing(accession_number, cik, form_type, filed_at, filing_url)` is a coroutine that executes the full pipeline in order:
  1. Write PENDING row to `filings`.
  2. Resolve ticker (TickerResolver); if UNRESOLVABLE, set `filter_status=UNRESOLVABLE` and return.
  3. Call `FilingFetcher.fetch(filing_url)` to get `filing_text`.
  4. Call `FMPClient.get_market_data(ticker)` to get `fmp_data` (may be None on failure).
  5. Call `FilterEngine.evaluate(...)`. If `FilterOutcome.passed is False`: update `filings.filter_status=FILTERED_OUT` and return.
  6. Call `DilutionService.get_dilution_data_v2(ticker)` for `ask_edgar_data` (AskEdgar enrichment — only called after all six filters pass; may be partial; non-blocking).
  7. Call `get_classifier().classify(filing_text, form_type)` to get `ClassificationResult`.
  8. If `setup_type == "NULL"`: update `filings.processing_status=CLASSIFIED` and return (no score, no signal).
  9. Call `Scorer.score(classification, fmp_data, ask_edgar_data, borrow_cost)`.
  10. Call `SignalManager.emit(scorer_result, classification, fmp_data, accession_number, ticker)`.
  11. Update `filings.processing_status=ALERTED`.
- All exceptions within `process_filing` are caught and logged; they update `filings.processing_status=ERROR` and do not propagate to the poller loop.
- `create_app()` registers all routers (Slice 13) and creates the FastAPI app with the `lifespan` parameter.

**Done When**:
- [ ] `uvicorn app.main:app --reload` starts without error (even with no API routes yet — a bare `FastAPI(lifespan=lifespan)` startup).
- [ ] Integration test: call `process_filing()` directly with a fixture filing record (real or mocked services). Verify the `filings` row transitions from PENDING to ALERTED (or to FILTERED_OUT if the fixture filing fails the filter).
- [ ] The `run_forever` poller loop calls the full `process_filing` pipeline (not the stub) for each new EDGAR entry.
- [ ] Both asyncio tasks (poller and lifecycle checker) are started in `lifespan` and cancelled cleanly on shutdown (verify with `asyncio.CancelledError` handling).
- [ ] `GET /health` (before routes are wired in Slice 13) is the only endpoint; it should return a minimal 200 response from a startup-only route added in `main.py` for testing.
- [ ] AskEdgar degradation integration test: call `process_filing()` with `DilutionService.get_dilution_data_v2` patched to raise `ExternalAPIError`. Verify that the pipeline continues (does not raise), the `filings` row has `askedgar_partial=True`, the `market_data` row has `data_source='PARTIAL'`, and a score and signal are still produced using FMP-only data.

---

### Slice 13: API Routes

**Goal**: Implement all six API routes in `app/api/v1/routes.py` and register them in `app/main.py`.

**Depends On**: Slices 2, 4, 11, 12

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/api/__init__.py` — new (empty)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/api/v1/__init__.py` — new (empty)
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/api/v1/routes.py` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/app/main.py` — modify: add `app.include_router(v1_router, prefix="/api/v1")`

**Implementation Notes**:
- All six routes from Section 5 of 02-ARCHITECTURE.md:
  - `GET /signals` — queries `signals` WHERE `status IN ('LIVE','WATCHLIST')`; computes `price_move_pct` and `elapsed_seconds` before returning; returns `SignalListResponse`.
  - `GET /signals/closed` — queries `signals` WHERE `status IN ('CLOSED','TIME_EXCEEDED')` ORDER BY `closed_at DESC` LIMIT 50; returns `SignalListResponse`.
  - `GET /signals/{id}` — queries `signals` JOIN `labels` JOIN `filings` for a single signal; returns `SignalDetailResponse`.
  - `POST /signals/{id}/position` — accepts `PositionRequest`, calls `SignalManager.record_position()`; returns `PositionResponse`.
  - `POST /signals/{id}/close` — calls `SignalManager.close(id, "MANUAL")`; returns updated `SignalDetailResponse`.
  - `GET /health` — reads from `EdgarPoller` instance properties and `settings`; returns `HealthResponse`. Status logic: "ok" if `last_success_at < 3min ago`, "degraded" if 3-10min ago, "error" if >10min ago or `last_success_at is None`.
- Route order matters in FastAPI: `GET /signals/closed` must be registered BEFORE `GET /signals/{id}` to avoid `/closed` being matched as an `id` parameter.
- All DuckDB queries use `asyncio.to_thread(db.execute, ...)`.
- `price_move_pct` is computed as `(current_price - price_at_alert) / price_at_alert * 100` using a fresh FMP call (or cached within the request scope). If FMP data unavailable: returns `None`.
- Return HTTP 404 if signal `id` does not exist. Return HTTP 422 on invalid `PositionRequest` (Pydantic validates automatically).

**Done When**:
- [ ] `GET /api/v1/health` returns `{"status": "ok", ...}` (or "error" if no polls yet) with all `HealthResponse` fields populated.
- [ ] `GET /api/v1/signals` returns `{"signals": [], "count": 0}` with an empty database.
- [ ] `GET /api/v1/signals/closed` returns `{"signals": [], "count": 0}` with an empty database.
- [ ] `GET /api/v1/signals/{id}` with a non-existent id returns HTTP 404.
- [ ] `POST /api/v1/signals/{id}/position` with `{"cover_price": 0.005}` returns HTTP 422.
- [ ] End-to-end: insert a test signal directly into DuckDB, then `GET /api/v1/signals` returns it in the response.
- [ ] `GET /api/v1/signals/closed` does not shadow `GET /api/v1/signals/{id}` (verify that `/signals/closed` returns a list, not a 404 for id "closed").

---

### Slice 14: Frontend Shell

**Goal**: Build the dashboard root page with the three-panel layout, `Header` component (updated for this app), `HealthBar` component, and empty states for all panels. No signal data yet.

**Depends On**: Slices 1, 13

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/app/page.tsx` — new (replaces ticker-lookup root page)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/app/layout.tsx` — extend (update title to "Dilution Short Filter", update metadata)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/app/globals.css` — extend (preserve dark theme CSS vars; add new CSS vars: `--rank-a` through `--rank-e`, `--bg-card-hover`, `--bg-input`, `--border-input`, `--positive`, `--negative`, `--warning`, spacing tokens per UI spec Section 1.1-1.3)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/Header.tsx` — extend (update title text to "DILUTION SHORT FILTER" with accent; remove ticker search input; add right-side slot for HealthBar)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/HealthBar.tsx` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/LiveNowPanel.tsx` — new (shell + empty state only)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/WatchlistPanel.tsx` — new (shell + empty state only)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/RecentClosedPanel.tsx` — new (shell + empty state only)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/services/api.ts` — new (replaces dilution.ts; implements `getSignals()`, `getClosedSignals()`, `getHealth()`, `getSignalDetail()`, `recordPosition()`, `closeSignal()` using `AbortController` pattern)

**Implementation Notes**:
- `page.tsx` renders: `<Header>`, `HealthBar` (inside header), `LiveNowPanel`, `WatchlistPanel`, `RecentClosedPanel`. Fixed-width 960px centered layout per UI spec Section 3.1.
- `HealthBar` polls `GET /api/v1/health` every 15 seconds (own interval). Renders the status dot (8px circle) and "Last poll: Xs ago" elapsed counter (updates client-side every 1 second from `last_success_at` timestamp). All four dot states from UI spec Section 6.2.
- API warning banner: if `HealthResponse.fmp_configured == false`, show the banner between header and Live Now panel (per UI spec Section 8.5).
- Each panel renders four states: Loading (skeleton rows), Empty, Error, Data. At this slice, only Loading and Empty states need to work; Data state uses empty arrays.
- All three panels each have their own fetch of `/api/v1/signals` (for Live Now and Watchlist) and `/api/v1/signals/closed` (for Recent Closed). Data state handled independently per panel per UI spec Section 8.

**Done When**:
- [ ] `npm run dev` starts without TypeScript errors.
- [ ] Dashboard loads at `http://localhost:3000` and shows the three panels in their empty states ("No active setups", "No setups on watchlist", "No closed setups yet").
- [ ] `HealthBar` renders the status dot and "Last poll: Xs ago" text; dot transitions to Error state when the API is not reachable.
- [ ] The FMP API warning banner appears when `fmp_configured: false` is returned from `/health`.
- [ ] Header shows "DILUTION SHORT" in white and "FILTER" in `--accent-cyan`.
- [ ] Dark theme is applied: page background is `#1a1a1a`, card background is `#2d2d2d`.
- [ ] No TypeScript compilation errors (`npx tsc --noEmit` passes).

---

### Slice 15: Signal Rows + Auto-Refresh

**Goal**: Implement the `SignalRow` component for all three panel variants and wire the 30-second auto-refresh loop with no-flash update behavior.

**Depends On**: Slice 14

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/SignalRow.tsx` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/LiveNowPanel.tsx` — modify (add Data state with SignalRows)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/WatchlistPanel.tsx` — modify (add Data state with SignalRows)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/RecentClosedPanel.tsx` — modify (add Data state with SignalRows)

**Implementation Notes**:
- `SignalRow` accepts a `panelType: "live" | "watchlist" | "closed"` prop and renders accordingly:
  - Live Now variant: ticker, setup type badge, score, price_move_pct, elapsed time (UI spec Section 4.1).
  - Watchlist variant: ticker, setup type badge, score, status label (derived per mapping in UI spec Section 4.2), elapsed time.
  - Closed variant: ticker, setup type badge, P&L, entry→cover prices, close reason (UI spec Section 4.3).
- Setup type badge: `[A]` pill with badge background at 20% opacity, full-opacity border, badge text — colors per UI spec Section 1.5.
- Row behaviors: hover state `--bg-card-hover`, cursor pointer. New arrival animation for Live Now only (background pulse `#1a3a3a` → `--bg-card` over 3 seconds on mount, once per new id). Implementation note: track previously-seen ids in a ref to fire animation only on genuinely new rows.
- Price move coloring: negative percentage = `--positive` (favorable short); positive = `--negative` (per UI spec Section 4.1 — note the inversion).
- Auto-refresh: `page.tsx` uses `setInterval(30000)` (or `NEXT_PUBLIC_REFRESH_INTERVAL_MS`) to re-fetch `/api/v1/signals` and `/api/v1/signals/closed`. Replace state data in-place without blanking panels (no-flash per UI spec Section 7.2). Rows sorted by score descending (Live Now, Watchlist) and by `closed_at` descending (Closed) before render.
- Each row is clickable (entire row); click handler opens `SetupDetailModal` (Slice 16) passing the signal id. At this slice, the click can be a `console.log(id)` placeholder.

**Done When**:
- [ ] With test data injected directly into DuckDB (a LIVE signal with Rank A), `LiveNowPanel` renders a `SignalRow` showing the ticker, badge `[A]`, score, and elapsed time.
- [ ] With a WATCHLIST signal, `WatchlistPanel` renders the watchlist variant with the correct status label.
- [ ] With a CLOSED signal, `RecentClosedPanel` renders the closed variant.
- [ ] After the 30-second interval fires, the panels update without a visible flash (verify by watching the dev tools Network tab and the UI).
- [ ] A new row added to the Live Now panel triggers the `#1a3a3a` → `--bg-card` background pulse animation exactly once.
- [ ] A row with `price_move_pct = -12.4` renders the percentage in `--positive` (green), not red.
- [ ] No TypeScript compilation errors.

---

### Slice 16: Setup Detail + Position Tracking

**Goal**: Implement `SetupDetailModal` (slide-in panel with all 8 classification fields and market data snapshot) and `PositionForm` (all 3 position states), wired to `POST /signals/{id}/position` and `POST /signals/{id}/close`.

**Depends On**: Slice 15

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/SetupDetailModal.tsx` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/PositionForm.tsx` — new
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/components/SignalRow.tsx` — modify (replace console.log placeholder with modal open handler)
- `/home/d-tuned/projects/gap-lens-dilution-filter/frontend/src/app/page.tsx` — modify (add SetupDetailModal rendered at root level, passing selectedSignalId state and close handler)

**Implementation Notes**:
- `SetupDetailModal` structure follows UI spec Section 5 exactly: slide-in from right, 480px wide, fixed position, backdrop overlay, vertical scroll internally.
- On open: fetches `GET /api/v1/signals/{id}` for `SignalDetailResponse`. Shows spinner while loading, error state on failure.
- Close triggers: X button in panel header, or click on backdrop.
- Panel sections (per UI spec Section 5.3): Filing Info, Classification Output (all 8 fields from `ClassificationDetail`), Market Data Snapshot, Position Tracking.
- `key_excerpt` renders as a blockquote: left border 3px `--accent-cyan`, italic, monospace 12px.
- `PositionForm` renders State A (no entry), State B (entry recorded, not covered), or State C (closed) based on `signal.entry_price` and `signal.cover_price`.
- State A: entry price input + "Record Entry" button + "Close Without Position" secondary button.
- State B: shows entry price, live P&L computation as user types cover price, "Close Position" button.
- State C: read-only display of both prices, P&L, closed_at, close_reason.
- Validation: entry price must be > 0; cover price must be at least $0.01. Inline error below field: "Entry price must be greater than $0.00" / "Cover price must be at least $0.01".
- On successful position record: panel updates to new state without closing or reloading the main dashboard.
- "Close Without Position" calls `POST /api/v1/signals/{id}/close`; on success, modal closes and the row moves from Live Now or Watchlist to Recent Closed on the next refresh cycle.

**Done When**:
- [ ] Clicking a signal row opens the `SetupDetailModal` with a loading spinner, then the full detail view.
- [ ] All 8 classification fields display correctly with their labels.
- [ ] `key_excerpt` renders with the cyan left border blockquote styling.
- [ ] `PositionForm` State A is shown for a signal with no entry price.
- [ ] Entering a valid entry price and clicking "Record Entry" transitions the form to State B without closing the modal.
- [ ] In State B, typing a cover price updates the live P&L display.
- [ ] Clicking "Close Position" with a valid cover price transitions to State C (read-only) and the signal appears in Recent Closed on the next 30s refresh.
- [ ] Attempting to submit entry price `0` displays the inline validation error "Entry price must be greater than $0.00".
- [ ] Attempting to submit cover price `0.005` displays the inline validation error "Cover price must be at least $0.01".
- [ ] Clicking backdrop closes the modal.
- [ ] No TypeScript compilation errors.

---

### Slice 17: End-to-End Smoke Test

**Goal**: Run the full pipeline with a real (or replayed) EDGAR filing and verify the signal appears on the dashboard within 5 minutes.

**Depends On**: Slices 12, 13, 16

**Files Created or Modified**:
- `/home/d-tuned/projects/gap-lens-dilution-filter/tests/test_e2e_smoke.py` — new

**Implementation Notes**:
- This slice produces a documented manual or semi-automated test script, not a fully mocked unit test.
- The test:
  1. Starts the FastAPI server (`uvicorn app.main:app`).
  2. Starts the Next.js dev server (`npm run dev` in `frontend/`).
  3. Either (a) waits for the EDGAR poller to pick up a real live filing, or (b) calls `process_filing()` directly with a fixture accession number and URL pointing to a known qualifying 424B2 or S-1 filing from EDGAR.
  4. Verifies that within 5 minutes, a signal row appears in `GET /api/v1/signals`.
  5. Loads the dashboard at `http://localhost:3000` and confirms the signal appears in Live Now or Watchlist.
  6. Clicks the row and verifies the `SetupDetailModal` opens with all 8 classification fields populated.
  7. Enters an entry price of `$5.00` and verifies State B of `PositionForm`.
  8. Enters a cover price of `$4.00` and verifies State C with `P&L: +20.0%`.
  9. Verifies the signal appears in Recent Closed.
- Document the chosen test filing (accession number, form type, expected classification) in a comment block at the top of `test_e2e_smoke.py`.
- If live EDGAR access is not available at test time: use a replayed EFTS JSON fixture, injecting a known accession number directly into `process_filing()`.

**Done When**:
- [ ] `GET /api/v1/health` returns `status: "ok"` after at least one successful EDGAR poll.
- [ ] A qualifying filing (real or fixture) produces a signal in `GET /api/v1/signals` with a valid `setup_type`, `score`, and `rank`.
- [ ] The signal is visible on the dashboard within 5 minutes of the filing being ingested.
- [ ] The `SetupDetailModal` opens and displays all 8 classification fields.
- [ ] The full position tracking flow (State A → B → C) completes successfully and the signal appears in Recent Closed.
- [ ] DuckDB contains the expected rows in `filings`, `filter_results`, `market_data`, `labels`, and `signals` tables.
- [ ] No unhandled exceptions appear in the FastAPI server logs during the test run.

---

## Deferred (Not This Roadmap)

The following items are explicitly out of scope for Phase 1. They must not be implemented in any slice above.

- Phase 2 ML classifier (Llama 3.2 1B, NIMClassifier, LoRA fine-tuning)
- Teacher labeling pipeline (GPT-4 or Claude 3.5 historical labeling)
- KDB-X data layer (DuckDB is the sole persistence layer in Phase 1)
- Interactive Brokers live borrow cost feed (default of 0.30 is used; the `ibkr_borrow_cost_enabled` config key is wired but the integration is not implemented)
- Email or Discord alert delivery (dashboard notification only)
- Mobile-responsive layout (desktop 960px optimized)
- Full historical backtest engine
- GPU acceleration
- Portfolio position sizing (NVIDIA Quant Portfolio Opt)
- User authentication or multi-user accounts
- Data export or CSV download
- Sector or industry filters beyond the six defined criteria
- Fly-wheel retraining pipeline

---

## File Ownership Summary

Each file is owned by exactly one slice. No file appears in more than one "created" list (modification is allowed in a later slice, noted explicitly).

| File | Created In | Modified In |
|------|-----------|-------------|
| `app/__init__.py` | Slice 1 | — |
| `app/core/__init__.py` | Slice 1 | — |
| `app/core/config.py` | Slice 1 | Slice 3 |
| `app/models/__init__.py` | Slice 1 | — |
| `app/models/responses.py` | Slice 1 | — |
| `app/services/__init__.py` | Slice 1 | — |
| `app/services/dilution.py` | Slice 1 | — (never modified) |
| `app/utils/__init__.py` | Slice 1 | — |
| `app/utils/errors.py` | Slice 1 | Slices 5, 6 (add new exception types) |
| `app/utils/formatting.py` | Slice 1 | — |
| `app/utils/validation.py` | Slice 1 | — |
| `requirements.txt` | Slice 1 | Slice 3 |
| `frontend/package.json` | Slice 1 | — |
| `frontend/tsconfig.json` | Slice 1 | — |
| `frontend/src/app/globals.css` | Slice 1 | Slice 14 |
| `.env` | Slice 1 | — |
| `.gitignore` | Slice 1 | — |
| `data/.gitkeep` | Slice 1 | — |
| `app/services/db.py` | Slice 2 | — |
| `app/models/signals.py` | Slice 4 | — |
| `frontend/src/types/signals.ts` | Slice 4 | — |
| `app/services/fmp_client.py` | Slice 5 | — |
| `app/services/filing_fetcher.py` | Slice 6 | — |
| `app/services/edgar_poller.py` | Slice 7 | Slice 12 |
| `app/services/filter_engine.py` | Slice 8 | — |
| `app/services/classifier/__init__.py` | Slice 9 | — |
| `app/services/classifier/protocol.py` | Slice 9 | — |
| `app/services/classifier/rule_based.py` | Slice 9 | — |
| `app/services/scorer.py` | Slice 10 | — |
| `app/services/signal_manager.py` | Slice 11 | — |
| `app/main.py` | Slice 12 | Slice 13 |
| `app/api/__init__.py` | Slice 13 | — |
| `app/api/v1/__init__.py` | Slice 13 | — |
| `app/api/v1/routes.py` | Slice 13 | — |
| `frontend/src/app/page.tsx` | Slice 14 | Slice 16 |
| `frontend/src/app/layout.tsx` | Slice 14 | — |
| `frontend/src/components/Header.tsx` | Slice 14 | — |
| `frontend/src/components/HealthBar.tsx` | Slice 14 | — |
| `frontend/src/components/LiveNowPanel.tsx` | Slice 14 | Slice 15 |
| `frontend/src/components/WatchlistPanel.tsx` | Slice 14 | Slice 15 |
| `frontend/src/components/RecentClosedPanel.tsx` | Slice 14 | Slice 15 |
| `frontend/src/services/api.ts` | Slice 14 | — |
| `frontend/src/components/SignalRow.tsx` | Slice 15 | Slice 16 |
| `frontend/src/components/SetupDetailModal.tsx` | Slice 16 | — |
| `frontend/src/components/PositionForm.tsx` | Slice 16 | — |
| `tests/test_e2e_smoke.py` | Slice 17 | — |
