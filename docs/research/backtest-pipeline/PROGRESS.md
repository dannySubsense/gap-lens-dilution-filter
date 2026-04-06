# Progress: backtest-pipeline

**Spec:** docs/research/backtest-pipeline/
**Started:** 2026-04-05
**Status:** COMPLETE

---

## Slices

- [x] Slice 1: Directory Scaffold and Shared Dataclasses — COMPLETE (2026-04-05)
- [x] Slice 2: TradingCalendar — COMPLETE (2026-04-05) [mock fallback while DB locked]
- [x] Slice 3: FilingDiscovery — COMPLETE (2026-04-05)
- [x] Slice 4: CIKResolver — COMPLETE (2026-04-05) [mock DB; real-DB integration pending lock release]
- [x] Slice 5: FilingTextFetcher — COMPLETE (2026-04-05)
- [x] Slice 6: BacktestClassifier — COMPLETE (2026-04-05)
- [x] Slice 7: UnderwriterExtractor — COMPLETE (2026-04-05)
- [x] Slice 8: MarketDataJoiner — COMPLETE (2026-04-05) [mock DB; schema columns to verify against real DB]
- [x] Slice 9: BacktestFilterEngine — COMPLETE (2026-04-05) [fixed dilution boundary: < → <=; added ADV+boundary tests; 27/27]
- [x] Slice 10: BacktestScorer — COMPLETE (2026-04-05) [20/20]
- [x] Slice 11: OutcomeComputer — COMPLETE (2026-04-05) [12/12]
- [x] Slice 12: OutputWriter and RunManifest — COMPLETE (2026-04-05) [8/8]
- [x] Slice 13: PipelineOrchestrator — COMPLETE (2026-04-05) [4/4 active, 1 skipped]; fixed PRICE_FAIL/ADV_FAIL canonical set (11 values now)
- [x] Slice 14: Research Contract Validation — COMPLETE (2026-04-05) [22/22] commit 7d9fdf5

---

## Current

Slice: 14 (ALL SLICES COMPLETE)
Step: DONE
Last updated: 2026-04-06

---

## Fix Attempts

| Test/File | Attempts | Last Error |
|-----------|----------|------------|
| bt_filter_engine.py | 1 | Dilution boundary: < instead of <=; fixed |

---

## Pre-Run Checklist (before first full pipeline run)

- [ ] Confirm PID 451482 backfill complete (~10h remaining as of 2026-04-06)
- [ ] Verify schema columns against real DB:
  ```bash
  duckdb /home/d-tuned/market_data/duckdb/market_data.duckdb -c \
    "DESCRIBE historical_float; DESCRIBE short_interest;"
  ```
  Expected: `historical_float.trade_date`, `short_interest.short_position`
  If different: patch `research/pipeline/market_data_joiner.py`
- [ ] Smoke test: `python research/run_backtest.py --dry-run 1`
- [ ] Full run: `python research/run_backtest.py --start-date 2017-01-01 --end-date 2025-12-31`
- [ ] Re-run Slices 2, 4, 8 tests against live DB to clear mock-DB caveats

---

## Notes

- Spec directory: docs/research/backtest-pipeline/
- Research pipeline lives under research/ at project root
- No production app/ code modified at any point
- market_data.duckdb: /home/d-tuned/market_data/duckdb/market_data.duckdb (read-only)
- DB backfill (PID 451482: 2009-01-01 to 2016-06-30) ~10h remaining as of 2026-04-06; all DB tests use in-memory fixtures until complete
- Column names to verify against real DB once lock releases: historical_float.trade_date, short_interest.short_position
- filter_status canonical set expanded to 11 values (added PRICE_FAIL, ADV_FAIL) — updated in dataclasses.py, 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, RESEARCH-CONTRACT.md
- Commit: 7d9fdf5 (45 files, 12,012 insertions)
