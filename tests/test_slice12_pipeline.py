"""
Slice 12: Pipeline Integration -- Acceptance Tests

Done-when criteria verified:
1.  `from app.main import app` succeeds and `app` is a FastAPI instance.
2.  Integration test: call process_filing() directly. Verify the filings row
    transitions from PENDING to ALERTED (happy path: all filters pass,
    rank A/B signal emitted).
3.  The run_forever poller loop calls the full process_filing pipeline --
    verify that set_process_filing wires the callback correctly and
    _process_new_filing calls it when set.
4.  Both asyncio tasks (poller + lifecycle) are started in lifespan and
    cancelled cleanly on shutdown -- verify asyncio.CancelledError is
    handled without propagating.
5.  GET /health returns 200 with {"status": "ok"}.
6.  AskEdgar degradation integration test: call process_filing() with
    DilutionService.get_dilution_data_v2 patched to raise ExternalAPIError.
    Verify pipeline continues, askedgar_partial=True, data_source='PARTIAL',
    and processing_status='ALERTED'.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import patch, AsyncMock, MagicMock  # noqa: E402

from app.services.db import _create_schema  # noqa: E402
from app.services.fmp_client import FMPMarketData  # noqa: E402
from app.services.filter_engine import FilterOutcome  # noqa: E402
from app.utils.errors import ExternalAPIError  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fmp_data() -> FMPMarketData:
    """FMPMarketData that passes all 5 FMP-dependent filters."""
    return FMPMarketData(
        price=5.00,
        market_cap=80_000_000,
        float_shares=15_000_000,
        adv_dollar=600_000,
        fetched_at=datetime.now(timezone.utc),
    )


def make_classification(setup_type: str = "A"):
    return {
        "setup_type": setup_type,
        "confidence": 0.85,
        "dilution_severity": 0.50,
        "immediate_pressure": True,
        "price_discount": 0.10,
        "short_attractiveness": 75,
        "key_excerpt": "test excerpt",
        "reasoning": "test reasoning",
    }


def make_mock_classifier(setup_type: str = "A"):
    mock_classifier = MagicMock()
    mock_classifier.classify = AsyncMock(return_value=make_classification(setup_type))
    return mock_classifier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# AC-1: App import test (sync)
# ---------------------------------------------------------------------------

def test_app_is_fastapi_instance():
    """from app.main import app succeeds and app is a FastAPI instance."""
    from app.main import app
    from fastapi import FastAPI

    assert isinstance(app, FastAPI)


# ---------------------------------------------------------------------------
# AC-2: Happy path PENDING -> ALERTED
# ---------------------------------------------------------------------------

async def test_process_filing_happy_path_pending_to_alerted(mem_db):
    """process_filing() transitions filings row from PENDING to ALERTED."""
    from app.main import process_filing

    acc = "0001234567-24-120001"
    fmp_data = make_fmp_data()

    with (
        patch("app.main.get_db", return_value=mem_db),
        patch("app.services.signal_manager.get_db", return_value=mem_db),
        patch("app.services.filter_engine.get_db", return_value=mem_db),
        patch("app.main.TickerResolver.resolve", return_value="ACME"),
        patch("app.main.FilingFetcher.fetch", new=AsyncMock(
            return_value="prospectus offering shares S-1 filing text"
        )),
        patch("app.main.FMPClient.get_market_data", new=AsyncMock(
            return_value=fmp_data
        )),
        patch("app.main.FilterEngine.evaluate", new=AsyncMock(
            return_value=FilterOutcome(passed=True, fail_criterion=None)
        )),
        patch("app.main.DilutionService.get_dilution_data_v2", new=AsyncMock(
            return_value={}
        )),
        patch("app.main.DilutionService.close", new=AsyncMock()),
        patch("app.main.get_classifier", return_value=make_mock_classifier("A")),
        patch("app.main.SignalManager.emit", new=AsyncMock(return_value=1)),
    ):
        await process_filing(
            accession_number=acc,
            cik="0001234567",
            form_type="S-1",
            filed_at=datetime.now(timezone.utc),
            filing_url="https://www.sec.gov/test",
            entity_name="Acme Corp",
            efts_ticker="ACME",
        )

    row = mem_db.execute(
        "SELECT processing_status FROM filings WHERE accession_number = ?",
        [acc],
    ).fetchone()
    assert row is not None, "Expected filings row to exist"
    assert row[0] == "ALERTED", (
        f"Expected processing_status='ALERTED', got {row[0]!r}"
    )


# ---------------------------------------------------------------------------
# AC-3: Poller callback wiring
# ---------------------------------------------------------------------------

async def test_poller_callback_wiring():
    """set_process_filing wires callback; _process_new_filing calls it."""
    from app.services.edgar_poller import EdgarPoller

    callback = AsyncMock()
    poller = EdgarPoller()
    poller.set_process_filing(callback)

    filed_at = datetime.now(timezone.utc)
    await poller._process_new_filing(
        "ACC-123",
        "0001234567",
        "S-1",
        filed_at,
        "https://www.sec.gov/test",
        "Test Entity",
        "TTST",
    )

    callback.assert_called_once_with(
        "ACC-123",
        "0001234567",
        "S-1",
        filed_at,
        "https://www.sec.gov/test",
        "Test Entity",
        "TTST",
    )


# ---------------------------------------------------------------------------
# AC-4: Lifespan task cancellation
# ---------------------------------------------------------------------------

async def test_lifespan_starts_and_cancels_tasks():
    """Lifespan enters and exits without raising; tasks are cancelled cleanly."""
    from app.main import lifespan, app as fastapi_app

    async def hang_forever(*args, **kwargs):
        await asyncio.sleep(9999)

    with (
        patch("app.main.init_db"),
        patch("app.main.TickerResolver.refresh", new=AsyncMock()),
        patch(
            "app.main.EdgarPoller.run_forever",
            new=AsyncMock(side_effect=hang_forever),
        ),
        patch(
            "app.main.SignalManager.run_lifecycle_loop",
            new=AsyncMock(side_effect=hang_forever),
        ),
        patch("app.main.EdgarPoller.set_process_filing"),
    ):
        async with lifespan(fastapi_app):
            pass  # immediately exit

    # If no exception raised, tasks were cancelled cleanly


# ---------------------------------------------------------------------------
# AC-5: Health endpoint
# ---------------------------------------------------------------------------

async def test_health_endpoint():
    """GET /health returns 200 with {"status": "ok"}."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app as fastapi_app

    async def hang_forever(*args, **kwargs):
        await asyncio.sleep(9999)

    with (
        patch("app.main.init_db"),
        patch("app.main.TickerResolver.refresh", new=AsyncMock()),
        patch(
            "app.main.EdgarPoller.run_forever",
            new=AsyncMock(side_effect=hang_forever),
        ),
        patch(
            "app.main.SignalManager.run_lifecycle_loop",
            new=AsyncMock(side_effect=hang_forever),
        ),
        patch("app.main.EdgarPoller.set_process_filing"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=fastapi_app),
            base_url="http://test",
        ) as client:
            resp = await client.get("/health")

    assert resp.status_code == 200, (
        f"Expected status 200, got {resp.status_code}"
    )
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# AC-6: AskEdgar degradation integration test
# ---------------------------------------------------------------------------

async def test_process_filing_askedgar_degradation(mem_db):
    """
    process_filing() with DilutionService.get_dilution_data_v2 raising
    ExternalAPIError: pipeline continues, askedgar_partial=True,
    data_source='PARTIAL', processing_status='ALERTED'.
    """
    from app.main import process_filing

    acc = "0001234567-24-120006"
    fmp_data = make_fmp_data()

    with (
        patch("app.main.get_db", return_value=mem_db),
        patch("app.services.signal_manager.get_db", return_value=mem_db),
        patch("app.services.filter_engine.get_db", return_value=mem_db),
        patch("app.main.TickerResolver.resolve", return_value="ACME"),
        patch("app.main.FilingFetcher.fetch", new=AsyncMock(
            return_value="prospectus offering shares S-1 filing text"
        )),
        patch("app.main.FMPClient.get_market_data", new=AsyncMock(
            return_value=fmp_data
        )),
        patch("app.main.FilterEngine.evaluate", new=AsyncMock(
            return_value=FilterOutcome(passed=True, fail_criterion=None)
        )),
        patch("app.main.DilutionService.get_dilution_data_v2", new=AsyncMock(
            side_effect=ExternalAPIError("AskEdgar down")
        )),
        patch("app.main.DilutionService.close", new=AsyncMock()),
        patch("app.main.get_classifier", return_value=make_mock_classifier("A")),
        patch("app.main.SignalManager.emit", new=AsyncMock(return_value=1)),
    ):
        await process_filing(
            accession_number=acc,
            cik="0001234567",
            form_type="S-1",
            filed_at=datetime.now(timezone.utc),
            filing_url="https://www.sec.gov/test",
            entity_name="Acme Corp",
            efts_ticker="ACME",
        )

    # Check filings row: processing_status = 'ALERTED', askedgar_partial = True
    filing_row = mem_db.execute(
        "SELECT processing_status, askedgar_partial FROM filings WHERE accession_number = ?",
        [acc],
    ).fetchone()
    assert filing_row is not None, "Expected filings row to exist"
    assert filing_row[0] == "ALERTED", (
        f"Expected processing_status='ALERTED', got {filing_row[0]!r}"
    )
    assert filing_row[1] is True, (
        f"Expected askedgar_partial=True, got {filing_row[1]!r}"
    )

    # Check market_data row: data_source = 'PARTIAL'
    md_row = mem_db.execute(
        "SELECT data_source FROM market_data WHERE accession_number = ?",
        [acc],
    ).fetchone()
    assert md_row is not None, "Expected market_data row to exist"
    assert md_row[0] == "PARTIAL", (
        f"Expected data_source='PARTIAL', got {md_row[0]!r}"
    )
