import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Coroutine, Any

import httpx

from app.core.config import settings
from app.services.db import get_db
from app.services.filing_fetcher import FilingFetcher

logger = logging.getLogger(__name__)

EFTS_HEADERS = {
    "User-Agent": "gap-lens-dilution-filter contact@yourdomain.com",
    "Accept": "application/json",
}
_BACKOFF = (1.0, 2.0, 4.0)


class EdgarPoller:
    """Poll the EDGAR EFTS JSON endpoint and hand new filings to process_filing."""

    def __init__(self) -> None:
        self._last_poll_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._process_filing: Callable[..., Coroutine[Any, Any, None]] | None = None
        self._fetcher = FilingFetcher()

    @property
    def last_poll_at(self) -> datetime | None:
        return self._last_poll_at

    @property
    def last_success_at(self) -> datetime | None:
        return self._last_success_at

    def set_process_filing(self, fn: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Wire in the full pipeline function (called in Slice 12)."""
        self._process_filing = fn

    async def run_forever(self) -> None:
        """Infinite polling loop. Follows the pattern from Architecture Section 8."""
        while True:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Poller cycle failed: %s", exc)
            await asyncio.sleep(settings.edgar_poll_interval)

    async def _poll_once(self) -> None:
        """Fetch one page of EFTS results, deduplicate, and dispatch new filings."""
        self._last_poll_at = datetime.now(timezone.utc)
        await asyncio.to_thread(
            self._update_poll_state, last_poll_at=self._last_poll_at
        )

        db = get_db()
        row = db.execute(
            "SELECT last_success_at FROM poll_state WHERE id = 1"
        ).fetchone()
        last_success = row[0] if row and row[0] else None

        if last_success:
            if isinstance(last_success, str):
                last_success = datetime.fromisoformat(last_success)
            startdt = max(
                last_success.date(),
                (datetime.now(timezone.utc) - timedelta(days=1)).date(),
            )
        else:
            startdt = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        today = datetime.now(timezone.utc).date()
        offset = 0
        total_hits = None

        async with httpx.AsyncClient(timeout=30.0, headers=EFTS_HEADERS) as client:
            while True:
                params = {
                    "forms": "S-1,S-1/A,S-3,424B2,424B4,8-K,13D/A",
                    "startdt": startdt.isoformat(),
                    "enddt": today.isoformat(),
                    "from": offset,
                }
                data = await self._fetch_efts(client, params)
                if data is None:
                    return  # malformed response, already logged

                hits = data.get("hits", [])
                if total_hits is None:
                    total_hits = data.get("total", {}).get("value", 0)

                for hit in hits:
                    src = hit.get("_source", {})
                    accession_no = src.get("accessionNo", "")
                    cik = str(src.get("cik", ""))
                    form_type = src.get("formType", "")
                    filed_at_raw = src.get("filedAt", "")
                    entity_name = src.get("entityName")
                    ticker = src.get("ticker")

                    if not accession_no:
                        continue

                    # Deduplicate
                    existing = db.execute(
                        "SELECT 1 FROM filings WHERE accession_number = ?",
                        [accession_no],
                    ).fetchone()
                    if existing:
                        continue

                    # Build filing URL
                    cik_padded = cik.zfill(10)
                    accession_clean = accession_no.replace("-", "")
                    filing_url = (
                        f"https://www.sec.gov/Archives/edgar/data/"
                        f"{cik_padded}/{accession_clean}/{accession_no}.txt"
                    )

                    try:
                        filed_at = datetime.fromisoformat(filed_at_raw)
                    except (ValueError, TypeError):
                        filed_at = datetime.now(timezone.utc)

                    await self._process_new_filing(
                        accession_no,
                        cik,
                        form_type,
                        filed_at,
                        filing_url,
                        entity_name,
                        ticker,
                    )

                offset += len(hits)
                if not hits or offset >= total_hits:
                    break

        self._last_success_at = datetime.now(timezone.utc)
        await asyncio.to_thread(
            self._update_poll_state,
            last_poll_at=self._last_poll_at,
            last_success_at=self._last_success_at,
        )

    async def _process_new_filing(
        self,
        accession_number: str,
        cik: str,
        form_type: str,
        filed_at: datetime,
        filing_url: str,
        entity_name: str | None,
        ticker: str | None,
    ) -> None:
        """Dispatch to the full pipeline callback, or log and skip."""
        if self._process_filing is not None:
            await self._process_filing(
                accession_number,
                cik,
                form_type,
                filed_at,
                filing_url,
                entity_name,
                ticker,
            )
        else:
            logger.debug(
                "No process_filing callback registered; skipping %s",
                accession_number,
            )

    async def _fetch_efts(self, client: httpx.AsyncClient, params: dict) -> dict | None:
        """Fetch one EFTS page with retry. Returns parsed JSON or None on failure."""
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF, start=1):
            try:
                resp = await client.get(settings.edgar_efts_url, params=params)
                resp.raise_for_status()
                try:
                    return resp.json()
                except Exception:
                    excerpt = resp.text[:500]
                    logger.error(
                        "EFTS malformed JSON (attempt %d): %s", attempt, excerpt
                    )
                    return None
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("EFTS request attempt %d failed: %s", attempt, exc)
                last_exc = exc
                if attempt < len(_BACKOFF):
                    await asyncio.sleep(backoff)
        logger.error("EFTS unreachable after %d attempts: %s", len(_BACKOFF), last_exc)
        return None

    @staticmethod
    def _update_poll_state(
        last_poll_at: datetime | None = None,
        last_success_at: datetime | None = None,
    ) -> None:
        db = get_db()
        if last_success_at is not None:
            db.execute(
                "UPDATE poll_state SET last_poll_at = ?, last_success_at = ? WHERE id = 1",
                [last_poll_at, last_success_at],
            )
        else:
            db.execute(
                "UPDATE poll_state SET last_poll_at = ? WHERE id = 1",
                [last_poll_at],
            )
