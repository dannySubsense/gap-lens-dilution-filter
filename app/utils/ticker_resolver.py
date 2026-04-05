import logging
from datetime import datetime, timezone

import httpx

from app.services.db import _sync_execute, _sync_executemany, _sync_fetchone, get_db  # noqa: F401

logger = logging.getLogger(__name__)

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
_last_refresh: datetime | None = None


class TickerResolver:
    """Resolve EDGAR CIK numbers to ticker symbols using a four-step fallback chain."""

    @staticmethod
    async def refresh() -> None:
        """
        Download SEC company_tickers_exchange.json and upsert into cik_ticker_map.
        Called from lifespan startup in main.py — NOT from init_db().
        Refreshes once per day.
        """
        global _last_refresh
        now = datetime.now(timezone.utc)
        if _last_refresh is not None:
            elapsed = (now - _last_refresh).total_seconds()
            if elapsed < 86400:
                logger.debug("TickerResolver: skipping refresh (%.0fs ago)", elapsed)
                return

        logger.info("TickerResolver: downloading company_tickers_exchange.json")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                SEC_TICKERS_URL,
                headers={
                    "User-Agent": "gap-lens-dilution-filter contact@yourdomain.com"
                },
            )
            resp.raise_for_status()
            data = resp.json()

        rows = data.get("data", [])

        # Deduplicate by CIK — SEC data lists some companies on multiple exchanges;
        # keep the first occurrence (primary listing appears first in the file).
        seen: dict[int, tuple] = {}
        for r in rows:
            cik = int(r[0])
            if cik not in seen:
                seen[cik] = (cik, r[2], r[1], r[3])

        _sync_execute("DELETE FROM cik_ticker_map")
        _sync_executemany(
            "INSERT INTO cik_ticker_map (cik, ticker, name, exchange) VALUES (?, ?, ?, ?)",
            list(seen.values()),
        )
        _last_refresh = now
        logger.info("TickerResolver: loaded %d tickers (%d dupes dropped)", len(seen), len(rows) - len(seen))

    @staticmethod
    def resolve(
        cik: str,
        efts_ticker: str | None,
        entity_name: str | None,
    ) -> str | None:
        """
        Four-step fallback chain:
        1. Query cik_ticker_map by CIK (primary source)
        2. Use efts_ticker from EFTS response if present
        3. Query FMP company name search (if entity_name provided)
        4. Return None (caller marks filing as UNRESOLVABLE)
        """
        # Step 1: DuckDB cik_ticker_map lookup
        try:
            cik_int = int(cik.lstrip("0") or "0")
            row = _sync_fetchone(
                "SELECT ticker FROM cik_ticker_map WHERE cik = ?", [cik_int]
            )
            if row:
                return row[0]
        except Exception as exc:
            logger.warning("CIK map lookup failed for %s: %s", cik, exc)

        # Step 2: EFTS response ticker field
        if efts_ticker:
            return efts_ticker

        # Step 3: FMP company name search — sync HTTP call avoided in phase 1;
        # return None and let caller handle UNRESOLVABLE rather than blocking here.
        # Full async FMP search can be wired in Slice 12 if needed.
        if entity_name:
            logger.debug(
                "TickerResolver: entity_name '%s' available but FMP search not "
                "wired in Slice 6; falling through to UNRESOLVABLE",
                entity_name,
            )

        # Step 4: UNRESOLVABLE
        return None
