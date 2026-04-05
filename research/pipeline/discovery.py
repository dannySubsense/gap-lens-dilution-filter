"""
FilingDiscovery: Downloads EDGAR quarterly master.gz files, caches them to
disk, parses the pipe-delimited format, and yields DiscoveredFiling objects
filtered to in-scope form types and the requested date range.
"""

import gzip
import logging
import os
from datetime import date
from pathlib import Path

import requests

from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import DiscoveredFiling

logger = logging.getLogger(__name__)


class FilingDiscovery:
    MASTER_GZ_URL = (
        "https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.gz"
    )
    USER_AGENT = "gap-lens-dilution-filter contact@example.com"

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.cache_dir = config.cache_dir / "master_gz"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def discover(
        self,
        start_date: date,
        end_date: date,
    ) -> tuple[list[DiscoveredFiling], list[str]]:
        """
        Return (filings, quarters_failed).

        quarters_failed is a list of quarter strings where download failed,
        e.g. ["2021_QTR2"].
        """
        filings: list[DiscoveredFiling] = []
        quarters_failed: list[str] = []

        for year, quarter in self._enumerate_quarters(start_date, end_date):
            quarter_key = f"{year}_QTR{quarter}"
            gz_bytes = self._load_or_download(year, quarter, quarter_key, quarters_failed)
            if gz_bytes is None:
                continue

            batch = self._parse_gz(gz_bytes, start_date, end_date, quarter_key)
            filings.extend(batch)

        return filings, quarters_failed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _enumerate_quarters(start_date: date, end_date: date) -> list[tuple[int, int]]:
        """Return all (year, quarter) pairs that overlap [start_date, end_date]."""
        quarters = []
        year = start_date.year
        quarter = _date_to_quarter(start_date)

        while True:
            quarters.append((year, quarter))
            # First day of the *next* quarter
            if quarter == 4:
                year += 1
                quarter = 1
            else:
                quarter += 1
            # Stop once the first day of the new quarter is past end_date
            if _quarter_start_date(year, quarter) > end_date:
                break

        return quarters

    def _cache_path(self, year: int, quarter: int) -> Path:
        return self.cache_dir / f"{year}_QTR{quarter}.gz"

    def _load_or_download(
        self,
        year: int,
        quarter: int,
        quarter_key: str,
        quarters_failed: list[str],
    ) -> bytes | None:
        """Return raw .gz bytes from cache or HTTP. None on failure."""
        path = self._cache_path(year, quarter)

        if path.exists():
            logger.debug("Cache hit: %s", path)
            return path.read_bytes()

        # Cache miss — download
        url = self.MASTER_GZ_URL.format(year=year, quarter=quarter)
        logger.info("Downloading %s", url)
        try:
            response = requests.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=30,
            )
            response.raise_for_status()
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as exc:
            logger.warning("Download failed for %s: %s", quarter_key, exc)
            quarters_failed.append(quarter_key)
            return None

        gz_bytes = response.content

        # Persist to cache
        os.makedirs(self.cache_dir, exist_ok=True)
        path.write_bytes(gz_bytes)
        return gz_bytes

    def _parse_gz(
        self,
        gz_bytes: bytes,
        start_date: date,
        end_date: date,
        quarter_key: str,
    ) -> list[DiscoveredFiling]:
        """Decompress and parse a master.gz blob; return matching filings."""
        allowed = set(self.config.allowed_form_types)
        results: list[DiscoveredFiling] = []

        try:
            raw_text = gzip.decompress(gz_bytes).decode("latin-1")
        except Exception as exc:
            logger.warning("Failed to decompress %s: %s", quarter_key, exc)
            return results

        for line in raw_text.splitlines():
            filing = _parse_line(line, start_date, end_date, allowed, quarter_key)
            if filing is not None:
                results.append(filing)

        return results


# ------------------------------------------------------------------
# Module-level pure functions
# ------------------------------------------------------------------

def _parse_line(
    line: str,
    start_date: date,
    end_date: date,
    allowed_form_types: set[str],
    quarter_key: str,
) -> DiscoveredFiling | None:
    """
    Parse one pipe-delimited line from master.gz.

    Returns None for header/separator lines and for rows that do not
    match the form-type or date filters.

    Expected format:
        CIK|CompanyName|FormType|DateFiled|Filename
    """
    parts = line.strip().split("|")
    if len(parts) != 5:
        return None

    cik_raw, entity_name, form_type, date_filed_str, filename = parts

    # Skip header rows — non-data lines contain no digit-only CIK
    if not cik_raw.strip().isdigit():
        return None

    # Form-type filter
    if form_type.strip() not in allowed_form_types:
        return None

    # Date filter
    try:
        filed_date = date.fromisoformat(date_filed_str.strip())
    except ValueError:
        return None

    if filed_date < start_date or filed_date > end_date:
        return None

    accession_number = _derive_accession_number(filename.strip())
    if accession_number is None:
        return None

    return DiscoveredFiling(
        cik=cik_raw.strip().zfill(10),
        entity_name=entity_name.strip(),
        form_type=form_type.strip(),
        date_filed=filed_date,
        filename=filename.strip(),
        accession_number=accession_number,
        quarter_key=quarter_key,
    )


def _derive_accession_number(filename: str) -> str | None:
    """
    Derive the accession number from an EDGAR filename path.

    Example:
        edgar/data/1234567/0001234567-22-000123.txt
        → 0001234567-22-000123

    Returns None if the filename does not end in .txt.
    """
    if not filename.endswith(".txt"):
        return None
    basename = filename.rsplit("/", 1)[-1]
    return basename[:-4]  # strip ".txt"


def _date_to_quarter(d: date) -> int:
    """Return the quarter number (1-4) for a given date."""
    return (d.month - 1) // 3 + 1


def _quarter_start_date(year: int, quarter: int) -> date:
    """Return the first calendar day of the given (year, quarter)."""
    month = (quarter - 1) * 3 + 1
    return date(year, month, 1)
