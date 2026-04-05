"""
Tests for Slice 11: OutcomeComputer.

Tests:
1. Normal case: all 4 forward prices present → all returns computed, all
   delisted_before flags = False, outcome_computable = True.
2. Delisting at T+3: forward_prices = {1: X, 3: None, 5: None, 20: None} →
   return_1d computed; return_3d/5d/20d = None;
   delisted_before_T1=False, delisted_before_T3/T5/T20=True.
3. price_at_T = None → outcome_computable = False, all returns None.
4. price_at_T = 0.0 → outcome_computable = False (division-by-zero guard).
5. Return calculation: price_at_T=2.00, forward T+5=1.60 → return_5d = -0.20.
6. Positive return: price_at_T=1.00, forward T+20=1.50 → return_20d = 0.50.
7. Large return not excluded: price_at_T=1.00, forward T+20=8.00 →
   return_20d = 7.00 (pipeline records it, does NOT filter).
8. price_at_T=5.00 with all forward prices present → outcome_computable=True.
"""

from datetime import date, datetime

import pytest

from research.pipeline.dataclasses import BacktestRow, MarketSnapshot
from research.pipeline.outcome_computer import OutcomeComputer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(price_at_T: float | None = 10.00) -> BacktestRow:
    """Build a minimal BacktestRow with only price_at_T varying."""
    return BacktestRow(
        accession_number="0001234567-22-000001",
        cik="0001234567",
        ticker="TEST",
        entity_name="Test Corp",
        form_type="424B4",
        filed_at=datetime(2022, 6, 1, 0, 0, 0),
        setup_type="DILUTION_PLAY",
        confidence=0.90,
        shares_offered_raw=1_000_000,
        dilution_severity=0.25,
        price_discount=0.10,
        immediate_pressure=True,
        key_excerpt="sold 1M shares",
        filter_status="PASSED",
        filter_fail_reason=None,
        float_available=True,
        in_smallcap_universe=True,
        price_at_T=price_at_T,
        market_cap_at_T=50_000_000.0,
        float_at_T=5_000_000.0,
        adv_at_T=750_000.0,
        short_interest_at_T=500_000.0,
        borrow_cost_source="DEFAULT",
        score=7,
        rank="B",
        dilution_extractable=True,
        outcome_computable=False,   # will be overwritten by OutcomeComputer
        return_1d=None,
        return_3d=None,
        return_5d=None,
        return_20d=None,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version="backtest-v1.0.0",
        processed_at=datetime(2025, 1, 1, 0, 0, 0),
    )


def _make_snapshot(
    price_at_T: float | None = 10.00,
    forward_prices: dict | None = None,
) -> MarketSnapshot:
    """Build a minimal MarketSnapshot."""
    if forward_prices is None:
        forward_prices = {}
    return MarketSnapshot(
        symbol="TEST",
        effective_trade_date=date(2022, 6, 1),
        price_at_T=price_at_T,
        market_cap_at_T=50_000_000.0,
        float_at_T=5_000_000.0,
        float_available=True,
        float_effective_date=date(2022, 6, 1),
        short_interest_at_T=500_000.0,
        short_interest_effective_date=date(2022, 6, 1),
        borrow_cost_source="DEFAULT",
        adv_at_T=750_000.0,
        in_smallcap_universe=True,
        forward_prices=forward_prices,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOutcomeComputerNormalCase:
    """Test 1: All four forward prices present."""

    def test_all_returns_computed(self) -> None:
        """All horizons populated → returns calculated, no delisting flags."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=10.00)
        snap = _make_snapshot(
            price_at_T=10.00,
            forward_prices={1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is True
        assert result.return_1d == pytest.approx(-0.05)
        assert result.return_3d == pytest.approx(-0.08)
        assert result.return_5d == pytest.approx(-0.10)
        assert result.return_20d == pytest.approx(-0.20)
        assert result.delisted_before_T1 is False
        assert result.delisted_before_T3 is False
        assert result.delisted_before_T5 is False
        assert result.delisted_before_T20 is False

    def test_returns_mutates_and_returns_same_row(self) -> None:
        """compute() mutates in place and returns the same object."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=10.00)
        snap = _make_snapshot(
            price_at_T=10.00,
            forward_prices={1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00},
        )
        result = comp.compute(row, snap)
        assert result is row


class TestOutcomeComputerDelistingAtT3:
    """Test 2: Delisting at T+3 — only T+1 price available."""

    def test_partial_delisting_flags(self) -> None:
        comp = OutcomeComputer()
        row = _make_row(price_at_T=10.00)
        snap = _make_snapshot(
            price_at_T=10.00,
            forward_prices={1: 9.50, 3: None, 5: None, 20: None},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is True
        assert result.return_1d == pytest.approx(-0.05)
        assert result.return_3d is None
        assert result.return_5d is None
        assert result.return_20d is None
        assert result.delisted_before_T1 is False
        assert result.delisted_before_T3 is True
        assert result.delisted_before_T5 is True
        assert result.delisted_before_T20 is True


class TestOutcomeComputerNullPrice:
    """Test 3: price_at_T = None."""

    def test_none_price_sets_not_computable(self) -> None:
        comp = OutcomeComputer()
        row = _make_row(price_at_T=None)
        snap = _make_snapshot(
            price_at_T=None,
            forward_prices={1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is False
        assert result.return_1d is None
        assert result.return_3d is None
        assert result.return_5d is None
        assert result.return_20d is None

    def test_delisting_flags_remain_false_when_price_none(self) -> None:
        """Delisting flags stay False — delisting is undefined without price_at_T."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=None)
        snap = _make_snapshot(price_at_T=None, forward_prices={})
        result = comp.compute(row, snap)

        assert result.delisted_before_T1 is False
        assert result.delisted_before_T3 is False
        assert result.delisted_before_T5 is False
        assert result.delisted_before_T20 is False


class TestOutcomeComputerZeroPrice:
    """Test 4: price_at_T = 0.0 — division-by-zero guard."""

    def test_zero_price_sets_not_computable(self) -> None:
        comp = OutcomeComputer()
        row = _make_row(price_at_T=0.0)
        snap = _make_snapshot(
            price_at_T=0.0,
            forward_prices={1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is False
        assert result.return_1d is None
        assert result.return_3d is None
        assert result.return_5d is None
        assert result.return_20d is None


class TestOutcomeComputerReturnCalculations:
    """Tests 5-7: Exact return arithmetic."""

    def test_negative_return_5d(self) -> None:
        """Test 5: price_at_T=2.00, forward T+5=1.60 → return_5d = -0.20."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=2.00)
        snap = _make_snapshot(
            price_at_T=2.00,
            forward_prices={1: 1.90, 3: 1.80, 5: 1.60, 20: 1.50},
        )
        result = comp.compute(row, snap)

        assert result.return_5d == pytest.approx(-0.20)
        assert result.outcome_computable is True

    def test_positive_return_20d(self) -> None:
        """Test 6: price_at_T=1.00, forward T+20=1.50 → return_20d = +0.50."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=1.00)
        snap = _make_snapshot(
            price_at_T=1.00,
            forward_prices={1: 1.10, 3: 1.20, 5: 1.30, 20: 1.50},
        )
        result = comp.compute(row, snap)

        assert result.return_20d == pytest.approx(0.50)
        assert result.outcome_computable is True

    def test_large_return_not_excluded(self) -> None:
        """Test 7: price_at_T=1.00, forward T+20=8.00 → return_20d = 7.00 (recorded as-is)."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=1.00)
        snap = _make_snapshot(
            price_at_T=1.00,
            forward_prices={1: 1.10, 3: 1.50, 5: 2.00, 20: 8.00},
        )
        result = comp.compute(row, snap)

        assert result.return_20d == pytest.approx(7.00)
        assert result.outcome_computable is True


class TestOutcomeComputerMiscellaneous:
    """Test 8: Additional coverage."""

    def test_outcome_computable_true_with_valid_price(self) -> None:
        """Test 8: price_at_T=5.00 with all forwards → outcome_computable=True."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=5.00)
        snap = _make_snapshot(
            price_at_T=5.00,
            forward_prices={1: 5.10, 3: 5.20, 5: 5.30, 20: 5.50},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is True

    def test_return_types_are_float(self) -> None:
        """All four return values are Python float, not int."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=10.00)
        snap = _make_snapshot(
            price_at_T=10.00,
            forward_prices={1: 9.50, 3: 9.20, 5: 9.00, 20: 8.00},
        )
        result = comp.compute(row, snap)

        assert isinstance(result.return_1d, float)
        assert isinstance(result.return_3d, float)
        assert isinstance(result.return_5d, float)
        assert isinstance(result.return_20d, float)

    def test_outcome_computable_true_even_when_all_delistings(self) -> None:
        """price_at_T valid but all forward prices None → outcome_computable=True."""
        comp = OutcomeComputer()
        row = _make_row(price_at_T=5.00)
        snap = _make_snapshot(
            price_at_T=5.00,
            forward_prices={1: None, 3: None, 5: None, 20: None},
        )
        result = comp.compute(row, snap)

        assert result.outcome_computable is True
        assert result.return_1d is None
        assert result.delisted_before_T1 is True
