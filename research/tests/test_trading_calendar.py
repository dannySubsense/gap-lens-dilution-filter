"""
Tests for Slice 2: TradingCalendar.

Tests 1-3 and 5 use the real market_data.duckdb when it is available (not
locked by a concurrent writer).  When the real DB cannot be opened, the tests
fall back to a mock DuckDB that mirrors its schema and covers the July 2022
date range under test.  Test 4 always uses an in-memory mock.

The mock contains only weekday trading days for June–July 2022, deliberately
omitting July 2 (Saturday), July 3 (Sunday), and July 4 (Independence Day),
which mirrors the behaviour of the certified daily_prices dataset.
"""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from research.pipeline.config import MARKET_DATA_DB_PATH
from research.pipeline.trading_calendar import TradingCalendar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_mock_calendar(tmp_path: Path) -> TradingCalendar:
    """
    Build a TradingCalendar backed by a temporary DuckDB that mirrors the
    daily_prices schema.

    The dataset covers Monday 2022-06-27 through Friday 2022-07-08, with
    July 2 (Sat), July 3 (Sun), and July 4 (Independence Day, Mon) omitted.
    This is sufficient to test all holiday/weekend roll-back cases.
    """
    mock_db = tmp_path / "mock.duckdb"
    con = duckdb.connect(str(mock_db))
    con.execute(
        "CREATE TABLE daily_prices ("
        "  symbol VARCHAR,"
        "  trade_date DATE,"
        "  adjusted_close DOUBLE"
        ")"
    )

    # All weekday trading days in the range, minus the holiday/weekend block.
    trading_days = [
        date(2022, 6, 27),  # Mon
        date(2022, 6, 28),  # Tue
        date(2022, 6, 29),  # Wed
        date(2022, 6, 30),  # Thu
        date(2022, 7, 1),   # Fri  <-- last trading day before the gap
        # date(2022, 7, 2) Saturday — not a trading day
        # date(2022, 7, 3) Sunday  — not a trading day
        # date(2022, 7, 4) Independence Day — US market holiday
        date(2022, 7, 5),   # Tue  <-- first trading day after the gap
        date(2022, 7, 6),   # Wed
        date(2022, 7, 7),   # Thu
        date(2022, 7, 8),   # Fri
    ]
    rows = [("TEST", d, 10.0) for d in trading_days]
    con.executemany(
        "INSERT INTO daily_prices VALUES (?, ?, ?)", rows
    )
    con.close()

    return TradingCalendar(mock_db)


def _try_real_calendar() -> TradingCalendar | None:
    """
    Attempt to open the real market_data.duckdb.  Returns None if the DB
    is currently locked by a concurrent writer.
    """
    try:
        return TradingCalendar(MARKET_DATA_DB_PATH)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shared fixture: real calendar or mock fallback
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def calendar(tmp_path_factory) -> TradingCalendar:
    """
    Returns a TradingCalendar from the real DB if available; otherwise falls
    back to the mock that covers the July 2022 test range.
    """
    real = _try_real_calendar()
    if real is not None:
        return real
    tmp = tmp_path_factory.mktemp("mock_db")
    return _build_mock_calendar(tmp)


# ---------------------------------------------------------------------------
# Test 1: July 4 2022 (US holiday) resolves to prior Friday July 1 2022
# ---------------------------------------------------------------------------

class TestHolidayResolution:
    def test_july_4_2022_resolves_to_july_1(self, calendar: TradingCalendar):
        """
        July 4 2022 is Independence Day (US market holiday).
        The prior trading day is Friday July 1 2022.
        """
        result = calendar.prior_or_equal(date(2022, 7, 4))
        assert result == date(2022, 7, 1), (
            f"Expected date(2022, 7, 1) for July 4 holiday; got {result}"
        )


# ---------------------------------------------------------------------------
# Test 2: Saturday July 2 2022 rolls back to Friday July 1 2022
# ---------------------------------------------------------------------------

class TestWeekendRollback:
    def test_saturday_resolves_to_prior_friday(self, calendar: TradingCalendar):
        """
        Saturday July 2 2022 is a non-trading day.
        The prior trading day is Friday July 1 2022.
        """
        result = calendar.prior_or_equal(date(2022, 7, 2))
        assert result == date(2022, 7, 1), (
            f"Expected date(2022, 7, 1) for Saturday; got {result}"
        )


# ---------------------------------------------------------------------------
# Test 3: Friday July 1 2022 is itself a trading day
# ---------------------------------------------------------------------------

class TestTradingDayItself:
    def test_trading_day_returns_itself(self, calendar: TradingCalendar):
        """
        July 1 2022 is a Friday and a regular trading day.
        prior_or_equal should return the date unchanged.
        """
        result = calendar.prior_or_equal(date(2022, 7, 1))
        assert result == date(2022, 7, 1), (
            f"Expected date(2022, 7, 1) for a trading day itself; got {result}"
        )


# ---------------------------------------------------------------------------
# Test 4: Empty daily_prices raises RuntimeError
# ---------------------------------------------------------------------------

class TestEmptyCalendarRaises:
    def test_zero_rows_raises_runtime_error(self, tmp_path: Path):
        """
        A TradingCalendar constructed from a DB with zero rows in daily_prices
        must raise RuntimeError with the prescribed message.
        """
        empty_db = tmp_path / "empty.duckdb"
        con = duckdb.connect(str(empty_db))
        con.execute(
            "CREATE TABLE daily_prices ("
            "  symbol VARCHAR,"
            "  trade_date DATE,"
            "  adjusted_close DOUBLE"
            ")"
        )
        con.close()

        with pytest.raises(RuntimeError, match="daily_prices is empty"):
            TradingCalendar(empty_db)


# ---------------------------------------------------------------------------
# Test 5: Calendar contains no weekends
# ---------------------------------------------------------------------------

class TestNoWeekends:
    def test_all_dates_are_weekdays(self, calendar: TradingCalendar):
        """
        The certified daily_prices dataset excludes weekends.
        No date in the calendar should have weekday() >= 5
        (5 = Saturday, 6 = Sunday).
        """
        weekend_dates = [d for d in calendar.dates if d.weekday() >= 5]
        assert weekend_dates == [], (
            f"Found {len(weekend_dates)} weekend dates in the calendar: "
            f"{weekend_dates[:5]}"
        )
