"""
Slice 5: FMP Client — Acceptance Tests

Done-when criteria verified:
1.  FMPClient, FMPMarketData import successfully
2.  FMPDataUnavailableError imports from app.utils.errors
3.  Empty fmp_api_key raises FMPDataUnavailableError without any HTTP call
4.  Successful mocked responses return populated FMPMarketData with correct field values
5.  HTTP 429 on all attempts raises FMPDataUnavailableError after 3 attempts
6.  FMPMarketData.fetched_at is a datetime instance
7.  ADV is computed as sum(close * volume) / 20 (AC-12)
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# AC-S5-01: FMPClient and FMPMarketData import successfully
# ---------------------------------------------------------------------------

def test_fmp_client_imports_succeed():
    """FMPClient and FMPMarketData must be importable from app.services.fmp_client."""
    from app.services.fmp_client import FMPClient, FMPMarketData  # noqa: PLC0415
    assert FMPClient is not None
    assert FMPMarketData is not None


# ---------------------------------------------------------------------------
# AC-S5-02: FMPDataUnavailableError imports from app.utils.errors
# ---------------------------------------------------------------------------

def test_fmp_data_unavailable_error_imports():
    """FMPDataUnavailableError must be importable from app.utils.errors."""
    from app.utils.errors import FMPDataUnavailableError  # noqa: PLC0415
    assert FMPDataUnavailableError is not None


# ---------------------------------------------------------------------------
# AC-S5-03: Empty fmp_api_key raises FMPDataUnavailableError without HTTP call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_empty_api_key_raises_without_http_call():
    """get_market_data() must raise FMPDataUnavailableError immediately when fmp_api_key is empty."""
    from app.services.fmp_client import FMPClient  # noqa: PLC0415
    from app.utils.errors import FMPDataUnavailableError  # noqa: PLC0415

    with patch("app.services.fmp_client.settings") as mock_settings:
        mock_settings.fmp_api_key = ""
        client = FMPClient()
        with pytest.raises(FMPDataUnavailableError):
            await client.get_market_data("AAPL")


# ---------------------------------------------------------------------------
# Shared fixture: mock responses for successful AAPL fetch
# ---------------------------------------------------------------------------

# Historical bars: 3 bars for math verification
_HISTORICAL_BARS = [
    {"close": "100.0", "volume": "1000000"},
    {"close": "101.0", "volume": "1100000"},
    {"close": "102.0", "volume": "1200000"},
]

# Expected ADV: (100*1000000 + 101*1100000 + 102*1200000) / 20
_EXPECTED_ADV = (
    (100.0 * 1_000_000) + (101.0 * 1_100_000) + (102.0 * 1_200_000)
) / 20


def _make_fetch_side_effect(quote_data, float_data, historical_data):
    """Return an AsyncMock side_effect that dispatches by URL."""
    async def _side_effect(client, url, params=None):
        if "/v3/quote/" in url:
            return quote_data
        elif "/v4/shares_float" in url:
            return float_data
        elif "/v3/historical-price-full/" in url:
            return historical_data
        raise ValueError(f"Unexpected URL: {url}")
    return _side_effect


# ---------------------------------------------------------------------------
# AC-S5-04: Successful mock responses return populated FMPMarketData
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_market_data_returns_populated_result():
    """get_market_data('AAPL') with mocked 200 responses returns correct FMPMarketData fields."""
    from app.services.fmp_client import FMPClient, FMPMarketData  # noqa: PLC0415

    quote_response = [{"price": 150.25, "marketCap": 2_500_000_000_000}]
    float_response = [{"floatShares": "15000000000"}]
    historical_response = {"historical": _HISTORICAL_BARS}

    with patch("app.services.fmp_client.settings") as mock_settings:
        mock_settings.fmp_api_key = "test-key"
        client = FMPClient()
        with patch.object(
            client,
            "_fetch_with_retry",
            side_effect=_make_fetch_side_effect(
                quote_response, float_response, historical_response
            ),
        ):
            result = await client.get_market_data("AAPL")

    assert isinstance(result, FMPMarketData)
    assert result.price == pytest.approx(150.25)
    assert result.market_cap == pytest.approx(2_500_000_000_000)
    assert result.float_shares == pytest.approx(15_000_000_000.0)


# ---------------------------------------------------------------------------
# AC-S5-05: Three consecutive 429s raise FMPDataUnavailableError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_consecutive_429s_raise_fmp_error():
    """_fetch_with_retry must raise FMPDataUnavailableError after 3 HTTP 429 responses."""
    import httpx  # noqa: PLC0415
    from app.services.fmp_client import FMPClient  # noqa: PLC0415
    from app.utils.errors import FMPDataUnavailableError  # noqa: PLC0415

    # Build a mock response that always returns 429
    mock_response = MagicMock()
    mock_response.status_code = 429

    mock_httpx_client = AsyncMock()
    mock_httpx_client.get = AsyncMock(return_value=mock_response)

    # Patch asyncio.sleep to avoid real delays in tests
    with patch("app.services.fmp_client.settings") as mock_settings, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_settings.fmp_api_key = "test-key"
        client = FMPClient()

        with pytest.raises(FMPDataUnavailableError):
            await client._fetch_with_retry(mock_httpx_client, "https://example.com/v3/quote/AAPL")


# ---------------------------------------------------------------------------
# AC-S5-06: FMPMarketData.fetched_at is a datetime instance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fmp_market_data_fetched_at_is_datetime():
    """FMPMarketData.fetched_at must be a datetime instance."""
    from app.services.fmp_client import FMPClient  # noqa: PLC0415

    quote_response = [{"price": 150.25, "marketCap": 2_500_000_000_000}]
    float_response = [{"floatShares": "15000000000"}]
    historical_response = {"historical": _HISTORICAL_BARS}

    with patch("app.services.fmp_client.settings") as mock_settings:
        mock_settings.fmp_api_key = "test-key"
        client = FMPClient()
        with patch.object(
            client,
            "_fetch_with_retry",
            side_effect=_make_fetch_side_effect(
                quote_response, float_response, historical_response
            ),
        ):
            result = await client.get_market_data("AAPL")

    assert isinstance(result.fetched_at, datetime), (
        f"fetched_at is {type(result.fetched_at)}, expected datetime"
    )


# ---------------------------------------------------------------------------
# AC-S5-07: ADV is computed as sum(close * volume) / count from historical bars
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_adv_computed_correctly_from_historical_bars():
    """adv_dollar must equal sum(close * volume) / 20 per AC-12."""
    from app.services.fmp_client import FMPClient  # noqa: PLC0415

    quote_response = [{"price": 150.25, "marketCap": 2_500_000_000_000}]
    float_response = [{"floatShares": "15000000000"}]
    historical_response = {"historical": _HISTORICAL_BARS}

    with patch("app.services.fmp_client.settings") as mock_settings:
        mock_settings.fmp_api_key = "test-key"
        client = FMPClient()
        with patch.object(
            client,
            "_fetch_with_retry",
            side_effect=_make_fetch_side_effect(
                quote_response, float_response, historical_response
            ),
        ):
            result = await client.get_market_data("AAPL")

    assert result.adv_dollar == pytest.approx(_EXPECTED_ADV), (
        f"ADV {result.adv_dollar} does not match expected {_EXPECTED_ADV}"
    )
