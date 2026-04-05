from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.classifier.protocol import ClassificationResult
from app.services.db import get_db
from app.services.fmp_client import FMPMarketData
from app.services.scorer import ScorerResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SignalManager:
    async def emit(
        self,
        scorer_result: ScorerResult,
        classification: ClassificationResult,
        fmp_data: FMPMarketData,
        accession_number: str,
        ticker: str,
    ) -> int | None:
        """
        Write one row to labels (all ranks A/B/C/D).
        Insert or update a row in signals for ranks A and B.
        Return signal_id for A/B ranks, None for C/D.
        """
        db = get_db()

        # Always write to labels (all ranks)
        await asyncio.to_thread(
            db.execute,
            """
            INSERT INTO labels (
                accession_number,
                classifier_version,
                setup_type,
                confidence,
                dilution_severity,
                immediate_pressure,
                price_discount,
                short_attractiveness,
                rank,
                key_excerpt,
                reasoning
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (accession_number, classifier_version) DO UPDATE SET
                setup_type = excluded.setup_type,
                confidence = excluded.confidence,
                dilution_severity = excluded.dilution_severity,
                immediate_pressure = excluded.immediate_pressure,
                price_discount = excluded.price_discount,
                short_attractiveness = excluded.short_attractiveness,
                rank = excluded.rank,
                key_excerpt = excluded.key_excerpt,
                reasoning = excluded.reasoning,
                scored_at = NOW()
            """,
            [
                accession_number,
                settings.classifier_name,
                classification["setup_type"],
                classification["confidence"],
                classification["dilution_severity"],
                classification["immediate_pressure"],
                classification["price_discount"],
                classification["short_attractiveness"],
                scorer_result.rank,
                classification["key_excerpt"],
                classification["reasoning"],
            ],
        )

        # Rank C or D: no signals insert
        if scorer_result.rank in ("C", "D"):
            return None

        # SETUP_UPDATE check: look for an existing open signal for this ticker
        # within the last 24 hours
        existing = await asyncio.to_thread(
            db.execute,
            """
            SELECT id FROM signals
            WHERE ticker = ?
              AND alerted_at > (NOW() - INTERVAL '24 hours')
              AND status != 'CLOSED'
            LIMIT 1
            """,
            [ticker],
        )
        row = existing.fetchone()

        if row is not None:
            existing_id: int = row[0]
            await asyncio.to_thread(
                db.execute,
                """
                UPDATE signals
                SET alert_type = 'SETUP_UPDATE',
                    score = ?,
                    rank = ?
                WHERE id = ?
                """,
                [scorer_result.score, scorer_result.rank, existing_id],
            )
            logger.info(
                "SETUP_UPDATE for ticker=%s signal_id=%d score=%d rank=%s",
                ticker,
                existing_id,
                scorer_result.score,
                scorer_result.rank,
            )
            return existing_id

        # Rank A -> LIVE, Rank B -> WATCHLIST
        status = "LIVE" if scorer_result.rank == "A" else "WATCHLIST"
        setup_quality_weight: float = settings.setup_quality[
            classification["setup_type"]
        ]

        result = await asyncio.to_thread(
            db.execute,
            """
            INSERT INTO signals (
                accession_number,
                ticker,
                setup_type,
                score,
                rank,
                status,
                alert_type,
                alerted_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'NEW_SETUP', NOW())
            RETURNING id
            """,
            [
                accession_number,
                ticker,
                classification["setup_type"],
                scorer_result.score,
                scorer_result.rank,
                status,
            ],
        )
        inserted = result.fetchone()
        if inserted is None:
            raise RuntimeError(
                f"INSERT INTO signals did not return an id for ticker={ticker}"
            )
        signal_id: int = inserted[0]
        logger.info(
            "NEW_SETUP signal_id=%d ticker=%s rank=%s score=%d setup_quality_weight=%.4f",
            signal_id,
            ticker,
            scorer_result.rank,
            scorer_result.score,
            setup_quality_weight,
        )
        return signal_id

    async def close(
        self, signal_id: int, close_reason: str, status: str = "CLOSED"
    ) -> None:
        """Mark a signal as closed with a reason and timestamp."""
        db = get_db()
        await asyncio.to_thread(
            db.execute,
            """
            UPDATE signals
            SET status = ?,
                closed_at = NOW(),
                close_reason = ?
            WHERE id = ?
            """,
            [status, close_reason, signal_id],
        )
        logger.info("Signal %d %s: %s", signal_id, status, close_reason)

    async def record_position(
        self,
        signal_id: int,
        entry_price: float | None,
        cover_price: float | None,
    ) -> None:
        """
        Update entry_price and/or cover_price on a signal.
        If both are provided, compute pnl_pct (short P&L) and close the signal.
        """
        db = get_db()

        if entry_price is not None:
            await asyncio.to_thread(
                db.execute,
                "UPDATE signals SET entry_price = ? WHERE id = ?",
                [entry_price, signal_id],
            )

        if cover_price is not None:
            await asyncio.to_thread(
                db.execute,
                "UPDATE signals SET cover_price = ? WHERE id = ?",
                [cover_price, signal_id],
            )

        if entry_price is not None and cover_price is not None:
            pnl_pct = (entry_price - cover_price) / entry_price * 100
            await asyncio.to_thread(
                db.execute,
                "UPDATE signals SET pnl_pct = ? WHERE id = ?",
                [pnl_pct, signal_id],
            )
            await self.close(signal_id, "MANUAL")

    async def run_lifecycle_loop(self) -> None:
        """
        Periodically check for signals that have exceeded their hold time and
        close them with reason 'TIME_EXCEEDED'.
        Hold times: A=3 days, B=2 days, C=1 day, D=skip, E=1 day.
        """
        logger.info(
            "Lifecycle loop started; interval=%ds",
            settings.lifecycle_check_interval,
        )
        try:
            while True:
                await asyncio.sleep(settings.lifecycle_check_interval)
                await self._expire_stale_signals()
        except asyncio.CancelledError:
            logger.info("Lifecycle loop cancelled; exiting cleanly")

    async def _expire_stale_signals(self) -> None:
        db = get_db()
        rows = await asyncio.to_thread(
            db.execute,
            """
            SELECT id, setup_type FROM signals
            WHERE status IN ('LIVE', 'WATCHLIST')
              AND (
                (setup_type = 'A' AND alerted_at < NOW() - INTERVAL '3 days') OR
                (setup_type = 'B' AND alerted_at < NOW() - INTERVAL '2 days') OR
                (setup_type IN ('C', 'E') AND alerted_at < NOW() - INTERVAL '1 day')
              )
            """,
        )
        expired = rows.fetchall()
        for row in expired:
            signal_id: int = row[0]
            setup_type: str = row[1]
            logger.info(
                "Expiring signal_id=%d setup_type=%s (TIME_EXCEEDED)",
                signal_id,
                setup_type,
            )
            await self.close(signal_id, "TIME_EXCEEDED", status="TIME_EXCEEDED")
