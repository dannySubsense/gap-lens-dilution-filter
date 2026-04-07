# Brief for DB Agent — market_data.duckdb

**From:** gap-lens-dilution-filter backtest pipeline
**Date:** 2026-04-07
**Priority:** Blocking — pipeline cannot run until item 1 is resolved

---

## 1. Storage Format Migration (BLOCKING)

**Problem:** The Python `duckdb` library is at v1.5.1. The database was created/maintained with duckdb CLI v1.1.3. When Python tries to open the file, it hits:

```
InternalException: ExtractIndexStorageInfo: index storage info with name 'idx_intraday_bars_date' not found
```

The CLI v1.1.3 opens fine. This is a storage format incompatibility — the index metadata written by 1.1.3 can't be read by 1.5.1.

**Requested action:** Migrate the database to a format readable by duckdb 1.5.x. Safest approach:

```bash
# 1. Backup
cp /home/d-tuned/market_data/duckdb/market_data.duckdb \
   /home/d-tuned/market_data/duckdb/market_data.duckdb.bak

# 2. Export with current CLI (v1.1.3)
duckdb /home/d-tuned/market_data/duckdb/market_data.duckdb \
  -c "EXPORT DATABASE '/tmp/market_data_export';"

# 3. Install duckdb CLI 1.5.1 (or latest), then import
duckdb /home/d-tuned/market_data/duckdb/market_data_v2.duckdb \
  -c "IMPORT DATABASE '/tmp/market_data_export';"

# 4. Verify row counts match (38 tables)
# 5. Swap: rename v2 → market_data.duckdb
```

Alternative (less safe): upgrade duckdb CLI in-place and let it auto-upgrade the storage on open.

**Verification we need:** After migration, this must work without error:
```python
import duckdb  # v1.5.1
con = duckdb.connect('/home/d-tuned/market_data/duckdb/market_data.duckdb', read_only=True)
con.execute('SELECT COUNT(*) FROM daily_prices').fetchone()
con.close()
```

---

## 2. CIK Coverage Question (NON-BLOCKING, but affects pipeline yield)

Our backtest pipeline resolves SEC CIK numbers from `raw_symbols_massive` to match EDGAR filings to tickers. Current coverage:

| Exchange | Tickers | Has CIK | Coverage |
|----------|---------|---------|----------|
| XNAS (NASDAQ) | 11,620 | 10,802 | 93.0% |
| XNYS (NYSE) | 10,825 | 9,264 | 85.6% |
| XASE (AMEX) | 1,939 | 1,562 | 80.6% |
| ARCX (NYSE Arca) | 4,373 | 2,916 | 66.7% |
| OTC Link | 15,973 | 0 | 0.0% |
| (empty) | 19,248 | 3,276 | 17.0% |

**Questions:**
- Is there a CIK enrichment pipeline planned or already available? SEC's EDGAR company search API can map company names to CIK. The 85-93% coverage on major exchanges is workable but leaves ~1,500+ NYSE tickers without CIK.
- What is the source for the CIK column today? (Polygon? SEC bulk download? Manual?)
- Any known issues with the 19K tickers that have no `primary_exchange` value?

---

## 3. Schema Clarification (NON-BLOCKING, informational)

We've verified the schemas we need and found one column name difference from our assumption:

| Table | Column we assumed | Actual column | Status |
|-------|-------------------|---------------|--------|
| `historical_float` | `trade_date` | `trade_date` | Correct |
| `historical_float` | `float_shares` | `float_shares` | Correct |
| `short_interest` | `trade_date` | **`settlement_date`** | Need to patch our joiner |
| `short_interest` | `short_position` | `short_position` | Correct |

We'll patch `market_data_joiner.py` to use `settlement_date` for the short interest AS-OF join.

---

## 4. Data Freshness (INFORMATIONAL)

Current ranges we observed:

| Table | Min Date | Max Date | Rows |
|-------|----------|----------|------|
| daily_prices | 2009-01-02 | 2026-04-06 | 33.8M |
| historical_float | 2020-03-04 | 2026-04-06 | 8.5M |
| short_interest | 2021-01-15 | 2026-03-13 | 580K |
| daily_universe | 2009-01-02 | 2026-04-06 | 52.2M |
| daily_market_cap | 2011-04-18 | 2026-04-06 | 28.8M |
| raw_symbols_massive | — | — | 67.2K |

Short interest ends at 2026-03-13 — is it expected to be ~3 weeks behind?
