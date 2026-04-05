# Progress: dilution-short-filter

## Status: IN_PROGRESS

## Slices
- [x] Slice 1: Project Scaffold — COMPLETE (2026-04-05, commit f599ca7, 29/29 tests)
- [x] Slice 2: DuckDB Foundation — COMPLETE (2026-04-05, commit 3ccc347, 10/10 tests)
- [x] Slice 3: Config Extension — COMPLETE (2026-04-05, commit 3ccc347, 17/17 tests)
- [x] Slice 4: Pydantic Models — COMPLETE (2026-04-05, commit cac3d12, 15/15 tests)
- [x] Slice 5: FMP Client — COMPLETE (2026-04-05, commit cac3d12, 7/7 tests)
- [x] Slice 6: Filing Fetcher + Ticker Resolver — COMPLETE (2026-04-05, commit cac3d12, 13/13 tests)
- [x] Slice 7: EDGAR Poller — COMPLETE (2026-04-05, commit 66ed0f0, 6/6 tests)
- [x] Slice 8: Filter Engine — COMPLETE (2026-04-05, commit 66ed0f0, 16/16 tests)
- [x] Slice 9: Classifier Protocol + Rule-Based — COMPLETE (2026-04-05, commit 66ed0f0, 18/18 tests)
- [x] Slice 10: Scorer — COMPLETE (2026-04-05, commit 7abbe24, 9/9 tests)
- [x] Slice 11: Signal Manager — COMPLETE (2026-04-05, commit 9f1159e, 7/7 tests)
- [x] Slice 12: Pipeline Integration — COMPLETE (2026-04-05, commit 07ab170, 6/6 tests)
- [x] Slice 13: API Routes — COMPLETE (2026-04-05, commit 1ef4eb2, 7/7 tests)
- [x] Slice 14: Frontend Shell — COMPLETE (2026-04-05, commit 31bd049, tsc PASS)
- [x] Slice 15: Signal Rows + Auto-Refresh — COMPLETE (2026-04-05, commit cf0eb51, tsc PASS)
- [x] Slice 16: Setup Detail + Position Tracking — COMPLETE (2026-04-05, commit e55f484, tsc PASS)
- [x] Slice 17: End-to-End Smoke Test — COMPLETE (2026-04-05, commit e55f484, 1/1 tests)
- [x] Post-Slice Fix: dilution_severity pipeline step 7.5 — COMPLETE (2026-04-05, commit 59adcb3, 161/161 tests)

## Current
Slice: ALL COMPLETE
Step: DONE — Phase 1 fully resolved, 161/161 unit tests + 16/16 Playwright QC passing
Last updated: 2026-04-05

## Fix Attempts
| Test/File | Attempts | Last Error |
|-----------|----------|------------|

## Post-Implementation Findings (commit 15bc101, 2026-04-05)

Five production bugs caught by Playwright QC run — invisible to unit test suite:

| # | Bug | File(s) | Root Cause |
|---|-----|---------|------------|
| 1 | Browser blocked all API calls | `app/main.py` | No CORS middleware; curl/httpx don't enforce CORS but browsers do |
| 2 | Backend fatal crash under concurrent load | `app/services/db.py` + all callers | Single DuckDB connection shared across `asyncio.to_thread` calls; execute+fetchall split between threads |
| 3 | P&L never computed when entry/cover recorded in separate requests | `app/services/signal_manager.py` | `record_position` only computed P&L when both values were in the same request |
| 4 | Poller crashed with `'str' has no .get` | `app/services/edgar_poller.py` | EFTS endpoint returned non-dict JSON on some responses |
| 5 | Backend crashed on startup | `app/utils/ticker_resolver.py` | SEC company_tickers_exchange.json has duplicate CIK entries; plain INSERT hit PK constraint |

**Lesson**: Unit tests pass on isolated components with mocked dependencies. Browser-level bugs (CORS), concurrency bugs (thread-safety), and multi-step UX flows (sequential position recording) require a full-stack browser test to surface. Playwright QC is the required final gate for any forge sprint.

## Notes
- Spec phase APPROVED 2026-04-05 (final review, zero blocking issues)
- Source repo /home/d-tuned/projects/gap-lens-dilution/ is read-only reference
- INVARIANTS.md created at docs/INVARIANTS.md
- Playwright QC SOP: docs/SOP_PLAYWRIGHT_QC.md
- Test & Deploy Playbook: docs/TEST_AND_DEPLOY_PLAYBOOK.md
