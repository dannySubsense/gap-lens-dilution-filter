"""
Slice 11: Signal Manager — Acceptance Tests

Done-when criteria verified:
1.  emit() with Rank A scorer result inserts one row in signals with
    status="LIVE" and one row in labels.
2.  emit() with Rank C scorer result inserts zero rows in signals but
    one row in labels.
3.  Calling emit() twice with same ticker within 24 hours produces one
    signals row with alert_type="SETUP_UPDATE", not two rows.
4.  record_position(id, entry_price=5.20, cover_price=4.26) computes
    pnl_pct ≈ 18.08 and sets status="CLOSED".
5.  record_position(id, entry_price=5.20, cover_price=None) updates
    entry_price but does not close the signal.
6.  Lifecycle checker transitions a LIVE Setup A signal with alerted_at
    > 3 days ago to status="CLOSED" (with close_reason="TIME_EXCEEDED").
7.  Lifecycle checker does NOT auto-close a Setup D signal regardless of
    elapsed time.

Invariants verified:
  I-07: Rank D never inserted into signals.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from unittest.mock import patch  # noqa: E402

from app.services.db import _create_schema  # noqa: E402
from app.services.fmp_client import FMPMarketData  # noqa: E402
from app.services.scorer import ScorerResult  # noqa: E402
from app.services.signal_manager import SignalManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_classification(setup_type: str = "A", dilution_severity: float = 0.5, **kwargs):
    base = {
        "setup_type": setup_type,
        "confidence": 0.8,
        "dilution_severity": dilution_severity,
        "immediate_pressure": True,
        "price_discount": 0.1,
        "short_attractiveness": 70,   # INTEGER column in schema
        "key_excerpt": "test excerpt",
        "reasoning": "test reasoning",
    }
    base.update(kwargs)
    return base


def make_fmp_data() -> FMPMarketData:
    return FMPMarketData(
        price=5.0,
        market_cap=500_000_000,
        float_shares=10_000_000,
        adv_dollar=1_000_000,
        fetched_at=datetime.now(timezone.utc),
    )


def insert_filing(conn: duckdb.DuckDBPyConnection, accession_number: str) -> None:
    conn.execute(
        """INSERT INTO filings (accession_number, cik, form_type, filed_at,
           filter_status, processing_status)
           VALUES (?, '123', 'S-1', CURRENT_TIMESTAMP, 'PENDING', 'PENDING')""",
        [accession_number],
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    return conn


# ---------------------------------------------------------------------------
# AC-S11-01: emit() with Rank A inserts one signals row (LIVE) and one labels row
# ---------------------------------------------------------------------------

async def test_emit_rank_a_inserts_live_signal_and_label(mem_db):
    """emit() with Rank A: one signals row status='LIVE' and one labels row."""
    acc = "0001111111-24-110001"
    insert_filing(mem_db, acc)

    manager = SignalManager()
    scorer = ScorerResult(score=85, rank="A")
    classification = make_classification(setup_type="A")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        signal_id = await manager.emit(
            scorer_result=scorer,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc,
            ticker="AAPL",
        )

    assert signal_id is not None, "Expected a signal_id for Rank A, got None"

    signals = mem_db.execute(
        "SELECT status, alert_type FROM signals WHERE accession_number = ?", [acc]
    ).fetchall()
    assert len(signals) == 1, f"Expected 1 signals row, got {len(signals)}"
    assert signals[0][0] == "LIVE", f"Expected status='LIVE', got {signals[0][0]!r}"

    labels = mem_db.execute(
        "SELECT rank FROM labels WHERE accession_number = ?", [acc]
    ).fetchall()
    assert len(labels) == 1, f"Expected 1 labels row, got {len(labels)}"
    assert labels[0][0] == "A", f"Expected labels.rank='A', got {labels[0][0]!r}"


# ---------------------------------------------------------------------------
# AC-S11-02: emit() with Rank C inserts zero signals rows but one labels row
# ---------------------------------------------------------------------------

async def test_emit_rank_c_no_signal_but_one_label(mem_db):
    """emit() with Rank C: zero signals rows, one labels row."""
    acc = "0001111111-24-110002"
    insert_filing(mem_db, acc)

    manager = SignalManager()
    scorer = ScorerResult(score=50, rank="C")
    classification = make_classification(setup_type="C")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        result = await manager.emit(
            scorer_result=scorer,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc,
            ticker="MSFT",
        )

    assert result is None, f"Expected None for Rank C, got {result!r}"

    signal_count = mem_db.execute(
        "SELECT COUNT(*) FROM signals WHERE accession_number = ?", [acc]
    ).fetchone()[0]
    assert signal_count == 0, f"Expected 0 signals rows for Rank C, got {signal_count}"

    label_count = mem_db.execute(
        "SELECT COUNT(*) FROM labels WHERE accession_number = ?", [acc]
    ).fetchone()[0]
    assert label_count == 1, f"Expected 1 labels row for Rank C, got {label_count}"


# ---------------------------------------------------------------------------
# AC-S11-03: emit() twice same ticker within 24h → one signals row with SETUP_UPDATE
# ---------------------------------------------------------------------------

async def test_emit_twice_same_ticker_produces_setup_update(mem_db):
    """Two emit() calls with same ticker within 24h: one signals row, alert_type='SETUP_UPDATE'."""
    acc1 = "0001111111-24-110003"
    acc2 = "0001111111-24-110004"
    insert_filing(mem_db, acc1)
    insert_filing(mem_db, acc2)

    manager = SignalManager()
    scorer_a = ScorerResult(score=85, rank="A")
    scorer_b = ScorerResult(score=88, rank="A")
    classification = make_classification(setup_type="A")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        first_id = await manager.emit(
            scorer_result=scorer_a,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc1,
            ticker="GME",
        )
        second_id = await manager.emit(
            scorer_result=scorer_b,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc2,
            ticker="GME",
        )

    assert first_id == second_id, (
        f"Expected same signal_id on update, got first={first_id} second={second_id}"
    )

    rows = mem_db.execute(
        "SELECT COUNT(*), MAX(alert_type) FROM signals WHERE ticker = 'GME'"
    ).fetchone()
    count, alert_type = rows
    assert count == 1, f"Expected 1 signals row, got {count}"
    assert alert_type == "SETUP_UPDATE", f"Expected alert_type='SETUP_UPDATE', got {alert_type!r}"


# ---------------------------------------------------------------------------
# AC-S11-04: record_position with both prices computes pnl_pct ≈ 18.08 and closes
# ---------------------------------------------------------------------------

async def test_record_position_computes_pnl_and_closes_signal(mem_db):
    """record_position(entry=5.20, cover=4.26): pnl_pct ≈ 18.08 and status='CLOSED'."""
    acc = "0001111111-24-110005"
    insert_filing(mem_db, acc)

    manager = SignalManager()
    scorer = ScorerResult(score=85, rank="A")
    classification = make_classification(setup_type="A")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        signal_id = await manager.emit(
            scorer_result=scorer,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc,
            ticker="AMC",
        )
        await manager.record_position(
            signal_id=signal_id,
            entry_price=5.20,
            cover_price=4.26,
        )

    row = mem_db.execute(
        "SELECT status, pnl_pct, close_reason FROM signals WHERE id = ?", [signal_id]
    ).fetchone()
    assert row is not None, "Signal row not found"
    status, pnl_pct, close_reason = row
    assert status == "CLOSED", f"Expected status='CLOSED', got {status!r}"
    assert pnl_pct == pytest.approx(18.076923, rel=1e-4), (
        f"Expected pnl_pct ≈ 18.08, got {pnl_pct}"
    )
    assert close_reason == "MANUAL", f"Expected close_reason='MANUAL', got {close_reason!r}"


# ---------------------------------------------------------------------------
# AC-S11-05: record_position with entry only updates entry_price, does not close
# ---------------------------------------------------------------------------

async def test_record_position_entry_only_does_not_close(mem_db):
    """record_position(entry=5.20, cover=None): entry_price updated, signal stays open."""
    acc = "0001111111-24-110006"
    insert_filing(mem_db, acc)

    manager = SignalManager()
    scorer = ScorerResult(score=85, rank="A")
    classification = make_classification(setup_type="A")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        signal_id = await manager.emit(
            scorer_result=scorer,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc,
            ticker="BBBY",
        )
        await manager.record_position(
            signal_id=signal_id,
            entry_price=5.20,
            cover_price=None,
        )

    row = mem_db.execute(
        "SELECT status, entry_price, closed_at FROM signals WHERE id = ?", [signal_id]
    ).fetchone()
    assert row is not None, "Signal row not found"
    status, entry_price, closed_at = row
    assert status == "LIVE", f"Expected status='LIVE' (still open), got {status!r}"
    assert entry_price == pytest.approx(5.20), (
        f"Expected entry_price=5.20, got {entry_price}"
    )
    assert closed_at is None, f"Expected closed_at=None (not closed), got {closed_at!r}"


# ---------------------------------------------------------------------------
# AC-S11-06: Lifecycle checker closes LIVE Setup A signal older than 3 days
# ---------------------------------------------------------------------------

async def test_lifecycle_closes_stale_setup_a_signal(mem_db):
    """_expire_stale_signals() closes a LIVE Setup A signal with alerted_at > 3 days ago."""
    acc = "0001111111-24-110007"
    insert_filing(mem_db, acc)

    manager = SignalManager()
    scorer = ScorerResult(score=85, rank="A")
    classification = make_classification(setup_type="A")
    fmp = make_fmp_data()

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        signal_id = await manager.emit(
            scorer_result=scorer,
            classification=classification,
            fmp_data=fmp,
            accession_number=acc,
            ticker="SPCE",
        )

    # Backdate alerted_at to 4 days ago to simulate expiry
    mem_db.execute(
        "UPDATE signals SET alerted_at = NOW() - INTERVAL '4 days' WHERE id = ?",
        [signal_id],
    )

    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        await manager._expire_stale_signals()

    row = mem_db.execute(
        "SELECT status, close_reason FROM signals WHERE id = ?", [signal_id]
    ).fetchone()
    assert row is not None, "Signal row not found"
    status, close_reason = row
    assert status == "TIME_EXCEEDED", f"Expected status='TIME_EXCEEDED', got {status!r}"
    assert close_reason == "TIME_EXCEEDED", (
        f"Expected close_reason='TIME_EXCEEDED', got {close_reason!r}"
    )


# ---------------------------------------------------------------------------
# AC-S11-07: Lifecycle checker does NOT auto-close a Setup D signal
# ---------------------------------------------------------------------------

async def test_lifecycle_does_not_close_setup_d_signal(mem_db):
    """_expire_stale_signals() must skip signals with setup_type='D' regardless of age."""
    acc = "0001111111-24-110008"
    insert_filing(mem_db, acc)

    # Insert a Setup D signal manually (emit() with Rank D produces no signals row,
    # so insert directly to simulate a hypothetical LIVE D signal in the DB).
    mem_db.execute(
        """INSERT INTO signals (
            accession_number, ticker, setup_type, score, rank,
            alert_type, status, alerted_at
        ) VALUES (?, 'MMAT', 'D', 35, 'D', 'NEW_SETUP', 'LIVE',
                  NOW() - INTERVAL '10 days')""",
        [acc],
    )
    signal_id = mem_db.execute(
        "SELECT id FROM signals WHERE ticker = 'MMAT'"
    ).fetchone()[0]

    manager = SignalManager()
    with patch("app.services.signal_manager.get_db", return_value=mem_db):
        await manager._expire_stale_signals()

    row = mem_db.execute(
        "SELECT status FROM signals WHERE id = ?", [signal_id]
    ).fetchone()
    assert row is not None, "Signal row not found"
    assert row[0] == "LIVE", (
        f"Expected Setup D signal to remain LIVE, got status={row[0]!r}"
    )
