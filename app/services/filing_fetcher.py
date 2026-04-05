import logging
from html.parser import HTMLParser

import httpx

from app.core.config import settings
from app.utils.errors import FilingFetchError

logger = logging.getLogger(__name__)

_BACKOFF = (1.0, 2.0, 4.0)


class _TextExtractor(HTMLParser):
    """Strip HTML tags and collect plain text."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._parts)


class FilingFetcher:
    """Fetch an EDGAR filing document and return stripped plain text."""

    async def fetch(self, filing_url: str) -> str:
        """
        Fetch filing_url, strip HTML, truncate to settings.filing_text_max_bytes.

        Raises FilingFetchError after 3 consecutive network failures.
        """
        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt, backoff in enumerate(_BACKOFF, start=1):
                try:
                    resp = await client.get(
                        filing_url,
                        headers={
                            "User-Agent": "gap-lens-dilution-filter contact@yourdomain.com"
                        },
                        follow_redirects=True,
                    )
                    resp.raise_for_status()
                    raw = resp.text
                    text = self._strip_html(raw)
                    # Truncate to max bytes (encode + decode to respect char boundaries)
                    encoded = text.encode("utf-8")[: settings.filing_text_max_bytes]
                    return encoded.decode("utf-8", errors="ignore")
                except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                    logger.warning(
                        "FilingFetcher attempt %d failed for %s: %s",
                        attempt,
                        filing_url,
                        exc,
                    )
                    last_exc = exc
                    if attempt < len(_BACKOFF):
                        import asyncio
                        await asyncio.sleep(backoff)
        raise FilingFetchError(
            f"Failed to fetch {filing_url} after {len(_BACKOFF)} attempts"
        ) from last_exc

    @staticmethod
    def _strip_html(html: str) -> str:
        parser = _TextExtractor()
        parser.feed(html)
        return parser.text
