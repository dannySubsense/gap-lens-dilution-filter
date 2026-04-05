# Architecture: dilution-short-filter

- **Project**: gap-lens-dilution-filter
- **Phase**: Phase 1 (Rule-Based Pipeline)
- **Status**: APPROVED
- **Date**: 2026-04-04
- **Author**: @architect

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         DILUTION SHORT FILTER SYSTEM                             │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────┐ │
│  │  FastAPI Backend (asyncio)                                                  │ │
│  │                                                                             │ │
│  │  ┌──────────────┐  poll EFTS JSON every 90s                                  │ │
│  │  │ EdgarPoller  │──────────────────────► EDGAR EFTS JSON (efts.sec.gov)      │ │
│  │  └──────┬───────┘                                                           │ │
│  │         │ new accession numbers                                             │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐                                                           │ │
│  │  │FilingFetcher │──────────────────────► EDGAR document URL                 │ │
│  │  └──────┬───────┘ filing text                                               │ │
│  │         │                                                                   │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐  Filter 1: filing type (no API)                           │ │
│  │  │FilterEngine  │  Filter 2-6: FMP market data                              │ │
│  │  └──────┬───────┘                                                           │ │
│  │         │ passed filings only          FMPClient ──► FMP Ultimate API       │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐                                                           │ │
│  │  │DilutionSvc   │──────────────────────► AskEdgar API (unchanged)           │ │
│  │  └──────┬───────┘ enrichment data                                           │ │
│  │         │                                                                   │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────────────────────────┐                                       │ │
│  │  │ ClassifierProtocol               │                                       │ │
│  │  │  get_classifier("rule-based-v1") │  Phase 2: "llama-1b-v1" added here    │ │
│  │  └──────┬───────────────────────────┘                                       │ │
│  │         │ ClassificationResult                                              │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐                                                           │ │
│  │  │    Scorer    │  SCORE = (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY ×         │ │
│  │  └──────┬───────┘           SETUP_QUALITY) / BORROW_COST → 0-100 int       │ │
│  │         │ rank A/B/C/D                                                      │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐  Rank A → LIVE signal + dashboard alert                   │ │
│  │  │SignalManager │  Rank B → WATCHLIST signal                                │ │
│  │  └──────┬───────┘  Rank C/D → DuckDB only, no dashboard                    │ │
│  │         │                                                                   │ │
│  │         ▼                                                                   │ │
│  │  ┌──────────────┐                                                           │ │
│  │  │   DuckDB     │  7 tables: filings, filter_results, market_data,          │ │
│  │  │  (db.py)     │  labels, signals, poll_state, cik_ticker_map              │ │
│  │  └──────────────┘                                                           │ │
│  │                                                                             │ │
│  │  API Layer: GET/POST /api/v1/signals, /api/v1/health                        │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
│                         │ HTTP (localhost:8000)                                  │
│  ┌──────────────────────▼──────────────────────────────────────────────────────┐ │
│  │  Next.js Frontend (TypeScript, dark theme)                                  │ │
│  │                                                                             │ │
│  │  Dashboard (auto-refresh 30s)                                               │ │
│  │  ├── HealthBar (last poll time, status indicator)                           │ │
│  │  ├── LiveNowPanel (Rank A signals)                                          │ │
│  │  ├── WatchlistPanel (Rank B signals)                                        │ │
│  │  └── RecentClosedPanel                                                      │ │
│  │       └── SetupDetailModal (classification output + position form)          │ │
│  └─────────────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory and File Structure

Legend: `[COPY]` = copied unchanged from gap-lens-dilution, `[EXTEND]` = copied and modified, `[NEW]` = new file.

```
/home/d-tuned/projects/gap-lens-dilution-filter/
├── .env                                    [NEW] — new env vars (see Section 9)
├── requirements.txt                        [EXTEND] — adds duckdb, lxml, aiofiles
├── app/
│   ├── __init__.py                         [COPY]
│   ├── main.py                             [EXTEND] — registers background poller on startup
│   ├── core/
│   │   ├── __init__.py                     [COPY]
│   │   └── config.py                       [EXTEND] — adds FMP, poller, scoring config keys
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py                 [NEW]
│   │       └── routes.py                   [NEW] — signals, health, position endpoints
│   ├── models/
│   │   ├── __init__.py                     [COPY]
│   │   ├── responses.py                    [COPY] — existing Pydantic models, unchanged
│   │   └── signals.py                      [NEW] — Signal, FilingRecord, FilterResult models
│   ├── services/
│   │   ├── __init__.py                     [COPY]
│   │   ├── dilution.py                     [COPY] — DilutionService, used unchanged
│   │   ├── edgar_poller.py                 [NEW] — EDGAR EFTS JSON polling loop
│   │   ├── filing_fetcher.py               [NEW] — fetch and parse filing document text
│   │   ├── filter_engine.py                [NEW] — 6-criterion filter pipeline
│   │   ├── fmp_client.py                   [NEW] — FMP Ultimate API client
│   │   ├── scorer.py                       [NEW] — SCORE formula + rank assignment
│   │   ├── signal_manager.py               [NEW] — alert lifecycle, status transitions
│   │   ├── db.py                           [NEW] — DuckDB connection + table init
│   │   └── classifier/
│   │       ├── __init__.py                 [NEW] — exports get_classifier factory
│   │       ├── protocol.py                 [NEW] — ClassifierProtocol + ClassificationResult
│   │       └── rule_based.py               [NEW] — RuleBasedClassifier (implements Protocol)
│   └── utils/
│       ├── __init__.py                     [COPY]
│       ├── errors.py                       [COPY] — existing error types, unchanged
│       ├── formatting.py                   [COPY]
│       ├── validation.py                   [COPY]
│       └── ticker_resolver.py              [NEW] — TickerResolver; CIK→ticker, cik_ticker_map cache
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css                 [EXTEND] — preserves dark theme vars, adds dashboard CSS
│   │   │   ├── layout.tsx                  [EXTEND] — updates page title and metadata
│   │   │   └── page.tsx                    [NEW] — dashboard root (replaces ticker-lookup)
│   │   ├── components/
│   │   │   ├── Header.tsx                  [EXTEND] — updated title, removes ticker search
│   │   │   ├── HealthBar.tsx               [NEW] — last poll time, status indicator
│   │   │   ├── LiveNowPanel.tsx            [NEW] — Rank A signal rows
│   │   │   ├── WatchlistPanel.tsx          [NEW] — Rank B signal rows
│   │   │   ├── RecentClosedPanel.tsx       [NEW] — closed signal rows
│   │   │   ├── SignalRow.tsx               [NEW] — shared row component for all panels
│   │   │   ├── SetupDetailModal.tsx        [NEW] — full classification output view
│   │   │   └── PositionForm.tsx            [NEW] — entry/cover price form
│   │   ├── services/
│   │   │   └── api.ts                      [NEW] — replaces dilution.ts with signals API client
│   │   └── types/
│   │       └── signals.ts                  [NEW] — TypeScript interfaces for all API responses
│   ├── package.json                        [COPY]
│   └── tsconfig.json                       [COPY]
└── docs/
    └── specs/
        └── dilution-short-filter/
            ├── 01-REQUIREMENTS.md
            └── 02-ARCHITECTURE.md          [THIS FILE]
```

---

## 3. Backend Service Layer

### 3.1 EdgarPoller (`app/services/edgar_poller.py`)

**Responsibility**: Continuously poll the EDGAR full-text search (EFTS) JSON endpoint, parse new accession numbers, deduplicate against DuckDB, and hand each new filing to the processing pipeline.

**Inputs**: Poll interval from `settings.edgar_poll_interval` (default 90s), last poll timestamp from `poll_state` table in DuckDB.

**Outputs**: Calls `process_filing(accession_number, cik, form_type, filed_at, filing_url)` for each new unique filing.

**Dependencies**: `httpx.AsyncClient`, `app.services.db`, `app.core.config`.

**Key behaviors**:
- Tracks `_last_poll_at` (UTC datetime) and `_last_success_at` in-memory; persisted to DuckDB `poll_state` on each success.
- Retries up to 3 times with exponential backoff (1s, 2s, 4s) on EDGAR unreachable.
- On malformed or unexpected JSON response: logs raw excerpt, skips cycle, does not crash.
- EFTS endpoint (returns **JSON**, not XML/RSS):
  ```
  GET https://efts.sec.gov/LATEST/search-index?forms=S-1,S-1%2FA,S-3,424B2,424B4,8-K,13D%2FA&startdt={startdt}&enddt={today}&from={offset}
  ```
  Required headers: `User-Agent: gap-lens-dilution-filter contact@yourdomain.com` (SEC requirement for automated access — IP may be blocked without this)
  Rate limit: 10 requests per second.
- Date parameter handling:
  - `startdt` = `MAX(last_poll_at::date, today - 1 day)` (from `poll_state` table, or `today - 1` on first run)
  - `enddt` = today's date in `YYYY-MM-DD` format
  - Deduplication is still required: overlapping date windows with MAX logic may return previously seen accession numbers
- Response JSON structure:
  ```json
  {
    "total": { "value": 42, "relation": "eq" },
    "hits": [
      {
        "_source": {
          "accessionNo": "0000065011-21-000020",
          "cik": "65011",
          "entityName": "COMPANY NAME",
          "formType": "S-1",
          "filedAt": "2026-01-08T16:31:36-05:00",
          "ticker": "ACME"
        }
      }
    ]
  }
  ```
- Key parsing notes:
  - Field name is `accessionNo` (not `accession_number`)
  - `cik` has no leading zeros — pad to 10 digits with `zfill(10)` for EDGAR filing URL construction
  - `ticker` field is absent for many filers (foreign private issuers, SPACs pre-listing) — do NOT rely on it for ticker resolution
  - `filedAt` is ISO 8601 datetime with timezone offset
  - Pagination: max 100 results per page; use `from=` offset parameter for pagination
  - Filing URL construction: `https://www.sec.gov/Archives/edgar/data/{cik}/{accessionNo_no_dashes}/{primary_doc}`
- Exposes `last_poll_at: datetime | None` and `last_success_at: datetime | None` as instance properties for the health endpoint.

---

### 3.2 FilingFetcher (`app/services/filing_fetcher.py`)

**Responsibility**: Given a filing URL, fetch the full document from EDGAR and extract plain text for classifier input.

**Inputs**: `filing_url: str`

**Outputs**: `filing_text: str` (raw text, up to a configured max bytes; default 500 KB).

**Dependencies**: `httpx.AsyncClient`, `lxml` or stdlib `html.parser` for HTML stripping.

**Key behaviors**:
- Strips HTML tags; preserves whitespace structure.
- Truncates to `settings.filing_text_max_bytes` (default 512000) before returning.
- Raises `FilingFetchError` on network failure after 3 retries.

#### CIK-to-Ticker Resolution (`app/utils/ticker_resolver.py`)

EDGAR filing headers identify companies by CIK. Ticker resolution uses the following fallback chain:

1. **Primary:** SEC `company_tickers_exchange.json` — `https://www.sec.gov/files/company_tickers_exchange.json`
   - Format: `{"fields": ["cik","name","ticker","exchange"], "data": [[320193,"Apple Inc.","AAPL","Nasdaq"],...]}`
   - Downloaded once per day on system startup, cached in DuckDB as a `cik_ticker_map` table (columns: `cik INTEGER`, `ticker TEXT`, `name TEXT`, `exchange TEXT`)
   - Covers ~10,000 exchange-listed companies; many small-cap EDGAR filers will NOT be in this file
   - `cik` in this file lacks leading zeros; normalize before comparison

2. **Fallback 1:** EFTS response `ticker` field — present when the SEC has mapped the CIK to a ticker. Check this field on the incoming EFTS hit before looking up the map.

3. **Fallback 2:** FMP company name search — query FMP `/v3/search?query={entity_name}&limit=1` and match on exact or close company name. Only use if the above two fail.

4. **Fallback 3:** Log as `UNRESOLVABLE` — store the filing in DuckDB with `ticker=NULL` and `filter_status=UNRESOLVABLE`. Do not attempt enrichment or filtering.

Implement as `TickerResolver` utility class in `app/utils/ticker_resolver.py`.

`TickerResolver.refresh()` is called from the FastAPI `lifespan` startup handler in `app/main.py`, after `init_db()` completes. It must NOT be called from within `init_db()` — mixing HTTP calls into the database initialization function creates unexpected side effects and makes unit testing harder.

---

### 3.3 FMPClient (`app/services/fmp_client.py`)

**Responsibility**: Fetch market data (quote, float, ADV) from the FMP Ultimate API for a given ticker.

**Inputs**: `ticker: str`

**Outputs**: `FMPMarketData` (dataclass: price, market_cap, float_shares, adv_dollar, fetched_at).

**Dependencies**: `httpx.AsyncClient`, `app.core.config.settings.fmp_api_key`.

**Key behaviors**:
- Endpoints used:
  - `GET /v3/quote/{ticker}` — returns `price`, `marketCap`, `volume`, `avgVolume`. Use for filter criteria 2 (market cap), 5 (price), and 6 (ADV as a fallback).
  - `GET /v4/shares_float?symbol={ticker}` — returns `floatShares`. Use for filter criterion 3 (float). Note: This is a separate endpoint from `/v3/profile`.
  - `GET /v3/historical-price-full/{ticker}?timeseries=20` — returns 20 daily OHLCV bars. Compute ADV as `sum(close * volume) / 20` (dollar-volume, not share-volume). Use for filter criterion 6 (ADV > $500K).
- Two API calls are made per ticker on enrichment: `/v3/quote` and `/v4/shares_float`. The historical endpoint is called only when `avgVolume * price` is insufficient to determine ADV (i.e., when a quick estimate from quote data is needed vs. a precise 20-day dollar-volume calculation). Document which ADV method is used as a field in `market_data.data_source`.
- Retries up to 3 times on 429 or 5xx with exponential backoff.
- On FMP key missing at startup: logs a warning; all enrichment calls return `None`, causing filter criteria 2/3/5/6 to fail conservatively.
- Raises `FMPDataUnavailableError` when data cannot be obtained after retries.

---

### 3.4 FilterEngine (`app/services/filter_engine.py`)

**Responsibility**: Apply the six filter criteria in order and record each result in DuckDB.

**Inputs**: `accession_number`, `form_type`, `filing_text`, `ticker`, `fmp_data: FMPMarketData | None`, `ask_edgar_dilution_pct: float | None`.

Note: `ask_edgar_dilution_pct` is an optional parameter included for re-evaluation scenarios only. During the primary pipeline flow, this parameter is `None` at filter time — AskEdgar enrichment runs after all six filter criteria pass (per US-13 / AC-13). When `ask_edgar_dilution_pct` is `None`, Filter 4 uses dilution percentage extracted from the filing text via keyword parsing. This avoids a contradiction between the filter sequence and the AskEdgar enrichment trigger.

**Outputs**: `FilterOutcome` (dataclass: passed: bool, fail_criterion: str | None).

**Dependencies**: `app.services.db`, `app.core.config`.

**Filter order and stop-on-fail**:

| # | Criterion | Source | Threshold |
|---|-----------|--------|-----------|
| 1 | Filing type match | form_type + keyword scan in filing_text | S-1/S-1A/S-3/424B2/424B4/8-K/13D/A with offering keywords |
| 2 | Market cap | FMP market_cap | < $2,000,000,000 |
| 3 | Float | FMP float_shares | < 50,000,000 |
| 4 | Dilution % | shares_offered / FMP float_shares | > 10% |
| 5 | Price | FMP price | > $1.00 |
| 6 | ADV | FMP adv_dollar | > $500,000 |

**Key behaviors**:
- Filter 1 runs before any API calls.
- If FMP data unavailable, filters 2/3/5/6 fail conservatively with criterion label `DATA_UNAVAILABLE`.
- Writes one record to `filter_results` per criterion evaluated; stops writing after first failure.
- If ticker cannot be resolved from filing header: sets `filter_status = UNRESOLVABLE` on filing record; no further processing.
- Filter 4 note: `shares_offered` is extracted from `filing_text` using the `SHARES_OFFERED_PATTERNS` regex list defined in Section 3.5.3. FilterEngine and RuleBasedClassifier both use this same shared extraction logic. Implement as a standalone utility function in `app/utils/` or in the classifier package's `__init__.py` so both callers can import it without circular imports.

---

### 3.5 Classifier Package (`app/services/classifier/`)

**Responsibility**: Define the `ClassifierProtocol` interface and implement `RuleBasedClassifier`. Provide the `get_classifier` factory.

#### 3.5.1 Protocol and TypedDict (`protocol.py`)

```python
from typing import Protocol, TypedDict


class ClassificationResult(TypedDict):
    setup_type: str           # "A", "B", "C", "D", "E", or "NULL"
    confidence: float         # 0.0 to 1.0
    dilution_severity: float  # final ratio: shares_offered / fmp_data.float_shares
                               # Classifier always returns 0.0; pipeline step 7.5 patches this
                               # to the real ratio before the Scorer is called. 0.0 only if
                               # shares_offered could not be extracted from the filing text.
    immediate_pressure: bool
    price_discount: float | None  # offering_price / last_close - 1
    short_attractiveness: int     # 0-100 (pre-scorer estimate; scorer may override)
    key_excerpt: str          # <= 500 characters
    reasoning: str            # one-sentence explanation


class ClassifierProtocol(Protocol):
    async def classify(
        self, filing_text: str, form_type: str
    ) -> ClassificationResult:
        ...
```

#### 3.5.2 Factory (`__init__.py`)

```python
from app.core.config import settings
from app.services.classifier.protocol import ClassifierProtocol
from app.services.classifier.rule_based import RuleBasedClassifier


def get_classifier(name: str | None = None) -> ClassifierProtocol:
    """
    Registry-based factory. Phase 2 adds 'llama-1b-v1' entry here only.
    No other pipeline code changes when Phase 2 classifier is introduced.
    """
    classifier_name = name or settings.classifier_name
    registry: dict[str, type[ClassifierProtocol]] = {
        "rule-based-v1": RuleBasedClassifier,
        # Phase 2: "llama-1b-v1": NIMClassifier,
    }
    if classifier_name not in registry:
        raise ValueError(f"Unknown classifier: {classifier_name!r}")
    return registry[classifier_name]()
```

#### 3.5.3 RuleBasedClassifier (`rule_based.py`)

**Responsibility**: Match filing text against pattern rules (form_type + keyword) to assign setup_type A-E or NULL.

**Inputs**: `filing_text: str`, `form_type: str`

**Outputs**: `ClassificationResult`

**Rules** (applied in precedence order A > E > B > C > D):

| Setup | Form Types | Required Keywords | confidence |
|-------|-----------|-------------------|------------|
| A | S-1, S-1/A | "effective date" OR "commence offering" | 1.0 |
| E | 13D/A, S-1 | "cashless exercise" OR "warrant" | 1.0 |
| B | 424B4 | "supplement" OR "takedown" | 1.0 |
| C | 424B2 | "priced" OR "underwritten" | 1.0 |
| D | 8-K | "at-the-market" OR "sales agent" | 1.0 |
| NULL | any | no rule matched | 0.0 |

**Key behaviors**:
- All keyword matching is case-insensitive.
- If multiple rules match (e.g. S-1 with both IPO and warrant language), the first in precedence order wins; all matched patterns logged to the filing record for training data.
- Extracts `key_excerpt`: first 500-character window containing the matched keyword.
- Sets `immediate_pressure = True` for setup types B, C; `False` for A, D, E.
- `price_discount` extraction: use the following patterns (try in order, use first match):
  ```python
  PRICE_PATTERNS = [
      r'at\s+\$(\d+\.?\d*)\s+per\s+share',
      r'offering\s+price\s+of\s+\$(\d+\.?\d*)',
      r'price\s+of\s+\$(\d+\.?\d*)\s+per\s+share',
      r'per\s+share\s+price\s+of\s+\$(\d+\.?\d*)',
      r'priced\s+at\s+\$(\d+\.?\d*)',
  ]
  # price_discount = (offering_price / last_close) - 1
  # If no pattern matches: price_discount = None (acceptable; field is optional)
  ```
- `shares_offered_raw: int` extraction (used to populate `ClassificationResult.dilution_severity` via pipeline step 7.5):
  The classifier extracts the raw share count from `filing_text` using the following regex patterns (try in order, first match wins):
  ```python
  SHARES_OFFERED_PATTERNS = [
      r'(\d[\d,]*)\s+shares?\s+of\s+common\s+stock',
      r'offering\s+of\s+(\d[\d,]*)\s+shares?',
      r'(\d[\d,]*)\s+shares?\s+(?:at|for|priced)',
      r'aggregate\s+of\s+(\d[\d,]*)\s+shares?',
      r'up\s+to\s+(\d[\d,]*)\s+shares?',
  ]
  # Post-processing: strip commas, convert to int
  # If no pattern matches: shares_offered_raw = 0 (filing will fail Filter 4 conservatively)
  ```
  The classifier stores this extracted integer on the `ClassificationResult` dict as a **transient field**
  `_shares_offered_raw: int` (underscore prefix signals it is a pipeline-internal value, not a stored field).
  The classifier always sets `dilution_severity = 0.0` in the returned `ClassificationResult` — the ratio
  is computed by the pipeline in step 7.5, not by the classifier. See Section 3.5.4 for the authoritative
  data path.

#### 3.5.4 Dilution Severity Resolution (Pipeline Step 7.5)

**This is the authoritative definition of where and how `dilution_severity` is computed.**

After step 7 (classify) and before step 9 (score), the pipeline executes an explicit resolution step:

```python
# Pipeline step 7.5 — resolve dilution_severity
shares_offered_raw: int = classification.get("_shares_offered_raw", 0)
if shares_offered_raw > 0 and fmp_data is not None and fmp_data.float_shares > 0:
    dilution_severity = min(shares_offered_raw / fmp_data.float_shares, 1.0)
else:
    dilution_severity = 0.0  # conservative; Filter 4 should have already blocked this path

classification["dilution_severity"] = dilution_severity
```

**Why the pipeline, not the classifier:**
- The classifier has `filing_text` but does NOT have `fmp_data.float_shares` — the FMP data is fetched
  at step 4, before classification. Passing `fmp_data` into the classifier would violate I-02
  (ClassifierProtocol must only receive `filing_text` and `form_type`).
- The Scorer reads `classification["dilution_severity"]` as an already-resolved float ratio. This
  contract is preserved. The Scorer never computes the ratio itself.
- The `labels` table write happens in `SignalManager.emit()` at step 10, which is after step 7.5.
  Therefore `labels.dilution_severity` always contains the final, real ratio — never 0.0 (unless
  shares_offered was genuinely not extractable, in which case the filing should have failed Filter 4).

**Clamping**: `dilution_severity` is clamped to `[0.0, 1.0]`. Values above 1.0 are clamped to 1.0
and logged as `DILUTION_SEVERITY_CLAMPED` with ticker and raw ratio.

**Transient field cleanup**: The `_shares_offered_raw` key is removed from the `ClassificationResult`
dict by step 7.5 before passing to the Scorer, so the Scorer and downstream consumers never see it.

> **S-3 classifier note**: S-3 filings pass Filter 1 (filing type match) but the classifier has no dedicated S-3 rule. An S-3 filing will classify as NULL unless it also contains keywords that match another setup rule (e.g., a shelf takedown filed as S-3 with "at-the-market" language would match setup type D via the 8-K rule only if the form_type check is bypassed — but form_type is part of the match condition, so a pure S-3 will always NULL). This is intentional: S-3s that do not exhibit specific offering language are not actionable. S-3 filings may contribute to training data as NULL examples.

---

### 3.6 Scorer (`app/services/scorer.py`)

**Responsibility**: Compute the normalized 0-100 short attractiveness score and assign rank.

**Inputs**: `ClassificationResult`, `FMPMarketData`, `borrow_cost: float`.

**Outputs**: `ScorerResult` (dataclass: score: int, rank: str).

**Formula**:
```
# DILUTION_SEVERITY is read from classification_result["dilution_severity"].
# This value is guaranteed to be the final resolved ratio (shares_offered / fmp_data.float_shares)
# patched into the ClassificationResult by pipeline step 7.5 before the Scorer is called.
# The Scorer never computes dilution_severity itself.
DILUTION_SEVERITY  = classification_result["dilution_severity"]
FLOAT_ILLIQUIDITY  = settings.adv_min_threshold / fmp_data.adv_dollar
# FLOAT_ILLIQUIDITY = ADV_MIN_THRESHOLD / adv_dollar where ADV_MIN_THRESHOLD is
# settings.adv_min_threshold (the $500,000 ADV filter threshold). A stock at
# exactly the threshold scores 1.0; more liquid stocks score lower.
SETUP_QUALITY      = settings.setup_quality[setup_type]  # configured per type
BORROW_COST        = borrow_cost (default settings.default_borrow_cost = 0.30)

raw_score = (DILUTION_SEVERITY * FLOAT_ILLIQUIDITY * SETUP_QUALITY) / BORROW_COST
normalized_score = clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)
```

**Worked examples**:

High-conviction (Rank A expected):
```
DILUTION_SEVERITY = 0.50
FLOAT_ILLIQUIDITY = 500000 / 600000 = 0.83
SETUP_QUALITY     = 0.65
BORROW_COST       = 0.30
RAW_SCORE         = (0.50 × 0.83 × 0.65) / 0.30 = 0.90
normalized_score  = clamp(int(0.90 / 1.0 * 100), 0, 100) = 90 → Rank A
```

Weak setup (Rank D expected):
```
DILUTION_SEVERITY = 0.25
FLOAT_ILLIQUIDITY = 500000 / 2000000 = 0.25
SETUP_QUALITY     = 0.55
BORROW_COST       = 0.30
RAW_SCORE         = (0.25 × 0.25 × 0.55) / 0.30 = 0.115
normalized_score  = clamp(int(0.115 / 1.0 * 100), 0, 100) = 11 → Rank D
```

**Rank thresholds**:
- score > 80 → Rank A (LIVE)
- 60 <= score <= 80 → Rank B (WATCHLIST)
- 40 <= score < 60 → Rank C (stored only)
- score < 40 → Rank D (stored only)

**Key behaviors**:
- If `BORROW_COST == 0.0`: substitute `settings.default_borrow_cost`, log warning.
- Normalization: `normalized_score = clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)` where `settings.score_normalization_ceiling` defaults to `1.0` and is configurable via `SCORE_NORMALIZATION_CEILING` env var.
- If normalized value exceeds 100: clamp to 100 and log data quality warning with raw value.
- Setup quality defaults per type (configurable via env):
  - A: 0.65, B: 0.55, C: 0.60, D: 0.45, E: 0.50

---

### 3.7 SignalManager (`app/services/signal_manager.py`)

**Responsibility**: Emit signals to DuckDB, manage status transitions, and run the lifecycle checker.

**Inputs**: `ScorerResult`, `ClassificationResult`, `FMPMarketData`, `accession_number`, `ticker`.

**Outputs**: Writes to `signals` and `labels` DuckDB tables. Returns `signal_id: int | None`.

**Key behaviors**:
- Rank A: inserts into `signals` with `status = LIVE`, `alert_type = NEW_SETUP`.
- Rank B: inserts with `status = WATCHLIST`, `alert_type = NEW_SETUP`.
- Rank C/D: writes only to `labels` and `filings`; no `signals` row.
- SETUP_UPDATE detection: if a signal with matching ticker and approximate filing date (within 24h) already exists in `signals`, updates in-place rather than inserting a new row; sets `alert_type = SETUP_UPDATE`.
- Lifecycle checker runs as a secondary asyncio task every 5 minutes:
  - For each LIVE or WATCHLIST signal: checks if `alerted_at + hold_time[setup_type]` has elapsed.
  - Hold times: A = 3 days, B = 2 days, C = 1 day, D = None (no auto-close), E = 1 day.
  - On expiry: sets `status = TIME_EXCEEDED`, `close_reason = TIME_EXCEEDED`, `closed_at = now()`.

---

### 3.8 DilutionService (`app/services/dilution.py`)

**Responsibility**: AskEdgar enrichment. Used unchanged from gap-lens-dilution.

The pipeline calls `DilutionService.get_dilution_data_v2(ticker)` after a filing passes all six filters. If AskEdgar is unavailable, the call returns a degraded result with null fields (already handled by `get_dilution_data_v2`'s `return_exceptions=True` gather pattern); the pipeline continues to scoring using FMP-only data and writes `data_source = PARTIAL` on the `market_data` row.

---

### 3.9 Database (`app/services/db.py`)

**Responsibility**: DuckDB connection management and schema initialization.

**Dependencies**: `duckdb` Python package.

**Key behaviors**:
- Singleton connection opened at app startup: `duckdb.connect(settings.duckdb_path)`.
- `init_db()` called once on startup; all CREATE TABLE statements use `IF NOT EXISTS`.
- All writes are synchronous (DuckDB is thread-safe for single-writer); poller calls `db.execute()` directly.
- Exposes `get_db() -> duckdb.DuckDBPyConnection` for use in route handlers.

---

## 4. ClassifierProtocol — Full Definition (Canonical)

This block in `app/services/classifier/protocol.py` is the single source of truth.

```python
from typing import Protocol, TypedDict


class ClassificationResult(TypedDict):
    setup_type: str           # "A", "B", "C", "D", "E", or "NULL"
    confidence: float         # 0.0 to 1.0; rule-based: 1.0 on match, 0.0 on NULL
    dilution_severity: float  # final ratio: shares_offered / fmp_data.float_shares,
                               # clamped [0.0, 1.0]. Classifier always returns 0.0;
                               # pipeline step 7.5 patches this to the real value before
                               # the Scorer is called. 0.0 only if shares_offered was
                               # not extractable (filing should have failed Filter 4).
    immediate_pressure: bool  # True for setup types B and C
    price_discount: float | None  # offering_price / last_close - 1; None if not extractable
    short_attractiveness: int     # 0-100; pre-scorer classifier estimate (scorer may override)
    key_excerpt: str          # <= 500 characters; truncated before storage
    reasoning: str            # one sentence


class ClassifierProtocol(Protocol):
    async def classify(
        self, filing_text: str, form_type: str
    ) -> ClassificationResult:
        """
        Classify a single filing.

        Args:
            filing_text: Raw text of the filing document (up to settings.filing_text_max_bytes).
            form_type:   EDGAR form type string (e.g. "S-1", "424B2", "8-K").

        Returns:
            ClassificationResult TypedDict.
        """
        ...
```

The factory in `app/services/classifier/__init__.py`:

```python
from app.core.config import settings
from app.services.classifier.protocol import ClassifierProtocol
from app.services.classifier.rule_based import RuleBasedClassifier


def get_classifier(name: str | None = None) -> ClassifierProtocol:
    classifier_name = name or settings.classifier_name
    registry: dict[str, type] = {
        "rule-based-v1": RuleBasedClassifier,
        # Phase 2: "llama-1b-v1": NIMClassifier,
    }
    if classifier_name not in registry:
        raise ValueError(f"Unknown classifier: {classifier_name!r}")
    return registry[classifier_name]()
```

The pipeline imports only `get_classifier`. It never imports `RuleBasedClassifier` directly.

---

## 5. API Routes

All routes live in `app/api/v1/routes.py` under the `/api/v1` prefix (registered in `main.py`).

| Method | Path | Purpose | Response Shape |
|--------|------|---------|----------------|
| GET | `/signals` | All active signals (LIVE + WATCHLIST) | `SignalListResponse` |
| GET | `/signals/{id}` | Signal detail with full classification output | `SignalDetailResponse` |
| GET | `/signals/closed` | Recent closed signals (last 50, desc by closed_at) | `SignalListResponse` |
| POST | `/signals/{id}/position` | Record entry or cover price | `PositionResponse` |
| POST | `/signals/{id}/close` | Manually close a signal | `SignalDetailResponse` |
| GET | `/health` | Last poll timestamp, system status | `HealthResponse` |

### Response Schemas (Pydantic models in `app/models/signals.py`)

```python
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class SignalRow(BaseModel):
    id: int
    accession_number: str
    ticker: str
    setup_type: str           # A, B, C, D, E, or NULL
    score: int
    rank: str                 # A, B, C, D
    alert_type: str           # NEW_SETUP, SETUP_UPDATE, TIME_EXCEEDED
    status: str               # LIVE, WATCHLIST, CLOSED, TIME_EXCEEDED
    alerted_at: datetime
    price_at_alert: Optional[float]
    entry_price: Optional[float]
    cover_price: Optional[float]
    pnl_pct: Optional[float]
    closed_at: Optional[datetime]
    close_reason: Optional[str]
    # For LIVE panel: computed from current price vs price_at_alert
    price_move_pct: Optional[float]
    elapsed_seconds: Optional[int]


class ClassificationDetail(BaseModel):
    setup_type: str
    confidence: float
    dilution_severity: float
    immediate_pressure: bool
    price_discount: Optional[float]
    short_attractiveness: int
    key_excerpt: str
    reasoning: str
    classifier_version: str
    scored_at: datetime


class SignalDetailResponse(BaseModel):
    signal: SignalRow
    ticker: str
    entity_name: str | None  # Company name from EFTS entityName; null for older records
    classification: ClassificationDetail
    filing_url: str
    form_type: str
    filed_at: datetime
    current_price: Optional[float] = None
    # Populated by a fresh FMP quote call when the detail endpoint is hit;
    # not from the stored market_data snapshot.


class SignalListResponse(BaseModel):
    signals: list[SignalRow]
    count: int

# elapsed_seconds computation (applied in GET /api/v1/signals handler before serialization):
# elapsed_seconds = int((datetime.now(timezone.utc) - signal.alerted_at).total_seconds())
# Computed server-side in the route handler before serialization; not stored in DuckDB.


class PositionRequest(BaseModel):
    entry_price: Optional[float] = None   # must be > 0 if provided
    cover_price: Optional[float] = None   # must be > 0.01 if provided


class PositionResponse(BaseModel):
    id: int
    entry_price: Optional[float]
    cover_price: Optional[float]
    pnl_pct: Optional[float]
    status: str


class HealthResponse(BaseModel):
    status: str              # "ok", "degraded", "error"
    last_poll_at: Optional[datetime]
    last_success_at: Optional[datetime]
    poll_interval_seconds: int
    fmp_configured: bool
    askedgar_configured: bool
    db_path: str
```

---

## 6. DuckDB Schema (CREATE TABLE Statements)

```sql
-- All tables initialized in app/services/db.py:init_db()

CREATE SEQUENCE IF NOT EXISTS filter_results_id_seq;
CREATE SEQUENCE IF NOT EXISTS market_data_id_seq;
CREATE SEQUENCE IF NOT EXISTS signals_id_seq;

CREATE TABLE IF NOT EXISTS cik_ticker_map (
    cik      INTEGER PRIMARY KEY,
    ticker   TEXT NOT NULL,
    name     TEXT,
    exchange TEXT
);
-- Populated from https://www.sec.gov/files/company_tickers_exchange.json on startup; refreshed daily by TickerResolver.

CREATE TABLE IF NOT EXISTS filings (
    accession_number     TEXT PRIMARY KEY,
    cik                  TEXT,
    ticker               TEXT,
    entity_name          TEXT,  -- Company name from EFTS response entityName field
    form_type            TEXT NOT NULL,
    filed_at             TIMESTAMP NOT NULL,
    ingested_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    filing_url           TEXT,
    filing_text          TEXT,
    filter_status        TEXT NOT NULL DEFAULT 'PENDING',
        -- values: PENDING, PASSED, FILTERED_OUT, UNRESOLVABLE
    filter_fail_reason   TEXT,
        -- criterion label if filtered out: FILING_TYPE, MARKET_CAP, FLOAT,
        --   DILUTION_PCT, PRICE, ADV, DATA_UNAVAILABLE
    processing_status    TEXT NOT NULL DEFAULT 'PENDING',
        -- values: PENDING, ENRICHED, CLASSIFIED, SCORED, ALERTED, ERROR
    askedgar_partial     BOOLEAN NOT NULL DEFAULT FALSE,
    all_matched_patterns TEXT
        -- JSON array of all matched setup patterns, for training data
);

CREATE TABLE IF NOT EXISTS filter_results (
    id                   INTEGER PRIMARY KEY DEFAULT nextval('filter_results_id_seq'),
    accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
    criterion            TEXT NOT NULL,
        -- FILING_TYPE, MARKET_CAP, FLOAT, DILUTION_PCT, PRICE, ADV
    passed               BOOLEAN NOT NULL,
    value_observed       REAL,
    evaluated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_data (
    id                   INTEGER PRIMARY KEY DEFAULT nextval('market_data_id_seq'),
    ticker               TEXT NOT NULL,
    snapshot_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    price                REAL,
    market_cap           REAL,
    float_shares         REAL,
    adv_dollar           REAL,
    data_source          TEXT NOT NULL DEFAULT 'FMP',
        -- values: FMP, ASKEDGAR, PARTIAL
    accession_number     TEXT
        -- EDGAR accession number (nullable FK to filings); direct join key
);

CREATE TABLE IF NOT EXISTS labels (
    accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
    classifier_version   TEXT NOT NULL,
        -- "rule-based-v1" (Phase 1); "llama-1b-v1" added in Phase 2
        -- Phase 1 and Phase 2 labels coexist in this table; query by classifier_version
    setup_type           TEXT,     -- A, B, C, D, E, or NULL
    confidence           REAL,
    dilution_severity    REAL,
    immediate_pressure   BOOLEAN,
    price_discount       REAL,
    short_attractiveness INTEGER,
    rank                 TEXT,     -- A, B, C, D
    key_excerpt          TEXT,     -- <= 500 characters
    reasoning            TEXT,
    scored_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (accession_number, classifier_version)
);

CREATE TABLE IF NOT EXISTS signals (
    id                   INTEGER PRIMARY KEY DEFAULT nextval('signals_id_seq'),
    accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
    ticker               TEXT NOT NULL,
    setup_type           TEXT,
    score                INTEGER,
    rank                 TEXT,
    alert_type           TEXT NOT NULL,
        -- NEW_SETUP, SETUP_UPDATE, TIME_EXCEEDED
    status               TEXT NOT NULL DEFAULT 'LIVE',
        -- LIVE, WATCHLIST, CLOSED, TIME_EXCEEDED
    alerted_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    price_at_alert       REAL,
    entry_price          REAL,
    cover_price          REAL,
    pnl_pct              REAL,
    closed_at            TIMESTAMP,
    close_reason         TEXT
        -- MANUAL, TIME_EXCEEDED
);

CREATE TABLE IF NOT EXISTS poll_state (
    id INTEGER PRIMARY KEY,
    last_poll_at TIMESTAMP,
    last_success_at TIMESTAMP
);
INSERT OR IGNORE INTO poll_state (id) VALUES (1);
-- This table has exactly one row (id=1) at all times. Updated in-place via UPDATE; never inserted twice.
```

---

## 7. Frontend Component Hierarchy and Data Flow

```
app/page.tsx                          (DashboardPage)
├── components/Header.tsx             — app title bar
├── components/HealthBar.tsx          — polls GET /api/v1/health every 15s
│                                       displays: last_poll_at, status indicator
│                                       red badge when: status != "ok" OR
│                                         last_success_at > 10 minutes ago
├── components/LiveNowPanel.tsx       — displays SignalRow[] where rank == "A"
│   └── components/SignalRow.tsx      — ticker, setup_type, score, price_move_pct,
│                                       elapsed time; click → SetupDetailModal
├── components/WatchlistPanel.tsx     — displays SignalRow[] where rank == "B"
│   └── components/SignalRow.tsx      — ticker, setup_type, score, status label
└── components/RecentClosedPanel.tsx  — displays SignalRow[] (closed)
    └── components/SignalRow.tsx      — ticker, setup_type, entry/cover/pnl_pct

Modal (rendered at root level, opened by SignalRow click):
SetupDetailModal.tsx
├── Displays all ClassificationDetail fields
├── Shows price_at_alert and current price side-by-side (when available)
└── PositionForm.tsx
    ├── entry_price input → POST /api/v1/signals/{id}/position
    └── cover_price input → POST /api/v1/signals/{id}/position
                            → triggers close when cover_price saved
```

### Data Fetch Pattern

- `DashboardPage` fetches `GET /api/v1/signals` on mount and every **30 seconds** via `setInterval` (not SSE in Phase 1). Controlled by `NEXT_PUBLIC_REFRESH_INTERVAL_MS` (default 30000ms).
- `HealthBar` fetches `GET /api/v1/health` on mount and every **15 seconds** via its own independent `setInterval`. This interval is fixed and is **not** shared with the signal refresh interval — the two timers are independent.
- `SetupDetailModal` fetches `GET /api/v1/signals/{id}` on open.
- Fetch uses `AbortController` to cancel in-flight requests on unmount (same pattern as gap-lens-dilution `services/api.ts`).

### TypeScript Interfaces (`frontend/src/types/signals.ts`)

```typescript
export interface SignalRow {
  id: number;
  accession_number: string;
  ticker: string;
  setup_type: string;
  score: number;
  rank: "A" | "B" | "C" | "D";
  alert_type: "NEW_SETUP" | "SETUP_UPDATE" | "TIME_EXCEEDED";
  status: "LIVE" | "WATCHLIST" | "CLOSED" | "TIME_EXCEEDED";
  alerted_at: string;      // ISO 8601
  price_at_alert: number | null;
  entry_price: number | null;
  cover_price: number | null;
  pnl_pct: number | null;
  closed_at: string | null;
  close_reason: "MANUAL" | "TIME_EXCEEDED" | null;
  price_move_pct: number | null;
  elapsed_seconds: number | null;
}

export interface ClassificationDetail {
  setup_type: string;
  confidence: number;
  dilution_severity: number;
  immediate_pressure: boolean;
  price_discount: number | null;
  short_attractiveness: number;
  key_excerpt: string;
  reasoning: string;
  classifier_version: string;
  scored_at: string;
}

export interface SignalDetailResponse {
  signal: SignalRow;
  ticker: string;
  entity_name: string | null;  // Company name from EFTS; null for older records
  classification: ClassificationDetail;
  filing_url: string;
  form_type: string;
  filed_at: string;
  current_price: number | null;
}

export interface SignalListResponse {
  signals: SignalRow[];
  count: number;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  last_poll_at: string | null;
  last_success_at: string | null;
  poll_interval_seconds: number;
  fmp_configured: boolean;
  askedgar_configured: boolean;
  db_path: string;
}

export interface PositionRequest {
  entry_price?: number;
  cover_price?: number;
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string };
```

### Dark Theme (preserved from gap-lens-dilution, in `globals.css`)

```css
:root {
  --color-bg:      #1a1a1a;
  --color-card:    #2d2d2d;
  --color-text:    #ffffff;
  --color-accent:  #00bcd4;
  --color-border:  #444444;
}
```

---

## 8. Async Background Task Design

The poller runs alongside FastAPI using asyncio background tasks, not Celery or a separate process.

### Startup Registration (`app/main.py`)

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.services.edgar_poller import EdgarPoller
from app.services.db import init_db

poller: EdgarPoller | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global poller
    # Startup sequence (order is required):
    # 1. init_db() — creates DuckDB tables
    # 2. TickerResolver.refresh() — downloads and caches cik_ticker_map (HTTP call; must be after init_db)
    # 3. asyncio.create_task(poller.run_forever()) — starts EDGAR polling loop
    # 4. asyncio.create_task(signal_manager.run_lifecycle_loop()) — starts lifecycle checker
    init_db()
    await TickerResolver.refresh()
    poller = EdgarPoller()
    task = asyncio.create_task(poller.run_forever())
    lifecycle_task = asyncio.create_task(signal_manager.run_lifecycle_loop())
    yield
    task.cancel()
    lifecycle_task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await lifecycle_task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="Dilution Short Filter API", lifespan=lifespan)
    # ... middleware, routers
    return app
```

### Poller Loop (`edgar_poller.py:run_forever`)

```python
async def run_forever(self) -> None:
    while True:
        try:
            await self._poll_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Poller cycle failed: %s", exc)
        await asyncio.sleep(settings.edgar_poll_interval)
```

`_poll_once` is fully async: it uses `httpx.AsyncClient` for EDGAR and FMP requests and `await asyncio.to_thread(db.execute, ...)` for any DuckDB writes that block.

### Lifecycle Checker

`SignalManager` exposes `run_lifecycle_loop()` — a separate asyncio task also started in `lifespan`, waking every 300 seconds (configurable via `settings.lifecycle_check_interval`).

### Concurrency Model

- Single asyncio event loop (uvicorn default).
- All service I/O is async (`httpx.AsyncClient`).
- DuckDB is accessed via `asyncio.to_thread` to avoid blocking the event loop.
- No process-level parallelism required for Phase 1 throughput (EDGAR volume is low; 90s poll interval with O(10s) processing per filing).

---

## 9. Config Extensions

New environment variables beyond what gap-lens-dilution already provides. All are loaded via `pydantic_settings.BaseSettings` in `app/core/config.py`.

| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `FMP_API_KEY` | str | `""` | FMP Ultimate API key (already in config but not wired) |
| `ASKEDGAR_API_KEY` | str | `""` | Already present; no change |
| `CLASSIFIER_NAME` | str | `"rule-based-v1"` | Active classifier in registry |
| `EDGAR_POLL_INTERVAL` | int | `90` | EFTS poll interval in seconds |
| `EDGAR_EFTS_URL` | str | (long EDGAR URL) | Full EDGAR EFTS JSON URL with form filter |
| `DUCKDB_PATH` | str | `"./data/filter.duckdb"` | DuckDB file path |
| `FILING_TEXT_MAX_BYTES` | int | `512000` | Max bytes of filing text to fetch |
| `DEFAULT_BORROW_COST` | float | `0.30` | Annualized borrow cost default (30%) |
| `ADV_MIN_THRESHOLD` | float | `500000` | ADV dollar threshold used in the FLOAT_ILLIQUIDITY numerator in the scoring formula. Matches the Filter 6 ADV threshold. |
| `SCORE_NORMALIZATION_CEILING` | float | `1.0` | Raw score mapped to 100 |
| `SETUP_QUALITY_A` | float | `0.65` | Historical win rate for setup A |
| `SETUP_QUALITY_B` | float | `0.55` | Historical win rate for setup B |
| `SETUP_QUALITY_C` | float | `0.60` | Historical win rate for setup C |
| `SETUP_QUALITY_D` | float | `0.45` | Historical win rate for setup D |
| `SETUP_QUALITY_E` | float | `0.50` | Historical win rate for setup E |
| `LIFECYCLE_CHECK_INTERVAL` | int | `300` | Lifecycle checker wake interval in seconds |
| `IBKR_BORROW_COST_ENABLED` | bool | `False` | If True, attempt IBKR borrow cost lookup |
| `NEXT_PUBLIC_REFRESH_INTERVAL_MS` | int | `30000` | Frontend auto-refresh interval (ms) |

### Extended `config.py` Settings Class

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Any


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Inherited from gap-lens-dilution
    askedgar_api_key: str = ""
    fmp_api_key: str = ""
    askedgar_url: str = "https://eapi.askedgar.io"
    request_timeout: int = 30
    cors_origins: list = ["*"]

    # New: classifier
    classifier_name: str = "rule-based-v1"

    # New: EDGAR poller
    edgar_poll_interval: int = 90
    edgar_efts_url: str = (
        "https://efts.sec.gov/LATEST/search-index?forms=S-1,S-1%2FA,S-3,424B2,424B4,8-K,13D%2FA"
    )

    # New: storage
    duckdb_path: str = "./data/filter.duckdb"
    filing_text_max_bytes: int = 512_000

    # New: scoring
    default_borrow_cost: float = 0.30
    adv_min_threshold: float = 500_000
    score_normalization_ceiling: float = 1.0
    setup_quality_a: float = 0.65
    setup_quality_b: float = 0.55
    setup_quality_c: float = 0.60
    setup_quality_d: float = 0.45
    setup_quality_e: float = 0.50

    @property
    def setup_quality(self) -> dict[str, float]:
        return {
            "A": self.setup_quality_a,
            "B": self.setup_quality_b,
            "C": self.setup_quality_c,
            "D": self.setup_quality_d,
            "E": self.setup_quality_e,
        }

    # New: lifecycle
    lifecycle_check_interval: int = 300
    ibkr_borrow_cost_enabled: bool = False


settings = Settings()
```

---

## 10. Phase 2 Accommodation

### 10.1 Architecture Seams Already in Phase 1

| Seam | Phase 1 Implementation | Phase 2 Change Required |
|------|----------------------|------------------------|
| Classifier registry | `get_classifier("rule-based-v1")` | Add `"llama-1b-v1": NIMClassifier` to registry dict; no pipeline changes |
| `labels.classifier_version` column | Written as `"rule-based-v1"` for every row | Phase 2 rows written as `"llama-1b-v1"`; both coexist in same table |
| `filings.filing_text` column | Full filing text stored | Already available for teacher labeling input; no schema change |
| `ClassificationResult` TypedDict | Identical to Phase 2 output schema | No change needed in scorer, signal_manager, or API layer |

### 10.2 Training Data Export Path

Query DuckDB to produce JSONL for teacher labeling:

```sql
SELECT
    f.accession_number,
    f.ticker,
    f.form_type,
    f.filed_at,
    f.filing_text,
    l.setup_type         AS rule_based_setup_type,
    l.confidence         AS rule_based_confidence,
    l.dilution_severity,
    l.immediate_pressure,
    l.price_discount,
    l.short_attractiveness AS rule_based_score,
    l.key_excerpt,
    l.reasoning,
    l.scored_at,
    m.price,
    m.market_cap,
    m.float_shares,
    m.adv_dollar
FROM filings f
LEFT JOIN labels l
    ON f.accession_number = l.accession_number
    AND l.classifier_version = 'rule-based-v1'
LEFT JOIN market_data m
    ON f.ticker = m.ticker
    AND m.snapshot_at = (
        SELECT MAX(snapshot_at) FROM market_data
        WHERE ticker = f.ticker AND snapshot_at <= f.filed_at
    )
WHERE f.filter_status IN ('PASSED', 'FILTERED_OUT')
ORDER BY f.filed_at DESC;
```

Output: newline-delimited JSON where each line contains `filing_text` (teacher input) and all rule-based label fields (used as initial labels or teacher comparison baseline).

### 10.3 Phase 2 NIM Serving Configuration

**Source**: KxSystems/nvidia-kx-samples `ai-model-distillation-for-financial-data` repository (reference only; none of this code is used in Phase 1).

#### NIM Docker Configuration Pattern

The KxSystems repo deploys NIM via the NeMo Microservices Platform on Kubernetes. For a local single-GPU deployment (your RTX 4090), the equivalent Docker pattern is:

```bash
docker run --gpus all \
  --name sec-classifier-nim \
  -p 8001:8000 \
  -e NIM_GUIDED_DECODING_BACKEND=outlines \
  -e NIM_MODEL_PROFILE=auto \
  -v /path/to/sec-classifier-1b:/opt/nim/models \
  nvcr.io/nim/meta/llama-3.2-1b-instruct:1.8.3
```

Key environment variables extracted from KxSystems config:
- `NIM_GUIDED_DECODING_BACKEND=outlines` — required for structured JSON output (the repo's `NIMConfig.to_dms_config()` injects this for all deployments)
- Model image: `nvcr.io/nim/{model_name}:{tag}` where tag is `1.8.3` for llama-3.2-1b-instruct
- Context length: `8192` tokens (set in `config.yaml` `nims[0].context_length`)
- PVC/volume: `25Gi` minimum model storage
- GPU: 1 GPU required
- Port: container port `8000`; expose on host port `8001` to avoid conflict with FastAPI

The NIMClassifier in Phase 2 will call the NIM container via the OpenAI-compatible endpoint:
```
POST http://localhost:8001/v1/chat/completions
```
with a structured output schema enforced via `outlines` guided decoding.

#### LoRA Training Configuration

Extracted from `config/config.yaml` and `src/config.py` `LoRAConfig` and `TrainingConfig`:

| Parameter | KxSystems Value | Notes |
|-----------|----------------|-------|
| `training_type` | `"sft"` | Supervised fine-tuning |
| `finetuning_type` | `"lora"` | LoRA adapter (not full fine-tune) |
| `adapter_dim` (r) | `16` | LoRA rank |
| `adapter_dropout` | `0.1` | Dropout on adapter layers |
| `sequence_packing_enabled` | `True` | Pack multiple sequences per batch |
| `learning_rate` | `0.0001` (1e-4) | Learning rate |
| `epochs` | `1` (config default) | Adjust upward for small datasets |
| `batch_size` | `64` | Per GPU |
| `max_seq_length` | `8192` | Matches NIM context length |
| `training_precision` | `"bf16-mixed"` | BF16 mixed precision |

The `sec-filing-distillation-spec.md` reference document specifies `lora_r=16, lora_alpha=32` — these align with the KxSystems `adapter_dim=16` setting (alpha is typically 2x rank).

For the dilution classifier: epochs should be 3 (from `sec-filing-distillation-spec.md`) rather than 1, given the smaller training set and more complex output schema.

#### Evaluation Patterns

The KxSystems repo uses `workload_type: "classification"` and evaluates with F1 score per class. For the dilution short filter:

**Evaluation strategy** (adapted from KxSystems `data_split_config`):
- `eval_size`: 100 held-out filings (never used in training)
- `val_ratio`: 0.1 (10% of training set for validation during training)
- `min_total_records`: 50 (minimum labeled examples before training is attempted)
- `random_seed`: 42
- `stratify_enabled`: True — maintain class balance across setup types A-E-NULL
- `min_samples_per_class`: 2

**Metrics** (from KxSystems evaluation + `sec-filing-distillation-spec.md`):
```python
from sklearn.metrics import classification_report

# Primary: per-class F1
report = classification_report(
    y_true, y_pred,
    target_names=["A", "B", "C", "D", "E", "NULL"],
    output_dict=True
)
# Target: weighted F1 > 0.90 across all setup types

# Secondary: backtest validation (from KxSystems backtest_config)
# cost_bps: 5.0 (5 basis points per trade)
# min_signals: 10 (minimum signals required for backtest validity)
# Metrics: win rate per rank, avg return, Sharpe, max drawdown
```

**Reporting format**: MLflow experiment tracking (KxSystems uses `experiment_name_prefix: "findistil"`). For Phase 2: adapt to `"dilution-short-filter"` experiment prefix.

#### Teacher-Student Pipeline Pattern

The KxSystems architecture uses a full NeMo Microservices Platform (NMP) with Celery workers and KDB-X. For Phase 2, the simplified equivalent:

```
Phase 1 DuckDB (filings + labels tables)
    │
    │ export JSONL via SQL query (Section 10.2)
    ▼
Teacher labeling (GPT-4 or Claude 3.5 Sonnet)
    │ write labeled JSONL
    ▼
LoRA fine-tune Llama 3.2 1B (RTX 4090, ~2-4 hours)
    │ adapter weights
    ▼
NIM container (local, port 8001)
    │ OpenAI-compatible endpoint
    ▼
NIMClassifier (new file: app/services/classifier/nim_classifier.py)
    │ registered as "llama-1b-v1" in get_classifier() registry
    ▼
No other pipeline changes
```

---

## 11. Error Handling and Degradation Strategy

### 11.1 EDGAR Unreachable

- Retry 3 times with exponential backoff (1s, 2s, 4s).
- On all retries exhausted: log `EDGAR_POLL_FAILED` with timestamp; `_last_poll_at` is updated but `_last_success_at` is not.
- Health endpoint returns `status: "degraded"` when `last_success_at` is older than 10 minutes.
- Dashboard `HealthBar` shows red badge when `status != "ok"` or last success > 10 minutes ago.
- Malformed or unexpected JSON: log parse error with raw excerpt (first 500 chars); skip cycle entirely; no crash.

### 11.2 FMP Unavailable or Key Missing

- On startup with missing key: `settings.fmp_api_key == ""` → log `FMP_KEY_MISSING` warning; dashboard health shows `fmp_configured: false`.
- Per-request failure (429 or 5xx): retry 3 times with exponential backoff.
- On all retries exhausted: `FMPDataUnavailableError` raised; `FilterEngine` catches this and:
  - Marks filters 2/3/5/6 as `DATA_UNAVAILABLE` in `filter_results`
  - Sets `filings.filter_fail_reason = DATA_UNAVAILABLE`
  - Does NOT pass the filing to the classifier
- Conservative default: a filing with missing critical market data does NOT pass the filter.

### 11.3 AskEdgar (DilutionService) Unavailable

- `DilutionService.get_dilution_data_v2` already handles sub-call failures with `return_exceptions=True`; returns degraded dict with null fields on any sub-call failure.
- Pipeline catches any exception from `DilutionService` at the enrichment step:
  - Continues to classification using FMP-only data
  - Sets `filings.askedgar_partial = True`
  - Sets `market_data.data_source = PARTIAL`
  - Logs `ASKEDGAR_PARTIAL_ENRICHMENT` warning with ticker and accession number

### 11.4 Classifier Failure

- Any exception from `ClassifierProtocol.classify()` is caught by the pipeline:
  - Sets `filings.processing_status = ERROR`
  - Logs full traceback
  - Does NOT create a signal row; filing is stored for manual review
  - Does NOT crash the poller loop

### 11.5 Scoring Anomalies

- `BORROW_COST == 0`: substitute `settings.default_borrow_cost`; log `BORROW_COST_ZERO_SUBSTITUTED` warning.
- Raw score outside [0, 100] after normalization: clamp to [0, 100]; log `SCORE_CLAMPED` warning with raw pre-normalization value and ticker.
- `dilution_severity = 0.0` after pipeline step 7.5: this can only occur if shares_offered was not extractable from the filing text AND Filter 4 was somehow bypassed. Under normal operation Filter 4 blocks such filings before they reach the scorer (conservative: treat unknown dilution % as failing the 10% threshold). If a 0.0 value reaches the Scorer, log `DILUTION_SEVERITY_ZERO` warning; the scorer returns a low score naturally (raw_score = 0), not an error.

### 11.6 Ticker Resolution Failure

- If EDGAR filing header contains no ticker or CIK cannot be mapped to a ticker:
  - `filings.filter_status = UNRESOLVABLE`
  - `filings.processing_status = ERROR`
  - No enrichment; no signal; logged for audit

### 11.7 Database Error

- On DuckDB write failure: log full error; do not crash poller.
- On startup `init_db()` failure: `FastAPI` startup fails with a clear error message (intentional: do not run without storage).

---

## 12. Dependencies

New dependencies to add to `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| `duckdb` | `^1.1` | Embedded analytical database |
| `lxml` | `^5.3` | Fast HTML parsing for filing text extraction |
| `aiofiles` | `^24.1` | Async file I/O (optional; for local filing cache) |
| `python-multipart` | `^0.0.12` | FastAPI form data support |

Existing dependencies (already in `requirements.txt`, no change):

| Package | Notes |
|---------|-------|
| `fastapi` | Backend framework |
| `uvicorn` | ASGI server |
| `httpx` | Async HTTP client (used by DilutionService and new services) |
| `pydantic-settings` | Config management |
| `pytest`, `pytest-asyncio`, `pytest-cov` | Testing |
| `black`, `flake8`, `mypy` | Code quality |

Frontend (`package.json` — preserved from gap-lens-dilution, no new packages required for Phase 1):
- `next` (Next.js)
- `react`, `react-dom`
- `typescript`

---

## 13. Integration Points with Existing System

| Existing Component | Integration Method |
|-------------------|-------------------|
| `app/services/dilution.py` (DilutionService) | Copied unchanged. Instantiated in the pipeline as `DilutionService()`. Called via `await dilution_service.get_dilution_data_v2(ticker)` at the AskEdgar enrichment step. |
| `app/utils/errors.py` | Copied unchanged. `TickerNotFoundError`, `RateLimitError`, `ExternalAPIError` used in `FMPClient` and `FilterEngine`. |
| `app/utils/validation.py` | Copied unchanged. `validate_ticker()` used in API route handlers. |
| `app/utils/formatting.py` | Copied unchanged. |
| `app/core/config.py` (Settings) | Extended with new fields; all existing fields retained. |
| `frontend/src/app/globals.css` | Dark theme CSS variables preserved verbatim. New dashboard layout rules appended. |
| `frontend/src/types/dilution.ts` | Not imported by new frontend. New `types/signals.ts` is the type contract. |

The original `gap-lens-dilution` repository at `/home/d-tuned/projects/gap-lens-dilution/` is never modified.

---

## 14. Components Summary

| Component | File | Type |
|-----------|------|------|
| EdgarPoller | `app/services/edgar_poller.py` | Async background service |
| FilingFetcher | `app/services/filing_fetcher.py` | Async service |
| FilterEngine | `app/services/filter_engine.py` | Sync service (called from async context) |
| FMPClient | `app/services/fmp_client.py` | Async service |
| ClassifierProtocol | `app/services/classifier/protocol.py` | Protocol + TypedDict |
| get_classifier | `app/services/classifier/__init__.py` | Factory function |
| RuleBasedClassifier | `app/services/classifier/rule_based.py` | ClassifierProtocol impl |
| Scorer | `app/services/scorer.py` | Pure function module |
| SignalManager | `app/services/signal_manager.py` | Stateful service |
| DilutionService | `app/services/dilution.py` | Async service (copied) |
| db | `app/services/db.py` | DuckDB connection singleton |
| API routes | `app/api/v1/routes.py` | FastAPI router |
| Settings | `app/core/config.py` | pydantic_settings (extended) |
| DashboardPage | `frontend/src/app/page.tsx` | Next.js page |
| HealthBar | `frontend/src/components/HealthBar.tsx` | React component |
| LiveNowPanel | `frontend/src/components/LiveNowPanel.tsx` | React component |
| WatchlistPanel | `frontend/src/components/WatchlistPanel.tsx` | React component |
| RecentClosedPanel | `frontend/src/components/RecentClosedPanel.tsx` | React component |
| SignalRow | `frontend/src/components/SignalRow.tsx` | React component |
| SetupDetailModal | `frontend/src/components/SetupDetailModal.tsx` | React component |
| PositionForm | `frontend/src/components/PositionForm.tsx` | React component |
| API service | `frontend/src/services/api.ts` | TypeScript module |
| Type definitions | `frontend/src/types/signals.ts` | TypeScript interfaces |
