# Requirements: Backtest Pipeline

**Feature name:** backtest-pipeline
**Document version:** 1.0
**Date:** 2026-04-05
**Author:** @requirements-analyst
**Hypotheses under test:** H1a, H1b, H1e, H1f, H1g

---

## Summary

A historical batch pipeline that discovers all in-scope SEC dilution filings from 2017-2025 via the EDGAR quarterly full-index, fetches and parses each filing's plain text, runs the existing rule-based classifier extended with underwriter extraction, joins each classified filing against certified market data (daily_prices, daily_market_cap, daily_universe, historical_float, short_interest), computes outcome returns at T+1, T+3, T+5, and T+20 trading days, and writes a labeled dataset in a reproducible format. The labeled dataset is the empirical input for findings documents testing H1a, H1b, H1e, H1f, and H1g.

---

## Hypotheses and Traceability

Each user story is tagged with the hypothesis sub-claim it is required to test.

| Hypothesis | Claim | Falsification condition |
|------------|-------|------------------------|
| H1a | Rank A signals produce larger and more consistent price declines than Rank B | Rank A and Rank B return distributions are statistically indistinguishable |
| H1b | Setup type is a meaningful predictor; C and B > D in edge | All setup type return distributions are statistically indistinguishable |
| H1e | Underwriter/placement agent identity is a significant predictor independent of setup type | Win rates across all named firms are uniform (no firm outperforms base rate) |
| H1f | A small set of repeat firms accounts for a disproportionate share of high-conviction signals | Top 5 firms account for less than 30% of qualifying filing events |
| H1g | Sales agent role in ATM programs carries distinct predictive value from lead underwriter role | Sales agent and lead underwriter win rate distributions are identical |

---

## User Stories

### US-01: Filing Discovery (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want the pipeline to discover all S-1, S-1/A, S-3, 424B2, 424B4, 8-K, and 13D/A filings filed between 2017-01-01 and 2025-12-31,
so that the backtest operates on a complete and reproducible universe of potential dilution events — not a curated subset.

### US-02: CIK-to-Ticker Resolution (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want each discovered filing's CIK to be resolved to a ticker symbol using the `raw_symbols_massive` table in market_data.duckdb,
so that I can join filing events against price and float data without introducing errors from manual mapping.

### US-03: Filing Text Fetching (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want the pipeline to fetch the plain text of each in-scope filing directly from SEC Archives at a rate compliant with SEC's published limit (no more than 10 requests per second),
so that the classifier can operate on actual filing content.

### US-04: Setup Type Classification (H1a, H1b)

As a researcher,
I want each fetched filing to be run through the existing `RuleBasedClassifier` (version: rule-based-v1) to assign a setup type (A, B, C, D, E, or NULL) and extract `shares_offered_raw`, `price_discount`, and `immediate_pressure`,
so that signals can be grouped by setup type for H1b analysis, and Rank A vs Rank B can be computed for H1a analysis.

### US-05: Underwriter Extraction (H1e, H1f, H1g)

As a researcher,
I want the pipeline to extract all named financial intermediaries from each filing's text and assign them a normalized role,
so that I can compute per-firm win rates (H1e), concentration analysis (H1f), and role-level comparison between lead underwriters and sales agents (H1g).

**Extraction targets by form type:**

| Form Type | Text section to search | Roles to extract |
|-----------|----------------------|-----------------|
| 424B4 | Cover page and "Plan of Distribution" section | lead_underwriter, co_manager |
| S-1 | Cover page and "Plan of Distribution" section | lead_underwriter, co_manager |
| 8-K (ATM announcement) | Full body text | sales_agent, placement_agent |
| 424B3 | Not applicable — 424B3 filings are not discovered in Phase R1 (not in the form_type filter set). 424B3 extraction is deferred to a future phase. | N/A (deferred) |
| 424B2 | Cover page and distribution section | lead_underwriter |
| 13D/A | Full body text | placement_agent (best-effort only) |

**Role normalization:** Firm names must be normalized to a canonical form (e.g., "H.C. Wainwright & Co., LLC" and "H.C. Wainwright" map to "H.C. Wainwright & Co."). A normalization table of known firms will be seeded as a static configuration file. Unrecognized names are stored as extracted without normalization.

### US-06: Market Data Join — Point-in-Time (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want each classified filing to be joined against market_data.duckdb tables using only data available on or before the filing's `filed_at` date,
so that no look-ahead bias contaminates the backtest results.

**Required joins per filing:**

| Data needed | Table | Join key | Anti-look-ahead rule |
|-------------|-------|----------|----------------------|
| In-scope universe flag | daily_universe | (symbol, filed_at date) | Use the row where trade_date = filing date; if market is closed, use the prior trading day |
| Price at T (for filter and scoring) | daily_prices | (symbol, filed_at date) | Same as above |
| Market cap at T | daily_market_cap | (symbol, filed_at date) | Same as above |
| Float at T | historical_float | (symbol, AS-OF filed_at) | Use most recent row with date <= filed_at |
| Short interest at T | short_interest | (symbol, AS-OF filed_at) | Use most recent row with date <= filed_at |

**Note on join ceiling asymmetry:** Daily snapshot joins (universe, price, market cap) use the trading-day-adjusted date (i.e., if filing date is a weekend or holiday, roll back to the prior trading day). AS-OF joins (float, short interest) use the raw `filed_at` date as the ceiling — these tables are not trading-day-constrained, so rolling back would incorrectly exclude same-day data. This asymmetry is intentional and conservative.

### US-07: Six-Filter Application (H1a, H1b)

As a researcher,
I want the pipeline to apply the same six filter criteria used in the live pipeline to each historical filing using the point-in-time market data joined in US-06,
so that the backtest signal universe is identical to what the live pipeline would have produced at that date.

**Filter criteria (from FilterEngine):**

| Filter | Criterion | Threshold |
|--------|-----------|-----------|
| 1 | Form type in allowed set AND offering keyword present | See ALLOWED_FORM_TYPES and OFFERING_KEYWORDS |
| 2 | Market cap at T | < $2,000,000,000 |
| 3 | Float at T | < 50,000,000 shares |
| 4 | Dilution % (shares_offered / float) | > 10% |
| 5 | Price at T | > $1.00 |
| 6 | ADV at T (20-day average dollar volume) | > $500,000 |

**Float availability rule:** For filings dated before 2020-03-04, historical_float data is unavailable. Filter 3 must be skipped for these filings. The output row must include a flag `float_available: false` and the filter fail reason must be set to `FLOAT_NOT_AVAILABLE` rather than `FILTERED_OUT`.

### US-08: Scoring (H1a, H1b)

As a researcher,
I want the pipeline to compute a score (0-100) and rank (A/B/C/D) for each filing that passes all applicable filters, using the existing `Scorer` formula,
so that H1a (Rank A > Rank B) can be tested.

**Two-tier scoring:**

| Window | Formula | Borrow cost source |
|--------|---------|-------------------|
| 2020-2025 (full fidelity) | `(DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY) / BORROW_COST` | short_interest proxy (2021+); `settings.default_borrow_cost` otherwise |
| 2017-2019 (partial fidelity) | Score and rank are computed but `float_available` flag is false; rank must not be used in H1a analysis without this flag check | N/A |

### US-09: Outcome Computation — Price Returns (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want the pipeline to compute price returns at T+1, T+3, T+5, and T+20 trading days after the filing date for each signal that passes filters,
so that I can measure the directional and magnitude performance of each signal.

**Return computation rules:**

- Use `adjusted_close` from `daily_prices` at each horizon date.
- "T+N trading days" means N rows forward in `daily_prices` for the same symbol, ordered by `trade_date`, from the filing date row. Do not count calendar days.
- If the symbol has fewer than N price rows remaining after the filing date (delisted or data ends), the return at that horizon is NULL and the field `delisted_before_TN: true` must be set.
- Return formula: `(price_at_TN / price_at_T) - 1`, where `price_at_T` is the `adjusted_close` on the filing date (or prior trading day if the market was closed).

### US-10: Survivorship Bias Inclusion (H1a, H1b)

As a researcher,
I want the pipeline to include filings for symbols that were subsequently delisted,
so that the return distribution is not biased toward surviving stocks.

**Rule:** Inclusion eligibility is determined at the filing date using `daily_universe.in_smallcap_universe`. A symbol that was alive and in-universe on the filing date must be included regardless of whether it was delisted afterward. Returns for such symbols are NULL at horizons where price data does not exist.

### US-11: Output Dataset (H1a, H1b, H1e, H1f, H1g)

As a researcher,
I want the pipeline to write its final labeled dataset to reproducible files:
- `docs/research/data/backtest_results.parquet` (with companion CSV at `docs/research/data/backtest_results.csv`)
- `docs/research/data/backtest_participants.parquet` (with companion CSV at `docs/research/data/backtest_participants.csv`)

so that finding documents can reference exact files and both datasets can be version-controlled by hash.

---

## Acceptance Criteria

### AC-01 (US-01)

- Given the pipeline runs against the 2017-2025 date range, when it completes, then the filing discovery log must show that all 36 quarterly master.gz files (2017 Q1 through 2025 Q4) were downloaded and parsed.
- Given a quarterly master.gz file is downloaded, when it is parsed, then only rows with FormType in {S-1, S-1/A, S-3, 424B2, 424B4, 8-K, 13D/A} are retained for further processing.

### AC-02 (US-02)

- Given a filing CIK, when the CIK-to-ticker lookup runs, then the pipeline joins on `raw_symbols_massive.cik` and returns the matching `ticker`; if no match is found, the filing is logged with `resolution_status = UNRESOLVABLE` and excluded from market data joins.
- Given a CIK that resolves to multiple tickers (corporate actions), the pipeline must select the ticker whose `symbol_history.start_date` through `symbol_history.end_date` window covers the filing date; if ambiguous, log the ambiguity and skip.

### AC-03 (US-03)

- Given a resolved ticker and filing URL, when the fetcher downloads the filing, then the fetcher must use the `User-Agent: gap-lens-dilution-filter contact@yourdomain.com` header in compliance with SEC requirements.
- Given the SEC returns HTTP 429 or 503, the fetcher must back off and retry (maximum 3 attempts, backoffs: 1s, 2s, 4s) before marking the filing as `FETCH_FAILED`.
- Given a successful fetch, the HTML is stripped to plain text (using the existing `_TextExtractor` HTML parser logic) before any classifier or extraction step runs.
- Given the plain text exceeds `settings.filing_text_max_bytes`, the text is truncated at that boundary before classification.
- The pipeline must not exceed 10 HTTP requests per second to any SEC domain.

### AC-04 (US-04)

- Given a fetched filing text and form_type, when classification runs, then the output contains: `setup_type` (one of A, B, C, D, E, NULL), `confidence`, `shares_offered_raw`, `price_discount`, `immediate_pressure`, `key_excerpt`, `reasoning`.
- Given `setup_type = NULL`, the filing is excluded from filter, scoring, and outcome computation steps; it is still written to the raw discovery log with `classification_status = NO_MATCH`.
- Given a 424B4 filing that contains both "supplement" and "takedown" keywords, the classifier assigns setup B (the first matching rule in `_RULES` order).

### AC-05 (US-05)

- Given a 424B4 or S-1 filing, when underwriter extraction runs, then the output includes at least one `filing_participants` row if any of the following patterns are present in the "Plan of Distribution" section or cover page: "lead underwriter", "book-running manager", "managing underwriter", "co-manager", "co-lead manager".
- Given an 8-K filing containing "equity distribution agreement" language, when extraction runs, then the output includes at least one `filing_participants` row with `role = sales_agent` or `role = placement_agent`.
- Given a firm name extracted, when normalization runs against the canonical normalization table, then known variants (e.g., "H.C. Wainwright & Co., LLC", "HC Wainwright", "H.C. Wainwright") all map to the same `firm_name` value.
- Given a firm name not in the normalization table, the raw extracted string is stored verbatim and `is_normalized = false` is set on the row.
- Given a filing where no financial intermediary names are found, zero `filing_participants` rows are written for that filing (not an error condition).

### AC-06 (US-06 and US-07)

- Given a filing date that falls on a weekend or market holiday, when the pipeline performs market data joins, then it uses the most recent prior trading day's row from `daily_prices`, `daily_market_cap`, and `daily_universe`.
- Given a filing dated before 2020-03-04, when filter 3 (float) is evaluated, then the filter is skipped and `float_available = false` is written to the output row; the filing proceeds to classification, scoring (partial), and outcome computation.
- Given a filing dated on or after 2020-03-04, when filter 3 runs, then `historical_float` is joined using the most recent row with `date <= filing_date`; if no row exists for that symbol, the filter fails with `FLOAT_NOT_AVAILABLE`.
- Given a filing for a ticker not present in `daily_universe` on the filing date, the filing is excluded with `universe_status = NOT_IN_UNIVERSE`.

### AC-07 (US-08)

- Given a filing that passes all applicable filters, when the Scorer runs, then the output contains `score` (integer 0-100) and `rank` (A, B, C, or D) computed using the current `Scorer.score()` formula.
- Given `borrow_cost = 0.0` (no short interest data available), then `settings.default_borrow_cost` is substituted and the output row includes `borrow_cost_source = DEFAULT`.
- Given `dilution_severity = 0.0` (shares_offered not extractable), then a score of 0 is written and the output row includes `dilution_extractable = false`.

### AC-08 (US-09)

- Given a filing that passes filters and has a score > 0, when outcome computation runs, then the output row contains: `return_1d`, `return_3d`, `return_5d`, `return_20d` (each as a decimal, e.g., -0.07 for -7%), computed from `adjusted_close`.
- Given a symbol delisted before T+N, then `return_TN = NULL` and `delisted_before_TN = true` for that horizon.
- Given `price_at_T = 0` or NULL (invalid price on filing date), the filing's outcome fields are all NULL and `outcome_computable = false` is set.
- Given the same symbol files multiple qualifying filings within a 20-trading-day window, each filing's outcome is computed independently; there is no deduplication of overlapping windows.

### AC-09 (US-10)

- Given a symbol that was delisted after the filing date, when the pipeline runs, then that symbol's filing is included in the output if it was in `daily_universe.in_smallcap_universe` on the filing date.
- Given a symbol whose last price row in `daily_prices` is before the filing date, the filing is excluded with `outcome_computable = false`.

### AC-10 (US-11)

- Given a completed pipeline run, when the output files are written, then `docs/research/data/backtest_results.parquet`, `docs/research/data/backtest_results.csv`, `docs/research/data/backtest_participants.parquet`, and `docs/research/data/backtest_participants.csv` are all created with the schemas defined below.
- Given the same pipeline is run twice against the same input files (no internet changes), then all output files are byte-for-byte identical (deterministic).
- Given the output files are written, then a companion metadata file `docs/research/data/backtest_run_metadata.json` is written containing: `run_date`, `pipeline_version`, `date_range_start`, `date_range_end`, `total_filings_discovered`, `total_classified`, `total_passed_filters`, `total_with_outcomes`, SHA-256 hash of the parquet file.

---

## Output Schema

### Table: backtest_results (one row per filing that received at least a classification attempt)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| accession_number | VARCHAR | NO | EDGAR accession number (primary key for this dataset) |
| cik | VARCHAR | NO | SEC CIK |
| ticker | VARCHAR | YES | Resolved ticker; NULL if UNRESOLVABLE |
| entity_name | VARCHAR | YES | Company name from master.gz |
| form_type | VARCHAR | NO | S-1, 424B4, 8-K, etc. |
| filed_at | TIMESTAMP | NO | Filing timestamp from EDGAR |
| setup_type | VARCHAR | YES | A, B, C, D, E, or NULL |
| confidence | REAL | YES | 0.0 or 1.0 (rule-based) |
| shares_offered_raw | BIGINT | YES | Raw integer from classifier |
| dilution_severity | REAL | YES | shares_offered / float_at_T |
| price_discount | REAL | YES | Offering price relative to close at T |
| immediate_pressure | BOOLEAN | YES | From rule |
| key_excerpt | VARCHAR | YES | Up to 500 chars |
| filter_status | VARCHAR | NO | PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, PRICE_FAIL, ADV_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR, UNRESOLVABLE, FETCH_FAILED |
| filter_fail_reason | VARCHAR | YES | First failed criterion name |
| float_available | BOOLEAN | NO | FALSE if filed_at < 2020-03-04 |
| in_smallcap_universe | BOOLEAN | YES | From daily_universe at T |
| price_at_T | REAL | YES | adjusted_close on filing date (or prior day) |
| market_cap_at_T | REAL | YES | From daily_market_cap at T |
| float_at_T | REAL | YES | From historical_float AS-OF filed_at; NULL if not available |
| adv_at_T | REAL | YES | 20-day dollar volume ADV from daily_prices at T |
| short_interest_at_T | REAL | YES | From short_interest AS-OF filed_at; NULL if unavailable |
| borrow_cost_source | VARCHAR | YES | SHORT_INTEREST, DEFAULT, or NULL |
| score | INTEGER | YES | 0-100; NULL if filter_status != PASSED |
| rank | VARCHAR | YES | A, B, C, D; NULL if filter_status != PASSED |
| dilution_extractable | BOOLEAN | YES | FALSE if dilution_severity could not be computed |
| outcome_computable | BOOLEAN | NO | FALSE if price_at_T is NULL or invalid |
| return_1d | REAL | YES | (close_T+1 / close_T) - 1 |
| return_3d | REAL | YES | (close_T+3 / close_T) - 1 |
| return_5d | REAL | YES | (close_T+5 / close_T) - 1 |
| return_20d | REAL | YES | (close_T+20 / close_T) - 1 |
| delisted_before_T1 | BOOLEAN | NO | TRUE if symbol delisted before T+1 |
| delisted_before_T3 | BOOLEAN | NO | TRUE if symbol delisted before T+3 |
| delisted_before_T5 | BOOLEAN | NO | TRUE if symbol delisted before T+5 |
| delisted_before_T20 | BOOLEAN | NO | TRUE if symbol delisted before T+20 |
| pipeline_version | VARCHAR | NO | Version tag of the pipeline code |
| processed_at | TIMESTAMP | NO | When this row was written |

### Table: backtest_participants (one row per named financial intermediary per filing)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| accession_number | VARCHAR | NO | FK to backtest_results |
| firm_name | VARCHAR | NO | Normalized canonical name |
| role | VARCHAR | NO | lead_underwriter, co_manager, sales_agent, placement_agent |
| is_normalized | BOOLEAN | NO | TRUE if name matched normalization table |
| raw_text_snippet | VARCHAR | YES | Up to 300 chars of source context |

---

## Edge Cases

| Case | Expected behavior |
|------|------------------|
| Filing date is a weekend | Use prior Friday's daily_prices, daily_market_cap, and daily_universe rows |
| Filing date falls on a US market holiday | Use prior trading day (requires a trading calendar lookup table) |
| Ticker resolves but has no rows in daily_prices at T | Set `outcome_computable = false`; still classify and filter |
| Multiple tickers share the same CIK (e.g., class A and class B shares) | Use the ticker whose symbol_history window covers the filing date; if both qualify, prefer the common share class (security_type = 'CS'); log if still ambiguous |
| Quarterly master.gz download fails | Log the failure, skip the quarter, and continue; surface unprocessed quarters in the run metadata |
| Filing URL from master.gz returns HTTP 404 | Log as FETCH_FAILED; do not retry 404s |
| Filing URL returns binary (XBRL instance) instead of HTML/text | Log as FETCH_FAILED with reason BINARY_CONTENT |
| Filing text is empty after HTML stripping | Set classification to NULL with reason EMPTY_TEXT |
| shares_offered is 0 after extraction AND form_type is 424B4 | Proceed; dilution_extractable = false; score = 0 |
| Symbol delisted on filing date itself | Include in output with outcome_computable = false for all horizons |
| Two filings from same company on same date (amended filing) | Treat as separate rows; do not deduplicate |
| 424B3 filing encountered | Not applicable — 424B3 is not in the Phase R1 discovery form_type set and will not be encountered; 424B3 extraction is deferred to a future phase |
| Firm name in filing text uses abbreviation not in normalization table | Store verbatim; is_normalized = false |
| historical_float has multiple rows for same symbol on same day | Use the row with the latest `date` value (most recent intraday update) |
| short_interest table is empty for a symbol in 2021+ | Treat as NULL; use default_borrow_cost; set borrow_cost_source = DEFAULT |
| 2017-2019 filing passes all non-float filters | Include in output with float_available = false and a note that rank should be interpreted with caution |
| Pipeline interrupted mid-run | The discovery and fetch phase must be idempotent: already-fetched filing texts are cached to disk and not re-fetched on resume |

---

## Out of Scope

- NOT: Real-time or live pipeline execution — this pipeline is batch-only, run offline.
- NOT: Teacher labeling (Claude LLM classification) — that is Phase R2 and depends on Phase R1 findings.
- NOT: Student model training (Llama 1B LoRA) — that is Phase R3.
- NOT: H1c validation (rule-based vs teacher agreement) — requires teacher labels not yet produced.
- NOT: H1d validation (student model F1) — requires student model not yet trained.
- NOT: Borrow cost data from IBKR API — disabled until Phase R4 per METHODOLOGY.md.
- NOT: The UNDERWRITER_FACTOR scoring multiplier — this multiplier depends on win rates computed from the backtest output; it cannot be used as an input to the same backtest. It is a Phase R1 output, not an input.
- NOT: Automated finding document generation — findings are written by the researcher after reviewing the output dataset.
- NOT: UI integration or dashboard updates — the output is a flat file for research analysis, not a live feed.
- NOT: Coverage of OTC-only securities — the backtest universe is NYSE, NASDAQ, AMEX only, consistent with the market_data certified dataset scope.
- NOT: Short borrow availability data — not in scope until Phase R4.
- Deferred: Position sizing, P&L simulation, and execution cost modeling — out of scope for signal validation.
- Deferred: FMP MCP server (localhost:8080) as a discovery source — EDGAR quarterly master.gz is the authoritative historical discovery method; the MCP server is for live production use.
- Deferred: 424B3 underwriter extraction beyond sales agent identification — structural parsing of ATM supplement supplements is a Phase R2 enhancement.

---

## Constraints

- Must: Every market data join must use only data with date <= filing date (no look-ahead bias).
- Must: Include filings for symbols that were subsequently delisted (anti-survivorship-bias rule).
- Must: Not exceed 10 HTTP requests per second to SEC domains (SEC published limit).
- Must: Use the User-Agent header format already established in the live pipeline.
- Must: The `RuleBasedClassifier` used must be tagged as `rule-based-v1` in the output `pipeline_version` field — no modifications to the core classification logic are permitted for this pipeline. The underwriter extraction is an additive step after classification, not a modification of setup type rules.
- Must: Float data hard floor is 2020-03-04. Any requirement that depends on float (filter 3, FLOAT_ILLIQUIDITY scoring component) must be skipped or flagged for pre-2020 data; it must never be imputed or estimated.
- Must: The output dataset must be reproducible — running the same pipeline against the same quarterly master.gz files and the same database snapshot must produce identical output.
- Must: All backtest_participants rows include the source filing's accession_number so that participants can be joined to price outcomes.
- Must: The output schema is frozen at the version written in this document. Changes to the schema require a revised requirements document.
- Must not: Delete or modify any rows in market_data.duckdb — this database is READ ONLY for the backtest pipeline.
- Must not: Use the AskEdgar API for historical filing discovery or text fetching at scale — the SEC quarterly master.gz + direct SEC Archives approach is required for cost and rate-limit reasons.
- Assumes: The market_data.duckdb database is at `/home/d-tuned/market_data/duckdb/market_data.duckdb` and is the certified v1.0.0 dataset (certification date 2026-02-19).
- Assumes: `daily_universe` is populated (43,168,646 rows as of certification). If the pipeline finds it empty, it must HALT with an error rather than silently producing incorrect results.
- Assumes: The normalization table of known underwriter firm names will be provided as a static configuration file before the pipeline is built. The exact contents are a research input, not a requirement for this pipeline to define.
- Assumes: A US market trading calendar (to identify non-trading days for the "prior trading day" logic) will be available as a static lookup table or derivable from gaps in `daily_prices` (days where no symbol has a price row).
- Assumes: `historical_float` and `short_interest` tables live in market_data.duckdb. If they are in a separate store, the architect must specify the join method.

---

## Open Questions (not blockers unless noted)

| # | Question | Impact | Status |
|---|----------|--------|--------|
| OQ-1 | What is the exact schema and location of `historical_float` and `short_interest` tables? The 00-PROJECT-ASSESSMENT.md references them as existing in market_data but their schemas are not in the certified DATASET-CERTIFICATION.md (suggesting they were added post-certification). | High — architect must confirm table schemas before implementation | OPEN |
| OQ-2 | Should the backtest pipeline run against market_data.duckdb directly (via DuckDB read-only connection) or against a copy? Read-only connection is preferred to protect the certified dataset. | Medium | OPEN |
| OQ-3 | What is the target wall-clock runtime budget for the full 2017-2025 run? This determines whether parallelism is required in the fetch stage. | Medium | OPEN |
| OQ-4 | The normalization table for underwriter firm names is referenced as a static config. Who provides the initial seed list (researcher vs automated extraction from a pilot run)? | Low — does not block pipeline build | OPEN |
