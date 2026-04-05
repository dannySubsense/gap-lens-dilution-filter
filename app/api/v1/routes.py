from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.signals import (
    ClassificationDetail,
    HealthResponse,
    PositionRequest,
    PositionResponse,
    SignalDetailResponse,
    SignalListResponse,
    SignalRow,
)
from app.services.db import get_db
from app.services.fmp_client import FMPClient, FMPDataUnavailableError
from app.services.signal_manager import SignalManager

logger = logging.getLogger(__name__)

router = APIRouter()

_SIGNAL_COLUMNS = (
    "id, accession_number, ticker, setup_type, score, rank, alert_type, status, "
    "alerted_at, price_at_alert, entry_price, cover_price, pnl_pct, closed_at, close_reason"
)


async def _get_current_price(ticker: str) -> Optional[float]:
    """Fetch current price from FMP; return None on any failure."""
    try:
        fmp = FMPClient()
        data = await fmp.get_market_data(ticker)
        return data.price
    except FMPDataUnavailableError:
        return None
    except Exception:
        logger.warning("Unexpected error fetching FMP price for ticker=%s", ticker)
        return None


def _row_to_signal_row(
    row: tuple,
    price_move_pct: Optional[float] = None,
    elapsed_seconds: Optional[int] = None,
) -> SignalRow:
    """Map a 15-element DB tuple to a SignalRow."""
    return SignalRow(
        id=row[0],
        accession_number=row[1],
        ticker=row[2],
        setup_type=row[3],
        score=row[4],
        rank=row[5],
        alert_type=row[6],
        status=row[7],
        alerted_at=row[8],
        price_at_alert=row[9],
        entry_price=row[10],
        cover_price=row[11],
        pnl_pct=row[12],
        closed_at=row[13],
        close_reason=row[14],
        price_move_pct=price_move_pct,
        elapsed_seconds=elapsed_seconds,
    )


@router.get("/signals", response_model=SignalListResponse)
async def list_signals() -> SignalListResponse:
    """Return all LIVE and WATCHLIST signals ordered by score descending."""
    db = get_db()
    result = await asyncio.to_thread(
        db.execute,
        f"SELECT {_SIGNAL_COLUMNS} FROM signals "
        "WHERE status IN ('LIVE', 'WATCHLIST') ORDER BY score DESC",
    )
    rows = result.fetchall()

    signals: list[SignalRow] = []
    for row in rows:
        ticker: str = row[2]
        price_at_alert: Optional[float] = row[9]

        current_price = await _get_current_price(ticker)

        price_move_pct: Optional[float] = None
        if current_price is not None and price_at_alert is not None:
            price_move_pct = (current_price - price_at_alert) / price_at_alert * 100

        alerted_at: datetime = row[8]
        if alerted_at.tzinfo is None:
            alerted_at = alerted_at.replace(tzinfo=timezone.utc)
        elapsed_seconds = int((datetime.now(timezone.utc) - alerted_at).total_seconds())

        signals.append(
            _row_to_signal_row(
                row, price_move_pct=price_move_pct, elapsed_seconds=elapsed_seconds
            )
        )

    return SignalListResponse(signals=signals, count=len(signals))


@router.get("/signals/closed", response_model=SignalListResponse)
async def list_closed_signals() -> SignalListResponse:
    """Return the 50 most-recently-closed signals."""
    db = get_db()
    result = await asyncio.to_thread(
        db.execute,
        f"SELECT {_SIGNAL_COLUMNS} FROM signals "
        "WHERE status IN ('CLOSED', 'TIME_EXCEEDED') ORDER BY closed_at DESC LIMIT 50",
    )
    rows = result.fetchall()
    signals = [_row_to_signal_row(row) for row in rows]
    return SignalListResponse(signals=signals, count=len(signals))


@router.get("/signals/{signal_id}", response_model=SignalDetailResponse)
async def get_signal(signal_id: int) -> SignalDetailResponse:
    """Return full detail for a single signal including classification and filing data."""
    db = get_db()
    result = await asyncio.to_thread(
        db.execute,
        """
        SELECT s.id, s.accession_number, s.ticker, s.setup_type, s.score, s.rank,
               s.alert_type, s.status, s.alerted_at, s.price_at_alert,
               s.entry_price, s.cover_price, s.pnl_pct, s.closed_at, s.close_reason,
               l.confidence, l.dilution_severity, l.immediate_pressure,
               l.price_discount, l.short_attractiveness, l.key_excerpt, l.reasoning,
               l.classifier_version, l.scored_at,
               f.entity_name, f.filing_url, f.form_type, f.filed_at
        FROM signals s
        LEFT JOIN labels l ON l.accession_number = s.accession_number
        LEFT JOIN filings f ON f.accession_number = s.accession_number
        WHERE s.id = ?
        """,
        [signal_id],
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_row = _row_to_signal_row(row[:15])

    classification = ClassificationDetail(
        setup_type=row[3],
        confidence=row[15],
        dilution_severity=row[16],
        immediate_pressure=row[17],
        price_discount=row[18],
        short_attractiveness=row[19],
        key_excerpt=row[20],
        reasoning=row[21],
        classifier_version=row[22],
        scored_at=row[23],
    )

    current_price = await _get_current_price(row[2])

    return SignalDetailResponse(
        signal=signal_row,
        ticker=row[2],
        entity_name=row[24],
        classification=classification,
        filing_url=row[25],
        form_type=row[26],
        filed_at=row[27],
        current_price=current_price,
    )


@router.post("/signals/{signal_id}/position", response_model=PositionResponse)
async def record_position(signal_id: int, body: PositionRequest) -> PositionResponse:
    """Set entry and/or cover price on a signal."""
    db = get_db()

    # Verify signal exists before mutating
    check = await asyncio.to_thread(
        db.execute,
        "SELECT id FROM signals WHERE id = ?",
        [signal_id],
    )
    if check.fetchone() is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_manager = SignalManager()
    await signal_manager.record_position(signal_id, body.entry_price, body.cover_price)

    result = await asyncio.to_thread(
        db.execute,
        "SELECT id, entry_price, cover_price, pnl_pct, status FROM signals WHERE id = ?",
        [signal_id],
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    return PositionResponse(
        id=row[0],
        entry_price=row[1],
        cover_price=row[2],
        pnl_pct=row[3],
        status=row[4],
    )


@router.post("/signals/{signal_id}/close", response_model=SignalDetailResponse)
async def close_signal(signal_id: int) -> SignalDetailResponse:
    """Manually close an open signal."""
    db = get_db()

    check = await asyncio.to_thread(
        db.execute,
        "SELECT id FROM signals WHERE id = ?",
        [signal_id],
    )
    if check.fetchone() is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_manager = SignalManager()
    await signal_manager.close(signal_id, "MANUAL")

    result = await asyncio.to_thread(
        db.execute,
        """
        SELECT s.id, s.accession_number, s.ticker, s.setup_type, s.score, s.rank,
               s.alert_type, s.status, s.alerted_at, s.price_at_alert,
               s.entry_price, s.cover_price, s.pnl_pct, s.closed_at, s.close_reason,
               l.confidence, l.dilution_severity, l.immediate_pressure,
               l.price_discount, l.short_attractiveness, l.key_excerpt, l.reasoning,
               l.classifier_version, l.scored_at,
               f.entity_name, f.filing_url, f.form_type, f.filed_at
        FROM signals s
        LEFT JOIN labels l ON l.accession_number = s.accession_number
        LEFT JOIN filings f ON f.accession_number = s.accession_number
        WHERE s.id = ?
        """,
        [signal_id],
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal_row = _row_to_signal_row(row[:15])

    classification = ClassificationDetail(
        setup_type=row[3],
        confidence=row[15],
        dilution_severity=row[16],
        immediate_pressure=row[17],
        price_discount=row[18],
        short_attractiveness=row[19],
        key_excerpt=row[20],
        reasoning=row[21],
        classifier_version=row[22],
        scored_at=row[23],
    )

    current_price = await _get_current_price(row[2])

    return SignalDetailResponse(
        signal=signal_row,
        ticker=row[2],
        entity_name=row[24],
        classification=classification,
        filing_url=row[25],
        form_type=row[26],
        filed_at=row[27],
        current_price=current_price,
    )


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Return system health including poller state."""
    db = get_db()
    result = await asyncio.to_thread(
        db.execute,
        "SELECT last_poll_at, last_success_at FROM poll_state WHERE id = 1",
    )
    row = result.fetchone()

    last_polled_at: Optional[datetime] = row[0] if row else None
    last_success_at: Optional[datetime] = row[1] if row else None

    now = datetime.now(timezone.utc)
    if last_success_at is None:
        status = "error"
    else:
        # Normalize to UTC-aware for comparison
        if last_success_at.tzinfo is None:
            last_success_at = last_success_at.replace(tzinfo=timezone.utc)
        delta_seconds = (now - last_success_at).total_seconds()
        if delta_seconds < 180:
            status = "ok"
        elif delta_seconds < 600:
            status = "degraded"
        else:
            status = "error"

    return HealthResponse(
        status=status,
        last_poll_at=last_polled_at,
        last_success_at=last_success_at,
        poll_interval_seconds=settings.edgar_poll_interval,
        fmp_configured=bool(settings.fmp_api_key),
        askedgar_configured=bool(settings.askedgar_api_key),
        db_path=settings.duckdb_path,
    )
