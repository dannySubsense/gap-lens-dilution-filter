"""
Slice 13: API Routes -- Acceptance Tests

Acceptance Criteria Coverage:
- [x] AC-1: GET /api/v1/health returns HealthResponse fields populated; status="error" when last_success_at is NULL
- [x] AC-2: GET /api/v1/signals returns {"signals": [], "count": 0} with empty DB
- [x] AC-3: GET /api/v1/signals/closed returns {"signals": [], "count": 0} with empty DB
- [x] AC-4: GET /api/v1/signals/{id} with non-existent id returns HTTP 404
- [x] AC-5: POST /api/v1/signals/{id}/position with {"cover_price": 0.005} returns HTTP 422
- [x] AC-6: End-to-end: insert test signal into DuckDB, GET /api/v1/signals returns it
- [x] AC-7: GET /api/v1/signals/closed does NOT shadow GET /api/v1/signals/{id}
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.db import _create_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    return conn


@pytest.fixture
def patched_app(mem_db):
    """App with all startup side-effects neutralized and DB pointed at mem_db."""
    with patch("app.main.init_db"), \
         patch("app.main.TickerResolver.refresh", new=AsyncMock()), \
         patch("app.main.EdgarPoller.run_forever", new=AsyncMock()), \
         patch("app.main.SignalManager.run_lifecycle_loop", new=AsyncMock()), \
         patch("app.main.EdgarPoller.set_process_filing"), \
         patch("app.services.db._conn", new=mem_db):
        from app.main import app
        yield app, mem_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_test_filing(mem_db, accession_number: str, ticker: str) -> None:
    """Insert a minimal filings row so the signals FK constraint is satisfied."""
    mem_db.execute(
        """
        INSERT INTO filings (accession_number, cik, form_type, filed_at, filing_url,
                             entity_name, ticker)
        VALUES (?, '0001234567', 'S-1', NOW(), 'https://sec.gov/test', 'Test Corp', ?)
        """,
        [accession_number, ticker],
    )


def _insert_test_signal(
    mem_db,
    accession_number: str = "ACC-TEST",
    ticker: str = "GME",
    status: str = "LIVE",
) -> None:
    """Insert a test signal row with required fields."""
    _insert_test_filing(mem_db, accession_number, ticker)
    mem_db.execute(
        """
        INSERT INTO signals (accession_number, ticker, setup_type, score, rank,
                             status, alert_type, alerted_at)
        VALUES (?, ?, 'A', 85, 'A', ?, 'NEW_SETUP', NOW())
        """,
        [accession_number, ticker, status],
    )


# ---------------------------------------------------------------------------
# AC-1: Health endpoint returns HealthResponse with status="error" when no polls
# ---------------------------------------------------------------------------

async def test_health_returns_all_fields_and_error_status_when_no_polls(patched_app):
    """
    AC-1: GET /api/v1/health returns {"status": ...} with all HealthResponse
    fields populated. status is "error" when last_success_at is NULL.
    """
    app, _ = patched_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/health")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()

    # All HealthResponse fields must be present
    expected_fields = {
        "status", "last_poll_at", "last_success_at",
        "poll_interval_seconds", "fmp_configured", "askedgar_configured", "db_path",
    }
    assert expected_fields <= data.keys(), (
        f"Missing fields: {expected_fields - data.keys()}"
    )

    # With no polls yet, last_success_at is NULL → status must be "error"
    assert data["status"] == "error", (
        f"Expected status='error' with no polls, got {data['status']!r}"
    )
    assert data["last_success_at"] is None, (
        f"Expected last_success_at=None, got {data['last_success_at']!r}"
    )


# ---------------------------------------------------------------------------
# AC-2: GET /api/v1/signals returns empty list with empty DB
# ---------------------------------------------------------------------------

async def test_list_signals_returns_empty_with_empty_db(patched_app):
    """
    AC-2: GET /api/v1/signals returns {"signals": [], "count": 0} with empty DB.
    """
    app, _ = patched_app

    with patch("app.api.v1.routes._get_current_price", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data == {"signals": [], "count": 0}, (
        f"Expected empty list response, got {data!r}"
    )


# ---------------------------------------------------------------------------
# AC-3: GET /api/v1/signals/closed returns empty list with empty DB
# ---------------------------------------------------------------------------

async def test_list_closed_signals_returns_empty_with_empty_db(patched_app):
    """
    AC-3: GET /api/v1/signals/closed returns {"signals": [], "count": 0} with empty DB.
    """
    app, _ = patched_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/closed")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data == {"signals": [], "count": 0}, (
        f"Expected empty list response, got {data!r}"
    )


# ---------------------------------------------------------------------------
# AC-4: GET /api/v1/signals/{id} with non-existent id returns HTTP 404
# ---------------------------------------------------------------------------

async def test_get_signal_nonexistent_returns_404(patched_app):
    """
    AC-4: GET /api/v1/signals/{id} with non-existent id returns HTTP 404.
    """
    app, _ = patched_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/signals/99999")

    assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
    assert "not found" in resp.json()["detail"].lower(), (
        f"Expected 'not found' in detail, got {resp.json()['detail']!r}"
    )


# ---------------------------------------------------------------------------
# AC-5: POST /api/v1/signals/{id}/position with cover_price=0.005 returns 422
# ---------------------------------------------------------------------------

async def test_record_position_cover_price_too_low_returns_422(patched_app):
    """
    AC-5: POST /api/v1/signals/{id}/position with {"cover_price": 0.005}
    returns HTTP 422 (cover_price must be > $0.01).
    """
    app, _ = patched_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/signals/1/position",
            json={"cover_price": 0.005},
        )

    assert resp.status_code == 422, f"Expected 422 (Unprocessable Entity), got {resp.status_code}"


# ---------------------------------------------------------------------------
# AC-6: End-to-end: insert test signal, GET /api/v1/signals returns it
# ---------------------------------------------------------------------------

async def test_list_signals_returns_inserted_signal(patched_app):
    """
    AC-6: Insert a test signal directly into DuckDB, then GET /api/v1/signals
    returns it with correct ticker and count=1.
    """
    app, mem_db = patched_app
    _insert_test_signal(mem_db, accession_number="ACC-TEST-E2E", ticker="GME", status="LIVE")

    with patch("app.api.v1.routes._get_current_price", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/signals")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data["count"] == 1, f"Expected count=1, got {data['count']}"
    assert len(data["signals"]) == 1, f"Expected 1 signal, got {len(data['signals'])}"
    assert data["signals"][0]["ticker"] == "GME", (
        f"Expected ticker='GME', got {data['signals'][0]['ticker']!r}"
    )


# ---------------------------------------------------------------------------
# AC-7: /signals/closed does NOT shadow /signals/{id}
# ---------------------------------------------------------------------------

async def test_signals_closed_does_not_shadow_signals_by_id(patched_app):
    """
    AC-7: GET /api/v1/signals/closed returns a list (200), not a 404.
    Both /signals/closed (list) and /signals/{id} (detail) routes coexist.
    FastAPI must resolve "closed" as the literal route, not as an integer id.
    """
    app, _ = patched_app

    # /signals/closed must return 200 (list endpoint, not treated as id="closed")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        closed_resp = await client.get("/api/v1/signals/closed")

    assert closed_resp.status_code == 200, (
        f"Expected /signals/closed to return 200, got {closed_resp.status_code}. "
        "The /signals/closed route is being shadowed by /signals/{{id}}."
    )
    data = closed_resp.json()
    # Response must be a list-shaped payload, not a 404 detail
    assert "signals" in data, (
        f"Expected list response with 'signals' key, got {data!r}"
    )
    assert "count" in data, (
        f"Expected list response with 'count' key, got {data!r}"
    )
