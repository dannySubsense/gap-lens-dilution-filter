"""
BacktestFilterEngine — Slice 9

Pure-function port of FilterEngine.evaluate(). Takes a BacktestRow and
MarketSnapshot; returns a FilterOutcome. No async, no DB writes, no HTTP.

Filter order:
    Universe check → Filter 1 (form type) → Filter 2 (market cap)
    → Filter 3 (float, skipped if float_available=False)
    → Filter 4 (dilution, skipped if float_available=False)
    → Filter 5 (price) → Filter 6 (ADV)

IMPORTANT: forward_prices in MarketSnapshot is NEVER accessed here.

Side effects on row:
    evaluate() computes dilution_severity and dilution_extractable from the
    MarketSnapshot and stores them on the BacktestRow before returning.
    This mirrors live pipeline "step 7.5" preparation.
"""

from __future__ import annotations

from app.services.filter_engine import ALLOWED_FORM_TYPES, OFFERING_KEYWORDS  # noqa: F401
from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import BacktestRow, FilterOutcome, MarketSnapshot


class BacktestFilterEngine:
    """
    Pure-function filter engine for the backtest pipeline.

    Applies the same six criteria as the live FilterEngine using only
    point-in-time market data from MarketSnapshot. No side effects beyond
    writing dilution_severity and dilution_extractable to the row.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config

    def evaluate(self, row: BacktestRow, snapshot: MarketSnapshot) -> FilterOutcome:
        """
        Apply all filters in order, stopping at the first failure.

        Returns FilterOutcome(passed=True, fail_criterion=None) if all pass,
        or FilterOutcome(passed=False, fail_criterion=<name>) for the first
        failing criterion.

        As a side effect, sets row.dilution_severity and
        row.dilution_extractable based on point-in-time data.

        forward_prices in snapshot is intentionally never accessed.
        """
        # --- Compute dilution severity (side effect on row) ---
        # This mirrors live pipeline "step 7.5". Must use only T-day data.
        shares_raw = row.shares_offered_raw
        float_at_T = snapshot.float_at_T

        if shares_raw is None or shares_raw == 0:
            row.dilution_severity = None
            row.dilution_extractable = False
        elif float_at_T is None or float_at_T == 0.0:
            row.dilution_severity = None
            row.dilution_extractable = False
        else:
            row.dilution_severity = shares_raw / float_at_T
            row.dilution_extractable = True

        # --- Universe check (before Filter 1) ---
        if not snapshot.in_smallcap_universe:
            return FilterOutcome(passed=False, fail_criterion="NOT_IN_UNIVERSE")

        # --- Filter 1: Form type ---
        # BacktestRow does not carry full plain_text; keyword check is not
        # repeatable here. The discovery and fetch stages pre-filter form
        # types, so the form_type check is the authoritative Filter 1 gate
        # in the backtest context. See 02-ARCHITECTURE.md §6.8 Filter 1.
        if row.form_type not in ALLOWED_FORM_TYPES:
            return FilterOutcome(passed=False, fail_criterion="FILING_TYPE")

        # --- Filter 2: Market cap < config.market_cap_max ---
        if snapshot.market_cap_at_T is None:
            return FilterOutcome(passed=False, fail_criterion="MARKET_CAP")
        if snapshot.market_cap_at_T >= self.config.market_cap_max:
            return FilterOutcome(passed=False, fail_criterion="MARKET_CAP")

        # --- Filter 3: Float < config.float_max (skip if float_available=False) ---
        if row.float_available:
            if snapshot.float_at_T is None:
                # float_available=True says float data should exist but it
                # is absent — treat as filter failure.
                return FilterOutcome(passed=False, fail_criterion="FLOAT")
            if snapshot.float_at_T >= self.config.float_max:
                return FilterOutcome(passed=False, fail_criterion="FLOAT")
        # float_available=False → skip Filter 3 (2017-2019 partial tier)

        # --- Filter 4: Dilution severity > config.dilution_pct_min ---
        # Skip entirely if float_available=False (cannot compute dilution).
        if row.float_available:
            if row.dilution_severity is not None:
                if row.dilution_severity <= self.config.dilution_pct_min:
                    return FilterOutcome(passed=False, fail_criterion="DILUTION_PCT")
            # dilution_severity is None (extractable=False): skip Filter 4

        # --- Filter 5: Price > config.price_min ---
        if snapshot.price_at_T is None:
            return FilterOutcome(passed=False, fail_criterion="PRICE")
        if snapshot.price_at_T <= self.config.price_min:
            return FilterOutcome(passed=False, fail_criterion="PRICE")

        # --- Filter 6: ADV > config.adv_min ---
        if snapshot.adv_at_T is None:
            return FilterOutcome(passed=False, fail_criterion="ADV")
        if snapshot.adv_at_T <= self.config.adv_min:
            return FilterOutcome(passed=False, fail_criterion="ADV")

        # All filters passed
        return FilterOutcome(passed=True, fail_criterion=None)
