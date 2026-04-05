"""
Tests for Slice 9: BacktestFilterEngine.

Tests:
1. All filters pass → FilterOutcome(passed=True, fail_criterion=None)
2. market_cap_at_T = None → fails with fail_criterion="MARKET_CAP"
3. float_at_T > config.float_max → fails with fail_criterion="FLOAT"
4. float_available=False with None float_at_T → float filter skipped,
   continues to next filter
5. price_at_T below config.price_min → fails with fail_criterion="PRICE"
6. in_smallcap_universe=False → fails with fail_criterion="NOT_IN_UNIVERSE"
7. Filter 1 fails → filters 2-6 not evaluated (no side effects beyond
   dilution computation)
8. Canary: two MarketSnapshots with same T-day data but different
   forward_prices produce identical FilterOutcome
"""

from datetime import date, datetime

import pytest

from research.pipeline.bt_filter_engine import BacktestFilterEngine
from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import BacktestRow, FilterOutcome, MarketSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config() -> BacktestConfig:
    """Return a default BacktestConfig."""
    return BacktestConfig()


def make_row(
    form_type: str = "424B4",
    float_available: bool = True,
    shares_offered_raw: int | None = 5_000_000,
    dilution_severity: float | None = None,
    dilution_extractable: bool | None = None,
) -> BacktestRow:
    """Build a minimal BacktestRow for testing."""
    return BacktestRow(
        accession_number="0001234567-22-000123",
        cik="0001234567",
        ticker="TEST",
        entity_name="Test Corp",
        form_type=form_type,
        filed_at=datetime(2022, 3, 15),
        setup_type="SHELF_TAKEDOWN",
        confidence=0.90,
        shares_offered_raw=shares_offered_raw,
        dilution_severity=dilution_severity,
        price_discount=0.10,
        immediate_pressure=True,
        key_excerpt="offering shares common stock",
        filter_status="",
        filter_fail_reason=None,
        float_available=float_available,
        in_smallcap_universe=True,
        price_at_T=2.50,
        market_cap_at_T=50_000_000,
        float_at_T=5_000_000.0,
        adv_at_T=800_000.0,
        short_interest_at_T=0.10,
        borrow_cost_source="DEFAULT",
        score=None,
        rank=None,
        dilution_extractable=dilution_extractable,
        outcome_computable=False,
        return_1d=None,
        return_3d=None,
        return_5d=None,
        return_20d=None,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version="backtest-v1.0.0",
        processed_at=datetime(2022, 3, 15),
    )


def make_snapshot(
    price_at_T: float | None = 2.50,
    market_cap_at_T: float | None = 50_000_000.0,
    float_at_T: float | None = 5_000_000.0,
    float_available: bool = True,
    adv_at_T: float | None = 800_000.0,
    in_smallcap_universe: bool | None = True,
    forward_prices: dict | None = None,
) -> MarketSnapshot:
    """Build a MarketSnapshot with all filters set to pass by default."""
    if forward_prices is None:
        forward_prices = {1: 2.10, 3: 1.90, 5: 1.80, 20: 1.50}
    return MarketSnapshot(
        symbol="TEST",
        effective_trade_date=date(2022, 3, 14),
        price_at_T=price_at_T,
        market_cap_at_T=market_cap_at_T,
        float_at_T=float_at_T,
        float_available=float_available,
        float_effective_date=date(2022, 3, 10),
        short_interest_at_T=0.10,
        short_interest_effective_date=date(2022, 3, 10),
        borrow_cost_source="DEFAULT",
        adv_at_T=adv_at_T,
        in_smallcap_universe=in_smallcap_universe,
        forward_prices=forward_prices,
        delisted_before={1: False, 3: False, 5: False, 20: False},
    )


# ---------------------------------------------------------------------------
# Test 1: All filters pass
# ---------------------------------------------------------------------------

class TestAllFiltersPass:
    def test_passing_snapshot_returns_passed_true(self):
        """A filing meeting all criteria returns FilterOutcome(passed=True)."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(
            form_type="424B4",
            float_available=True,
            shares_offered_raw=5_000_000,  # 5M / 5M float = 100% dilution
        )
        snapshot = make_snapshot(
            price_at_T=2.50,
            market_cap_at_T=50_000_000,
            float_at_T=5_000_000.0,
            adv_at_T=800_000.0,
            in_smallcap_universe=True,
        )
        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is True
        assert outcome.fail_criterion is None


# ---------------------------------------------------------------------------
# Test 2: market_cap_at_T = None → MARKET_CAP fail
# ---------------------------------------------------------------------------

class TestMarketCapNone:
    def test_none_market_cap_fails_market_cap_filter(self):
        """market_cap_at_T=None is treated as filter 2 failure."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(market_cap_at_T=None)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "MARKET_CAP"

    def test_market_cap_at_threshold_fails(self):
        """market_cap_at_T >= $2B fails Filter 2 with MARKET_CAP."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(market_cap_at_T=3_000_000_000)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "MARKET_CAP"


# ---------------------------------------------------------------------------
# Test 3: float_at_T > float_max → FLOAT fail
# ---------------------------------------------------------------------------

class TestFloatFail:
    def test_float_exceeds_max_fails_float_filter(self):
        """float_at_T > 50M shares fails Filter 3 with FLOAT."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True)
        snapshot = make_snapshot(float_at_T=60_000_000.0)  # > 50M threshold

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "FLOAT"

    def test_float_exactly_at_max_fails(self):
        """float_at_T == 50M shares fails (filter requires strictly < 50M)."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True)
        snapshot = make_snapshot(float_at_T=50_000_000.0)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "FLOAT"


# ---------------------------------------------------------------------------
# Test 4: float_available=False with None float_at_T → skip float filter
# ---------------------------------------------------------------------------

class TestFloatSkippedWhenUnavailable:
    def test_float_unavailable_skips_filter_3_and_4(self):
        """
        2017-2019 filing with float_available=False and None float_at_T must
        NOT fail on FLOAT or DILUTION_PCT criteria — both filters are skipped.
        """
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        # float_available=False: 2017-2019 partial tier
        row = make_row(
            float_available=False,
            shares_offered_raw=5_000_000,
        )
        # None float_at_T — would fail if Filter 3 were evaluated
        snapshot = make_snapshot(float_at_T=None, float_available=False)

        outcome = engine.evaluate(row, snapshot)

        # Must NOT fail on float or dilution criterion
        assert outcome.fail_criterion != "FLOAT"
        assert outcome.fail_criterion != "DILUTION_PCT"

    def test_float_unavailable_passes_if_other_criteria_met(self):
        """With float_available=False, a filing passing all other criteria passes."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(
            float_available=False,
            shares_offered_raw=None,
        )
        snapshot = make_snapshot(float_at_T=None, float_available=False)

        outcome = engine.evaluate(row, snapshot)

        # Other filters pass → overall pass
        assert outcome.passed is True
        assert outcome.fail_criterion is None

    def test_float_unavailable_large_float_does_not_fail(self):
        """Even if the snapshot happened to have a float value, if float_available=False
        the filter is skipped entirely."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=False)
        # Snapshot has a float value that would fail if float_available=True
        snapshot = make_snapshot(float_at_T=100_000_000.0, float_available=False)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.fail_criterion != "FLOAT"


# ---------------------------------------------------------------------------
# Test 5: price_at_T below price_min → PRICE fail
# ---------------------------------------------------------------------------

class TestPriceFail:
    def test_price_at_threshold_fails_price_filter(self):
        """price_at_T <= $1.00 fails Filter 5 with PRICE."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(price_at_T=1.00)  # at threshold, not above

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "PRICE"

    def test_price_below_min_fails(self):
        """price_at_T = $0.75 fails Filter 5."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(price_at_T=0.75)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "PRICE"

    def test_price_none_fails(self):
        """price_at_T = None fails Filter 5."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(price_at_T=None)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "PRICE"


# ---------------------------------------------------------------------------
# Test 6: in_smallcap_universe=False → NOT_IN_UNIVERSE
# ---------------------------------------------------------------------------

class TestUniverseCheck:
    def test_not_in_universe_returns_not_in_universe_criterion(self):
        """in_smallcap_universe=False → fail_criterion='NOT_IN_UNIVERSE'."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(in_smallcap_universe=False)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "NOT_IN_UNIVERSE"

    def test_universe_none_returns_not_in_universe(self):
        """in_smallcap_universe=None → fail_criterion='NOT_IN_UNIVERSE'."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(in_smallcap_universe=None)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "NOT_IN_UNIVERSE"

    def test_universe_check_runs_before_filter_1(self):
        """NOT_IN_UNIVERSE is returned even when form_type would also fail."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        # form_type would fail Filter 1
        row = make_row(form_type="DEF 14A")
        snapshot = make_snapshot(in_smallcap_universe=False)

        outcome = engine.evaluate(row, snapshot)

        # Universe check fires first
        assert outcome.fail_criterion == "NOT_IN_UNIVERSE"


# ---------------------------------------------------------------------------
# Test 7: Filter 1 failure stops evaluation (no further side effects)
# ---------------------------------------------------------------------------

class TestFilterStopOnFirstFail:
    def test_filter_1_fail_stops_at_filing_type(self):
        """
        A filing with form_type='DEF 14A' (not in ALLOWED_FORM_TYPES) fails
        Filter 1. Filters 2-6 must not be evaluated.
        """
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(form_type="DEF 14A")
        # All other criteria are passing values to prove they were not reached
        snapshot = make_snapshot(
            price_at_T=2.50,
            market_cap_at_T=50_000_000,
            float_at_T=5_000_000.0,
            adv_at_T=800_000.0,
            in_smallcap_universe=True,
        )

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "FILING_TYPE"

    def test_filter_2_fail_does_not_reach_filter_3(self):
        """Market cap failure must not be overridden by a float failure."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(
            market_cap_at_T=3_000_000_000,  # fails Filter 2
            float_at_T=100_000_000.0,        # would also fail Filter 3
        )

        outcome = engine.evaluate(row, snapshot)

        # Must fail at Filter 2, not Filter 3
        assert outcome.fail_criterion == "MARKET_CAP"


# ---------------------------------------------------------------------------
# Test 8: Canary — forward_prices do not influence filter outcome
# ---------------------------------------------------------------------------

class TestCanaryNoForwardLookAhead:
    def test_different_forward_prices_produce_identical_outcomes(self):
        """
        Two MarketSnapshots with identical T-day data but opposite forward_prices
        must produce the EXACT same FilterOutcome. This proves that the engine
        never accesses forward prices during filtering.
        """
        # snapshot_a: big decline in forward prices
        snapshot_a = MarketSnapshot(
            symbol="TEST",
            effective_trade_date=date(2022, 1, 1),
            price_at_T=2.50,
            market_cap_at_T=50_000_000,
            float_at_T=5_000_000.0,
            float_available=True,
            float_effective_date=date(2021, 12, 31),
            short_interest_at_T=0.10,
            short_interest_effective_date=date(2021, 12, 31),
            borrow_cost_source="DEFAULT",
            adv_at_T=800_000.0,
            in_smallcap_universe=True,
            forward_prices={1: 2.10, 3: 1.90, 5: 1.80, 20: 1.50},  # big decline
            delisted_before={1: False, 3: False, 5: False, 20: False},
        )

        # snapshot_b: big rally in forward prices — all T-day data identical
        snapshot_b = MarketSnapshot(
            symbol="TEST",
            effective_trade_date=date(2022, 1, 1),
            price_at_T=2.50,
            market_cap_at_T=50_000_000,
            float_at_T=5_000_000.0,
            float_available=True,
            float_effective_date=date(2021, 12, 31),
            short_interest_at_T=0.10,
            short_interest_effective_date=date(2021, 12, 31),
            borrow_cost_source="DEFAULT",
            adv_at_T=800_000.0,
            in_smallcap_universe=True,
            forward_prices={1: 3.00, 3: 3.50, 5: 4.00, 20: 5.00},  # big rally
            delisted_before={1: False, 3: False, 5: False, 20: False},
        )

        engine = BacktestFilterEngine(config=make_config())

        # Same row for both evaluations
        row_a = make_row(shares_offered_raw=1_000_000)
        row_b = make_row(shares_offered_raw=1_000_000)

        result_a = engine.evaluate(row_a, snapshot_a)
        result_b = engine.evaluate(row_b, snapshot_b)

        assert result_a.passed == result_b.passed, (
            f"Forward prices contaminated filter: "
            f"result_a.passed={result_a.passed}, result_b.passed={result_b.passed}"
        )
        assert result_a.fail_criterion == result_b.fail_criterion, (
            f"Forward prices contaminated fail_criterion: "
            f"result_a={result_a.fail_criterion}, result_b={result_b.fail_criterion}"
        )

    def test_canary_with_none_vs_set_forward_prices(self):
        """
        Roadmap spec variant: forward_prices with values vs. all None must
        produce identical filter outcome.
        """
        engine = BacktestFilterEngine(config=make_config())

        row_a = make_row(shares_offered_raw=1_000_000)
        row_b = make_row(shares_offered_raw=1_000_000)

        snapshot_with_prices = make_snapshot(
            forward_prices={1: 0.95, 3: 0.88, 5: 0.82, 20: 0.70}
        )
        snapshot_with_none = make_snapshot(
            forward_prices={1: None, 3: None, 5: None, 20: None}
        )

        result_with_prices = engine.evaluate(row_a, snapshot_with_prices)
        result_with_none = engine.evaluate(row_b, snapshot_with_none)

        assert result_with_prices.passed == result_with_none.passed
        assert result_with_prices.fail_criterion == result_with_none.fail_criterion


# ---------------------------------------------------------------------------
# Test: dilution_extractable = False when float_at_T = None and float_available = True
# ---------------------------------------------------------------------------

class TestDilutionExtractable:
    def test_dilution_extractable_false_when_float_at_T_none(self):
        """
        When float_available=True but float_at_T=None, evaluate() must set
        row.dilution_extractable = False (float data expected but absent).
        """
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True, shares_offered_raw=5_000_000)
        snapshot = make_snapshot(float_at_T=None)

        engine.evaluate(row, snapshot)

        assert row.dilution_extractable is False
        assert row.dilution_severity is None

    def test_dilution_extractable_true_when_float_present(self):
        """When float_at_T is present and non-zero, dilution_extractable=True."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True, shares_offered_raw=1_000_000)
        snapshot = make_snapshot(float_at_T=5_000_000.0)

        engine.evaluate(row, snapshot)

        assert row.dilution_extractable is True
        assert row.dilution_severity == pytest.approx(1_000_000 / 5_000_000.0)

    def test_dilution_extractable_false_when_shares_none(self):
        """When shares_offered_raw=None, dilution_extractable=False."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True, shares_offered_raw=None)
        snapshot = make_snapshot(float_at_T=5_000_000.0)

        engine.evaluate(row, snapshot)

        assert row.dilution_extractable is False
        assert row.dilution_severity is None

    def test_dilution_extractable_false_when_float_zero(self):
        """When float_at_T=0.0, dilution_extractable=False (prevent division by zero)."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row(float_available=True, shares_offered_raw=5_000_000)
        snapshot = make_snapshot(float_at_T=0.0)

        engine.evaluate(row, snapshot)

        assert row.dilution_extractable is False
        assert row.dilution_severity is None


# ---------------------------------------------------------------------------
# Test: ADV filter (Filter 6)
# ---------------------------------------------------------------------------

class TestADVFilter:
    def test_adv_at_threshold_fails(self):
        """adv_at_T <= $500K fails Filter 6 with ADV (at-threshold boundary)."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(adv_at_T=500_000.0)  # exactly at threshold, not above

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "ADV"

    def test_adv_below_threshold_fails(self):
        """adv_at_T below $500K fails Filter 6."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(adv_at_T=300_000.0)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "ADV"

    def test_adv_none_fails(self):
        """adv_at_T=None fails Filter 6."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        row = make_row()
        snapshot = make_snapshot(adv_at_T=None)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "ADV"


# ---------------------------------------------------------------------------
# Test: Dilution boundary — exactly at threshold must fail (matches live engine)
# ---------------------------------------------------------------------------

class TestDilutionBoundary:
    def test_dilution_exactly_at_threshold_fails(self):
        """
        dilution_severity == dilution_pct_min (0.10 exactly) must FAIL Filter 4.
        Live FilterEngine uses `dilution_pct <= threshold` (line 105 of
        app/services/filter_engine.py). Backtest must match.
        """
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        # 1_000_000 shares / 10_000_000 float = 0.10 exactly
        row = make_row(float_available=True, shares_offered_raw=1_000_000)
        snapshot = make_snapshot(float_at_T=10_000_000.0)

        outcome = engine.evaluate(row, snapshot)

        assert outcome.passed is False
        assert outcome.fail_criterion == "DILUTION_PCT"

    def test_dilution_just_above_threshold_passes(self):
        """dilution_severity slightly above 0.10 passes Filter 4."""
        config = make_config()
        engine = BacktestFilterEngine(config=config)
        # 1_001_000 shares / 10_000_000 float = 0.1001
        row = make_row(float_available=True, shares_offered_raw=1_001_000)
        snapshot = make_snapshot(float_at_T=10_000_000.0)

        outcome = engine.evaluate(row, snapshot)

        # Should NOT fail on dilution
        assert outcome.fail_criterion != "DILUTION_PCT"
