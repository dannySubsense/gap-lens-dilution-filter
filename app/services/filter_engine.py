import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.db import get_db
from app.services.fmp_client import FMPMarketData

logger = logging.getLogger(__name__)

# Filter 1: allowed form types (13D/A added per spec G-02 fix)
ALLOWED_FORM_TYPES = frozenset({
    "S-1", "S-1/A", "S-3", "424B2", "424B4", "8-K", "13D/A"
})

# Filter 1: all 7 offering keywords (AC-02)
OFFERING_KEYWORDS = [
    "offering", "shares", "prospectus", "at-the-market",
    "sales agent", "underwritten", "priced",
]

# Thresholds (per spec)
MARKET_CAP_THRESHOLD = 2_000_000_000   # < $2B
FLOAT_THRESHOLD = 50_000_000           # < 50M shares
DILUTION_PCT_THRESHOLD = 0.10          # > 10%
PRICE_THRESHOLD = 1.00                 # > $1.00
ADV_THRESHOLD = 500_000               # > $500K

# Shares-offered extraction patterns (from Architecture Section 3.5.3)
SHARES_OFFERED_PATTERNS = [
    re.compile(r"(\d[\d,]*)\s+shares?\s+of\s+common\s+stock", re.IGNORECASE),
    re.compile(r"offering\s+of\s+(\d[\d,]*)\s+shares?", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+shares?\s+(?:at|for|priced)", re.IGNORECASE),
    re.compile(r"aggregate\s+of\s+(\d[\d,]*)\s+shares?", re.IGNORECASE),
    re.compile(r"up\s+to\s+(\d[\d,]*)\s+shares?", re.IGNORECASE),
]


@dataclass
class FilterOutcome:
    passed: bool
    fail_criterion: str | None


class FilterEngine:
    """Apply six filter criteria in order. Stop on first failure (I-04)."""

    async def evaluate(
        self,
        accession_number: str,
        form_type: str,
        filing_text: str,
        ticker: str | None,
        fmp_data: FMPMarketData | None,
        ask_edgar_dilution_pct: float | None = None,
    ) -> FilterOutcome:
        db = get_db()

        # Unresolvable ticker: mark filing and return immediately
        if ticker is None:
            await asyncio.to_thread(
                db.execute,
                "UPDATE filings SET filter_status = 'UNRESOLVABLE' WHERE accession_number = ?",
                [accession_number],
            )
            return FilterOutcome(passed=False, fail_criterion="UNRESOLVABLE")

        # --- Filter 1: Filing type + offering keywords ---
        form_ok = form_type in ALLOWED_FORM_TYPES
        text_lower = filing_text.lower()
        keyword_ok = any(kw in text_lower for kw in OFFERING_KEYWORDS)
        if not (form_ok and keyword_ok):
            await self._write_result(db, accession_number, "FILING_TYPE", False, None)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "FILING_TYPE")
            return FilterOutcome(passed=False, fail_criterion="FILING_TYPE")
        await self._write_result(db, accession_number, "FILING_TYPE", True, None)

        # Filters 2, 3, 5, 6 require FMP data
        if fmp_data is None:
            await self._write_result(db, accession_number, "MARKET_CAP", False, None)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "DATA_UNAVAILABLE")
            return FilterOutcome(passed=False, fail_criterion="DATA_UNAVAILABLE")

        # --- Filter 2: Market cap < $2B ---
        if fmp_data.market_cap >= MARKET_CAP_THRESHOLD:
            await self._write_result(db, accession_number, "MARKET_CAP", False, fmp_data.market_cap)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "MARKET_CAP")
            return FilterOutcome(passed=False, fail_criterion="MARKET_CAP")
        await self._write_result(db, accession_number, "MARKET_CAP", True, fmp_data.market_cap)

        # --- Filter 3: Float < 50M shares ---
        if fmp_data.float_shares >= FLOAT_THRESHOLD:
            await self._write_result(db, accession_number, "FLOAT", False, fmp_data.float_shares)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "FLOAT")
            return FilterOutcome(passed=False, fail_criterion="FLOAT")
        await self._write_result(db, accession_number, "FLOAT", True, fmp_data.float_shares)

        # --- Filter 4: Dilution % > 10% ---
        dilution_pct = ask_edgar_dilution_pct
        if dilution_pct is None:
            shares_offered = _extract_shares_offered(filing_text)
            if shares_offered is not None and fmp_data.float_shares > 0:
                dilution_pct = shares_offered / fmp_data.float_shares
        if dilution_pct is None or dilution_pct <= DILUTION_PCT_THRESHOLD:
            await self._write_result(db, accession_number, "DILUTION_PCT", False, dilution_pct)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "DILUTION_PCT")
            return FilterOutcome(passed=False, fail_criterion="DILUTION_PCT")
        await self._write_result(db, accession_number, "DILUTION_PCT", True, dilution_pct)

        # --- Filter 5: Price > $1.00 ---
        if fmp_data.price <= PRICE_THRESHOLD:
            await self._write_result(db, accession_number, "PRICE", False, fmp_data.price)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "PRICE")
            return FilterOutcome(passed=False, fail_criterion="PRICE")
        await self._write_result(db, accession_number, "PRICE", True, fmp_data.price)

        # --- Filter 6: ADV > $500K ---
        if fmp_data.adv_dollar <= ADV_THRESHOLD:
            await self._write_result(db, accession_number, "ADV", False, fmp_data.adv_dollar)
            await self._set_filter_status(db, accession_number, "FILTERED_OUT", "ADV")
            return FilterOutcome(passed=False, fail_criterion="ADV")
        await self._write_result(db, accession_number, "ADV", True, fmp_data.adv_dollar)

        # All filters passed
        await self._set_filter_status(db, accession_number, "PASSED", None)
        return FilterOutcome(passed=True, fail_criterion=None)

    @staticmethod
    async def _write_result(
        db, accession_number: str, criterion: str, passed: bool, value: float | None
    ) -> None:
        await asyncio.to_thread(
            db.execute,
            """INSERT INTO filter_results
               (accession_number, criterion, passed, value_observed, evaluated_at)
               VALUES (?, ?, ?, ?, ?)""",
            [accession_number, criterion, passed, value, datetime.now(timezone.utc)],
        )

    @staticmethod
    async def _set_filter_status(
        db, accession_number: str, status: str, reason: str | None
    ) -> None:
        await asyncio.to_thread(
            db.execute,
            """UPDATE filings
               SET filter_status = ?, filter_fail_reason = ?
               WHERE accession_number = ?""",
            [status, reason, accession_number],
        )


def _extract_shares_offered(filing_text: str) -> int | None:
    """
    Extract shares offered count from filing text using SHARES_OFFERED_PATTERNS.
    Shared utility used by both FilterEngine (Filter 4) and RuleBasedClassifier.
    Returns None if no pattern matches.
    """
    for pattern in SHARES_OFFERED_PATTERNS:
        m = pattern.search(filing_text)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return int(raw)
            except ValueError:
                continue
    return None
