import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.utils.errors import FMPDataUnavailableError

logger = logging.getLogger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api"
_BACKOFF = (1.0, 2.0, 4.0)  # seconds between retries


@dataclass
class FMPMarketData:
    price: float
    market_cap: float
    float_shares: float
    adv_dollar: float
    fetched_at: datetime


class FMPClient:
    """Async client for the FMP Ultimate API."""

    async def get_market_data(self, ticker: str) -> FMPMarketData:
        """
        Fetch price, market cap, float shares, and 20-day ADV for ticker.

        Makes two API calls: /v3/quote (price, market_cap) and
        /v4/shares_float (float_shares). ADV is computed from
        /v3/historical-price-full (20 daily bars, sum(close*volume)/20).

        Raises FMPDataUnavailableError if data cannot be obtained after retries.
        """
        if not settings.fmp_api_key:
            logger.warning("FMP_API_KEY not configured; enrichment unavailable")
            raise FMPDataUnavailableError("FMP_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            quote = await self._get_quote(client, ticker)
            float_shares = await self._get_float_shares(client, ticker)
            adv_dollar = await self._get_adv(client, ticker)

        return FMPMarketData(
            price=quote["price"],
            market_cap=quote["marketCap"],
            float_shares=float_shares,
            adv_dollar=adv_dollar,
            fetched_at=datetime.now(timezone.utc),
        )

    async def _get_quote(self, client: httpx.AsyncClient, ticker: str) -> dict:
        url = f"{FMP_BASE_URL}/v3/quote/{ticker}"
        data = await self._fetch_with_retry(client, url)
        if not data:
            raise FMPDataUnavailableError(f"Empty quote response for {ticker}")
        return data[0]

    async def _get_float_shares(self, client: httpx.AsyncClient, ticker: str) -> float:
        url = f"{FMP_BASE_URL}/v4/shares_float"
        data = await self._fetch_with_retry(client, url, params={"symbol": ticker})
        if not data:
            raise FMPDataUnavailableError(f"Empty shares_float response for {ticker}")
        return float(data[0]["floatShares"])

    async def _get_adv(self, client: httpx.AsyncClient, ticker: str) -> float:
        """Compute 20-day average dollar volume: sum(close * volume) / 20."""
        url = f"{FMP_BASE_URL}/v3/historical-price-full/{ticker}"
        data = await self._fetch_with_retry(client, url, params={"timeseries": 20})
        historical = data.get("historical", []) if isinstance(data, dict) else []
        if not historical:
            raise FMPDataUnavailableError(f"No historical data for {ticker}")
        dollar_volume = sum(
            float(bar["close"]) * float(bar["volume"]) for bar in historical
        )
        return dollar_volume / 20

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict | None = None,
    ) -> dict | list:
        all_params = {"apikey": settings.fmp_api_key, **(params or {})}
        last_exc: Exception | None = None
        for attempt, backoff in enumerate(_BACKOFF, start=1):
            try:
                resp = await client.get(url, params=all_params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        "FMP %s attempt %d: HTTP %d", url, attempt, resp.status_code
                    )
                    if attempt < len(_BACKOFF):
                        await asyncio.sleep(backoff)
                    continue
                resp.raise_for_status()
                return resp.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning("FMP %s attempt %d failed: %s", url, attempt, exc)
                last_exc = exc
                if attempt < len(_BACKOFF):
                    await asyncio.sleep(backoff)
        raise FMPDataUnavailableError(
            f"FMP request failed after {len(_BACKOFF)} attempts: {url}"
        ) from last_exc
