"""
Slice 6: FilingFetcher & TickerResolver — Acceptance Tests

Done-when criteria verified:
1.  FilingFetcher, TickerResolver import successfully
2.  FilingFetchError imports from app.utils.errors
3.  FilingFetcher._strip_html('<p>Hello <b>world</b></p>') returns text containing
    "Hello" and "world" (no tags)
4.  FilingFetcher._strip_html on empty string returns empty string
5.  Mock fetch: fetch(url) with a mocked 200 HTML response returns stripped plain text
6.  Truncation: response larger than settings.filing_text_max_bytes is truncated
7.  Three consecutive network errors raise FilingFetchError
8.  TickerResolver.resolve("320193", None, None) with "AAPL" in map returns "AAPL"
9.  TickerResolver.resolve("9999999", "XYZ", None) returns "XYZ" (EFTS ticker fallback)
10. TickerResolver.resolve("9999999", None, None) returns None (UNRESOLVABLE)
11. TickerResolver.resolve("0", None, None) returns None (zero CIK, not in map)
12. TickerResolver.refresh() calls get_db(), not init_db() — invariant I-12
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import duckdb
import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.db import _create_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture: in-memory DuckDB with cik_ticker_map populated
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    """In-memory DuckDB with schema and a single AAPL row in cik_ticker_map."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    conn.execute(
        "INSERT INTO cik_ticker_map VALUES (320193, 'AAPL', 'Apple Inc', 'Nasdaq')"
    )
    with patch("app.services.db._conn", new=conn):
        yield conn
    conn.close()


# ---------------------------------------------------------------------------
# AC-S6-01: FilingFetcher and TickerResolver import successfully
# ---------------------------------------------------------------------------

def test_filing_fetcher_imports():
    """FilingFetcher must be importable from app.services.filing_fetcher."""
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415
    assert FilingFetcher is not None


def test_ticker_resolver_imports():
    """TickerResolver must be importable from app.utils.ticker_resolver."""
    from app.utils.ticker_resolver import TickerResolver  # noqa: PLC0415
    assert TickerResolver is not None


# ---------------------------------------------------------------------------
# AC-S6-02: FilingFetchError imports from app.utils.errors
# ---------------------------------------------------------------------------

def test_filing_fetch_error_imports():
    """FilingFetchError must be importable from app.utils.errors."""
    from app.utils.errors import FilingFetchError  # noqa: PLC0415
    assert FilingFetchError is not None


# ---------------------------------------------------------------------------
# AC-S6-03: _strip_html removes tags and preserves text content
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags_and_preserves_text():
    """_strip_html('<p>Hello <b>world</b></p>') must return text containing 'Hello' and 'world'."""
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415
    result = FilingFetcher._strip_html("<p>Hello <b>world</b></p>")
    assert "Hello" in result, f"'Hello' not found in stripped text: {result!r}"
    assert "world" in result, f"'world' not found in stripped text: {result!r}"
    assert "<" not in result, f"HTML tag found in stripped text: {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-04: _strip_html on empty string returns empty string
# ---------------------------------------------------------------------------

def test_strip_html_empty_string_returns_empty():
    """_strip_html('') must return an empty string."""
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415
    result = FilingFetcher._strip_html("")
    assert result == "", f"Expected empty string, got {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-05: fetch() with mocked 200 HTML response returns stripped plain text
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_mocked_200_returns_stripped_text():
    """FilingFetcher.fetch() with a mocked 200 response must return stripped plain text."""
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415

    html_content = "<html><body><p>This is the <b>filing</b> text.</p></body></html>"
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        fetcher = FilingFetcher()
        result = await fetcher.fetch("https://www.sec.gov/Archives/test.htm")

    assert "filing" in result, f"'filing' not found in result: {result!r}"
    assert "<" not in result, f"HTML tags found in result: {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-06: Response larger than filing_text_max_bytes is truncated
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_truncates_to_max_bytes():
    """FilingFetcher.fetch() must truncate output to settings.filing_text_max_bytes."""
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415

    # Generate HTML that expands to much more than 10 bytes when stripped
    large_text = "A" * 1000
    html_content = f"<p>{large_text}</p>"
    max_bytes = 10

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = html_content
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("app.services.filing_fetcher.settings") as mock_settings:
        mock_settings.filing_text_max_bytes = max_bytes
        fetcher = FilingFetcher()
        result = await fetcher.fetch("https://www.sec.gov/Archives/test.htm")

    assert len(result.encode("utf-8")) <= max_bytes, (
        f"Result length {len(result.encode('utf-8'))} bytes exceeds max {max_bytes}"
    )


# ---------------------------------------------------------------------------
# AC-S6-07: Three consecutive network errors raise FilingFetchError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_three_network_errors_raise_filing_fetch_error():
    """FilingFetcher.fetch() must raise FilingFetchError after 3 consecutive network failures."""
    import httpx  # noqa: PLC0415
    from app.services.filing_fetcher import FilingFetcher  # noqa: PLC0415
    from app.utils.errors import FilingFetchError  # noqa: PLC0415

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.RequestError("connection refused", request=MagicMock())
    )
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        fetcher = FilingFetcher()
        with pytest.raises(FilingFetchError):
            await fetcher.fetch("https://www.sec.gov/Archives/test.htm")


# ---------------------------------------------------------------------------
# AC-S6-08: resolve("320193", None, None) with AAPL in map returns "AAPL"
# ---------------------------------------------------------------------------

def test_resolver_cik_lookup_returns_ticker(mem_db):
    """TickerResolver.resolve('320193', None, None) must return 'AAPL' from cik_ticker_map."""
    from app.utils.ticker_resolver import TickerResolver  # noqa: PLC0415
    result = TickerResolver.resolve("320193", None, None)
    assert result == "AAPL", f"Expected 'AAPL', got {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-09: resolve("9999999", "XYZ", None) returns "XYZ" (EFTS ticker fallback)
# ---------------------------------------------------------------------------

def test_resolver_efts_ticker_fallback(mem_db):
    """TickerResolver.resolve('9999999', 'XYZ', None) must return 'XYZ' via EFTS fallback."""
    from app.utils.ticker_resolver import TickerResolver  # noqa: PLC0415
    result = TickerResolver.resolve("9999999", "XYZ", None)
    assert result == "XYZ", f"Expected 'XYZ', got {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-10: resolve("9999999", None, None) returns None (UNRESOLVABLE)
# ---------------------------------------------------------------------------

def test_resolver_unknown_cik_no_efts_returns_none(mem_db):
    """TickerResolver.resolve('9999999', None, None) must return None (UNRESOLVABLE)."""
    from app.utils.ticker_resolver import TickerResolver  # noqa: PLC0415
    result = TickerResolver.resolve("9999999", None, None)
    assert result is None, f"Expected None, got {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-11: resolve("0", None, None) returns None (zero CIK, not in map)
# ---------------------------------------------------------------------------

def test_resolver_zero_cik_returns_none(mem_db):
    """TickerResolver.resolve('0', None, None) must return None (CIK 0 not in map)."""
    from app.utils.ticker_resolver import TickerResolver  # noqa: PLC0415
    result = TickerResolver.resolve("0", None, None)
    assert result is None, f"Expected None for zero CIK, got {result!r}"


# ---------------------------------------------------------------------------
# AC-S6-12: TickerResolver.refresh() calls get_db(), not init_db() — invariant I-12
# ---------------------------------------------------------------------------

def test_ticker_resolver_refresh_calls_get_db_not_init_db():
    """Invariant I-12: refresh() must use get_db(), not init_db()."""
    import ast
    import pathlib

    src = pathlib.Path("app/utils/ticker_resolver.py").read_text()
    tree = ast.parse(src)
    imported_names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.append(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.append(alias.name)
    assert "init_db" not in imported_names, (
        "ticker_resolver.py must not import init_db — use get_db() only (Invariant I-12)"
    )
    assert "get_db" in imported_names, (
        "ticker_resolver.py must import get_db"
    )
