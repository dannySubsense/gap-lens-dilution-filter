"""
Shared dataclasses for the backtest pipeline.

This module is the single source of truth for all inter-component data
contracts. All pipeline stages import their input/output types from here.

Canonical filter_status values:
    PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL,
    PRICE_FAIL, ADV_FAIL,
    NOT_IN_UNIVERSE, PIPELINE_ERROR, UNRESOLVABLE, FETCH_FAILED
"""

from dataclasses import dataclass, field
from datetime import date, datetime


# ---------------------------------------------------------------------------
# Stage 1: Discovery
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredFiling:
    """Filing from master.gz before CIK resolution."""

    cik: str                # Zero-padded to 10 digits as stored in master.gz
    entity_name: str
    form_type: str          # S-1, 424B4, 8-K, etc.
    date_filed: date        # From master.gz DateFiled column
    filename: str           # Relative path segment from master.gz
    accession_number: str   # Derived from filename: last 20 chars, dashes normalized
    quarter_key: str        # "2021_QTR2" — source quarter for resume tracking


# ---------------------------------------------------------------------------
# Stage 2: CIK Resolution
# ---------------------------------------------------------------------------

@dataclass
class ResolvedFiling(DiscoveredFiling):
    """Filing after CIK → ticker resolution."""

    ticker: str | None = None          # None means UNRESOLVABLE
    resolution_status: str = ""        # "RESOLVED", "UNRESOLVABLE", "AMBIGUOUS_SKIPPED"
    permanent_id: str | None = None    # From symbol_history if resolution succeeded


# ---------------------------------------------------------------------------
# Stage 3: Text Fetch
# ---------------------------------------------------------------------------

@dataclass
class FetchedFiling(ResolvedFiling):
    """Filing after HTML fetch and text extraction."""

    plain_text: str | None = None      # Stripped, truncated at filing_text_max_bytes
    fetch_status: str = ""             # "OK", "FETCH_FAILED", "EMPTY_TEXT" — binary content returns FETCH_FAILED with fetch_error="BINARY_CONTENT"
    fetch_error: str | None = None     # Error detail if fetch_status != "OK"


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

@dataclass
class MarketSnapshot:
    """Point-in-time market data for one filing."""

    symbol: str
    effective_trade_date: date          # Prior-trading-day-adjusted date for all T joins
    price_at_T: float | None
    market_cap_at_T: float | None
    float_at_T: float | None            # None if float unavailable (pre-2020 or no row found)
    float_available: bool
    float_effective_date: date | None   # Actual date of the AS-OF float row used
    short_interest_at_T: float | None
    short_interest_effective_date: date | None
    borrow_cost_source: str             # "SHORT_INTEREST", "DEFAULT"
    adv_at_T: float | None             # 20-day dollar volume ADV
    in_smallcap_universe: bool | None
    # Key: N (1, 3, 5, 20), Value: adjusted_close or None
    forward_prices: dict[int, float | None] = field(default_factory=dict)
    # Key: N (1, 3, 5, 20), Value: bool
    delisted_before: dict[int, bool] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Underwriter Participants
# ---------------------------------------------------------------------------

@dataclass
class ParticipantRecord:
    """One named financial intermediary per filing."""

    accession_number: str
    firm_name: str              # Canonical name after normalization
    role: str                   # "lead_underwriter", "co_manager", "sales_agent", "placement_agent"
    is_normalized: bool
    raw_text_snippet: str | None = None   # Up to 300 chars


# ---------------------------------------------------------------------------
# Final Output Row
# ---------------------------------------------------------------------------

@dataclass
class BacktestRow:
    """
    One row of the final output dataset.

    Assembles all stages before writing to Parquet/CSV.
    """

    accession_number: str
    cik: str
    ticker: str | None
    entity_name: str | None
    form_type: str
    filed_at: datetime           # UTC; time component set to 00:00:00 if only date known
    setup_type: str | None       # None (not string "NULL") for no-match
    confidence: float | None
    shares_offered_raw: int | None
    dilution_severity: float | None
    price_discount: float | None
    immediate_pressure: bool | None
    key_excerpt: str | None
    filter_status: str           # one of 9 canonical values
    filter_fail_reason: str | None
    float_available: bool
    in_smallcap_universe: bool | None
    price_at_T: float | None
    market_cap_at_T: float | None
    float_at_T: float | None
    adv_at_T: float | None
    short_interest_at_T: float | None
    borrow_cost_source: str | None   # "DEFAULT" or "SHORT_INTEREST"
    score: int | None
    rank: str | None
    dilution_extractable: bool | None
    outcome_computable: bool
    return_1d: float | None
    return_3d: float | None
    return_5d: float | None
    return_20d: float | None
    delisted_before_T1: bool
    delisted_before_T3: bool
    delisted_before_T5: bool
    delisted_before_T20: bool
    pipeline_version: str
    processed_at: datetime


# ---------------------------------------------------------------------------
# Scorer Adapter
# ---------------------------------------------------------------------------

@dataclass
class BacktestMarketData:
    """
    Adapter satisfying Scorer's FMPMarketData interface.

    bt_scorer populates this from a MarketSnapshot before calling the live
    Scorer; the real ScorerResult is imported from app.services.scorer.
    """

    adv_dollar: float
    float_shares: float
    price: float
    market_cap: float


# ---------------------------------------------------------------------------
# Stubs — full logic lives in the respective pipeline modules
# ---------------------------------------------------------------------------

@dataclass
class FilterOutcome:
    """
    Result of filter engine evaluation.

    Stub used by bt_filter_engine; full logic implemented there.
    """

    passed: bool
    fail_criterion: str | None = None


@dataclass
class ScorerResult:
    """
    Result of scoring.

    Stub only — bt_scorer imports the real ScorerResult from
    app.services.scorer and uses that type at runtime.
    """

    score: int
    rank: str
    raw_score: float
