"""
TradingCalendar — derives all US trading days from daily_prices in market_data.duckdb
and resolves any date to the nearest prior (or equal) trading day.

Usage:
    from research.pipeline.trading_calendar import TradingCalendar
    from research.pipeline.config import MARKET_DATA_DB_PATH

    calendar = TradingCalendar(MARKET_DATA_DB_PATH)
    effective_date = calendar.prior_or_equal(filing_date_filed)
"""

import bisect
from datetime import date
from pathlib import Path

import duckdb


class TradingCalendar:
    """
    Loads all distinct trading days from daily_prices once at construction,
    then resolves arbitrary dates to the most recent trading day on or before them.

    The calendar is derived from the certified daily_prices dataset, which
    already excludes weekends and US market holidays — no external holiday
    calendar file is required.
    """

    def __init__(self, db_path: Path) -> None:
        """
        Build the calendar by querying daily_prices.

        Parameters
        ----------
        db_path:
            Path to market_data.duckdb (opened read-only).

        Raises
        ------
        RuntimeError
            If daily_prices contains zero rows.
        """
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            rows = con.execute(
                "SELECT DISTINCT trade_date FROM daily_prices ORDER BY trade_date"
            ).fetchall()
        finally:
            con.close()

        if not rows:
            raise RuntimeError(
                "daily_prices is empty — cannot build trading calendar"
            )

        # trade_date is a DATE column; DuckDB returns datetime.date objects.
        self.dates: list[date] = [row[0] for row in rows]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def prior_or_equal(self, d: date) -> date:
        """
        Return the largest trading day in the calendar that is <= d.

        Parameters
        ----------
        d:
            The target date (typically a filing's date_filed).

        Returns
        -------
        date
            The most recent trading day on or before d.

        Raises
        ------
        ValueError
            If d is earlier than the first known trading day.
        """
        # bisect_right gives the insertion point after any existing entry equal
        # to d, so subtracting 1 yields the index of the largest date <= d.
        idx = bisect.bisect_right(self.dates, d) - 1
        if idx < 0:
            raise ValueError(
                f"Date {d} is before the earliest known trading day "
                f"({self.dates[0]}); cannot resolve."
            )
        return self.dates[idx]

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def min_date(self) -> date:
        """The earliest trading day in the calendar."""
        return self.dates[0]

    @property
    def max_date(self) -> date:
        """The latest trading day in the calendar."""
        return self.dates[-1]
