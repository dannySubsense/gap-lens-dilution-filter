"""
Slice 7: EdgarPoller — Acceptance Tests

Done-when criteria verified:
1.  3 hits → 3 PENDING rows in filings
2.  Deduplication: calling _poll_once() twice with same hits yields exactly 3 rows
3.  Malformed JSON: _fetch_efts returning None returns normally without raising
4.  Unreachable EDGAR (3 retries): httpx.ConnectError propagated through retries,
    _poll_once() returns without raising
5.  poll_state.last_success_at updated after successful _poll_once()
6.  Properties last_poll_at and last_success_at start as None
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.db import _create_schema  # noqa: E402


# ---------------------------------------------------------------------------
# EFTS JSON fixture shared across tests
# ---------------------------------------------------------------------------

EFTS_FIXTURE = {
    "total": {"value": 3, "relation": "eq"},
    "hits": [
        {"_source": {"accessionNo": "0001234567-24-000001", "cik": "1234567",
                     "formType": "S-1", "filedAt": "2024-01-08T16:31:36-05:00",
                     "entityName": "Test Corp", "ticker": "TEST"}},
        {"_source": {"accessionNo": "0001234567-24-000002", "cik": "1234567",
                     "formType": "424B4", "filedAt": "2024-01-08T17:00:00-05:00",
                     "entityName": "Test Corp", "ticker": "TEST"}},
        {"_source": {"accessionNo": "0001234567-24-000003", "cik": "2345678",
                     "formType": "8-K", "filedAt": "2024-01-08T18:00:00-05:00",
                     "entityName": "Other Inc", "ticker": "OTHR"}},
    ],
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# AC-S7-01: 3 hits → 3 PENDING rows in filings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_hits_produce_three_pending_rows(mem_db):
    """_poll_once() with 3 EFTS hits must invoke process_filing for each, producing 3 PENDING rows."""
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415
    from datetime import datetime

    poller = EdgarPoller()

    # Simulate process_filing writing a PENDING row (as it does in the real pipeline)
    async def fake_process_filing(accession_number, cik, form_type, filed_at, filing_url,
                                   entity_name=None, efts_ticker=None):
        mem_db.execute(
            "INSERT INTO filings (accession_number, cik, form_type, filed_at, filing_url, processing_status)"
            " VALUES (?, ?, ?, ?, ?, 'PENDING') ON CONFLICT (accession_number) DO NOTHING",
            [accession_number, cik, form_type, filed_at, filing_url],
        )

    poller.set_process_filing(fake_process_filing)

    with patch("app.services.edgar_poller.get_db", return_value=mem_db), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch.object(poller, "_fetch_efts", new_callable=AsyncMock, return_value=EFTS_FIXTURE):
        await poller._poll_once()

    rows = mem_db.execute(
        "SELECT accession_number, processing_status FROM filings ORDER BY accession_number"
    ).fetchall()
    assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}: {rows}"
    for acc_no, status in rows:
        assert status == "PENDING", (
            f"Row {acc_no} has processing_status={status!r}, expected 'PENDING'"
        )


# ---------------------------------------------------------------------------
# AC-S7-02: Deduplication — second _poll_once() with same hits yields no new rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_deduplication_no_duplicate_rows_on_second_poll(mem_db):
    """Calling _poll_once() twice with the same 3 hits must not create duplicate rows."""
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415

    poller = EdgarPoller()

    async def fake_process_filing(accession_number, cik, form_type, filed_at, filing_url,
                                   entity_name=None, efts_ticker=None):
        mem_db.execute(
            "INSERT INTO filings (accession_number, cik, form_type, filed_at, filing_url, processing_status)"
            " VALUES (?, ?, ?, ?, ?, 'PENDING') ON CONFLICT (accession_number) DO NOTHING",
            [accession_number, cik, form_type, filed_at, filing_url],
        )

    poller.set_process_filing(fake_process_filing)

    with patch("app.services.edgar_poller.get_db", return_value=mem_db), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch.object(poller, "_fetch_efts", new_callable=AsyncMock, return_value=EFTS_FIXTURE):
        await poller._poll_once()
        await poller._poll_once()

    count = mem_db.execute("SELECT COUNT(*) FROM filings").fetchone()[0]
    assert count == 3, f"Expected exactly 3 rows after two identical polls, got {count}"


# ---------------------------------------------------------------------------
# AC-S7-03: Malformed JSON — _fetch_efts returning None returns normally
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_json_returns_without_raising(mem_db):
    """_poll_once() must return normally (no exception) when _fetch_efts returns None."""
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415

    poller = EdgarPoller()

    with patch("app.services.edgar_poller.get_db", return_value=mem_db), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch.object(poller, "_fetch_efts", new_callable=AsyncMock, return_value=None):
        # Must not raise
        await poller._poll_once()


# ---------------------------------------------------------------------------
# AC-S7-04: Unreachable EDGAR — ConnectError through retries, no exception raised
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unreachable_edgar_returns_without_raising(mem_db):
    """_poll_once() must return without raising after httpx.ConnectError on all retries."""
    import httpx  # noqa: PLC0415
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415

    poller = EdgarPoller()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.ConnectError("Connection refused")
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.edgar_poller.get_db", return_value=mem_db), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("httpx.AsyncClient", return_value=mock_client):
        # Must not raise
        await poller._poll_once()


# ---------------------------------------------------------------------------
# AC-S7-05: poll_state.last_success_at updated after successful _poll_once()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_last_success_at_updated_after_successful_poll(mem_db):
    """After a successful _poll_once(), last_success_at is not None and persisted in poll_state."""
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415

    poller = EdgarPoller()

    with patch("app.services.edgar_poller.get_db", return_value=mem_db), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch.object(poller, "_fetch_efts", new_callable=AsyncMock, return_value=EFTS_FIXTURE):
        await poller._poll_once()

    assert poller.last_success_at is not None, (
        "last_success_at property must be set after a successful poll"
    )

    row = mem_db.execute(
        "SELECT last_success_at FROM poll_state WHERE id = 1"
    ).fetchone()
    assert row is not None and row[0] is not None, (
        "poll_state.last_success_at must be persisted in the database"
    )


# ---------------------------------------------------------------------------
# AC-S7-06: Properties start as None before any poll
# ---------------------------------------------------------------------------

def test_properties_start_as_none():
    """EdgarPoller().last_poll_at and last_success_at must be None before any poll."""
    from app.services.edgar_poller import EdgarPoller  # noqa: PLC0415

    poller = EdgarPoller()
    assert poller.last_poll_at is None, (
        f"last_poll_at should be None on init, got {poller.last_poll_at!r}"
    )
    assert poller.last_success_at is None, (
        f"last_success_at should be None on init, got {poller.last_success_at!r}"
    )
