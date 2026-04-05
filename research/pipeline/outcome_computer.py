"""
OutcomeComputer — Slice 11 of the backtest pipeline.

Computes T+1, T+3, T+5, T+20 price returns and delisting flags from the
forward_prices dict pre-populated by MarketDataJoiner.

No DB or HTTP calls are made here — this is pure arithmetic over data
already assembled in BacktestRow and MarketSnapshot.

Return calculation note (Research Contract RC-17):
    Uses adjusted_close for both price_at_T and forward prices (split-adjusted).
    Large returns (>500% or <-99%) are recorded as-is — they are NOT excluded.
    These are potential corporate action artifacts to be noted in findings.
"""

from research.pipeline.dataclasses import BacktestRow, MarketSnapshot

_HORIZONS = [1, 3, 5, 20]


class OutcomeComputer:
    """
    Populates return and delisting-flag fields on a BacktestRow.

    Horizon counting is strictly trading-day based. The forward_prices dict
    is pre-populated by MarketDataJoiner using row-number ordering on
    daily_prices; OutcomeComputer only divides.
    """

    def compute(self, row: BacktestRow, snapshot: MarketSnapshot) -> BacktestRow:
        """
        Populate return_1d, return_3d, return_5d, return_20d and
        delisted_before_T1/T3/T5/T20 on row.

        Mutates the row in place and also returns it.

        Parameters
        ----------
        row:
            BacktestRow with price_at_T already set from MarketSnapshot.
        snapshot:
            MarketSnapshot whose forward_prices dict is keyed by horizon N
            (1, 3, 5, 20) with adjusted_close values or None for delistings.

        Returns
        -------
        The updated BacktestRow.
        """
        if row.price_at_T is None or row.price_at_T == 0.0:
            row.outcome_computable = False
            # Return fields default to None; delisted flags default to False.
            # Delisting is undefined when price_at_T itself is absent.
            return row

        row.outcome_computable = True

        for n in _HORIZONS:
            forward_price = snapshot.forward_prices.get(n)
            if forward_price is None:
                _set_horizon(row, n, return_val=None, delisted=True)
            else:
                ret = (forward_price / row.price_at_T) - 1.0
                _set_horizon(row, n, return_val=ret, delisted=False)

        return row


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _set_horizon(
    row: BacktestRow,
    n: int,
    return_val: float | None,
    delisted: bool,
) -> None:
    """Write return and delisting flag for horizon N onto row."""
    if n == 1:
        row.return_1d = return_val
        row.delisted_before_T1 = delisted
    elif n == 3:
        row.return_3d = return_val
        row.delisted_before_T3 = delisted
    elif n == 5:
        row.return_5d = return_val
        row.delisted_before_T5 = delisted
    elif n == 20:
        row.return_20d = return_val
        row.delisted_before_T20 = delisted
