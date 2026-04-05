#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_playwright_qc.sh — Full Playwright QC orchestration
#
# Usage:
#   bash scripts/run_playwright_qc.sh
#
# What it does:
#   1. Seed test signal into DuckDB (backend must be stopped)
#   2. Start backend (uvicorn)
#   3. Start frontend (next dev)
#   4. Wait for both services to be ready
#   5. Run Playwright QC suite
#   6. Stop both services
#   7. Clean up test signal from DuckDB
#   8. Exit with the pytest exit code
# ---------------------------------------------------------------------------

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

BACKEND_URL="http://localhost:8000/api/v1/health"
FRONTEND_URL="http://localhost:3000"
UVICORN_LOG="/tmp/uvicorn_qc.log"
NEXTJS_LOG="/tmp/nextjs_qc.log"
UVICORN_PID=""
NEXTJS_PID=""
PYTEST_EXIT=0

cleanup() {
    echo ""
    echo "--- Stopping services ---"
    [ -n "$UVICORN_PID" ] && kill "$UVICORN_PID" 2>/dev/null && echo "Stopped uvicorn (PID $UVICORN_PID)"
    [ -n "$NEXTJS_PID" ]  && kill "$NEXTJS_PID"  2>/dev/null && echo "Stopped Next.js (PID $NEXTJS_PID)"
    # Also kill anything still on those ports (handles stale processes)
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    sleep 1

    echo ""
    echo "--- Cleaning up test signal ---"
    python3 scripts/cleanup_playwright_qc.py
}

trap cleanup EXIT

# ---------------------------------------------------------------------------
# Step 1: Kill any stale services and seed test data
# ---------------------------------------------------------------------------
echo "=== Step 1: Clearing ports and seeding test signal ==="
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

python3 scripts/seed_playwright_qc.py

# ---------------------------------------------------------------------------
# Step 2: Start backend
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 2: Starting backend ==="
uvicorn app.main:app --host 0.0.0.0 --port 8000 > "$UVICORN_LOG" 2>&1 &
UVICORN_PID=$!
echo "uvicorn PID: $UVICORN_PID (log: $UVICORN_LOG)"

# ---------------------------------------------------------------------------
# Step 3: Start frontend
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 3: Starting frontend ==="
(cd frontend && npm run dev > "$NEXTJS_LOG" 2>&1) &
NEXTJS_PID=$!
echo "Next.js PID: $NEXTJS_PID (log: $NEXTJS_LOG)"

# ---------------------------------------------------------------------------
# Step 4: Wait for both services
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 4: Waiting for services (max 90s) ==="
READY=0
for i in $(seq 1 45); do
    BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL" 2>/dev/null || echo "000")
    FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" 2>/dev/null || echo "000")
    printf "  [%2ds] backend: %s  frontend: %s\n" $((i * 2)) "$BACKEND_STATUS" "$FRONTEND_STATUS"

    if [ "$BACKEND_STATUS" = "200" ] && [ "$FRONTEND_STATUS" = "200" ]; then
        READY=1
        echo "  Both services ready."
        break
    fi
    sleep 2
done

if [ "$READY" = "0" ]; then
    echo ""
    echo "ERROR: Services did not become ready within 90s."
    echo "--- uvicorn log tail ---"
    tail -20 "$UVICORN_LOG"
    echo "--- next.js log tail ---"
    tail -20 "$NEXTJS_LOG"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 5: Run Playwright QC
# ---------------------------------------------------------------------------
echo ""
echo "=== Step 5: Running Playwright QC ==="
python3 -m pytest tests/test_playwright_qc.py -v -s || PYTEST_EXIT=$?

# ---------------------------------------------------------------------------
# Exit (cleanup trap fires automatically)
# ---------------------------------------------------------------------------
echo ""
echo "=== Playwright QC complete — exit code: $PYTEST_EXIT ==="
exit $PYTEST_EXIT
