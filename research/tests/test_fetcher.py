"""
Tests for Slice 5: FilingTextFetcher.

All HTTP calls are mocked — no live SEC network calls are made.

Tests:
1. Cache hit: existing cache file is returned without HTTP.
2. Successful fetch: HTTP 200 with HTML → fetch_status="OK", HTML tags stripped.
3. HTTP 404 → fetch_status="FETCH_FAILED", fetch_error contains "404".
4. HTTP 429 retry: first call 429, second call 200 → fetch_status="OK".
5. Text truncation: 700 000-byte response → plain_text ≤ 512 000 bytes.
6. Empty HTML → fetch_status="EMPTY_TEXT".
7. Three consecutive HTTP 503 failures → fetch_status="FETCH_FAILED".
"""

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import FetchedFiling, ResolvedFiling
from research.pipeline.fetcher import FilingTextFetcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_resolved(
    accession_number: str = "0001234567-22-000123",
    resolution_status: str = "RESOLVED",
    filename: str = "edgar/data/1234567/0001234567-22-000123.txt",
) -> ResolvedFiling:
    return ResolvedFiling(
        cik="0001234567",
        entity_name="Acme Corp",
        form_type="424B4",
        date_filed=date(2022, 3, 15),
        filename=filename,
        accession_number=accession_number,
        quarter_key="2022_QTR1",
        ticker="ACME",
        resolution_status=resolution_status,
        permanent_id="PERM-001",
    )


def make_config(tmp_path: Path) -> BacktestConfig:
    cfg = BacktestConfig()
    cfg.cache_dir = tmp_path / "cache"
    cfg.filing_text_max_bytes = 512_000
    cfg.fetch_concurrency = 8
    cfg.fetch_rate_limit_per_sec = 10
    cfg.fetch_timeout_sec = 30
    return cfg


# ---------------------------------------------------------------------------
# Helper: build a minimal mock aiohttp response
# ---------------------------------------------------------------------------

def _mock_response(status: int, body: bytes = b"", content_type: str = "text/html") -> MagicMock:
    """Return a context-manager-compatible mock response."""
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Content-Type": content_type}
    resp.read = AsyncMock(return_value=body)

    # Support `async with session.get(url) as resp:`
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(get_response: MagicMock) -> MagicMock:
    """Return a context-manager-compatible mock aiohttp.ClientSession."""
    session = MagicMock()
    session.get = MagicMock(return_value=get_response)

    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


# ---------------------------------------------------------------------------
# Test 1: Cache hit — no HTTP call made
# ---------------------------------------------------------------------------

class TestCacheHit:
    def test_cache_hit_returns_ok_without_http(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        # Pre-populate the cache.
        cache_dir = cfg.cache_dir / "filing_text"
        cache_dir.mkdir(parents=True)
        cache_file = cache_dir / f"{filing.accession_number}.txt"
        cache_file.write_text("Cached plain text content.", encoding="utf-8")

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession") as mock_cls:
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        # HTTP should not have been called.
        mock_cls.assert_not_called()
        assert result.fetch_status == "OK"
        assert result.plain_text == "Cached plain text content."
        assert result.accession_number == filing.accession_number


# ---------------------------------------------------------------------------
# Test 2: Successful fetch — HTML is stripped, status OK
# ---------------------------------------------------------------------------

class TestSuccessfulFetch:
    def test_fetch_200_strips_html(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        html_body = b"<html><body><p>Hello world</p></body></html>"
        mock_resp = _mock_response(200, html_body, "text/html")
        mock_sess = _mock_session(mock_resp)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=mock_sess):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "OK"
        assert result.plain_text is not None
        assert "Hello world" in result.plain_text
        # Confirm HTML tags are absent.
        assert "<p>" not in result.plain_text
        assert "<html>" not in result.plain_text


# ---------------------------------------------------------------------------
# Test 3: HTTP 404 → FETCH_FAILED with "404" in fetch_error
# ---------------------------------------------------------------------------

class TestHttp404:
    def test_404_returns_fetch_failed(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        mock_resp = _mock_response(404, b"Not found", "text/html")
        mock_sess = _mock_session(mock_resp)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=mock_sess):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "FETCH_FAILED"
        assert result.fetch_error is not None
        assert "404" in result.fetch_error


# ---------------------------------------------------------------------------
# Test 4: HTTP 429 triggers retry — first 429, second 200 → OK
# ---------------------------------------------------------------------------

class TestHttp429Retry:
    def test_429_retries_and_succeeds(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        html_body = b"<html><body><p>Retry success</p></body></html>"

        resp_429 = _mock_response(429, b"Rate limited", "text/html")
        resp_200 = _mock_response(200, html_body, "text/html")

        # First call returns 429, second call returns 200.
        call_count = {"n": 0}

        def _get_side_effect(url, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return resp_429
            return resp_200

        session = MagicMock()
        session.get = MagicMock(side_effect=_get_side_effect)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=session), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "OK"
        assert result.plain_text is not None
        assert "Retry success" in result.plain_text


# ---------------------------------------------------------------------------
# Test 5: Text truncation at max_bytes
# ---------------------------------------------------------------------------

class TestTextTruncation:
    def test_large_text_is_truncated(self, tmp_path):
        cfg = make_config(tmp_path)
        cfg.filing_text_max_bytes = 512_000
        filing = make_resolved()

        # Build ~700 000 bytes of HTML text (ASCII chars, 1 byte each).
        long_content = "A" * 700_000
        html_body = f"<html><body><p>{long_content}</p></body></html>".encode("utf-8")

        mock_resp = _mock_response(200, html_body, "text/html")
        mock_sess = _mock_session(mock_resp)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=mock_sess):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "OK"
        assert result.plain_text is not None
        assert len(result.plain_text.encode("utf-8")) <= 512_000


# ---------------------------------------------------------------------------
# Test 6: Empty HTML → EMPTY_TEXT
# ---------------------------------------------------------------------------

class TestEmptyHtml:
    def test_whitespace_only_html_returns_empty_text(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        # HTML with no visible text content.
        html_body = b"<html><body>   \n\t  </body></html>"
        mock_resp = _mock_response(200, html_body, "text/html")
        mock_sess = _mock_session(mock_resp)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=mock_sess):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "EMPTY_TEXT"
        assert result.plain_text is None


# ---------------------------------------------------------------------------
# Test 7: Three consecutive HTTP 503 → FETCH_FAILED after all retries
# ---------------------------------------------------------------------------

class TestHttp503AllRetriesFail:
    def test_503_all_retries_exhausted(self, tmp_path):
        cfg = make_config(tmp_path)
        filing = make_resolved()

        resp_503 = _mock_response(503, b"Service Unavailable", "text/html")

        session = MagicMock()
        session.get = MagicMock(return_value=resp_503)
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)

        fetcher = FilingTextFetcher(cfg)

        with patch("aiohttp.ClientSession", return_value=session), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result: FetchedFiling = asyncio.run(fetcher.fetch(filing))

        assert result.fetch_status == "FETCH_FAILED"
        assert result.fetch_error is not None
        # Confirm we tried at least 3 times (1 per session context).
        assert session.get.call_count == FilingTextFetcher.MAX_RETRIES
