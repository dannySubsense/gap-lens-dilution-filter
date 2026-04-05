# Test & Deploy Playbook — gap-lens-dilution-filter

**Tailscale IP**: `100.70.21.69`
**Project root**: `/home/d-tuned/projects/gap-lens-dilution-filter`

---

## Ports

| Service | Port | URL (local) | URL (Tailscale) |
|---------|------|-------------|-----------------|
| Backend (FastAPI) | 8000 | http://localhost:8000 | http://100.70.21.69:8000 |
| Frontend (Next.js) | 3000 | http://localhost:3000 | http://100.70.21.69:3000 |
| API docs (Swagger) | 8000 | http://localhost:8000/docs | http://100.70.21.69:8000/docs |

---

## 1. Run the Test Suite (no services required)

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter

# Full suite — should be 161/161
python3 -m pytest tests/ -q

# Single slice
python3 -m pytest tests/test_slice12_pipeline.py -v

# E2E smoke only
python3 -m pytest tests/test_e2e_smoke.py -v
```

---

## 2. Start the Backend

Open a dedicated terminal (tmux pane or separate tab).

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter

# Development (auto-reload on file changes)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Production-style (no reload)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**What you'll see on healthy startup:**
```
INFO:     Started server process
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO     app.services.edgar_poller:edgar_poller.py:... EDGAR poller started; interval=90s
INFO     app.services.signal_manager:signal_manager.py:... Lifecycle loop started; interval=300s
```

**If FMP key is missing or invalid**, you'll see a warning but startup continues.

### Verify backend is live

```bash
curl http://localhost:8000/api/v1/health
```

Expected (before any successful poll):
```json
{"status": "error", "last_poll_at": null, "last_success_at": null, "elapsed_seconds": null}
```

Expected (after first successful EDGAR poll, ~90s):
```json
{"status": "ok", "last_poll_at": "...", "last_success_at": "...", "elapsed_seconds": 12}
```

---

## 3. Start the Frontend

Open a second terminal.

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter/frontend

# For LOCAL access only (browser on same machine)
npm run dev

# For TAILSCALE access (browser on another device via 100.70.21.69)
NEXT_PUBLIC_API_URL=http://100.70.21.69:8000 npm run dev -- --hostname 0.0.0.0
```

Frontend is ready when you see:
```
▲ Next.js 14.x.x
- Local:        http://localhost:3000
- Network:      http://100.70.21.69:3000
```

---

## 4. What to Expect on a Weekend (No Market Activity)

EDGAR does receive some weekend filings (8-Ks, amended filings) but dilution events
(S-1, 424B, ATM supplements) are rare. The poller will still run every 90 seconds.

**Normal weekend behavior:**
- Health bar: will turn green after the first successful EDGAR poll (~90s after backend start)
- Signal table: likely empty or showing only signals from previous weekday sessions
- Poller logs: "0 new filings" hits are normal

**The poller IS active and talking to EDGAR regardless of market hours.**

---

## 5. Manual Smoke Tests (No Market Data Required)

### 5a. Health endpoint
```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```
Wait ~90s after startup — status should move from `"error"` → `"ok"`.

### 5b. Signals list (empty is fine)
```bash
curl -s http://localhost:8000/api/v1/signals | python3 -m json.tool
```

### 5c. Closed signals
```bash
curl -s http://localhost:8000/api/v1/signals/closed | python3 -m json.tool
```

### 5d. Swagger UI
Open http://localhost:8000/docs (or http://100.70.21.69:8000/docs from another device).
All 6 routes should be listed. You can call them interactively from the UI.

### 5e. Frontend dashboard
Open http://localhost:3000 (or http://100.70.21.69:3000).

Checklist:
- [ ] Page loads with dark theme
- [ ] "Gap Lens — Dilution Filter" header visible
- [ ] Health bar present in header (dots visible)
- [ ] After ~90s: health dots turn cyan/green
- [ ] Signal table columns visible (Ticker, Setup, Score, Rank, Filed, Status)
- [ ] "No signals" or empty state displayed — not an error

---

## 6. Inject a Test Signal (Optional, No Market Required)

You can manually insert a row to verify the full UI flow without waiting for a real filing.

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter

python3 - <<'EOF'
import duckdb
from datetime import datetime, timezone

conn = duckdb.connect("./data/filter.duckdb")

# Insert a test filing first (signals FK references accession_number)
conn.execute("""
INSERT INTO filings (accession_number, cik, form_type, filed_at, filing_url, processing_status)
VALUES ('TEST-SIGNAL-001', '9999999', '424B4', NOW(), 'https://www.sec.gov', 'ALERTED')
ON CONFLICT (accession_number) DO NOTHING
""")

# Insert a test signal
conn.execute("""
INSERT INTO signals (accession_number, ticker, setup_type, score, rank, status, alert_type, alerted_at)
VALUES ('TEST-SIGNAL-001', 'TEST', 'C', 76, 'B', 'WATCHLIST', 'NEW_SETUP', NOW())
ON CONFLICT DO NOTHING
""")

# Insert a labels row (required for signal detail endpoint)
conn.execute("""
INSERT INTO labels (accession_number, classifier_version, setup_type, confidence,
    dilution_severity, immediate_pressure, price_discount, short_attractiveness,
    rank, key_excerpt, reasoning)
VALUES ('TEST-SIGNAL-001', 'rule-based-v1', 'C', 0.95, 0.50, true, 0.03, 0,
    'B', 'Test excerpt for manual validation.', 'Manual test signal.')
ON CONFLICT DO NOTHING
""")

print("Test signal inserted. Refresh the dashboard.")
conn.close()
EOF
```

After running: refresh the dashboard — TEST/[C] should appear in the signal table.
Click it to open the detail panel and test position tracking (State A → B → C).

### Clean up test signal
```bash
python3 - <<'EOF'
import duckdb
conn = duckdb.connect("./data/filter.duckdb")
conn.execute("DELETE FROM labels WHERE accession_number = 'TEST-SIGNAL-001'")
conn.execute("DELETE FROM signals WHERE accession_number = 'TEST-SIGNAL-001'")
conn.execute("DELETE FROM filings WHERE accession_number = 'TEST-SIGNAL-001'")
print("Test signal removed.")
conn.close()
EOF
```

---

## 7. TypeScript Type Check (Frontend, No Browser Required)

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter/frontend
npx tsc --noEmit
```
Should produce no output (zero errors).

---

## 8. Stop Services

```bash
# Backend: Ctrl+C in the uvicorn terminal

# Frontend: Ctrl+C in the next dev terminal

# Or kill by port if running detached:
kill $(lsof -ti:8000)
kill $(lsof -ti:3000)
```

---

## 9. Database Inspection

```bash
cd /home/d-tuned/projects/gap-lens-dilution-filter

python3 - <<'EOF'
import duckdb
conn = duckdb.connect("./data/filter.duckdb")
for table in ["filings", "filter_results", "market_data", "labels", "signals", "poll_state"]:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table:20s}: {count} rows")
conn.close()
EOF
```

---

## 10. Environment Variables Reference

| Variable | Default | Notes |
|----------|---------|-------|
| `FMP_API_KEY` | (set in .env) | Required for price enrichment; banner shown if missing |
| `ASKEDGAR_API_KEY` | (set in .env) | AskEdgar text extraction; pipeline degrades gracefully if unavailable |
| `EDGAR_POLL_INTERVAL` | 90 | Seconds between EDGAR polls |
| `DUCKDB_PATH` | ./data/filter.duckdb | Relative to project root |
| `DEFAULT_BORROW_COST` | 0.30 | Used when IBKR borrow feed is disabled |
| `IBKR_BORROW_COST_ENABLED` | false | IBKR integration not wired in Phase 1 |
| `LIFECYCLE_CHECK_INTERVAL` | 300 | Seconds between signal expiry checks |
| `NEXT_PUBLIC_API_URL` | http://localhost:8000 | Override for Tailscale: http://100.70.21.69:8000 |
| `NEXT_PUBLIC_REFRESH_INTERVAL_MS` | 30000 | Dashboard auto-refresh in ms |
