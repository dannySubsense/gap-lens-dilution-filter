import asyncio
import time
from datetime import datetime, timezone, timedelta
import httpx
from typing import Dict, Any
from app.core.config import settings
from app.utils.errors import TickerNotFoundError, RateLimitError, ExternalAPIError


class DilutionService:
    """Service for interacting with Ask-Edgar API with retry logic."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=settings.request_timeout,
            headers={"API-KEY": settings.askedgar_api_key},
            follow_redirects=True,
        )
        self.max_retries = 3
        self.retry_delay = 1  # seconds
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _make_request(self, endpoint: str, ticker: str) -> Dict[str, Any]:
        """Make a request to the Ask-Edgar API with retry logic."""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(
                    f"{settings.askedgar_url}{endpoint}?ticker={ticker}"
                )

                if response.status_code == 404:
                    raise TickerNotFoundError(f"Ticker '{ticker}' not found")
                elif response.status_code == 429:
                    if attempt == self.max_retries - 1:
                        raise RateLimitError("Rate limit exceeded")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                elif response.status_code >= 400:
                    raise ExternalAPIError(
                        f"API request failed with status {response.status_code}"
                    )

                response.raise_for_status()
                data = response.json()
                return data.get("results", [{}])[0] if data.get("results") else {}

            except httpx.RequestError as e:
                if attempt == self.max_retries - 1:
                    raise ExternalAPIError(f"Request error: {str(e)}")
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise ExternalAPIError("Max retries exceeded")

    async def _make_request_list(self, endpoint: str, params: Dict[str, Any]) -> list:
        """Make a request to the Ask-Edgar API and return list results."""
        for attempt in range(self.max_retries):
            try:
                response = await self.client.get(
                    f"{settings.askedgar_url}{endpoint}",
                    params=params
                )

                if response.status_code == 404:
                    return []
                elif response.status_code == 429:
                    if attempt == self.max_retries - 1:
                        raise RateLimitError("Rate limit exceeded")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
                elif response.status_code >= 400:
                    raise ExternalAPIError(
                        f"API request failed with status {response.status_code}"
                    )

                response.raise_for_status()
                data = response.json()
                return data.get("results", [])

            except httpx.RequestError as e:
                if attempt == self.max_retries - 1:
                    raise ExternalAPIError(f"Request error: {str(e)}")
                await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise ExternalAPIError("Max retries exceeded")

    def _cache_get(self, key: str) -> Any | None:
        """Return cached value if within TTL, else None."""
        if key in self._cache:
            stored_at, value = self._cache[key]
            if time.time() - stored_at < 1800:  # 30 min TTL
                return value
        return None

    def _cache_set(self, key: str, value: Any) -> None:
        """Cache a value. Never cache None."""
        if value is not None:
            self._cache[key] = (time.time(), value)

    async def _make_request_cached(self, endpoint: str, ticker: str, cache_key: str) -> dict | None:
        """Cached wrapper for _make_request. Returns None on error (does not raise)."""
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = await self._make_request(endpoint, ticker)
            self._cache_set(cache_key, result)
            return result
        except Exception:
            return None

    async def _make_request_list_cached(self, endpoint: str, params: dict, cache_key: str) -> list:
        """Cached wrapper for _make_request_list. Returns [] on error."""
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        try:
            result = await self._make_request_list(endpoint, params)
            self._cache_set(cache_key, result)
            return result
        except Exception:
            return []

    async def get_news(self, ticker: str, limit: int = 10) -> list:
        """
        Fetch news and filings for a given ticker.

        Args:
            ticker (str): The stock ticker symbol
            limit (int): Maximum number of results to return

        Returns:
            list: News and filings data
        """
        params = {"ticker": ticker, "limit": limit}
        return await self._make_request_list("/enterprise/v1/news", params)

    async def get_registrations(self, ticker: str) -> list:
        """
        Fetch registration data (shelf, ATM, equity line, S-1) for a given ticker.

        Args:
            ticker (str): The stock ticker symbol

        Returns:
            list: Registration data
        """
        params = {"ticker": ticker}
        return await self._make_request_list("/enterprise/v1/registrations", params)

    async def get_dilution_detail(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch detailed dilution data (warrants and convertibles) for a given ticker.

        Args:
            ticker (str): The stock ticker symbol

        Returns:
            Dict[str, Any]: Detailed dilution data including warrants and convertibles
        """
        params = {"ticker": ticker}
        results = await self._make_request_list("/enterprise/v1/dilution-data", params)

        # The API returns a list, we'll organize by type
        warrants = []
        convertibles = []

        for item in results:
            if item.get("warrants_amount") or item.get("warrants_remaining"):
                warrants.append(item)
            if item.get("convertible_debt_remaining") or item.get("offering_amount"):
                convertibles.append(item)

        return {
            "warrants": warrants,
            "convertibles": convertibles
        }

    async def get_dilution_data(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch comprehensive dilution data for a given ticker from all endpoints.

        Args:
            ticker (str): The stock ticker symbol

        Returns:
            Dict[str, Any]: Combined dilution data with camelCase keys

        Raises:
            TickerNotFoundError: If ticker is not found
            RateLimitError: If rate limit is exceeded
            ExternalAPIError: For other API errors
        """
        # Fetch all endpoints concurrently
        dilution_task = self._make_request("/enterprise/v1/dilution-rating", ticker)
        float_task = self._make_request("/enterprise/v1/float-outstanding", ticker)
        news_task = self.get_news(ticker, limit=10)
        registrations_task = self.get_registrations(ticker)
        dilution_detail_task = self.get_dilution_detail(ticker)

        dilution_data, float_data, news_data, registrations_data, dilution_detail_data = await asyncio.gather(
            dilution_task, float_task, news_task, registrations_task, dilution_detail_task
        )

        # Merge and map to camelCase
        result = {}

        # Map dilution-rating fields
        result["ticker"] = ticker.upper()
        result["offeringRisk"] = dilution_data.get("overall_offering_risk")
        result["offeringAbility"] = dilution_data.get("offering_ability")
        result["offeringAbilityDesc"] = dilution_data.get("offering_ability_desc")
        result["dilutionRisk"] = dilution_data.get("dilution")
        result["dilutionDesc"] = dilution_data.get("dilution_desc")
        result["offeringFrequency"] = dilution_data.get("offering_frequency")
        result["cashNeed"] = dilution_data.get("cash_need")
        result["cashNeedDesc"] = dilution_data.get("cash_need_desc")
        result["cashRunway"] = dilution_data.get("cash_remaining_months")
        result["cashBurn"] = dilution_data.get("cash_burn")
        result["estimatedCash"] = dilution_data.get("estimated_cash")
        result["warrantExercise"] = dilution_data.get("warrant_exercise")
        result["warrantExerciseDesc"] = dilution_data.get("warrant_exercise_desc")

        # Map float-outstanding fields
        result["float"] = float_data.get("float")
        result["outstanding"] = float_data.get("outstanding")
        result["marketCap"] = float_data.get("market_cap_final")
        result["industry"] = float_data.get("industry")
        result["sector"] = float_data.get("sector")
        result["country"] = float_data.get("country")
        result["insiderOwnership"] = float_data.get("insider_percent")
        result["institutionalOwnership"] = float_data.get("institutions_percent")

        # Add news data
        result["news"] = news_data

        # Add registrations data
        result["registrations"] = registrations_data

        # Add detailed dilution data
        result["warrants"] = dilution_detail_data.get("warrants", [])
        result["convertibles"] = dilution_detail_data.get("convertibles", [])

        return result

    async def get_gap_stats(self, ticker: str) -> list:
        return await self._make_request_list_cached(
            "/v1/gap-stats", {"ticker": ticker, "page": 1, "limit": 100}, f"gapstats:{ticker.upper()}"
        )

    async def get_offerings(self, ticker: str) -> list:
        return await self._make_request_list_cached(
            "/v1/offerings", {"ticker": ticker, "limit": 5}, f"offerings:{ticker.upper()}"
        )

    async def get_ownership(self, ticker: str) -> dict | None:
        cached = self._cache_get(f"ownership:{ticker.upper()}")
        if cached is not None:
            return cached
        try:
            results = await self._make_request_list("/v1/ownership", {"ticker": ticker, "limit": 100})
            value = results[0] if results else None
            self._cache_set(f"ownership:{ticker.upper()}", value)
            return value
        except Exception:
            return None

    async def get_chart_analysis(self, ticker: str) -> dict | None:
        cached = self._cache_get(f"chart:{ticker.upper()}")
        if cached is not None:
            return cached
        try:
            results = await self._make_request_list("/v1/ai-chart-analysis", {"ticker": ticker, "limit": 1})
            value = results[0] if results else None
            self._cache_set(f"chart:{ticker.upper()}", value)
            return value
        except Exception:
            return None

    async def get_screener_price(self, ticker: str) -> float | None:
        cached = self._cache_get(f"price:{ticker.upper()}")
        if cached is not None:
            return cached
        try:
            result = await self._make_request("/enterprise/v1/screener", ticker)
            price = result.get("price") if result else None
            self._cache_set(f"price:{ticker.upper()}", price)
            return price
        except Exception:
            return None

    async def get_dilution_data_v2(self, ticker: str) -> Dict[str, Any]:
        """
        Fetch comprehensive V2 dilution data for a given ticker from all endpoints.

        Runs all 9 sub-calls concurrently via asyncio.gather with return_exceptions=True.
        Sub-call failures degrade gracefully to null/[] — never raises due to a sub-call failure.

        Args:
            ticker (str): The stock ticker symbol

        Returns:
            Dict[str, Any]: Combined V2 dilution data with camelCase keys
        """
        upper = ticker.upper()

        (
            dilution_data,
            float_data,
            news_data,
            dilution_raw,
            gap_stats_data,
            offerings_data,
            ownership_data,
            chart_data,
            screener_price,
        ) = await asyncio.gather(
            self._make_request_cached("/enterprise/v1/dilution-rating", ticker, f"dilution:{upper}"),
            self._make_request_cached("/enterprise/v1/float-outstanding", ticker, f"float:{upper}"),
            self.get_news(ticker, limit=10),
            self._make_request_list_cached(
                "/enterprise/v1/dilution-data", {"ticker": ticker}, f"dilutiondata:{upper}"
            ),
            self.get_gap_stats(ticker),
            self.get_offerings(ticker),
            self.get_ownership(ticker),
            self.get_chart_analysis(ticker),
            self.get_screener_price(ticker),
            return_exceptions=True,
        )

        # Replace any Exception results with safe defaults
        if isinstance(dilution_data, Exception):
            dilution_data = {}
        if isinstance(float_data, Exception):
            float_data = {}
        if isinstance(news_data, Exception):
            news_data = []
        if isinstance(dilution_raw, Exception):
            dilution_raw = []
        if isinstance(gap_stats_data, Exception):
            gap_stats_data = []
        if isinstance(offerings_data, Exception):
            offerings_data = []
        if isinstance(ownership_data, Exception):
            ownership_data = None
        if isinstance(chart_data, Exception):
            chart_data = None
        if isinstance(screener_price, Exception):
            screener_price = None

        # Ensure dict/list types after None-coercion
        if not isinstance(dilution_data, dict):
            dilution_data = {}
        if not isinstance(float_data, dict):
            float_data = {}
        if not isinstance(news_data, list):
            news_data = []
        if not isinstance(dilution_raw, list):
            dilution_raw = []
        if not isinstance(gap_stats_data, list):
            gap_stats_data = []
        if not isinstance(offerings_data, list):
            offerings_data = []

        # Fetch registrations (cached)
        try:
            registrations_data = await self._make_request_list_cached(
                "/enterprise/v1/registrations", {"ticker": ticker}, f"registrations:{upper}"
            )
        except Exception:
            registrations_data = []
        if not isinstance(registrations_data, list):
            registrations_data = []

        # Compute 4x price filter threshold
        max_price = (screener_price * 4) if isinstance(screener_price, (int, float)) else None

        # Extract warrants and convertibles from raw dilution-data with 4x filter
        now = datetime.utcnow()
        cutoff_180 = now - timedelta(days=180)

        warrants = []
        convertibles = []

        for item in dilution_raw:
            conversion_price = item.get("conversion_price")
            underlying_remaining = item.get("underlying_shares_remaining") or 0
            warrants_remaining = item.get("warrants_remaining") or 0
            registered = item.get("registered", "")
            filed_at_str = item.get("filed_at")
            is_not_registered = registered == "Not Registered"

            # Determine if filed within 180 days
            filed_within_180 = False
            if filed_at_str:
                try:
                    filed_dt = datetime.fromisoformat(filed_at_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    filed_within_180 = filed_dt >= cutoff_180
                except (ValueError, AttributeError):
                    pass

            # Convertibles: conversion_price present and underlying_shares_remaining > 0
            is_convertible = conversion_price is not None and underlying_remaining > 0
            if is_convertible:
                if max_price is None or conversion_price <= max_price:
                    convertibles.append(item)

            # Warrants: warrants_remaining > 0, not (not-registered AND filed within 180 days)
            if warrants_remaining > 0:
                exclude_from_warrants = is_not_registered and filed_within_180
                if not exclude_from_warrants:
                    exercise_price = item.get("warrants_exercise_price")
                    if max_price is None or exercise_price is None or exercise_price <= max_price:
                        warrants.append(item)

        # Build result dict
        result: Dict[str, Any] = {}

        result["ticker"] = upper

        # Dilution-rating fields
        result["offeringRisk"] = dilution_data.get("overall_offering_risk")
        result["offeringAbility"] = dilution_data.get("offering_ability")
        result["offeringAbilityDesc"] = dilution_data.get("offering_ability_desc")
        result["dilutionRisk"] = dilution_data.get("dilution")
        result["dilutionDesc"] = dilution_data.get("dilution_desc")
        result["offeringFrequency"] = dilution_data.get("offering_frequency")
        result["cashNeed"] = dilution_data.get("cash_need")
        result["cashNeedDesc"] = dilution_data.get("cash_need_desc")
        result["cashRunway"] = dilution_data.get("cash_remaining_months")
        result["cashBurn"] = dilution_data.get("cash_burn")
        result["estimatedCash"] = dilution_data.get("estimated_cash")
        result["warrantExercise"] = dilution_data.get("warrant_exercise")
        result["warrantExerciseDesc"] = dilution_data.get("warrant_exercise_desc")
        result["mgmtCommentary"] = dilution_data.get("mgmt_commentary")

        # Float-outstanding fields
        result["float"] = float_data.get("float")
        result["outstanding"] = float_data.get("outstanding")
        result["marketCap"] = float_data.get("market_cap_final")
        result["industry"] = float_data.get("industry")
        result["sector"] = float_data.get("sector")
        result["country"] = float_data.get("country")
        result["insiderOwnership"] = float_data.get("insider_percent")
        result["institutionalOwnership"] = float_data.get("institutions_percent")

        # List fields
        result["news"] = news_data
        result["registrations"] = registrations_data
        result["warrants"] = warrants
        result["convertibles"] = convertibles

        # New V2 fields
        result["gapStats"] = gap_stats_data
        result["offerings"] = offerings_data
        result["ownership"] = ownership_data
        result["chartAnalysis"] = chart_data
        result["stockPrice"] = screener_price

        return result

    async def close(self):
        """Close the HTTP client session."""
        await self.client.aclose()
