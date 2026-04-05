# Requirements: dilution-short-filter

- **Project**: gap-lens-dilution-filter
- **Phase**: Phase 1 (Rule-Based Pipeline)
- **Status**: Approved for spec
- **Date**: 2026-04-04
- **Author**: @requirements-analyst

---

## Summary

The dilution-short-filter is a proactive SEC filing scanner and dilution short alert system. It continuously polls EDGAR for new filings, applies a six-criterion filter, classifies each passing filing into one of five setup types (A-E) using a rule-based classifier, scores short attractiveness using a defined formula, and surfaces ranked alerts on a real-time dashboard. It is built as a new project derived from gap-lens-dilution and must be architected so the rule-based classifier can be replaced with a fine-tuned Llama 3.2 1B model in Phase 2 without restructuring the pipeline.

---

## User Stories

### US-01: EDGAR Filing Ingestion
As a trader,
I want the system to automatically detect new relevant SEC filings as they appear on EDGAR,
so that I do not need to manually monitor EDGAR for dilution events.

### US-02: Filing Filter
As a trader,
I want each detected filing to be automatically tested against six filter criteria (filing type, market cap, float, dilution percentage, price, and average daily volume),
so that only actionable, liquid, small-cap dilution events reach my attention.

### US-03: Setup Classification
As a trader,
I want each filing that passes the filter to be classified into a setup type (A: IPO/Primary, B: Shelf Tap, C: Priced Deal, D: ATM Active, E: Warrant Exercise, or NULL for non-matching),
so that I can immediately understand the nature and expected behavior of the dilution event.

### US-04: Short Attractiveness Scoring
As a trader,
I want each classified setup to receive a numeric short attractiveness score (0-100) computed from dilution severity, float illiquidity, setup quality, and borrow cost,
so that I can prioritize my attention and capital on the highest-conviction opportunities.

### US-05: Rank-A Alert
As a trader,
I want to receive an immediate alert when a setup scores above 80 (Rank A),
so that I can act on high-urgency setups within minutes of the filing appearing on EDGAR.

### US-06: Watchlist Visibility
As a trader,
I want setups scoring 60-80 (Rank B) to appear on a watchlist section of the dashboard,
so that I can monitor developing situations that are not yet at entry-level urgency.

### US-07: Dashboard Overview
As a trader,
I want a single-page dashboard showing Live Now (score > 80), Watchlist (score 60-80), and Recent Closed sections,
so that I can survey all active and recent dilution setups at a glance without switching contexts.

### US-08: Setup Detail View
As a trader,
I want to click into any setup to see its full classification output — setup type, confidence, dilution severity, immediate pressure flag, price discount, score, key excerpt from the filing, and reasoning —
so that I can validate the system's classification before deciding to act.

### US-09: Position Tracking (Manual Entry)
As a trader,
I want to record a short entry price and cover price for any setup on the dashboard,
so that I can track my P&L on closed positions without leaving the application.

### US-10: Setup Lifecycle Management
As a trader,
I want setups to transition automatically from Live Now to Recent Closed when I mark them as covered, or when their expected hold time elapses,
so that the dashboard does not accumulate stale alerts.

### US-11: Alert Type Differentiation
As a trader,
I want alerts to distinguish between new setup detection, setup update (pricing announced or terms changed), and time-exceeded notifications,
so that I understand at a glance why a notification was generated.

### US-12: Market Data Enrichment
As a trader,
I want each filing to be enriched with current float, market cap, price, and average daily volume from FMP,
so that the filter criteria and scoring formula use accurate, live market data.

### US-13: AskEdgar Enrichment
As a trader,
I want each passing filing to be supplemented with AskEdgar dilution data (float/outstanding, registration history, dilution rating),
so that dilution severity and setup context are grounded in structured filing-derived data.

### US-14: Classifier Abstraction for Phase 2 Readiness
As a developer,
I want the classification step to be implemented behind a ClassifierProtocol interface,
so that the rule-based Phase 1 classifier can be replaced with a fine-tuned Llama 3.2 1B model in Phase 2 without modifying any other part of the pipeline.

### US-15: Training Data Logging
As a developer,
I want every filing processed by the system — along with its rule-based classification output and market data snapshot — to be persisted in DuckDB,
so that the stored records can serve as a training dataset for the Phase 2 fine-tuned model.

### US-16: Polling Health Visibility
As a trader,
I want to see the last successful EDGAR poll timestamp and current system status on the dashboard,
so that I know immediately if the ingestion pipeline has stalled or fallen behind.

---

## Acceptance Criteria

### AC-01: EDGAR Filing Ingestion

- [ ] Given the EDGAR EFTS JSON endpoint is reachable, when the poller runs, then it fetches and parses all new filings published since the last poll.
- [ ] Given the poller has run successfully, when the next poll executes, then only filings with a publication timestamp after the previous poll are processed (no duplicates).
- [ ] Given a filing has been seen before (matched by accession number), when it appears again in the feed, then it is skipped without re-processing.
- [ ] Given the EDGAR feed is unreachable, when the poller attempts to fetch, then it retries up to 3 times with exponential backoff before logging a failure and moving on.
- [ ] Given the system is running continuously, when a filing is published on EDGAR, then the system ingests it within 5 minutes of publication.
- [ ] The poller interval is configurable via environment variable with a default of 90 seconds.

### AC-02: Filing Filter

- [ ] Given a new filing is ingested, when evaluated against Filter 1, then only filings of types S-1, S-1/A, S-3, 424B2, 424B4, 8-K, and 13D/A containing at least one of the following offering-language keywords pass: 'offering', 'shares', 'prospectus', 'at-the-market', 'sales agent', 'underwritten', 'priced'.
- [ ] Given a filing passes Filter 1, when evaluated against Filter 2, then only tickers with FMP market cap strictly less than $2,000,000,000 pass.
- [ ] Given a filing passes Filter 2, when evaluated against Filter 3, then only tickers with float strictly less than 50,000,000 shares pass.
- [ ] Given a filing passes Filter 3, when evaluated against Filter 4, then only filings where computed dilution percentage exceeds 10% pass.
- [ ] Given a filing passes Filter 4, when evaluated against Filter 5, then only tickers with current price strictly greater than $1.00 pass.
- [ ] Given a filing passes Filter 5, when evaluated against Filter 6, then only tickers with average daily volume (dollar value) strictly greater than $500,000 pass.
- [ ] Given a filing fails any filter criterion, when logged, then the record is stored in DuckDB with the specific failing criterion noted and a status of FILTERED_OUT.
- [ ] All six filter criteria must be evaluated in order; evaluation stops at the first failure.

### AC-03: Setup Classification

- [ ] Given a filing passes all six filters, when the rule-based classifier runs, then it returns a classification result conforming to the ClassifierProtocol output schema.
- [ ] Given a filing with form type S-1 or S-1/A containing keywords "effective date" or "commence offering", when classified, then setup_type is A.
- [ ] Given a filing with form type 424B4 containing keywords "supplement" or "takedown", when classified, then setup_type is B.
- [ ] Given a filing with form type 424B2 containing keywords "priced" or "underwritten", when classified, then setup_type is C.
- [ ] Given a filing with form type 8-K containing keywords "at-the-market" or "sales agent", when classified, then setup_type is D.
- [ ] Given a filing with form type 13D/A or S-1 containing keywords "cashless exercise" or "warrant", when classified, then setup_type is E.
- [ ] Given a filing passes all filters but no rule matches any setup pattern, when classified, then setup_type is NULL and the filing is not surfaced on the dashboard.
- [ ] The rule-based classifier returns a confidence value; for Phase 1 rule-based logic, confidence is 1.0 on a match and 0.0 on NULL.
- [ ] Given the ClassifierProtocol interface is defined, when a mock classifier implementing the same interface is substituted in tests, then the rest of the pipeline executes without modification.

### AC-04: Short Attractiveness Scoring

- [ ] Given a classification result with setup_type A-E, when the scorer runs, then it computes SCORE = (DILUTION_SEVERITY x FLOAT_ILLIQUIDITY x SETUP_QUALITY) / BORROW_COST.
- [ ] DILUTION_SEVERITY is computed as shares_offered / pre_float, sourced from the filing and AskEdgar/FMP data.
- [ ] FLOAT_ILLIQUIDITY is computed as `settings.adv_min_threshold / fmp_data.adv_dollar`, where `adv_min_threshold` is the configured ADV filter threshold (default $500,000). A stock with ADV exactly at the filter threshold scores 1.0; more liquid stocks score lower.
- [ ] SETUP_QUALITY is the configured historical win rate for the matched setup type and is a configurable value per setup type stored in application config. Phase 1 default values (A: 0.65, B: 0.55, C: 0.60, D: 0.45, E: 0.50) are initial estimates only — not derived from historical data. These values represent a plausible starting range; actual win rates may be higher or lower depending on market conditions and entry timing. They must be treated as placeholders to be calibrated after the system has operated for a sufficient period. Phase 2 will derive these values from actual trade history stored in DuckDB.
- [ ] Given Interactive Brokers borrow cost data is unavailable, when scoring, then BORROW_COST defaults to a configurable default value (default: 0.30 annualized, i.e., 30%).
- [ ] Given BORROW_COST would produce a divide-by-zero, when scoring, then the system uses the configured default and logs a warning.
- [ ] The raw SCORE value is normalized to a 0-100 integer scale before assignment of rank.
- [ ] Given a computed score, when ranked, then scores above 80 receive Rank A, 60-80 receive Rank B, 40-60 receive Rank C, and below 40 receive Rank D.
- [ ] Rank D setups are stored in DuckDB but are not surfaced on the dashboard or sent as alerts.

### AC-05: Rank-A Alerts

- [ ] Given a setup receives Rank A (score > 80), when scored, then an alert event is emitted within the same processing cycle.
- [ ] Given an alert is emitted, when delivered, then it includes: ticker symbol, setup type, score, key excerpt, and timestamp of filing.
- [ ] The alert mechanism is extensible; Phase 1 must support at minimum an in-app dashboard notification (no email or Discord required in Phase 1).
- [ ] Given a Rank A setup has already triggered an alert, when the same accession number is re-encountered, then no duplicate alert is emitted.

### AC-06: Watchlist Visibility

- [ ] Given a setup receives Rank B (score 60-80), when processed, then it appears in the Watchlist section of the dashboard.
- [ ] Given a Rank B setup's underlying filing is updated (e.g., pricing announced), when re-evaluated, then the score is recalculated and rank updated accordingly.

### AC-07: Dashboard Overview

- [ ] Given the dashboard is loaded, when rendered, then it displays three distinct sections: Live Now (Rank A, score > 80), Watchlist (Rank B, score 60-80), and Recent Closed.
- [ ] Given there are active Rank A setups, when displayed in Live Now, then each row shows: ticker, setup type, score, percentage price move since alert time, and elapsed time since alert.
- [ ] Given there are active Rank B setups, when displayed in Watchlist, then each row shows: ticker, setup type, score, and a status label.
- [ ] Given there are closed setups, when displayed in Recent Closed, then each row shows: ticker, setup type, entry price (if recorded), cover price (if recorded), and percentage P&L (if both prices recorded).
- [ ] The dashboard uses the dark theme design system (background #1a1a1a, card background #2d2d2d, text primary #ffffff, accent #00bcd4, border #444444) consistent with gap-lens-dilution.
- [ ] The dashboard displays the last successful EDGAR poll timestamp and a system status indicator.
- [ ] The dashboard refreshes active setup data automatically at a configurable interval (default: 30 seconds) without a full page reload.

### AC-08: Setup Detail View

- [ ] Given a user clicks on any setup row in the dashboard, when the detail view opens, then it displays all fields from the ClassifierProtocol output schema: setup_type, confidence, dilution_severity, immediate_pressure, price_discount, short_attractiveness, key_excerpt, and reasoning.
- [ ] Given a setup detail view is open, when market data has been refreshed since the setup was created, then both the original-at-alert values and current values are shown for price and score.

### AC-09: Position Tracking

- [ ] Given a user views a setup detail, when they submit an entry price (numeric, greater than $0.00), then it is persisted to DuckDB against that setup's record.
- [ ] Given a user has recorded an entry price, when they submit a cover price (numeric, greater than $0.01), then the P&L percentage is computed and displayed, and the setup is marked as closed.
- [ ] Given a setup is marked as closed, when displayed, then it moves from Live Now or Watchlist to Recent Closed.
- [ ] Entry and cover prices are stored in USD with up to four decimal places.

### AC-10: Setup Lifecycle Management

- [ ] Given a setup's expected hold time has elapsed (based on setup type: A = 3 days, B = 2 days, C = 1 day, D = ongoing/manual close only, E = 1 day), when the lifecycle checker runs, then the setup transitions to a TIME_EXCEEDED status and moves to Recent Closed with a note.
- [ ] Given a setup is manually closed (cover price entered), when saved, then it transitions immediately to Recent Closed regardless of hold time.
- [ ] Lifecycle transitions are recorded with a timestamp in DuckDB.

### AC-11: Alert Type Differentiation

- [ ] Given a new filing passes the full pipeline, when an alert is generated, then the alert type is NEW_SETUP.
- [ ] Given a filing matches a ticker already in the pipeline and the setup terms have changed (different shares_offered or price_discount), when processed, then the alert type is SETUP_UPDATE and the existing record is updated.
- [ ] Given a setup's hold time has elapsed, when the lifecycle checker transitions it, then a TIME_EXCEEDED notification is generated.

### AC-12: Market Data Enrichment

- [ ] Given a filing passes Filter 1 (filing type match), when enrichment runs, then the system queries FMP for float, market cap, current price, and 20-day average dollar volume for the associated ticker.
- [ ] Given FMP returns data for a ticker, when enrichment completes, then float, market cap, price, and ADV are stored in the DuckDB market_data table with a timestamp.
- [ ] Given FMP returns a 429 or 5xx response, when enrichment runs, then the system retries up to 3 times with exponential backoff before recording a DATA_UNAVAILABLE status for the affected filter criteria.
- [ ] Given FMP data is unavailable for a ticker, when filter evaluation continues, then the affected filter criteria are treated as failing (conservative default: do not pass a filing with missing critical data).

### AC-13: AskEdgar Enrichment

- [ ] Given a filing passes all six filters, when AskEdgar enrichment runs, then the system calls the existing DilutionService to fetch dilution rating, float/outstanding, and registrations for the ticker.
- [ ] Given AskEdgar returns data, when stored, then the enrichment snapshot is persisted in DuckDB alongside the filing record.
- [ ] Given AskEdgar is unavailable, when enrichment runs, then the system continues to scoring using FMP-only data and records a partial enrichment flag on the filing record.
- [ ] The DilutionService is used as-is from the gap-lens-dilution codebase with no modifications.

### AC-14: Classifier Abstraction

- [ ] A ClassifierProtocol interface is defined that accepts a filing text string and returns a classification result dict matching the defined output schema.
- [ ] The rule-based classifier implements ClassifierProtocol.
- [ ] The pipeline instantiates the classifier via a factory or dependency injection mechanism; no pipeline code references the concrete rule-based class directly.
- [ ] Given ClassifierProtocol is defined, when a stub implementation is injected in unit tests, then all pipeline stages downstream of classification pass without modification.

### AC-15: Training Data Logging

- [ ] Given any filing is processed by the pipeline (whether it passes or fails the filter), when processing completes, then a record is written to DuckDB including: accession number, CIK, form type, filed datetime, full filing text (or URL), filter pass/fail result and reason, classification output (if applicable), scoring output (if applicable), and a market data snapshot at time of processing.
- [ ] Given a filing record exists in DuckDB, when queried, then it includes all fields required by the ClassifierProtocol output schema so it can serve as a labeled training example.

### AC-16: Polling Health Visibility

- [ ] Given the dashboard is loaded, when displayed, then the header or status bar shows the timestamp of the last successful EDGAR poll.
- [ ] Given the most recent EDGAR poll failed or the last success was more than 10 minutes ago, when the status is displayed, then the indicator changes to a visually distinct error or warning state (e.g., red badge).

---

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Filing matches multiple setup type patterns (e.g., S-1 with both IPO language and warrant exercise language) | Apply the first matching rule in precedence order A > E > B > C > D; log all matched patterns for training data |
| Ticker symbol cannot be resolved to a CIK (EDGAR filing lacks a ticker in the header) | Log the filing as UNRESOLVABLE; skip enrichment and filter; do not surface alert |
| FMP returns market cap >= $2B for a ticker but AskEdgar float data implies small-cap | FMP is authoritative for market cap; filing fails Filter 2 |
| Dilution percentage cannot be computed because shares_offered is not extractable from the filing via keyword matching | Treat dilution % as unknown; filing fails Filter 4 (conservative default) |
| Score computation results in a value outside the 0-100 normalized range due to extreme inputs | Clamp to [0, 100]; log a data quality warning with the raw pre-normalization value |
| BORROW_COST from Interactive Brokers is returned as zero | Substitute the configured default borrow cost; log a warning to avoid divide-by-zero |
| The same company files multiple qualifying forms in rapid succession (e.g., S-1 followed by S-1/A within minutes) | Each is processed independently; the S-1/A updates the existing record if the same deal is identified by matching ticker + approximate filing date |
| A setup is already in Live Now when a SETUP_UPDATE alert fires for the same ticker | Update the existing record in-place; do not create a duplicate dashboard row; re-sort by updated score |
| User attempts to enter a cover price lower than $0.01 | Reject with a validation error; display inline message: "Cover price must be at least $0.01" |
| EDGAR EFTS endpoint returns malformed or unparseable JSON | Log a parse error with the raw response excerpt (first 500 bytes); skip the poll cycle; retry on next scheduled poll |
| FMP API key is missing or invalid on startup | System starts but enrichment fails for every filing; dashboard displays a prominent API key configuration warning |
| Setup type is D (ATM Active, hold time: ongoing) and no manual close is entered | Setup remains in Live Now indefinitely; no automatic lifecycle transition to Recent Closed |
| A filing's key_excerpt extracted by the rule-based classifier exceeds 500 characters | Truncate to 500 characters before storing; store the full text in the filing record for training data |

---

## Out of Scope (Phase 1)

- NOT: ML-based classifier (Llama 3.2 1B, LoRA fine-tuning, NVIDIA NIM serving) — deferred to Phase 2
- NOT: Teacher labeling pipeline (GPT-4 or Claude 3.5 labeling of historical filings) — deferred to Phase 2
- NOT: KDB-X data layer — Phase 1 uses DuckDB exclusively
- NOT: Automated trade execution or broker order routing — the system surfaces signals only; manual trade entry
- NOT: Email or Discord alert delivery — Phase 1 dashboard notification only
- NOT: Mobile-responsive design — desktop-optimized only, consistent with gap-lens-dilution
- NOT: Full historical backtest engine — forward-only paper alerting in Phase 1
- NOT: GPU acceleration — CPU is sufficient for rule-based classification
- NOT: Portfolio position sizing optimization (NVIDIA Quant Portfolio Opt integration) — future phase
- NOT: Interactive Brokers borrow cost live feed (optional P1 integration; system falls back to default if unavailable) — Phase 1 defaults are acceptable
- NOT: User authentication or multi-user accounts — single-user deployment, no auth layer
- NOT: Data export or CSV download — view-only dashboard
- NOT: Modification of the existing gap-lens-dilution repository — new project only, original repo unchanged
- NOT: Sector or industry filters beyond the six defined criteria — no sector exclusions in Phase 1
- NOT: Fly-wheel retraining pipeline — data is logged, but automated retraining is Phase 2

---

## Constraints

- Must: Alert latency from EDGAR publication to dashboard display must be under 5 minutes under normal operating conditions.
- Must: The classifier must implement ClassifierProtocol so Phase 2 is a drop-in swap at one seam with no pipeline changes.
- Must: All six filter criteria must pass for a filing to reach the classifier; partial passes are not permitted.
- Must: Use DuckDB as the sole data persistence layer in Phase 1.
- Must: Use the existing DilutionService from gap-lens-dilution unchanged for AskEdgar API calls.
- Must: Use FMP Ultimate API (fmp_api_key already in config.py) for float, market cap, price, and ADV data; do not use Finviz or Ortex in Phase 1.
- Must: Preserve the dark theme design system (#1a1a1a background, #2d2d2d card, #ffffff text, #00bcd4 accent) from gap-lens-dilution in the new frontend.
- Must: Store every processed filing record in DuckDB (both filtered-out and scored) to support future ML training data needs.
- Must not: Modify the gap-lens-dilution source repository; all development is in the new gap-lens-dilution-filter project directory.
- Must not: Make scope decisions that require GPU hardware in Phase 1; all Phase 1 processing runs on CPU.
- Must not: Surface Rank D setups (score < 40) on the dashboard or in any alert channel.
- Assumes: EDGAR EFTS JSON endpoint (efts.sec.gov/LATEST/search-index) remains publicly accessible and continues to index S-1, S-3, 424B2, 424B4, 8-K, and 13D/A form types.
- Assumes: FMP Ultimate API provides float, market cap, price, and ADV data for all small-cap US equities that appear in EDGAR filings; if a ticker is not in FMP, it is treated as failing data-dependent filter criteria.
- Assumes: The SETUP_QUALITY (historical win rate per setup type) values used in scoring are pre-populated as configuration constants in Phase 1, not derived from live trade history (which does not yet exist).
- Assumes: Interactive Brokers borrow cost integration is optional in Phase 1; the system must function correctly using the default borrow cost if IBKR data is not configured.
- Assumes: A single deployment serves one user; there are no concurrent user session or multi-tenancy requirements in Phase 1.

---

## Data Requirements

### DuckDB Tables (High-Level Schema)

#### filings
Stores every filing ingested from EDGAR, regardless of filter outcome.

| Column | Type | Description |
|--------|------|-------------|
| accession_number | TEXT (PK) | EDGAR accession number (unique per filing) |
| cik | TEXT | Company CIK |
| ticker | TEXT | Resolved ticker symbol (nullable) |
| form_type | TEXT | S-1, 424B2, 8-K, etc. |
| filed_at | TIMESTAMP | EDGAR publication datetime (UTC) |
| ingested_at | TIMESTAMP | System ingestion datetime (UTC) |
| filing_url | TEXT | Full EDGAR filing document URL |
| filing_text | TEXT | Raw extracted text for classifier input |
| filter_status | TEXT | PASSED, FILTERED_OUT, UNRESOLVABLE |
| filter_fail_reason | TEXT | Criterion label if filtered out (nullable) |
| processing_status | TEXT | PENDING, ENRICHED, CLASSIFIED, SCORED, ALERTED, ERROR |
| askedgar_partial | BOOLEAN | True if AskEdgar enrichment failed and only FMP data was used |
| all_matched_patterns | TEXT | JSON array of all classifier rule patterns that matched (for training data) |

#### filter_results
One record per filing per filter criterion evaluated.

| Column | Type | Description |
|--------|------|-------------|
| accession_number | TEXT (FK) | |
| criterion | TEXT | FILING_TYPE, MARKET_CAP, FLOAT, DILUTION_PCT, PRICE, ADV |
| passed | BOOLEAN | |
| value_observed | REAL | Actual value at time of evaluation (nullable) |
| evaluated_at | TIMESTAMP | |

#### market_data
FMP data snapshot at time of filing evaluation.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK, auto) | |
| ticker | TEXT | |
| snapshot_at | TIMESTAMP | |
| price | REAL | Current price (USD) |
| market_cap | REAL | Market cap (USD) |
| float_shares | REAL | Float shares count |
| adv_dollar | REAL | 20-day average dollar volume |
| data_source | TEXT | FMP, ASKEDGAR, or PARTIAL |
| accession_number | TEXT | EDGAR accession number (nullable FK to filings); populated when market data is fetched as part of a filing's pipeline run; allows direct join to the filing record without a date-proximity query |

#### labels
Classification and scoring output per filing.

| Column | Type | Description |
|--------|------|-------------|
| accession_number | TEXT (FK) | |
| classifier_version | TEXT | e.g., "rule-based-v1" or "llama-1b-v1" (Phase 2) |
| setup_type | TEXT | A, B, C, D, E, or NULL |
| confidence | REAL | 0.0 to 1.0 |
| dilution_severity | REAL | shares_offered / pre_float |
| immediate_pressure | BOOLEAN | |
| price_discount | REAL | Offering price / last close - 1 (nullable) |
| short_attractiveness | INTEGER | 0-100 |
| rank | TEXT | A, B, C, or D |
| key_excerpt | TEXT | Up to 500 characters |
| reasoning | TEXT | One-sentence explanation |
| scored_at | TIMESTAMP | |

#### signals
Active and closed alert signals surfaced to the dashboard.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK, auto) | |
| accession_number | TEXT (FK) | |
| ticker | TEXT | |
| setup_type | TEXT | |
| score | INTEGER | |
| rank | TEXT | |
| alert_type | TEXT | NEW_SETUP, SETUP_UPDATE, TIME_EXCEEDED |
| status | TEXT | LIVE, WATCHLIST, CLOSED, TIME_EXCEEDED |
| alerted_at | TIMESTAMP | |
| price_at_alert | REAL | Price at time of alert (from FMP) |
| entry_price | REAL | User-entered short entry price (nullable) |
| cover_price | REAL | User-entered cover price (nullable) |
| pnl_pct | REAL | Computed P&L percentage (nullable) |
| closed_at | TIMESTAMP | Nullable |
| close_reason | TEXT | MANUAL, TIME_EXCEEDED, nullable |

#### poll_state
Internal single-row table holding the most recent EDGAR poller state. Always contains exactly one row (`id=1`), updated in-place on each poll cycle.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER (PK) | Always 1 (single-state row) |
| last_poll_at | TIMESTAMP | When the most recent poll attempt ran (UTC) |
| last_success_at | TIMESTAMP | When the most recent successful poll completed (UTC, nullable) |

#### cik_ticker_map
CIK-to-ticker lookup table populated from SEC `company_tickers_exchange.json`. Refreshed once per day on startup. Used by `TickerResolver` for the primary CIK resolution step.

| Column | Type | Description |
|--------|------|-------------|
| cik | INTEGER (PK) | SEC Central Index Key (no leading zeros) |
| ticker | TEXT | Exchange-listed ticker symbol |
| name | TEXT | Company name |
| exchange | TEXT | Exchange (e.g., "Nasdaq", "NYSE") |

---

## Integration Requirements

### EDGAR EFTS Feed
- Source: EDGAR full-text search (EFTS) JSON endpoint — `https://efts.sec.gov/LATEST/search-index?forms=S-1,S-1%2FA,S-3,424B2,424B4,8-K,13D%2FA&startdt={startdt}&enddt={today}&from={offset}`
- Poll interval: Configurable, default 90 seconds
- Response format: **JSON** (not XML/RSS). Key fields per hit: `accessionNo`, `cik`, `formType`, `filedAt` (ISO 8601), `entityName`, `ticker` (nullable). Pagination via `from=` offset, max 100 per page.
- Date handling: `startdt` = `MAX(last_poll_at::date, today - 1)` from `poll_state`; first run uses `today - 1`.
- Required request header: `User-Agent: gap-lens-dilution-filter contact@yourdomain.com` (SEC rate-limit enforcement).
- Rate limit: 10 requests per second.
- Deduplication: by `accessionNo` against the `filings` table (`accession_number` column)

### AskEdgar API (DilutionService — reused unchanged)
- Endpoints used: /enterprise/v1/dilution-rating, /enterprise/v1/float-outstanding, /enterprise/v1/registrations, /enterprise/v1/dilution-data
- Authentication: API-KEY header from settings.askedgar_api_key
- Retry logic: 3 retries with exponential backoff (already implemented in DilutionService)
- Cache TTL: 30 minutes (already implemented in DilutionService)
- Usage pattern: Called after all six filter criteria pass. AskEdgar enrichment is never triggered before Filter 6 completes — this prevents unnecessary paid API calls for filings that will be filtered out.

### FMP Ultimate API
- Endpoints used:
  - `/v3/quote/{ticker}` — price (field: `price`), market cap (field: `marketCap`), volume (field: `volume`), average volume (field: `avgVolume`)
  - `/v4/shares_float?symbol={ticker}` — float shares (field: `floatShares`)
  - `/v3/historical-price-full/{ticker}?timeseries=20` — 20 daily bars; ADV computed as `sum(close * volume) / 20` (dollar-volume average, not share-volume average)

  Note: Two API calls are required per ticker (quote + shares_float). No single FMP endpoint returns all required fields.
- Authentication: apikey query parameter from settings.fmp_api_key
- Rate limit handling: Retry up to 3 times on 429; log failure and treat data as unavailable
- Usage pattern: Called for every filing that passes Filter 1 to supply filter criteria 2, 3, 5, and 6

### Interactive Brokers API (Optional, Phase 1)
- Purpose: Retrieve annualized borrow cost for a ticker to use in the scoring formula
- If not configured: System uses default borrow cost of 0.30 (30% annualized)
- Integration is optional; absence must not block any other pipeline function

---

## Phase 2 Accommodation Requirements

The following requirements ensure Phase 1 is built in a way that does not require refactoring when Phase 2 ML classifier is introduced:

1. ClassifierProtocol must be defined as a formal Python Protocol class (or ABC) with a single classify(filing_text: str) -> ClassificationResult method signature before any classifier implementation is written.
2. The pipeline must instantiate classifiers by name via a registry or factory, not by direct import of the concrete rule-based class.
3. Every filing record written to DuckDB must include the raw filing_text field (or a stable URL pointing to the full text) so it can be used as input to Phase 2 teacher labeling without re-fetching from EDGAR.
4. The labels table must include a classifier_version column so Phase 1 rule-based labels and Phase 2 model-generated labels can coexist in the same table for comparison.
5. The ClassificationResult data structure must be identical to the Phase 2 output schema (setup_type, confidence, dilution_severity, immediate_pressure, price_discount, short_attractiveness, key_excerpt, reasoning) so downstream scoring and alerting code requires no changes in Phase 2.
