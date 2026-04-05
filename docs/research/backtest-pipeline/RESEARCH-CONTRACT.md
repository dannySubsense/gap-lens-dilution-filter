# Research Contract: Backtest Pipeline

**Pipeline:** backtest-pipeline v1.0  
**Contract version:** 1.0  
**Date:** 2026-04-05  
**Author:** @research-contract-writer  
**Hypotheses covered:** H1a, H1b, H1e, H1f, H1g  

---

## Purpose

This document defines the validity criteria that the backtest pipeline's output must satisfy before any result produced by it can be accepted as research evidence or cited in a white paper. It is not a functional specification. Code that passes all unit and integration tests can still produce methodologically unsound findings. This contract defines the additional bar.

Every criterion in this document is testable. Vague language ("results should be reasonable") is not used. If a criterion cannot be checked with a concrete assertion against the output data or the run manifest, it does not belong in this document.

---

## 1. Output Schema Contract

The following columns are required in `backtest_results.parquet` (and its CSV companion). A pipeline output that is missing any required column, or that contains values outside the valid ranges below, must not be used for findings.

### 1.1 Required Columns: backtest_results

| Column | Type | Nullable | Valid Range / Allowed Values | NULL Semantics |
|--------|------|----------|------------------------------|----------------|
| `accession_number` | VARCHAR | NO | 20-char EDGAR accession number, format `XXXXXXXXXX-YY-ZZZZZZ` | — |
| `cik` | VARCHAR | NO | Non-empty string; numeric digits only | — |
| `ticker` | VARCHAR | YES | 1-5 uppercase letters or alphanumeric | NULL = CIK did not resolve to a ticker (`resolution_status = UNRESOLVABLE`) |
| `entity_name` | VARCHAR | YES | Non-empty string | NULL = not present in master.gz |
| `form_type` | VARCHAR | NO | `{S-1, S-1/A, S-3, 424B2, 424B4, 8-K, 13D/A}` | — |
| `filed_at` | TIMESTAMP | NO | `2017-01-01T00:00:00` ≤ value ≤ `2025-12-31T23:59:59` | — |
| `setup_type` | VARCHAR | YES | `{A, B, C, D, E}` | NULL = classifier returned NO_MATCH or fetch failed |
| `confidence` | REAL | YES | `{0.0, 1.0}` (rule-based classifier is binary) | NULL = classifier did not run |
| `shares_offered_raw` | BIGINT | YES | ≥ 0 | NULL = shares not extractable from filing text |
| `dilution_severity` | REAL | YES | ≥ 0.0; no upper bound enforced but values > 10.0 (1000% dilution) must be flagged in findings as outliers | NULL = `float_at_T` is NULL or zero |
| `price_discount` | REAL | YES | Any real number; negative means offering above market | NULL = classifier did not extract offering price |
| `immediate_pressure` | BOOLEAN | YES | `{true, false}` | NULL = classifier did not run |
| `key_excerpt` | VARCHAR | YES | ≤ 500 characters | NULL = classifier did not run |
| `filter_status` | VARCHAR | NO | `{PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, PRICE_FAIL, ADV_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR, UNRESOLVABLE, FETCH_FAILED}` | — |
| `filter_fail_reason` | VARCHAR | YES | First failing criterion name or `FLOAT_NOT_AVAILABLE` or `NOT_IN_UNIVERSE` | NULL = `filter_status = PASSED` |
| `float_available` | BOOLEAN | NO | `{true, false}` | — (always populated; `false` iff `filed_at < 2020-03-04`) |
| `in_smallcap_universe` | BOOLEAN | YES | `{true, false}` | NULL = ticker not found in `daily_universe` on `effective_trade_date` |
| `price_at_T` | REAL | YES | > 0.0 if non-NULL | NULL = no price row in `daily_prices` for symbol at `effective_trade_date` |
| `market_cap_at_T` | REAL | YES | > 0.0 if non-NULL | NULL = no row in `daily_market_cap` for symbol at `effective_trade_date` |
| `float_at_T` | REAL | YES | > 0.0 if non-NULL; units: number of shares (not millions) | NULL = `float_available = false` OR no AS-OF row found for post-2020 filing |
| `adv_at_T` | REAL | YES | > 0.0 if non-NULL; units: USD dollar volume | NULL = fewer than 20 prior trading days of `daily_prices` rows available |
| `short_interest_at_T` | REAL | YES | ≥ 0.0 if non-NULL; units: number of shares | NULL = no AS-OF row in `short_interest` table (expected for pre-2021 filings) |
| `borrow_cost_source` | VARCHAR | YES | `{SHORT_INTEREST, DEFAULT}` | NULL = scoring did not run (`filter_status != PASSED`) |
| `score` | INTEGER | YES | 0–100 inclusive | NULL = `filter_status != PASSED` |
| `rank` | VARCHAR | YES | `{A, B, C, D}` | NULL = `filter_status != PASSED` |
| `dilution_extractable` | BOOLEAN | YES | `{true, false}` | NULL = filter stage did not run (fetch failed or no classification) |
| `outcome_computable` | BOOLEAN | NO | `{true, false}` | — (always populated; `false` iff `price_at_T` is NULL or zero) |
| `return_1d` | REAL | YES | Any real number; expected range for research-relevant events: −0.99 to +5.0; values outside −0.99 to +10.0 must be flagged as outliers | NULL = `outcome_computable = false` OR `delisted_before_T1 = true` |
| `return_3d` | REAL | YES | Same outlier range as `return_1d` | NULL = `outcome_computable = false` OR `delisted_before_T3 = true` |
| `return_5d` | REAL | YES | Same outlier range as `return_1d` | NULL = `outcome_computable = false` OR `delisted_before_T5 = true` |
| `return_20d` | REAL | YES | Any real number; expected range: −0.99 to +20.0; values outside −0.99 to +50.0 must be flagged as outliers | NULL = `outcome_computable = false` OR `delisted_before_T20 = true` |

**Note on return computation methodology:** Returns (`return_1d`, `return_3d`, `return_5d`, `return_20d`) are computed from the `adjusted_close` column in `daily_prices`. This column is split-adjusted. For small-cap stocks that undergo reverse splits — common in dilution scenarios — the `adjusted_close` values before the split date are divided by the split ratio, which can make pre-split prices appear very low. This creates apparent returns of +900% or more when the stock price has not actually changed in economic terms. These are corporate action artifacts, not real returns. Any row where `return_20d > +500%` or `return_20d < -99%` must be flagged in findings analysis as a potential corporate action artifact and investigated before being cited.
| `delisted_before_T1` | BOOLEAN | NO | `{true, false}` | — |
| `delisted_before_T3` | BOOLEAN | NO | `{true, false}` | — |
| `delisted_before_T5` | BOOLEAN | NO | `{true, false}` | — |
| `delisted_before_T20` | BOOLEAN | NO | `{true, false}` | — |
| `pipeline_version` | VARCHAR | NO | Non-empty; must match value logged in `backtest_run_metadata.json` | — |
| `processed_at` | TIMESTAMP | NO | Must be identical across all rows in the same run (set to run start time, not per-row wall clock) | — |

### 1.2 Required Columns: backtest_participants

| Column | Type | Nullable | Valid Range / Allowed Values | NULL Semantics |
|--------|------|----------|------------------------------|----------------|
| `accession_number` | VARCHAR | NO | Must match a row in `backtest_results` | — |
| `firm_name` | VARCHAR | NO | Non-empty; ≤ 200 characters | — |
| `role` | VARCHAR | NO | `{lead_underwriter, co_manager, sales_agent, placement_agent}` | — |
| `is_normalized` | BOOLEAN | NO | `{true, false}` | — |
| `raw_text_snippet` | VARCHAR | YES | ≤ 300 characters | NULL = context text was unavailable |

### 1.3 Structural Integrity Checks

Before any finding document is written, the following assertions must pass against the output files:

1. `backtest_results.parquet` must be readable by `pyarrow.parquet.read_table()` without error.
2. Zero rows may have `filter_status = PASSED` and `score IS NULL` simultaneously.
3. Zero rows may have `filter_status = PASSED` and `rank IS NULL` simultaneously.
4. Zero rows may have `outcome_computable = true` and `price_at_T IS NULL` simultaneously.
5. Zero rows may have `delisted_before_T1 = false` and `return_1d IS NULL` and `outcome_computable = true` simultaneously. (Same logic for T3, T5, T20.)
6. Zero rows may have `float_available = true` and `filed_at < 2020-03-04` simultaneously.
7. Zero rows may have `float_available = false` and `filed_at >= 2020-03-04` simultaneously. (Note: `float_at_T` may still be NULL for post-2020 filings if no AS-OF row exists — this is a data gap, not a flag violation.)
8. Every `accession_number` in `backtest_participants` must have a corresponding row in `backtest_results`.
9. `processed_at` must be identical across all rows (single constant per run).
10. `pipeline_version` must be identical across all rows and must match `backtest_run_metadata.json`.
11. The SHA-256 hash of `backtest_results.parquet` must match `backtest_run_metadata.json.parquet_sha256`.
12. Zero rows in `backtest_results` may have `setup_type` equal to the string literal `'NULL'`. All no-match cases must be represented as Parquet null (Python None), not the string `'NULL'`. The live classifier returns `setup_type="NULL"` (a string) for no-match cases; the pipeline must map this to Python None before writing to Parquet. If this mapping is missed, `WHERE setup_type IS NULL` queries will silently return zero rows.

---

## 2. Look-Ahead Bias Constraints

Look-ahead bias — the use of data that was not available at the time of the filing decision — is the most dangerous methodological failure in a backtest. A finding produced with look-ahead bias is not research evidence; it is an artifact of the pipeline design. This section defines, for each data join, what was available at time T, what was not, and how the architecture enforces the constraint.

**Definition of T:** For each filing, T is `TradingCalendar.prior_or_equal(filing.date_filed)` — the most recent trading day on or before the EDGAR filing timestamp. This adjusted date (`effective_trade_date`) is computed once in `MarketDataJoiner` and applied consistently to all joins. It is never re-derived per join.

### 2.1 Price at T

**Available at time T:** The `adjusted_close` price in `daily_prices` for the symbol on `effective_trade_date`. This is the price a short seller would have observed at the close of the last trading day on or before the filing.

**Not yet known at time T:** Any price after `effective_trade_date` — specifically `return_1d`, `return_3d`, `return_5d`, `return_20d`.

**Architecture enforcement:** `MarketDataJoiner` executes `SELECT adjusted_close FROM daily_prices WHERE symbol = ? AND trade_date = ?` with `trade_date = effective_trade_date`. Forward prices are fetched in a separate query keyed by `ROW_NUMBER() OVER (ORDER BY trade_date)` for rows with `trade_date > effective_trade_date`; this result is stored in `MarketSnapshot.forward_prices` and is only read by `OutcomeComputer` — it is never passed to `BacktestFilterEngine` or `BacktestScorer`.

**Required canary test:** In `test_bt_filter_engine.py` and `test_bt_scorer.py`, assert that neither `BacktestFilterEngine` nor `BacktestScorer` accepts a `MarketSnapshot` object that contains `forward_prices`. The `BacktestMarketData` adapter passed to `Scorer.score()` must contain exactly four fields: `adv_dollar`, `float_shares`, `price`, `market_cap` — none of which are forward-looking. A test must construct a `MarketSnapshot` with `forward_prices = {1: -0.20, 3: -0.40, 5: -0.50, 20: -0.70}` and confirm that `BacktestScorer.score()` produces the same result as it would with `forward_prices = {1: None, 3: None, 5: None, 20: None}`.

### 2.2 Float at T

**Available at time T:** The most recent `float_shares` row in `historical_float` with `trade_date <= filing.date_filed`.

**Not yet known at time T:** Any `historical_float` row with `trade_date > filing.date_filed`.

**Architecture enforcement:** `MarketDataJoiner` executes the AS-OF query: `SELECT float_shares, trade_date FROM historical_float WHERE symbol = ? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1`. The `?` parameter is `filing.date_filed` (not `effective_trade_date` — the AS-OF join uses the raw filing date for the upper bound, which is correct and conservative). For filings dated before `FLOAT_DATA_START_DATE = date(2020, 3, 4)`, this query is skipped entirely.

**Required canary test:** Given a filing dated `2022-06-15` for a symbol whose `historical_float` contains rows dated `2022-06-10` and `2022-06-20`, the AS-OF join must return the `2022-06-10` row, not the `2022-06-20` row. This test must be present in `test_market_data_joiner.py`.

### 2.3 Short Interest at T

**Available at time T:** The most recent `short_position` row in `short_interest` with `settlement_date <= filing.date_filed`.

**Not yet known at time T:** Any `short_interest` row with `settlement_date > filing.date_filed`.

**Architecture enforcement:** `MarketDataJoiner` executes `SELECT short_position, settlement_date FROM short_interest WHERE symbol = ? AND settlement_date <= ? ORDER BY settlement_date DESC LIMIT 1`. For pre-2021 filings, this query returns zero rows (the table covers 2021+); `short_interest_at_T` is set to NULL and `borrow_cost_source` is set to `DEFAULT`.

**Required canary test:** Given a filing dated `2022-03-01` for a symbol whose `short_interest` contains rows dated `2022-02-15` and `2022-03-15`, the AS-OF join must return the `2022-02-15` row. This test must be present in `test_market_data_joiner.py`.

### 2.4 Market Cap at T

**Available at time T:** The `market_cap` row in `daily_market_cap` for the symbol on `effective_trade_date`.

**Not yet known at time T:** Any `daily_market_cap` row after `effective_trade_date`.

**Architecture enforcement:** Same point-in-time date as price join: `SELECT market_cap FROM daily_market_cap WHERE symbol = ? AND trade_date = ?` with `trade_date = effective_trade_date`. No AS-OF logic required because market cap is a daily snapshot.

### 2.5 ADV at T

**Available at time T:** The 20-trading-day average dollar volume computed from `daily_prices` rows with `trade_date <= effective_trade_date`.

**Not yet known at time T:** Any volume data after `effective_trade_date`.

**Architecture enforcement:** The ADV SQL in `MarketDataJoiner` selects rows where `trade_date <= effective_trade_date` and uses `LIMIT 1 OFFSET 19` to enforce a 20-row window ending at T. A window ending at T+1 or later is architecturally prevented by the `trade_date <= ?` constraint.

**Required canary test:** Given a filing dated `2022-06-15` (effective_trade_date = `2022-06-15`), the ADV query must produce the same value regardless of whether additional price rows exist in `daily_prices` for `2022-06-16` onward. This must be demonstrated in `test_market_data_joiner.py`.

### 2.6 Universe Membership at T

**Available at time T:** The `in_smallcap_universe` flag in `daily_universe` for the symbol on `effective_trade_date`.

**Not yet known at time T:** Universe membership on any date after `effective_trade_date`, including whether the symbol is delisted.

**Architecture enforcement:** `MarketDataJoiner` executes `SELECT in_smallcap_universe FROM daily_universe WHERE symbol = ? AND trade_date = ?` with `trade_date = effective_trade_date`. Subsequent delistings have no effect on this check.

### 2.7 Underwriter Extraction

**Available at time T:** The normalized firm name and role are extracted from the filing text itself, which was filed at `filed_at`. The normalization table (`underwriter_normalization.json`) is a static config fixed at pipeline build time.

**Not yet known at time T:** Nothing in the extraction step uses future data. The normalization table does not encode any information derived from post-filing price outcomes.

**Architecture enforcement:** `UnderwriterExtractor` receives only `FetchedFiling.plain_text` and the static normalization config. It has no access to `MarketSnapshot` or any return fields.

**Prohibition:** The `UNDERWRITER_FACTOR` scoring multiplier (a proposed future component that would use historical win rates per firm) must NOT be used as an input to this pipeline. The win rates it would require are an output of this backtest; using them as inputs would create circular look-ahead contamination. This is explicitly out of scope per `01-REQUIREMENTS.md`.

### 2.8 Canary Test: T+5 Return Not Accessible in Filter/Scoring Inputs

The following canary test must exist and pass before any finding is accepted:

**Test name:** `test_canary_no_forward_return_in_scoring`

**Procedure:**
1. Create a `MarketSnapshot` with `forward_prices = {1: 0.95, 3: 0.88, 5: 0.82, 20: 0.70}` (simulating a 5% decline at T+1, 18% at T+3, etc.).
2. Create an identical `MarketSnapshot` with `forward_prices = {1: None, 3: None, 5: None, 20: None}`.
3. Run `BacktestFilterEngine.evaluate()` on both. Assert the `FilterOutcome` is identical.
4. Run `BacktestScorer.score()` on both. Assert the `ScorerResult` (score and rank) is identical.
5. Log the test result in the run manifest as `canary_no_lookahead: PASS` or `FAIL`.

If this canary test fails, the pipeline output must not be used for findings and the contract is violated.

---

## 3. Survivorship Bias Constraints

Survivorship bias in a backtest occurs when the analysis is restricted to securities that survived to the present day, inflating apparent performance because the worst-performing (often delisted) securities are excluded. This pipeline must not exhibit this bias.

### 3.1 Inclusion Rule

A filing event is eligible for inclusion in the backtest output if and only if the symbol was in `daily_universe.in_smallcap_universe = true` on `effective_trade_date`. Subsequent delistings do not affect eligibility. A symbol delisted the day after filing is as eligible as a symbol that is still actively trading in 2025.

This rule is enforced by `BacktestFilterEngine`: the universe check evaluates `snapshot.in_smallcap_universe` (a value derived from the filing date), not current active status.

### 3.2 Treatment of Delisted Symbols Post-Filing

When a symbol delists before a return horizon is reached, the return at that horizon is NULL and `delisted_before_TN = true`. This row remains in the output; it is not removed. Aggregate statistics that depend on return values (win rate, mean return, Sharpe ratio) must state explicitly how NULL returns are treated:

- **Conservative treatment (required for primary claims):** Treat NULL returns at a given horizon as the worst-observed return in the sample for that horizon. This penalizes the strategy for delistings, which is methodologically conservative and appropriate for a short-selling strategy (a delisted long counterpart is a win for the short seller — but this pipeline does not simulate P&L, so the conservative treatment is to flag the limitation, not to simulate outcomes).
- **Sensitivity analysis (required if delistings exceed 5% of returns at any horizon):** Report win rates computed both including NULLs-as-worst and excluding NULL rows entirely. The gap between the two is the delisting sensitivity.

### 3.3 Required Reporting: Delisted Symbol Disclosure

The finding document `001_backtest_results.md` must include the following statistics:

- Total events with `filter_status = PASSED` (the analysis universe).
- Of those, count and percentage with `delisted_before_T5 = true`.
- Of those, count and percentage with `delisted_before_T20 = true`.

**If the percentage of events with `delisted_before_T20 = true` exceeds 10% of the PASSED universe, this finding must be disclosed in the white paper abstract and in the limitations section of the relevant finding document.** The disclosure text must state the exact percentage and must explain that return distributions at the T+20 horizon are censored.

### 3.4 UNRESOLVABLE Filing Distribution

Filings whose CIK is not found in `raw_symbols_massive` are assigned `filter_status = UNRESOLVABLE` and are excluded from all market data joins. These exclusions could introduce survivorship bias if the missing tickers systematically skew toward distressed or recently delisted companies (i.e., the companies most likely to undergo dilutive offerings).

**Required analysis:** Before accepting findings, the researcher must inspect the distribution of UNRESOLVABLE filings by year and form_type. This data is available in the run manifest field `total_unresolvable_count` and can be broken out from the output Parquet by querying:
```sql
SELECT YEAR(filed_at) AS year, form_type, COUNT(*) AS unresolvable_count
FROM backtest_results
WHERE filter_status = 'UNRESOLVABLE'
GROUP BY 1, 2
ORDER BY 1, 2
```

**Threshold:** If the UNRESOLVABLE rate exceeds 5% of total discovered filings for any single calendar year, the survivorship bias disclosure in the white paper must state this explicitly and discuss the potential direction of bias (i.e., whether the unresolvable filings are more likely to be from distressed issuers than the resolved population).

### 3.5 Prohibition

The pipeline must not, at any stage, filter its input based on whether a symbol is currently active (i.e., active as of the pipeline run date, 2026). The `CIKResolver` correctly queries both active and inactive symbols via `raw_symbols_massive` (which contains an `active` column but uses it only for tie-breaking in CIK resolution, not for exclusion). This must be confirmed in `test_cik_resolver.py` with a test that resolves a CIK for a known-delisted symbol and confirms the filing is included in the output.

---

## 4. Two-Tier Coverage Rules

The float data constraint creates two tiers of analytical validity. Mixing tier outputs in aggregate statistics without labeling is a methodological error that would invalidate any claim so made.

### 4.1 Tier Definitions

| Tier | Date range | `float_available` | Valid claims |
|------|------------|-------------------|--------------|
| Partial fidelity | `filed_at < 2020-03-04` | `false` | Setup type distribution; directional price signal (H1b qualified); raw signal counts |
| Full fidelity | `filed_at >= 2020-03-04` | `true` | All claims including scoring formula, rank comparison (H1a), FLOAT_ILLIQUIDITY analysis |

The boundary date `2020-03-04` is `FLOAT_DATA_START_DATE` in `market_data_joiner.py`. It is the first date for which FMP's historical float endpoint provides data.

### 4.2 Partial Tier: Permitted Claims (2017–2019)

Findings that cite 2017-2019 data may make claims only about:

- Setup type classification rate per form type (what fraction of filings of each type yield a non-NULL setup type).
- Directional price signal: whether returns at T+1, T+3, T+5 are negative more often than not, disaggregated by setup type.
- Rank is computed for 2017-2019 filings and stored in the output, but rank in this tier is based on a partial scorer (FLOAT_ILLIQUIDITY = 1.0 neutral, no dilution severity if float unavailable). **Rank-based claims using 2017-2019 data must be labeled "Partial-fidelity tier (2017-2019): rank approximation only; FLOAT_ILLIQUIDITY not available."**

### 4.3 Full Tier: Permitted Claims (2020–2025)

Full-tier findings may make claims about:

- Rank A vs Rank B return distributions (H1a).
- Setup type edge (H1b) using the complete scoring formula.
- FLOAT_ILLIQUIDITY contribution to signal quality.
- Any claim involving the full scoring formula: `DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY / BORROW_COST`.
- Underwriter-level win rates (H1e, H1f, H1g) — these must use the full-tier universe.

### 4.4 Prohibition: No Unlabeled Tier Mixing

The following are prohibited:

- Aggregate win rate statistics that include both `float_available = true` and `float_available = false` rows without explicit labeling in the finding text and any table headers.
- A Sharpe ratio computed over the full 2017-2025 date range without a separate disclosure that 2017-2019 uses partial scoring.
- Any claim about `SETUP_QUALITY × FLOAT_ILLIQUIDITY` scoring must cite only 2020-2025 data. A claim that names this scoring interaction but uses pre-2020 rows is a contract violation.

**Enforcement mechanism:** Every finding document that presents aggregate statistics must include a SQL `WHERE` clause (or equivalent filter description) specifying which tier(s) the data comes from. Unfiltered aggregates are not acceptable.

**Required filter for H1a claims:**
```sql
WHERE filter_status = 'PASSED'
  AND float_available = true
  AND outcome_computable = true
```

**Required filter for H1b claims (full fidelity):**
Same as H1a filter.

**Acceptable filter for H1b claims (extended 2017-2019 with disclosure):**
```sql
WHERE filter_status = 'PASSED'
  AND outcome_computable = true
-- Requires disclosure: "includes 2017-2019 partial-fidelity tier; rank is approximation"
```

---

## 5. Underwriter Extraction Validity

Results from `backtest_participants` may not be cited in findings (H1e, H1f, H1g) until the extraction component has passed the following validation gate.

### 5.1 Required Human-Review Sample

Before firm-level findings are cited, the `UnderwriterExtractor` must be validated against a human-reviewed sample of 50 filings.

**Sampling procedure:**
- Select 50 filings at random from the backtest output where `filter_status = PASSED` and `form_type IN ('424B4', 'S-1', '8-K')`.
- Stratify the sample: at least 20 must be 424B4 or S-1 (lead underwriter extraction), at least 15 must be 8-K ATM announcements (sales agent extraction).
- For each selected filing, retrieve the plain text from `research/cache/filing_text/` and manually identify all financial intermediaries and their roles by reading the "Plan of Distribution" section (for 424B4/S-1) or the body text (for 8-K).

**Review output:** A spreadsheet with columns: `accession_number`, `form_type`, `expected_firm_name`, `expected_role`, `extracted_firm_name`, `extracted_role`, `match_type`, `notes`.

### 5.2 Accuracy Threshold

**Definition of a match:** An extraction is a match if the extracted `firm_name` (after normalization) resolves to the same canonical firm as the expected firm name identified by human review. Canonical comparison is case-insensitive and strips legal suffixes (`LLC`, `Inc.`, `& Co.`, `Securities`, `Capital`).

Examples:
- `"H.C. Wainwright & Co."` extracted vs `"H.C. Wainwright"` expected: **MATCH** (same canonical firm).
- `"Maxim Group LLC"` extracted vs `"Maxim Group"` expected: **MATCH**.
- `"Maxim Group LLC"` extracted vs `"Spartan Capital Securities"` expected: **NO MATCH**.
- `"Unknown"` or no extraction vs firm present in filing: **NO MATCH** (missed extraction, not a hallucination).
- A firm name extracted that does not appear anywhere in the filing text: **HALLUCINATION** (treated as NO MATCH with a separate flag).

**Required accuracy:** ≥ 85% match rate across the 50-filing sample, computed as:
```
accuracy = (number of expected firms matched) / (total expected firms in sample)
```

where total expected firms counts every `(accession_number, role)` pair identified by human review.

**"Unknown" is acceptable; hallucinated firm names are not.** If the extractor produces a firm name that does not appear in the filing text, that is a hallucination. Hallucinations count as incorrect and must be counted separately in the validation report. A hallucination rate above 5% (more than 2-3 hallucinations in the 50-filing sample) requires investigation and code fix before any firm-level finding is accepted.

**Confidence interval disclosure:** At N=50 and an observed accuracy of 85%, the 95% Wilson confidence interval is approximately [72.6%, 92.8%]. A lower bound of 72.6% means roughly 1 in 4 firm-filing associations could be wrong, which would materially distort per-firm win rates. To narrow this CI to ±7%, a validation sample of at least 100 filings is preferred. If the validation sample size is 50 filings, the confidence interval must be reported alongside the accuracy figure in the white paper. All underwriter win rate claims (H1e) must acknowledge the extraction accuracy lower bound.

**If accuracy is below 85%:** The `UnderwriterExtractor` must be revised and re-validated before H1e, H1f, or H1g findings are accepted. The finding status for those hypotheses must remain BLOCKED until re-validation passes.

### 5.3 Validation Artifact

The validation spreadsheet and its aggregate statistics must be logged in `RESEARCH_LOG.md` as a finding entry (type: Finding, with the accuracy score, hallucination count, and sample composition). This entry is the gate record.

---

## 6. Sample Size Thresholds

Research claims made with insufficient sample sizes carry intervals too wide to be meaningful. The following thresholds define the minimum sample sizes for each claim type. Below-threshold samples are flagged as "insufficient sample" — they are not silently omitted and they are not reported as if the thresholds were met.

### 6.1 Per-Setup-Type Win Rate

**Minimum N:** 30 events with `filter_status = PASSED` AND `float_available = true` AND `outcome_computable = true` AND `return_5d IS NOT NULL` for each setup type before a win rate for that setup type may be cited.

**Below threshold:** Report as: "Setup type [X]: N=[count] events — insufficient sample (threshold: 30). Win rate not reported."

### 6.2 Per-Firm Win Rate

**Minimum N:** 20 events where `backtest_participants.firm_name = [canonical firm name]` AND the associated filing has `filter_status = PASSED` AND `outcome_computable = true` AND `return_5d IS NOT NULL`.

**Below threshold:** Report as: "Firm [name]: N=[count] qualifying events — insufficient sample (threshold: 20). Firm-level win rate not reported."

**Note for H1f (concentration analysis):** Even if a firm's win rate cannot be cited (N < 20), the firm's presence and event count must still be included in the concentration/frequency table — only the win rate column is suppressed.

### 6.3 Aggregate Sharpe Ratio

**Minimum N:** 100 events with `filter_status = PASSED` AND `float_available = true` AND `outcome_computable = true` AND `return_5d IS NOT NULL`.

**Below threshold:** Do not report Sharpe ratio. Report: "Sharpe ratio not computed — insufficient sample (N=[count]; threshold: 100)."

### 6.4 Rank Comparison (H1a)

**Minimum N per rank:** 30 events per rank level (Rank A and Rank B separately) before a rank comparison claim is made. If Rank A has 30+ events but Rank B has fewer than 30, the comparison cannot be made.

**Below threshold:** Report as: "Rank [X]: N=[count] events — insufficient sample for rank comparison."

### 6.5 Role-Level Win Rate Comparison (H1g)

**Minimum N:** 20 events per role type (`lead_underwriter` separately from `sales_agent`) before a role-level comparison is made.

**Below threshold:** Report the role as "insufficient sample" and state explicitly that H1g cannot be evaluated for that role with current data.

### 6.6 Reporting of Below-Threshold Results

All below-threshold setup types, firms, and role combinations must be reported in findings tables, with N shown and the "insufficient sample" label applied. They must not be omitted from tables. Omitting a setup type because it has low count is cherry-picking (prohibited by METHODOLOGY.md rule 1).

---

## 7. Reproducibility Requirements

A finding that cannot be reproduced from a stated run is not a finding — it is an anecdote. Every cited result must be traceable to a specific pipeline run.

### 7.1 Run ID Requirement

Every cited result in a finding document must reference a specific `run_id`. The `run_id` is defined as the SHA-256 hash of `backtest_results.parquet` as recorded in `backtest_run_metadata.json`.

Citation format: `(run_id: <first 12 chars of SHA-256>, metadata: backtest_run_metadata.json)`.

A finding document that presents results without citing a `run_id` may not be included in the white paper.

### 7.2 Run Manifest Required Fields

`backtest_run_metadata.json` must contain all of the following fields. A run manifest missing any required field is incomplete and the run must not be cited.

| Field | Type | Required value / constraint |
|-------|------|-----------------------------|
| `run_date` | ISO 8601 string | UTC timestamp of pipeline run start |
| `pipeline_version` | string | e.g. `"backtest-v1.0.0"` — must match `backtest_results.pipeline_version` in every row |
| `classifier_version` | string | Must be `"rule-based-v1"` for Phase R1 runs |
| `date_range_start` | string | ISO 8601 date, e.g. `"2017-01-01"` |
| `date_range_end` | string | ISO 8601 date, e.g. `"2025-12-31"` |
| `form_types` | list of strings | The exact set used, e.g. `["S-1", "S-1/A", "S-3", "424B2", "424B4", "8-K", "13D/A"]` |
| `market_cap_threshold` | integer | In USD; e.g. `2000000000` |
| `float_threshold` | integer | In shares; e.g. `50000000` |
| `dilution_pct_threshold` | float | e.g. `0.10` |
| `price_threshold` | float | e.g. `1.00` |
| `adv_threshold` | float | In USD; e.g. `500000.0` |
| `scoring_formula_version` | string | e.g. `"v1.0"` — must reference the exact formula used |
| `float_data_start` | string | Must be `"2020-03-04"` |
| `market_data_db_path` | string | Absolute path to `market_data.duckdb` used |
| `market_data_db_certification` | string | e.g. `"v1.0.0 (certified 2026-02-19)"` |
| `execution_timestamp` | ISO 8601 string | UTC timestamp of run start (same as `run_date`) |
| `total_filings_discovered` | integer | ≥ 0 |
| `total_cik_resolved` | integer | ≥ 0 |
| `total_fetch_ok` | integer | ≥ 0 |
| `total_classified` | integer | ≥ 0 |
| `total_passed_filters` | integer | ≥ 0 |
| `total_with_outcomes` | integer | ≥ 0 |
| `total_unresolvable_count` | integer | ≥ 0; count of filings assigned `filter_status = UNRESOLVABLE` (CIK not in `raw_symbols_massive`) |
| `quarters_failed` | list of strings | Empty list if all quarters succeeded |
| `parquet_sha256` | string | 64-char hex SHA-256 |
| `parquet_row_count` | integer | Must match actual row count in the Parquet file |
| `canary_no_lookahead` | string | `"PASS"` or `"FAIL"` — result of canary test from Section 2.8 |
| `normalization_config_loaded` | boolean | `true` if `underwriter_normalization.json` was loaded and non-empty; `false` if the file was missing or empty |
| `normalization_config_entry_count` | integer | Number of normalization mappings loaded; 0 if config was missing or empty |

### 7.3 Determinism Requirement

Running the pipeline twice against the same inputs must produce byte-for-byte identical `backtest_results.parquet` output. "Same inputs" means: same `market_data.duckdb` state, same quarterly master.gz cache files, same underwriter normalization config, same pipeline version.

Determinism is enforced by:
- Output DataFrame sorted by `(cik, filed_at, accession_number)` before writing.
- `processed_at` set to the run start timestamp (a constant for all rows), not per-row wall clock.
- Parquet written with fixed row group size and `snappy` compression (deterministic codec).

**Verification procedure:** Run the pipeline twice on the same cache with `--resume`. Compute `sha256sum backtest_results.parquet` for both runs. If the hashes differ, the determinism requirement is violated and neither run may be cited until the non-determinism is identified and fixed.

### 7.4 Version Pinning

The following must be fixed at the time the cited run is executed and must not change between runs cited in the same finding document:

- `RuleBasedClassifier` version (must be `"rule-based-v1"`; no modifications permitted during Phase R1).
- `Scorer.score()` formula (must match `scoring_formula_version` in the run manifest).
- `underwriter_normalization.json` contents (changes require a new run and new run_id).
- `market_data.duckdb` certification state (must be v1.0.0 certified dataset).

---

## 8. Research Validity Acceptance Criteria

The following checklist must be completed before any result from a pipeline run is accepted as research evidence. Each criterion is mapped to the hypothesis sub-claim it protects. The checklist must be recorded in the finding document as a completed table.

### Acceptance Checklist

| # | Criterion | How to verify | Hypothesis protected | Pass / Fail |
|---|-----------|---------------|----------------------|-------------|
| RC-01 | All Section 1.3 structural integrity checks pass against the output Parquet file | Run assertions programmatically; all must pass | H1a, H1b, H1e, H1f, H1g | |
| RC-02 | `backtest_run_metadata.json` contains all fields listed in Section 7.2 | Check JSON key set | H1a, H1b, H1e, H1f, H1g | |
| RC-03 | `canary_no_lookahead = "PASS"` in run manifest | Check JSON field | H1a, H1b | |
| RC-04 | Determinism verified: two runs produce identical Parquet SHA-256 | Run pipeline twice; compare hashes | H1a, H1b, H1e, H1f, H1g | |
| RC-05 | All 32 quarters (2017 Q1 – 2025 Q4) are accounted for: either in `total_filings_discovered` or in `quarters_failed` with explicit documentation | Check manifest; if any quarters failed, document in finding as a coverage gap | H1a, H1b | |
| RC-06 | H1a analysis uses only rows where `float_available = true` AND `filter_status = PASSED` AND `outcome_computable = true` | Verify SQL filter in finding document | H1a (Rank A vs Rank B claims) | |
| RC-07 | H1b analysis that cites scoring formula uses only rows where `float_available = true` | Verify SQL filter in finding document | H1b (setup type edge claims) | |
| RC-08 | Delisted symbol disclosure completed: `delisted_before_T20` percentage computed and disclosed if > 10% | Check finding document statistics section | H1a, H1b (return distribution validity) | |
| RC-09 | Win rates cited only for setup types and firms meeting minimum N thresholds (Section 6); below-threshold results flagged, not omitted | Check finding tables for "insufficient sample" labels | H1a, H1b, H1e, H1f, H1g | |
| RC-10 | Underwriter extraction accuracy ≥ 85% validated on 50-filing human-review sample and logged in RESEARCH_LOG.md (Section 5) before H1e/H1f/H1g findings are cited | Check RESEARCH_LOG.md for validation entry | H1e, H1f, H1g | |
| RC-11 | Null results (falsified sub-hypotheses) documented with same detail as confirmed findings — failure distributions are reported, not suppressed | Check finding document for any setup type or rank with random returns | H1a, H1b, H1e, H1f, H1g | |
| RC-12 | No aggregate statistics mix 2017-2019 and 2020-2025 data without explicit labeling of tier membership | Check all table headers and SQL filters in finding document | H1a, H1b | |
| RC-13 | Win rate confidence intervals (Wilson score) computed for all cited win rates (Section 9) | Check finding document | H1a, H1b, H1e, H1f, H1g | |
| RC-14 | Sharpe ratio, if cited, states return series, period, and risk-free rate assumption (Section 9) | Check finding document | H1a | |
| RC-15 | No "statistically significant" language used without a stated test name and p-value threshold (Section 9) | Check finding document text | H1a, H1b, H1e, H1f, H1g | |
| RC-16 | `classifier_version = "rule-based-v1"` in run manifest — no classifier modifications were made during Phase R1 | Check manifest field | H1a, H1b (signal is from unmodified rule-based-v1, not a fitted model) | |
| RC-17 | The count of rows where `ABS(return_20d) > 500%` is documented in the findings and each such row has been investigated for corporate action artifacts (reverse splits) before being cited (see Section 1.1 return methodology note) | Check finding document for artifact investigation section | H1a, H1b | |
| RC-18 | If `normalization_config_entry_count = 0` in the run manifest, H1e, H1f, and H1g findings must not be cited; the run manifest must disclose this | Check manifest field `normalization_config_entry_count` before citing firm-level findings | H1e, H1f, H1g | |

**All 18 criteria must pass.** A finding document where any criterion is marked FAIL or left blank must not be submitted for white paper inclusion. The finding may be published to `docs/research/findings/` as a preliminary or blocked finding, with the failing criterion noted.

---

## 9. White Paper Citation Standard

These rules apply to any result from this pipeline when cited in the white paper. They exist to prevent the white paper from making claims that are not supported by the evidence standard of the research.

### 9.1 Win Rate Claims

Every win rate claim must include a 95% confidence interval computed using the Wilson score interval.

**Formula:**
```
p̂ = successes / n
z = 1.96  (for 95%)
center = (p̂ + z²/(2n)) / (1 + z²/n)
half_width = z * sqrt(p̂(1−p̂)/n + z²/(4n²)) / (1 + z²/n)
CI = [center − half_width, center + half_width]
```

**Required citation format:**
> "Setup type C produced a 5-day win rate of 68.3% (95% CI: [61.2%, 74.7%], N=120, run_id: a3f9c2d1b8e4)."

A win rate cited without a confidence interval is not acceptable in the white paper.

### 9.2 Sharpe Ratio Claims

Every Sharpe ratio claim must state:

1. **Return series:** Which return column was used (e.g., `return_5d`) and whether returns are raw or annualized. For a 5-day return series, if annualizing: multiply mean return by 52 (52 trading weeks per year) and multiply standard deviation by √52.
2. **Period:** The exact date range of the subset used (e.g., "2020-01-01 to 2025-12-31, full-fidelity tier only").
3. **Risk-free rate assumption:** Use 0% as the default unless the finding document explicitly states otherwise and provides justification.
4. **N:** The number of return observations used in the calculation.

**Required citation format:**
> "Annualized Sharpe ratio of 1.42 computed from 5-day returns (return_5d), 2020-2025, N=247 events, risk-free rate = 0%, run_id: a3f9c2d1b8e4."

A Sharpe ratio cited without all four components is not acceptable in the white paper.

### 9.3 Statistical Significance Language

The phrase "statistically significant" (and equivalent phrases: "significant difference", "significant predictor", "significantly different from random") is prohibited in the white paper unless:

1. The specific statistical test is named (e.g., "two-sample t-test", "Mann-Whitney U test", "chi-squared test").
2. The p-value threshold is stated as p < 0.05 (the default for this research program, per METHODOLOGY.md) unless a different threshold is explicitly justified in the finding document.
3. The actual p-value or test statistic is reported.

**Acceptable:** "The mean 5-day return for Rank A signals (−12.3%) was significantly different from zero (one-sample t-test: t(89) = −4.21, p < 0.001)."

**Not acceptable:** "Rank A signals produced significantly better returns than Rank B signals."

### 9.4 Minimum N Per Claim

Minimum sample sizes per Section 6 apply to white paper claims without exception. Claims made below the minimum N threshold are not acceptable in the white paper regardless of whether they appear to show strong effects. A strong effect in a small sample is not evidence — it is noise.

### 9.5 Null Results

If any sub-hypothesis is falsified (H1a, H1b, H1e, H1f, or H1g), the null result must be reported in the white paper with the same detail as a confirmed finding:

- The return distributions must be shown (not just a statement that the signal was absent).
- The sample size must be stated.
- The confidence intervals must be computed.
- The finding must be assigned a finding document number in `docs/research/findings/`.

Per METHODOLOGY.md rule 4: "If a hypothesis is falsified, it is recorded as a finding with the same detail as a confirmation. Null results are results." This applies equally to the white paper. Suppressing a null result — reporting positive findings but omitting tested hypotheses that showed no effect — is research misconduct. Any finding document that omits a tested hypothesis because the result was null is incomplete.

### 9.6 Run ID Citation

Every quantitative result cited in the white paper must include the `run_id` (first 12 characters of `parquet_sha256`) and a reference to `backtest_run_metadata.json`. Results without a `run_id` citation cannot be traced to a specific pipeline configuration and are not citable.

---

## 10. Contract Versioning

This contract is version 1.0, dated 2026-04-05. It governs all Phase R1 backtest pipeline runs.

Changes to this contract require:
1. A new contract version number and date.
2. A `RESEARCH_LOG.md` entry explaining the change and its rationale.
3. If the change relaxes a constraint (e.g., lowers a minimum N threshold), explicit justification for why the relaxation is methodologically acceptable.
4. Any pipeline runs cited under a previous contract version must be clearly labeled with the contract version under which they were produced.

---

*End of Research Contract*
