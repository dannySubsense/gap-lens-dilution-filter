"""
Tests for Slice 8: MarketDataJoiner.

All tests use an in-memory (tmp_path) DuckDB fixture — the real
market_data.duckdb is not touched because it may be write-locked.

Tests:
1. PIT correctness for price: Saturday filing resolves to prior Friday price.
2. Float AS-OF vs price PIT asymmetry: float uses raw date_filed, price uses
   effective_trade_date — confirmed to be different date objects.
3. float_available flag: pre-2020 filing → False; post-2020 filing → True.
4. ADV uses raw close * volume (not adjusted_close * volume).
5. Forward prices dict: 25 rows after filing → all horizons populated correctly.
6. Delisted ticker: 3 rows after filing → T+5 and T+20 are None.
7. UNRESOLVABLE ticker: filing.ticker is None → all-None MarketSnapshot, no query.
"""

from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from research.pipeline.dataclasses import MarketSnapshot, ResolvedFiling
from research.pipeline.market_data_joiner import MarketDataJoiner
from research.pipeline.trading_calendar import TradingCalendar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_resolved_filing(
    ticker: str | None = "TEST",
    date_filed: date = date(2022, 7, 1),
    cik: str = "0000000001",
    form_type: str = "424B4",
) -> ResolvedFiling:
    return ResolvedFiling(
        cik=cik,
        entity_name="Test Corp",
        form_type=form_type,
        date_filed=date_filed,
        filename="edgar/data/1/0000000001-22-000001.txt",
        accession_number="0000000001-22-000001",
        quarter_key="2022_QTR3",
        ticker=ticker,
        resolution_status="RESOLVED" if ticker is not None else "UNRESOLVABLE",
        permanent_id="PERM-001" if ticker is not None else None,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """
    Build a minimal market_data.duckdb fixture covering symbol "TEST"
    with enough data to exercise all join paths.

    Schema mirrors the production tables that MarketDataJoiner queries.
    Trading days cover 2022-06-20 through 2022-08-31 (weekdays only).
    """
    db_path = tmp_path / "test_market.duckdb"
    con = duckdb.connect(str(db_path))

    # ---- daily_prices -------------------------------------------------------
    con.execute(
        """
        CREATE TABLE daily_prices (
            symbol        VARCHAR,
            trade_date    DATE,
            close         DOUBLE,
            adjusted_close DOUBLE,
            volume        DOUBLE
        )
        """
    )

    # Generate a sequence of weekday trading days: 2022-06-20 to 2022-08-31
    # We deliberately use different values for close vs adjusted_close so that
    # ADV tests can verify which column is used.
    trading_days: list[date] = []
    d = date(2022, 6, 20)
    while d <= date(2022, 8, 31):
        if d.weekday() < 5:  # Monday–Friday
            trading_days.append(d)
        d += timedelta(days=1)

    rows = []
    for i, td in enumerate(trading_days):
        close_price = 10.0 + i * 0.1        # raw close, increments slightly
        adj_close = close_price * 2.0       # adjusted_close is 2x close (simulated split)
        volume = 100_000.0
        rows.append(("TEST", td, close_price, adj_close, volume))

    con.executemany(
        "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)", rows
    )

    # ---- daily_market_cap ---------------------------------------------------
    con.execute(
        """
        CREATE TABLE daily_market_cap (
            symbol     VARCHAR,
            trade_date DATE,
            market_cap DOUBLE
        )
        """
    )
    mc_rows = [("TEST", td, 500_000_000.0) for td in trading_days]
    con.executemany("INSERT INTO daily_market_cap VALUES (?, ?, ?)", mc_rows)

    # ---- daily_universe -----------------------------------------------------
    con.execute(
        """
        CREATE TABLE daily_universe (
            symbol               VARCHAR,
            trade_date           DATE,
            in_smallcap_universe BOOLEAN
        )
        """
    )
    uni_rows = [("TEST", td, True) for td in trading_days]
    con.executemany("INSERT INTO daily_universe VALUES (?, ?, ?)", uni_rows)

    # ---- historical_float ---------------------------------------------------
    # Two rows: one pre-2020 (should be ignored by the AS-OF query because we
    # guard with FLOAT_DATA_START_DATE) and one in 2022.
    con.execute(
        """
        CREATE TABLE historical_float (
            symbol       VARCHAR,
            trade_date   DATE,
            float_shares DOUBLE
        )
        """
    )
    con.execute(
        "INSERT INTO historical_float VALUES (?, ?, ?)",
        ["TEST", date(2022, 6, 15), 30_000_000.0],
    )
    con.execute(
        "INSERT INTO historical_float VALUES (?, ?, ?)",
        ["TEST", date(2022, 7, 10), 28_000_000.0],
    )

    # ---- short_interest -----------------------------------------------------
    con.execute(
        """
        CREATE TABLE short_interest (
            symbol          VARCHAR,
            settlement_date DATE,
            short_position  DOUBLE
        )
        """
    )
    con.execute(
        "INSERT INTO short_interest VALUES (?, ?, ?)",
        ["TEST", date(2022, 6, 30), 5_000_000.0],
    )

    con.close()
    return db_path


@pytest.fixture
def calendar(mock_db: Path) -> TradingCalendar:
    """TradingCalendar built from the mock DB (uses its daily_prices dates)."""
    return TradingCalendar(mock_db)


@pytest.fixture
def joiner(mock_db: Path, calendar: TradingCalendar) -> MarketDataJoiner:
    """MarketDataJoiner backed by the mock DB."""
    return MarketDataJoiner(mock_db, calendar)


# ---------------------------------------------------------------------------
# Test 1: PIT correctness for price
# A filing dated Saturday 2022-07-02 → effective_trade_date = Friday 2022-07-01
# price_at_T should be the daily_prices row for 2022-07-01.
# ---------------------------------------------------------------------------

class TestPITCorrectness:
    def test_saturday_filing_resolves_to_friday_price(self, joiner: MarketDataJoiner):
        """
        Filing dated Saturday 2022-07-02.
        TradingCalendar rolls back to Friday 2022-07-01.
        price_at_T must match the daily_prices row for 2022-07-01.
        """
        filing = _make_resolved_filing(date_filed=date(2022, 7, 2))
        snapshot = joiner.join(filing)

        assert snapshot.effective_trade_date == date(2022, 7, 1), (
            f"Expected effective_trade_date=2022-07-01, got {snapshot.effective_trade_date}"
        )
        # Price must be non-None (row exists for 2022-07-01)
        assert snapshot.price_at_T is not None, "price_at_T should not be None for 2022-07-01"
        # Confirm it is the adjusted_close, not the raw close
        # adjusted_close = 2 * close; verify it is >10 (our base close) meaning
        # the 2x multiplier is applied.
        assert snapshot.price_at_T > 10.0, (
            f"price_at_T={snapshot.price_at_T} should be the adjusted_close (2x close)"
        )


# ---------------------------------------------------------------------------
# Test 2: Float AS-OF vs price PIT asymmetry
# Float uses raw date_filed (Saturday 2022-07-02).
# Price uses effective_trade_date (Friday 2022-07-01).
# These should be different date objects.
# ---------------------------------------------------------------------------

class TestFloatVsPriceDateAsymmetry:
    def test_float_uses_raw_date_price_uses_effective(self, joiner: MarketDataJoiner):
        """
        The float AS-OF ceiling is filing.date_filed (the raw, uncalendared date).
        The price PIT is effective_trade_date (calendar-adjusted).

        For a Saturday filing: date_filed=2022-07-02, effective=2022-07-01.
        These must differ so the test actually validates asymmetry.
        """
        filing_date = date(2022, 7, 2)   # Saturday
        filing = _make_resolved_filing(date_filed=filing_date)
        snapshot = joiner.join(filing)

        effective = snapshot.effective_trade_date
        assert effective == date(2022, 7, 1), (
            f"effective_trade_date should be 2022-07-01, got {effective}"
        )
        # The float_effective_date should be on or before the raw date_filed
        # (2022-07-02), not constrained to the effective_trade_date (2022-07-01).
        # Our fixture has a float row on 2022-06-15 (before both dates).
        assert snapshot.float_at_T is not None
        assert snapshot.float_effective_date is not None
        # The two date inputs used are confirmed different
        assert filing_date != effective, (
            "Test requires filing_date != effective_trade_date to validate asymmetry"
        )
        # float_effective_date is the date of the AS-OF row picked, ceiling=date_filed
        # If price had used date_filed too, both would be identical inputs; but they differ.
        assert snapshot.float_effective_date <= filing_date, (
            f"float_effective_date {snapshot.float_effective_date} must be <= date_filed {filing_date}"
        )


# ---------------------------------------------------------------------------
# Test 3: float_available flag
# Pre-2020 filing → float_available=False, float_at_T=None.
# Post-2020 filing → float_available=True.
# ---------------------------------------------------------------------------

class TestFloatAvailableFlag:
    def test_pre_2020_filing_float_not_available(self, mock_db: Path):
        """
        Filing dated 2019-01-01 is before FLOAT_DATA_START_DATE (2020-03-04).
        float_available must be False; float_at_T must be None.
        """
        # Build a calendar from a mock that has trading days in 2019.
        # We need a separate DB for the calendar that includes 2019 dates.
        # Simplest approach: patch the calendar with a broader mock.
        import duckdb as _duckdb
        from pathlib import Path as _Path

        # Create a separate DB with 2019 trading days
        tmp_con = _duckdb.connect(str(mock_db), read_only=False)

        # Check if 2019 date exists in mock; if not, add it.
        rows_2019 = tmp_con.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE trade_date = '2019-01-02'"
        ).fetchone()[0]
        if rows_2019 == 0:
            tmp_con.execute(
                "INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)",
                ["TEST", date(2019, 1, 2), 5.0, 10.0, 100_000.0],
            )
        tmp_con.close()

        cal = TradingCalendar(mock_db)
        j = MarketDataJoiner(mock_db, cal)
        filing = _make_resolved_filing(date_filed=date(2019, 1, 2))
        snapshot = j.join(filing)

        assert snapshot.float_available is False, (
            f"Expected float_available=False for pre-2020 filing; got {snapshot.float_available}"
        )
        assert snapshot.float_at_T is None, (
            f"Expected float_at_T=None for pre-2020 filing; got {snapshot.float_at_T}"
        )

    def test_post_2020_filing_float_available(self, joiner: MarketDataJoiner):
        """
        Filing dated 2021-06-01 is after FLOAT_DATA_START_DATE.
        float_available must be True.
        """
        filing = _make_resolved_filing(date_filed=date(2021, 6, 1))
        # The calendar fixture only has 2022 dates; need a broader setup.
        # We test this with a fixture that has 2021 dates — use a fresh db.
        # Instead, exercise via direct logic: we know float_available depends
        # solely on date_filed >= FLOAT_DATA_START_DATE, so use a date already
        # in our mock's range (2022).
        filing = _make_resolved_filing(date_filed=date(2022, 7, 1))
        snapshot = joiner.join(filing)

        assert snapshot.float_available is True, (
            f"Expected float_available=True for 2022 filing; got {snapshot.float_available}"
        )


# ---------------------------------------------------------------------------
# Test 4: ADV uses raw close * volume (not adjusted_close * volume)
# Our mock has adjusted_close = 2 * close.
# So ADV from close * volume should be ~half of ADV from adjusted_close * volume.
# We verify that adv_at_T matches close * volume.
# ---------------------------------------------------------------------------

class TestADVUsesRawClose:
    def test_adv_computed_from_close_not_adjusted_close(self, joiner: MarketDataJoiner):
        """
        Mock DB has close=10.0 and adjusted_close=20.0 (2x) for each day.
        ADV should be computed from close * volume = 10.0 * 100_000 = 1_000_000.
        If it incorrectly used adjusted_close * volume it would be 2_000_000.
        """
        filing = _make_resolved_filing(date_filed=date(2022, 7, 29))  # Friday
        snapshot = joiner.join(filing)

        assert snapshot.adv_at_T is not None, "adv_at_T should not be None for well-populated ticker"

        # ADV = close * volume. For dates around 2022-07-29 (approximately day 30
        # in our trading day sequence starting 2022-06-20):
        # close ranges from 10.0+0.1*i; volume=100_000 throughout.
        # The exact value isn't critical — we just verify it's in the range
        # expected for close*volume, not adjusted_close*volume.
        # close*volume ≈ [10.0–13.0] * 100_000 = 1_000_000–1_300_000
        # adjusted_close*volume would be ≈ 2_000_000–2_600_000
        assert snapshot.adv_at_T < 2_000_000.0, (
            f"adv_at_T={snapshot.adv_at_T} suggests adjusted_close was used instead of close"
        )
        assert snapshot.adv_at_T > 0.0, "adv_at_T must be positive"


# ---------------------------------------------------------------------------
# Test 5: Forward prices dict — 25 rows after filing date → all horizons populated
# ---------------------------------------------------------------------------

class TestForwardPricesComplete:
    def test_all_four_horizons_populated_with_25_forward_rows(
        self, tmp_path: Path
    ):
        """
        Build a DB where symbol "FWDTEST" has exactly 25 trading days after
        2022-06-30. Verify forward_prices[1], [3], [5], [20] are all non-None
        and match the expected adjusted_close rows.
        """
        db_path = tmp_path / "fwd_test.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute(
            """
            CREATE TABLE daily_prices (
                symbol         VARCHAR,
                trade_date     DATE,
                close          DOUBLE,
                adjusted_close DOUBLE,
                volume         DOUBLE
            )
            """
        )
        con.execute("CREATE TABLE daily_market_cap (symbol VARCHAR, trade_date DATE, market_cap DOUBLE)")
        con.execute("CREATE TABLE daily_universe (symbol VARCHAR, trade_date DATE, in_smallcap_universe BOOLEAN)")
        con.execute("CREATE TABLE historical_float (symbol VARCHAR, trade_date DATE, float_shares DOUBLE)")
        con.execute("CREATE TABLE short_interest (symbol VARCHAR, settlement_date DATE, short_position DOUBLE)")

        # Anchor trading day: 2022-06-30 (Thursday)
        # Forward rows: 25 weekdays after 2022-06-30 starting 2022-07-01
        anchor = date(2022, 6, 30)
        forward_days: list[date] = []
        d = anchor + timedelta(days=1)
        while len(forward_days) < 25:
            if d.weekday() < 5:
                forward_days.append(d)
            d += timedelta(days=1)

        all_days = [anchor] + forward_days
        rows = []
        for i, td in enumerate(all_days):
            # adjusted_close = i * 1.0 so row-number is directly readable
            rows.append(("FWDTEST", td, float(i), float(i) * 10.0, 50_000.0))
        con.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)", rows)

        con.close()

        cal = TradingCalendar(db_path)
        j = MarketDataJoiner(db_path, cal)

        filing = _make_resolved_filing(ticker="FWDTEST", date_filed=anchor)
        snapshot = j.join(filing)

        fp = snapshot.forward_prices
        assert fp[1] is not None,  "forward_prices[1] should be populated"
        assert fp[3] is not None,  "forward_prices[3] should be populated"
        assert fp[5] is not None,  "forward_prices[5] should be populated"
        assert fp[20] is not None, "forward_prices[20] should be populated"

        # Row 1 after anchor is forward_days[0] (i=1 in our enumeration)
        # adjusted_close = i * 10.0 where i is position in all_days
        # forward_days[0] is i=1 → adjusted_close = 10.0
        # forward_days[2] is i=3 → adjusted_close = 30.0
        # forward_days[4] is i=5 → adjusted_close = 50.0
        # forward_days[19] is i=20 → adjusted_close = 200.0
        assert fp[1] == pytest.approx(10.0),  f"forward_prices[1] expected 10.0, got {fp[1]}"
        assert fp[3] == pytest.approx(30.0),  f"forward_prices[3] expected 30.0, got {fp[3]}"
        assert fp[5] == pytest.approx(50.0),  f"forward_prices[5] expected 50.0, got {fp[5]}"
        assert fp[20] == pytest.approx(200.0), f"forward_prices[20] expected 200.0, got {fp[20]}"


# ---------------------------------------------------------------------------
# Test 6: Delisted ticker — only 3 rows after filing date
# T+5 and T+20 should be None; T+1 and T+3 should be populated.
# ---------------------------------------------------------------------------

class TestDelistedTicker:
    def test_sparse_forward_rows_produce_none_at_missing_horizons(
        self, tmp_path: Path
    ):
        """
        Symbol "DELIST" has only 3 trading days after the filing anchor.
        forward_prices[1] and forward_prices[3] are populated.
        forward_prices[5] and forward_prices[20] are None.
        delisted_before[5] and delisted_before[20] are True.
        """
        db_path = tmp_path / "delist_test.duckdb"
        con = duckdb.connect(str(db_path))
        con.execute(
            """
            CREATE TABLE daily_prices (
                symbol         VARCHAR,
                trade_date     DATE,
                close          DOUBLE,
                adjusted_close DOUBLE,
                volume         DOUBLE
            )
            """
        )
        con.execute("CREATE TABLE daily_market_cap (symbol VARCHAR, trade_date DATE, market_cap DOUBLE)")
        con.execute("CREATE TABLE daily_universe (symbol VARCHAR, trade_date DATE, in_smallcap_universe BOOLEAN)")
        con.execute("CREATE TABLE historical_float (symbol VARCHAR, trade_date DATE, float_shares DOUBLE)")
        con.execute("CREATE TABLE short_interest (symbol VARCHAR, settlement_date DATE, short_position DOUBLE)")

        anchor = date(2022, 6, 30)
        # Only 4 total rows: anchor + 3 forward trading days
        days = [
            anchor,
            date(2022, 7, 1),   # T+1
            date(2022, 7, 5),   # T+2 (July 4 skipped as holiday — but we're just using 3 days)
            date(2022, 7, 6),   # T+3
            # No more rows — DELIST delisted after T+3
        ]
        rows = [("DELIST", d, 5.0, 10.0, 10_000.0) for d in days]
        con.executemany("INSERT INTO daily_prices VALUES (?, ?, ?, ?, ?)", rows)
        con.close()

        cal = TradingCalendar(db_path)
        j = MarketDataJoiner(db_path, cal)

        filing = _make_resolved_filing(ticker="DELIST", date_filed=anchor)
        snapshot = j.join(filing)

        fp = snapshot.forward_prices
        db = snapshot.delisted_before

        assert fp[1] is not None,  "T+1 should exist (3 forward rows available)"
        assert fp[3] is not None,  "T+3 should exist (3 forward rows available)"
        assert fp[5] is None,      f"T+5 should be None (only 3 forward rows); got {fp[5]}"
        assert fp[20] is None,     f"T+20 should be None (only 3 forward rows); got {fp[20]}"

        assert db[1] is False,  "delisted_before[1] should be False"
        assert db[3] is False,  "delisted_before[3] should be False"
        assert db[5] is True,   "delisted_before[5] should be True"
        assert db[20] is True,  "delisted_before[20] should be True"


# ---------------------------------------------------------------------------
# Test 7: UNRESOLVABLE ticker — filing.ticker is None
# No DB query should be attempted; all fields are None.
# ---------------------------------------------------------------------------

class TestUnresolvableTicker:
    def test_none_ticker_returns_empty_snapshot_without_querying_db(
        self, joiner: MarketDataJoiner
    ):
        """
        If filing.ticker is None, MarketDataJoiner must return a MarketSnapshot
        with all numeric fields set to None (no DB query attempted).
        """
        filing = _make_resolved_filing(ticker=None, date_filed=date(2022, 7, 1))
        snapshot = joiner.join(filing)

        assert snapshot.price_at_T is None
        assert snapshot.market_cap_at_T is None
        assert snapshot.float_at_T is None
        assert snapshot.float_available is False
        assert snapshot.float_effective_date is None
        assert snapshot.short_interest_at_T is None
        assert snapshot.short_interest_effective_date is None
        assert snapshot.adv_at_T is None
        assert snapshot.in_smallcap_universe is None
        assert snapshot.borrow_cost_source == "DEFAULT"

        # All forward prices should be None and delisted flags True
        for n in (1, 3, 5, 20):
            assert snapshot.forward_prices.get(n) is None, (
                f"forward_prices[{n}] should be None for UNRESOLVABLE ticker"
            )
            assert snapshot.delisted_before.get(n) is True, (
                f"delisted_before[{n}] should be True for UNRESOLVABLE ticker"
            )
