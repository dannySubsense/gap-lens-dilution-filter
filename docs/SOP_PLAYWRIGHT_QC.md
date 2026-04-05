# SOP: Playwright QC — gap-lens-dilution-filter

**Version**: 1.0  
**Last updated**: 2026-04-05  
**Owner**: Orchestrator  

---

## Purpose

The Playwright QC suite is the required final gate before any forge sprint is closed or any deployment is made. It exercises the full stack — real browser, real CORS, real concurrent HTTP, real UX flows — and catches bugs that are invisible to the unit test suite.

---

## When to Run

| Trigger | Required? |
|---------|-----------|
| End of every forge sprint (all slices complete) | Yes — mandatory before sprint closure |
| Before any production deployment | Yes |
| After any change to API routes, middleware, or DB access patterns | Yes |
| After any change to frontend fetch logic or component state | Yes |
| After routine bug fixes not touching the above | Recommended |
| During standard development iteration | No — use unit suite instead |

---

## Prerequisites

1. Both services must NOT be running before the script starts (it manages them)
2. The live DuckDB file must exist at `./data/filter.duckdb`
3. The `.env` file must be populated (see `docs/TEST_AND_DEPLOY_PLAYBOOK.md`)
4. Playwright + Chromium must be installed:
   ```bash
   pip3 install playwright
   playwright install chromium
   ```

---

## How to Run

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter
bash scripts/run_playwright_qc.sh
```

The script handles the full lifecycle automatically:
1. Clears ports 8000 and 3000
2. Seeds test signal into DuckDB (ticker=PWQC)
3. Starts uvicorn backend on port 8000
4. Starts Next.js frontend on port 3000
5. Polls until both services are ready (max 90s)
6. Runs 16 browser + API tests via headless Chromium
7. Stops both services
8. Removes the test signal from DuckDB
9. Exits with pytest's exit code (0 = pass, non-zero = fail)

---

## Pass Criteria

```
16 passed in ~25s
Exit code: 0
```

All 16 tests must pass. Any failure is a blocker — the sprint is not closed until 16/16.

---

## What the 16 Tests Cover

| QC ID | Area | What It Verifies |
|-------|------|-----------------|
| QC-01 | Page load | Dashboard loads, no JS errors |
| QC-02 | Header | Brand text + health dot present |
| QC-03 | Config | FMP banner absent (key configured) |
| QC-04 | Layout | All 3 panels render |
| QC-05 | Signal display | Injected WATCHLIST signal appears |
| QC-06 | Signal row | Ticker + setup badge visible |
| QC-07 | Interaction | Row click opens detail panel |
| QC-08 | Detail panel | Filing Info section populated |
| QC-09 | Detail panel | Classification section populated |
| QC-10 | Position State A | Entry input + buttons visible |
| QC-11 | Position State A→B | Entry price recorded, cover input appears |
| QC-12 | Position State B→C | Cover price recorded, P&L shown (+20.0%) |
| QC-13 | Closed panel | Signal appears in Recent Closed after cover |
| QC-14 | Panel close | Backdrop click closes detail panel |
| QC-15 | API contract | `/api/v1/health` JSON shape + fmp_configured=true |
| QC-16 | API contract | `/api/v1/signals` JSON shape |

---

## Known Characteristic: Test Ordering Dependency

QC-11, QC-12, and QC-13 are intentionally ordered — each builds on the state left by the previous:
- QC-11 records entry_price=5.00 → signal moves to State B
- QC-12 records cover_price=4.00 → P&L computed, signal closed
- QC-13 verifies the closed signal appears in Recent Closed panel

A failure in QC-11 will cascade to QC-12 and QC-13. This is by design — it mirrors the real user flow. If QC-12 or QC-13 fail in isolation (QC-11 passed), the root cause is in the cover/close logic, not the entry logic.

---

## On Failure

1. **Read the failure message** — Playwright prints the failing assertion and a call log showing what it was waiting for.

2. **Check the service logs:**
   ```bash
   tail -50 /tmp/uvicorn_qc.log
   tail -50 /tmp/nextjs_qc.log
   ```

3. **Classify the failure:**

   | Symptom | Likely cause |
   |---------|-------------|
   | "Failed to load — retrying" in all panels | CORS misconfiguration |
   | Backend crash in log | DuckDB concurrency issue or unhandled exception |
   | Text element not found | API returning wrong data, or timing issue |
   | `httpx.ConnectError` in QC-15/16 | Backend crashed mid-run |
   | `Timeout exceeded` | Slow FMP response or frontend rendering delay |

4. **Fix the root cause** — do not adjust test timeouts to paper over real bugs.

5. **Re-run the full suite** to confirm 16/16 before closing.

---

## Relation to Unit Test Suite

| | Unit Tests (`pytest tests/ --ignore=test_playwright_qc.py`) | Playwright QC |
|--|-------------------------------------------------------------|---------------|
| Speed | ~5 seconds | ~25 seconds |
| Services required | No | Yes |
| What it catches | Logic, data flow, edge cases | CORS, concurrency, browser rendering, multi-step UX |
| Run frequency | Every commit / every iteration | Sprint closure gate + pre-deploy |
| Exit code drives CI | Yes | Yes (sprint gate) |

Both must pass. Neither replaces the other.

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/run_playwright_qc.sh` | Full orchestration (preferred — use this) |
| `scripts/seed_playwright_qc.py` | Insert test signal (run before starting backend) |
| `scripts/cleanup_playwright_qc.py` | Remove test signal (run after stopping backend) |
| `tests/test_playwright_qc.py` | Pytest test file (called by the shell script) |
