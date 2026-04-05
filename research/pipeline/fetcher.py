"""
FilingTextFetcher — Slice 5.

Fetches filing HTML from SEC EDGAR Archives, strips HTML to plain text,
caches to disk, and returns FetchedFiling objects.

Rate limiting: TokenBucketRateLimiter(rate=10, capacity=10) singleton.
Concurrency: asyncio.Semaphore(value=8) per-fetcher instance.
"""

import asyncio
import copy
import logging
import os
import time
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup

from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import FetchedFiling, ResolvedFiling

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Token Bucket Rate Limiter
# ---------------------------------------------------------------------------

class TokenBucketRateLimiter:
    """
    Simple async token bucket rate limiter.

    Tokens refill at `rate` tokens/second up to `capacity`.
    Call `acquire()` before each HTTP request.
    """

    def __init__(self, rate: float, capacity: float) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._capacity,
                self._tokens + elapsed * self._rate,
            )
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# Module-level shared singleton — one rate limiter across all fetcher instances.
_GLOBAL_RATE_LIMITER: TokenBucketRateLimiter | None = None
_RATE_LIMITER_LOCK = asyncio.Lock()


async def _get_global_rate_limiter(rate: float, capacity: float) -> TokenBucketRateLimiter:
    global _GLOBAL_RATE_LIMITER
    if _GLOBAL_RATE_LIMITER is None:
        async with _RATE_LIMITER_LOCK:
            if _GLOBAL_RATE_LIMITER is None:
                _GLOBAL_RATE_LIMITER = TokenBucketRateLimiter(rate=rate, capacity=capacity)
    return _GLOBAL_RATE_LIMITER


# ---------------------------------------------------------------------------
# FilingTextFetcher
# ---------------------------------------------------------------------------

class FilingTextFetcher:
    """
    Fetches SEC filing HTML, strips to plain text, and caches to disk.

    Usage:
        fetcher = FilingTextFetcher(config)
        result: FetchedFiling = await fetcher.fetch(resolved_filing)
    """

    BASE_URL = "https://www.sec.gov/Archives/"
    USER_AGENT = "gap-lens-dilution-filter contact@example.com"
    MAX_RETRIES = 3
    RETRY_BACKOFFS = [1, 2, 4]  # seconds

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self.cache_dir = config.cache_dir / "filing_text"
        self._semaphore = asyncio.Semaphore(config.fetch_concurrency)
        self._rate_limiter: TokenBucketRateLimiter | None = None

    async def _get_rate_limiter(self) -> TokenBucketRateLimiter:
        if self._rate_limiter is None:
            self._rate_limiter = await _get_global_rate_limiter(
                rate=self.config.fetch_rate_limit_per_sec,
                capacity=self.config.fetch_rate_limit_per_sec,
            )
        return self._rate_limiter

    def _cache_path(self, accession_number: str) -> Path:
        return self.cache_dir / f"{accession_number}.txt"

    def _make_fetched(self, resolved: ResolvedFiling, **kwargs) -> FetchedFiling:
        """Build a FetchedFiling from a ResolvedFiling, applying keyword overrides."""
        base = copy.copy(resolved)
        return FetchedFiling(
            cik=base.cik,
            entity_name=base.entity_name,
            form_type=base.form_type,
            date_filed=base.date_filed,
            filename=base.filename,
            accession_number=base.accession_number,
            quarter_key=base.quarter_key,
            ticker=base.ticker,
            resolution_status=base.resolution_status,
            permanent_id=base.permanent_id,
            plain_text=kwargs.get("plain_text", None),
            fetch_status=kwargs.get("fetch_status", "FETCH_FAILED"),
            fetch_error=kwargs.get("fetch_error", None),
        )

    def _strip_html(self, html_bytes: bytes) -> str:
        """Strip HTML to plain text using BeautifulSoup with lxml parser."""
        try:
            soup = BeautifulSoup(html_bytes, "lxml")
        except Exception:
            soup = BeautifulSoup(html_bytes, "html.parser")
        return soup.get_text(separator=" ")

    def _is_binary_content(self, content_type: str, body_start: bytes) -> bool:
        """Return True if the response appears to be XBRL/binary (not HTML/text)."""
        ct_lower = content_type.lower()
        if "application/xml" in ct_lower or "xbrl" in ct_lower:
            return True
        if body_start.lstrip()[:5] == b"<?xml":
            return True
        return False

    async def fetch(self, filing: ResolvedFiling) -> FetchedFiling:
        """
        Fetch and cache the plain-text content of one SEC filing.

        Steps:
        1. Skip if resolution_status != "RESOLVED".
        2. Check disk cache; return cached text if present.
        3. Fetch via HTTP with retry on 429/503.
        4. Strip HTML, truncate, cache atomically.
        5. Return FetchedFiling with appropriate status.
        """
        # Step 1: Skip unresolved filings.
        if filing.resolution_status != "RESOLVED":
            return self._make_fetched(
                filing,
                fetch_status="FETCH_FAILED",
                fetch_error=f"SKIP_UNRESOLVED:{filing.resolution_status}",
            )

        # Step 2: Cache hit.
        cache_path = self._cache_path(filing.accession_number)
        if cache_path.exists():
            try:
                cached_text = cache_path.read_text(encoding="utf-8", errors="replace")
                logger.debug("Cache hit: %s", filing.accession_number)
                return self._make_fetched(
                    filing,
                    plain_text=cached_text,
                    fetch_status="OK",
                )
            except OSError as exc:
                logger.warning(
                    "Cache read failed for %s: %s — refetching",
                    filing.accession_number,
                    exc,
                )

        # Step 3: HTTP fetch with rate limiting and concurrency control.
        url = self.BASE_URL + filing.filename
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "text/html, text/plain",
        }
        timeout = aiohttp.ClientTimeout(total=self.config.fetch_timeout_sec)

        rate_limiter = await self._get_rate_limiter()

        async with self._semaphore:
            response_bytes: bytes | None = None
            response_content_type: str = ""
            last_status: int = 0

            for attempt in range(self.MAX_RETRIES):
                await rate_limiter.acquire()
                try:
                    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                        async with session.get(url) as resp:
                            last_status = resp.status
                            response_content_type = resp.headers.get("Content-Type", "")

                            if resp.status == 200:
                                response_bytes = await resp.read()
                                break

                            if resp.status == 404:
                                return self._make_fetched(
                                    filing,
                                    fetch_status="FETCH_FAILED",
                                    fetch_error="HTTP_404",
                                )

                            if resp.status in (429, 503):
                                if attempt < self.MAX_RETRIES - 1:
                                    backoff = self.RETRY_BACKOFFS[attempt]
                                    logger.warning(
                                        "HTTP %d for %s — retry %d/%d in %ds",
                                        resp.status,
                                        filing.accession_number,
                                        attempt + 1,
                                        self.MAX_RETRIES,
                                        backoff,
                                    )
                                    await asyncio.sleep(backoff)
                                    continue
                                # All retries exhausted.
                                return self._make_fetched(
                                    filing,
                                    fetch_status="FETCH_FAILED",
                                    fetch_error=f"HTTP_{resp.status}_AFTER_RETRIES",
                                )

                            # Other HTTP error (e.g. 500).
                            if attempt < self.MAX_RETRIES - 1:
                                backoff = self.RETRY_BACKOFFS[attempt]
                                await asyncio.sleep(backoff)
                                continue
                            return self._make_fetched(
                                filing,
                                fetch_status="FETCH_FAILED",
                                fetch_error=f"HTTP_{resp.status}",
                            )

                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    if attempt < self.MAX_RETRIES - 1:
                        backoff = self.RETRY_BACKOFFS[attempt]
                        logger.warning(
                            "Network error for %s (attempt %d): %s — retrying in %ds",
                            filing.accession_number,
                            attempt + 1,
                            exc,
                            backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    return self._make_fetched(
                        filing,
                        fetch_status="FETCH_FAILED",
                        fetch_error=f"NETWORK_ERROR:{exc}",
                    )

            if response_bytes is None:
                return self._make_fetched(
                    filing,
                    fetch_status="FETCH_FAILED",
                    fetch_error=f"HTTP_{last_status}_AFTER_RETRIES",
                )

        # Step 4a: Binary/XBRL content check.
        body_start = response_bytes[:100]
        if self._is_binary_content(response_content_type, body_start):
            return self._make_fetched(
                filing,
                fetch_status="FETCH_FAILED",
                fetch_error="BINARY_CONTENT",
            )

        # Step 4b: Strip HTML.
        plain_text = self._strip_html(response_bytes)

        # Step 4c: Empty text check.
        if not plain_text.strip():
            return self._make_fetched(
                filing,
                fetch_status="EMPTY_TEXT",
            )

        # Step 4d: Truncate at max bytes.
        max_bytes = self.config.filing_text_max_bytes
        if len(plain_text.encode("utf-8")) > max_bytes:
            plain_text = plain_text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")

        # Step 4e: Atomic cache write.
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = cache_path.with_suffix(".txt.tmp")
        try:
            tmp_path.write_text(plain_text, encoding="utf-8")
            os.rename(tmp_path, cache_path)
        except OSError as exc:
            logger.warning(
                "Cache write failed for %s: %s",
                filing.accession_number,
                exc,
            )
            # Non-fatal: return result without caching.

        return self._make_fetched(
            filing,
            plain_text=plain_text,
            fetch_status="OK",
        )
