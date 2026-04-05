"""
MarketDataJoiner — Slice 8 of the backtest pipeline.

Joins point-in-time market data from market_data.duckdb for each resolved
filing. Assembles a MarketSnapshot containing price, market cap, float, ADV,
short interest, universe membership, and forward prices.

Point-in-time rules enforced here:
- Price, market cap, ADV, and universe membership use effective_trade_date
  (the prior-or-equal trading day per TradingCalendar).
- Float and short interest use filing.date_filed (raw, calendar-unadjusted)
  as the AS-OF ceiling — these datasets update on their own schedules.
- Forward prices are row-number-indexed strictly after effective_trade_date.
"""

from datetime import date
from pathlib import Path

import duckdb

from research.pipeline.config import FLOAT_DATA_START_DATE
from research.pipeline.dataclasses import MarketSnapshot, ResolvedFiling
from research.pipeline.trading_calendar import TradingCalendar


class MarketDataJoiner:
    """
    Executes all point-in-time joins against market_data.duckdb and
    assembles a MarketSnapshot for each filing.

    A single read-only DuckDB connection is opened at construction time
    and reused across all join() calls.
    """

    def __init__(self, db_path: Path, calendar: TradingCalendar) -> None:
        """
        Parameters
        ----------
        db_path:
            Path to market_data.duckdb. Opened read-only.
        calendar:
            Pre-constructed TradingCalendar used to resolve
            filing.date_filed to the nearest prior trading day.
        """
        self._con = duckdb.connect(str(db_path), read_only=True)
        self._calendar = calendar

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def join(self, filing: ResolvedFiling) -> MarketSnapshot:
        """
        Compute the MarketSnapshot for one filing.

        If filing.ticker is None (UNRESOLVABLE), returns an empty
        MarketSnapshot with all numeric fields set to None and
        float_available=False.

        Parameters
        ----------
        filing:
            A resolved filing. Must have date_filed set.

        Returns
        -------
        MarketSnapshot
            Point-in-time market data for the filing's ticker and date.
        """
        if filing.ticker is None:
            return MarketSnapshot(
                symbol="",
                effective_trade_date=filing.date_filed,
                price_at_T=None,
                market_cap_at_T=None,
                float_at_T=None,
                float_available=False,
                float_effective_date=None,
                short_interest_at_T=None,
                short_interest_effective_date=None,
                borrow_cost_source="DEFAULT",
                adv_at_T=None,
                in_smallcap_universe=None,
                forward_prices={1: None, 3: None, 5: None, 20: None},
                delisted_before={1: True, 3: True, 5: True, 20: True},
            )

        symbol = filing.ticker
        effective_trade_date = self._calendar.prior_or_equal(filing.date_filed)

        price_at_T = self._fetch_price(symbol, effective_trade_date)
        market_cap_at_T = self._fetch_market_cap(symbol, effective_trade_date)
        adv_at_T = self._fetch_adv(symbol, effective_trade_date)
        in_smallcap_universe = self._fetch_universe(symbol, effective_trade_date)

        float_at_T, float_available, float_effective_date = self._fetch_float(
            symbol, filing.date_filed
        )

        short_interest_at_T, short_interest_effective_date = self._fetch_short_interest(
            symbol, filing.date_filed
        )
        borrow_cost_source = (
            "SHORT_INTEREST" if short_interest_at_T is not None else "DEFAULT"
        )

        forward_prices, delisted_before = self._fetch_forward_prices(
            symbol, effective_trade_date
        )

        return MarketSnapshot(
            symbol=symbol,
            effective_trade_date=effective_trade_date,
            price_at_T=price_at_T,
            market_cap_at_T=market_cap_at_T,
            float_at_T=float_at_T,
            float_available=float_available,
            float_effective_date=float_effective_date,
            short_interest_at_T=short_interest_at_T,
            short_interest_effective_date=short_interest_effective_date,
            borrow_cost_source=borrow_cost_source,
            adv_at_T=adv_at_T,
            in_smallcap_universe=in_smallcap_universe,
            forward_prices=forward_prices,
            delisted_before=delisted_before,
        )

    def close(self) -> None:
        """Close the underlying DuckDB connection."""
        self._con.close()

    # ------------------------------------------------------------------
    # Private join helpers
    # ------------------------------------------------------------------

    def _fetch_price(self, symbol: str, trade_date: date) -> float | None:
        """
        Point-in-time price (adjusted_close) from daily_prices.
        Returns None if no row exists for (symbol, trade_date).
        """
        row = self._con.execute(
            """
            SELECT adjusted_close
            FROM daily_prices
            WHERE symbol = ? AND trade_date = ?
            """,
            [symbol, trade_date],
        ).fetchone()
        return row[0] if row is not None else None

    def _fetch_market_cap(self, symbol: str, trade_date: date) -> float | None:
        """
        Point-in-time market cap from daily_market_cap.
        Returns None if no row exists.
        """
        row = self._con.execute(
            """
            SELECT market_cap
            FROM daily_market_cap
            WHERE symbol = ? AND trade_date = ?
            """,
            [symbol, trade_date],
        ).fetchone()
        return row[0] if row is not None else None

    def _fetch_adv(self, symbol: str, trade_date: date) -> float | None:
        """
        20-day dollar-volume ADV ending at trade_date (inclusive).

        Uses close * volume (raw close, not adjusted_close) to avoid
        split distortions. Returns None if fewer than 20 rows exist.

        The subquery finds the trade_date of the 20th most recent row
        (OFFSET 19 in DESC order), then the outer query averages all
        rows between that anchor date and trade_date inclusive.
        """
        row = self._con.execute(
            """
            SELECT AVG(close * volume) AS adv
            FROM daily_prices
            WHERE symbol = ?
              AND trade_date <= ?
              AND trade_date >= (
                  SELECT trade_date FROM daily_prices
                  WHERE symbol = ? AND trade_date <= ?
                  ORDER BY trade_date DESC
                  LIMIT 1 OFFSET 19
              )
            """,
            [symbol, trade_date, symbol, trade_date],
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    def _fetch_universe(self, symbol: str, trade_date: date) -> bool | None:
        """
        Point-in-time universe membership from daily_universe.
        Returns None if no row exists for (symbol, trade_date).
        """
        row = self._con.execute(
            """
            SELECT in_smallcap_universe
            FROM daily_universe
            WHERE symbol = ? AND trade_date = ?
            """,
            [symbol, trade_date],
        ).fetchone()
        return row[0] if row is not None else None

    def _fetch_float(
        self, symbol: str, date_filed: date
    ) -> tuple[float | None, bool, date | None]:
        """
        AS-OF float join from historical_float, using date_filed as ceiling.

        Returns (float_at_T, float_available, float_effective_date).

        - If date_filed < FLOAT_DATA_START_DATE: skip query, return
          (None, False, None).
        - If query returns no row for a post-2020 filing: return
          (None, True, None) — data gap, not a pre-2020 flag.
        """
        if date_filed < FLOAT_DATA_START_DATE:
            return None, False, None

        row = self._con.execute(
            """
            SELECT float_shares, trade_date AS float_effective_date
            FROM historical_float
            WHERE symbol = ?
              AND trade_date <= ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            [symbol, date_filed],
        ).fetchone()

        if row is None:
            return None, True, None

        return float(row[0]), True, row[1]

    def _fetch_short_interest(
        self, symbol: str, date_filed: date
    ) -> tuple[float | None, date | None]:
        """
        AS-OF short interest join, using date_filed as ceiling.

        Returns (short_interest_at_T, short_interest_effective_date).
        Pre-2021 filings will return (None, None) because no rows exist.
        """
        row = self._con.execute(
            """
            SELECT short_position, settlement_date AS si_effective_date
            FROM short_interest
            WHERE symbol = ?
              AND settlement_date <= ?
            ORDER BY settlement_date DESC
            LIMIT 1
            """,
            [symbol, date_filed],
        ).fetchone()

        if row is None:
            return None, None

        return float(row[0]), row[1]

    def _fetch_forward_prices(
        self, symbol: str, effective_trade_date: date
    ) -> tuple[dict[int, float | None], dict[int, bool]]:
        """
        Fetch forward prices at horizons T+1, T+3, T+5, T+20.

        Rows are numbered 1..N in chronological order, strictly after
        effective_trade_date. Missing rows indicate the symbol was
        delisted before that horizon.

        Returns
        -------
        forward_prices : dict[int, float | None]
            Keys 1, 3, 5, 20. None if delisted before that horizon.
        delisted_before : dict[int, bool]
            True if fewer than N rows exist after effective_trade_date.
        """
        horizons = {1, 3, 5, 20}

        rows = self._con.execute(
            """
            SELECT rn, adjusted_close
            FROM (
                SELECT adjusted_close,
                       ROW_NUMBER() OVER (ORDER BY trade_date) AS rn
                FROM daily_prices
                WHERE symbol = ? AND trade_date > ?
            ) sub
            WHERE rn IN (1, 3, 5, 20)
            """,
            [symbol, effective_trade_date],
        ).fetchall()

        rn_to_price: dict[int, float] = {int(r[0]): r[1] for r in rows}

        forward_prices: dict[int, float | None] = {}
        delisted_before: dict[int, bool] = {}

        for n in horizons:
            if n in rn_to_price:
                forward_prices[n] = rn_to_price[n]
                delisted_before[n] = False
            else:
                forward_prices[n] = None
                delisted_before[n] = True

        return forward_prices, delisted_before
