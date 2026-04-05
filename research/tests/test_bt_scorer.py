"""
Tests for Slice 10: BacktestScorer.

Tests
-----
1.  setup_type=None → returns None (no-match filing, do not score).
2.  adv_at_T=None   → returns None (missing ADV, cannot score).
3.  adv_at_T=0.0    → returns None (zero ADV guard, avoid division by zero).
4.  PASSED filing with valid market data → score in [0, 100], rank in {A,B,C,D}.
5.  Dilution severity patching: row.dilution_severity=0.5 overrides
    classification["dilution_severity"]=0.0; score changes accordingly.
6.  borrow_cost_source is always "DEFAULT" for all valid inputs.
7.  CANARY: Two MarketSnapshots with identical T-day data but different
    forward_prices → identical score and rank.
8.  Score normalization: raw_score above score_normalization_ceiling → score=100
    and rank="A".
"""

import dataclasses
from datetime import date

import pytest

from app.core.config import settings
from research.pipeline.bt_scorer import BacktestScorer
from research.pipeline.dataclasses import BacktestMarketData, BacktestRow, MarketSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(
    adv_at_T: float | None = 2_000_000.0,
    float_at_T: float | None = 10_000_000.0,
    price_at_T: float | None = 5.0,
    market_cap_at_T: float | None = 100_000_000.0,
    short_interest_at_T: float | None = 500_000.0,
    forward_prices: dict | None = None,
) -> MarketSnapshot:
    """Build a minimal MarketSnapshot for testing."""
    return MarketSnapshot(
        symbol="TEST",
        effective_trade_date=date(2022, 3, 15),
        price_at_T=price_at_T,
        market_cap_at_T=market_cap_at_T,
        float_at_T=float_at_T,
        float_available=float_at_T is not None,
        float_effective_date=date(2022, 3, 15) if float_at_T is not None else None,
        short_interest_at_T=short_interest_at_T,
        short_interest_effective_date=date(2022, 3, 15) if short_interest_at_T is not None else None,
        borrow_cost_source="DEFAULT",
        adv_at_T=adv_at_T,
        in_smallcap_universe=True,
        forward_prices=forward_prices or {},
        delisted_before={},
    )


def _make_row(
    dilution_severity: float | None = 0.25,
    setup_type: str | None = "B",
    score: int | None = None,
    rank: str | None = None,
) -> BacktestRow:
    """Build a minimal BacktestRow for testing."""
    from datetime import datetime

    return BacktestRow(
        accession_number="0001234567-22-000123",
        cik="0001234567",
        ticker="TEST",
        entity_name="Test Corp",
        form_type="424B4",
        filed_at=datetime(2022, 3, 15, 0, 0, 0),
        setup_type=setup_type,
        confidence=1.0,
        shares_offered_raw=2_500_000,
        dilution_severity=dilution_severity,
        price_discount=-0.10,
        immediate_pressure=True,
        key_excerpt="We are offering 2,500,000 shares.",
        filter_status="PASSED",
        filter_fail_reason=None,
        float_available=True,
        in_smallcap_universe=True,
        price_at_T=5.0,
        market_cap_at_T=100_000_000.0,
        float_at_T=10_000_000.0,
        adv_at_T=2_000_000.0,
        short_interest_at_T=500_000.0,
        borrow_cost_source="DEFAULT",
        score=score,
        rank=rank,
        dilution_extractable=True,
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
        processed_at=datetime(2026, 4, 5, 0, 0, 0),
    )


def _make_classification(
    setup_type: str | None = "B",
    dilution_severity: float = 0.0,
) -> dict:
    """Build a minimal ClassificationResult dict for testing."""
    return {
        "setup_type": setup_type,
        "confidence": 1.0 if setup_type is not None else 0.0,
        "dilution_severity": dilution_severity,
        "immediate_pressure": True,
        "price_discount": -0.10,
        "short_attractiveness": 50,
        "key_excerpt": "We are offering shares.",
        "reasoning": "Takedown offering with discount.",
    }


# ---------------------------------------------------------------------------
# Test 1: setup_type=None → None
# ---------------------------------------------------------------------------

class TestSetupTypeNoneReturnsNone:
    def test_none_setup_type_returns_none(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type=None)
        snapshot = _make_snapshot()
        row = _make_row(setup_type=None)

        result = scorer.score(classification, snapshot, row)

        assert result is None

    def test_none_setup_type_returns_none_regardless_of_adv(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type=None)
        snapshot = _make_snapshot(adv_at_T=5_000_000.0)
        row = _make_row(setup_type=None)

        result = scorer.score(classification, snapshot, row)

        assert result is None


# ---------------------------------------------------------------------------
# Test 2: adv_at_T=None → None
# ---------------------------------------------------------------------------

class TestAdvAtTNoneReturnsNone:
    def test_adv_none_returns_none(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        snapshot = _make_snapshot(adv_at_T=None)
        row = _make_row()

        result = scorer.score(classification, snapshot, row)

        assert result is None


# ---------------------------------------------------------------------------
# Test 3: adv_at_T=0.0 → None
# ---------------------------------------------------------------------------

class TestAdvAtTZeroReturnsNone:
    def test_adv_zero_returns_none(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        snapshot = _make_snapshot(adv_at_T=0.0)
        row = _make_row()

        result = scorer.score(classification, snapshot, row)

        assert result is None

    def test_adv_negative_returns_none(self):
        # Defensive: negative ADV is also invalid.
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        snapshot = _make_snapshot(adv_at_T=-1.0)
        row = _make_row()

        result = scorer.score(classification, snapshot, row)

        assert result is None


# ---------------------------------------------------------------------------
# Test 4: Valid inputs → score in [0, 100], rank in {A, B, C, D}
# ---------------------------------------------------------------------------

class TestValidInputsProduceScore:
    def test_passed_filing_returns_valid_score(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        snapshot = _make_snapshot()
        row = _make_row(dilution_severity=0.25)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert isinstance(result["score"], int)
        assert 0 <= result["score"] <= 100
        assert result["rank"] in {"A", "B", "C", "D"}

    def test_result_contains_required_keys(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="A")
        snapshot = _make_snapshot(adv_at_T=1_000_000.0)
        row = _make_row(dilution_severity=0.30)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert set(result.keys()) == {"score", "rank", "raw_score", "borrow_cost_source"}

    def test_raw_score_is_float(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="C")
        snapshot = _make_snapshot()
        row = _make_row(dilution_severity=0.20)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert isinstance(result["raw_score"], float)


# ---------------------------------------------------------------------------
# Test 5: Dilution severity patching
# ---------------------------------------------------------------------------

class TestDilutionSeverityPatching:
    """
    Verifies that row.dilution_severity overrides classification["dilution_severity"].
    The live classifier always returns dilution_severity=0.0; the backtest must
    patch this with the computed value before calling Scorer.score().
    """

    def test_patching_changes_score(self):
        scorer = BacktestScorer()
        snapshot = _make_snapshot(adv_at_T=2_000_000.0)

        # Classification has dilution_severity=0.0 (live classifier default).
        classification_zero = _make_classification(setup_type="B", dilution_severity=0.0)

        # Row with dilution_severity=0.0 (no float data).
        row_zero = _make_row(dilution_severity=0.0)

        # Row with dilution_severity=0.5 (patched from computed value).
        row_patched = _make_row(dilution_severity=0.5)

        result_zero = scorer.score(classification_zero, snapshot, row_zero)
        result_patched = scorer.score(classification_zero, snapshot, row_patched)

        assert result_zero is not None
        assert result_patched is not None
        # dilution_severity=0.5 produces a non-zero raw_score; 0.0 produces 0.
        assert result_patched["score"] != result_zero["score"], (
            "Dilution severity patching must change the score: "
            f"zero={result_zero['score']}, patched={result_patched['score']}"
        )

    def test_zero_dilution_severity_produces_zero_score(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B", dilution_severity=0.0)
        snapshot = _make_snapshot(adv_at_T=2_000_000.0)
        row = _make_row(dilution_severity=0.0)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        # dilution_severity=0 → raw_score=0 → score=0.
        assert result["score"] == 0

    def test_none_dilution_severity_falls_back_to_zero(self):
        """row.dilution_severity=None must fall back to 0.0 (live pipeline behaviour)."""
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B", dilution_severity=0.0)
        snapshot = _make_snapshot(adv_at_T=2_000_000.0)
        row = _make_row(dilution_severity=None)

        result = scorer.score(classification, snapshot, row)

        # None → fallback to 0.0 → score = 0.
        assert result is not None
        assert result["score"] == 0


# ---------------------------------------------------------------------------
# Test 6: borrow_cost_source is always "DEFAULT"
# ---------------------------------------------------------------------------

class TestBorrowCostSourceAlwaysDefault:
    def test_borrow_cost_source_default_when_short_interest_available(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="A")
        # Snapshot has both short_interest_at_T and float_at_T.
        snapshot = _make_snapshot(
            short_interest_at_T=500_000.0,
            float_at_T=10_000_000.0,
        )
        row = _make_row(dilution_severity=0.25)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert result["borrow_cost_source"] == "DEFAULT"

    def test_borrow_cost_source_default_when_short_interest_none(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        snapshot = _make_snapshot(short_interest_at_T=None)
        row = _make_row(dilution_severity=0.25)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert result["borrow_cost_source"] == "DEFAULT"

    def test_borrow_cost_source_default_all_setup_types(self):
        scorer = BacktestScorer()
        snapshot = _make_snapshot()
        for st in ("A", "B", "C", "D", "E"):
            classification = _make_classification(setup_type=st)
            row = _make_row(setup_type=st, dilution_severity=0.20)
            result = scorer.score(classification, snapshot, row)
            assert result is not None
            assert result["borrow_cost_source"] == "DEFAULT", (
                f"Expected DEFAULT for setup_type={st}, got {result['borrow_cost_source']}"
            )


# ---------------------------------------------------------------------------
# Test 7: CANARY — forward_prices must not affect score or rank
# ---------------------------------------------------------------------------

class TestCanaryNoLookahead:
    """
    Research Contract Section 2.8 canary test.

    Two MarketSnapshots with identical T-day data but different forward_prices
    must produce identical score and rank. This guarantees that no outcome
    data leaks into the scoring step.
    """

    def test_different_forward_prices_produce_identical_score(self):
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        row = _make_row(dilution_severity=0.25)

        snapshot_with_prices = _make_snapshot(
            forward_prices={1: 0.95, 3: 0.88, 5: 0.82, 20: 0.70},
        )
        snapshot_without_prices = _make_snapshot(
            forward_prices={1: None, 3: None, 5: None, 20: None},
        )

        result_with = scorer.score(classification, snapshot_with_prices, row)
        result_without = scorer.score(classification, snapshot_without_prices, row)

        assert result_with is not None
        assert result_without is not None

        assert result_with["score"] == result_without["score"], (
            f"Score contaminated by forward_prices: "
            f"with={result_with['score']}, without={result_without['score']}"
        )
        assert result_with["rank"] == result_without["rank"], (
            f"Rank contaminated by forward_prices: "
            f"with={result_with['rank']}, without={result_without['rank']}"
        )

    def test_extreme_forward_prices_do_not_change_score(self):
        """Extreme forward prices (crash vs. rally) must not affect T-day score."""
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="A")
        row = _make_row(dilution_severity=0.30, setup_type="A")

        snapshot_crash = _make_snapshot(
            forward_prices={1: 0.50, 3: 0.30, 5: 0.20, 20: 0.10},
        )
        snapshot_rally = _make_snapshot(
            forward_prices={1: 1.50, 3: 2.00, 5: 3.00, 20: 5.00},
        )

        result_crash = scorer.score(classification, snapshot_crash, row)
        result_rally = scorer.score(classification, snapshot_rally, row)

        assert result_crash is not None
        assert result_rally is not None
        assert result_crash["score"] == result_rally["score"]
        assert result_crash["rank"] == result_rally["rank"]


# ---------------------------------------------------------------------------
# Test 8: Score normalization ceiling
# ---------------------------------------------------------------------------

class TestScoreNormalization:
    """
    A raw_score above score_normalization_ceiling must map to score=100 and rank="A".
    score_normalization_ceiling is 1.0 per settings.
    """

    def test_very_high_dilution_severity_maps_to_100(self):
        """
        raw_score = dilution_severity * (adv_min_threshold/adv_dollar) * setup_quality / borrow_cost
        To guarantee raw_score > ceiling (1.0), use dilution_severity=10.0.
        With adv_dollar=adv_min_threshold (ratio=1.0), setup_quality_b=0.55,
        borrow_cost=0.30:
          raw_score = 10.0 * 1.0 * 0.55 / 0.30 ≈ 18.3  (>> 1.0 ceiling)
        """
        scorer = BacktestScorer()
        classification = _make_classification(setup_type="B")
        # adv_dollar == adv_min_threshold so float_illiquidity = 1.0.
        snapshot = _make_snapshot(adv_at_T=settings.adv_min_threshold)
        row = _make_row(dilution_severity=10.0)

        result = scorer.score(classification, snapshot, row)

        assert result is not None
        assert result["score"] == 100
        assert result["rank"] == "A"
        assert result["raw_score"] > settings.score_normalization_ceiling


# ---------------------------------------------------------------------------
# Structural guard: BacktestMarketData has exactly four fields
# ---------------------------------------------------------------------------

class TestBacktestMarketDataStructure:
    def test_exactly_four_fields(self):
        fields = dataclasses.fields(BacktestMarketData)
        field_names = {f.name for f in fields}
        assert field_names == {"adv_dollar", "float_shares", "price", "market_cap"}, (
            f"BacktestMarketData must have exactly four fields, found: {field_names}"
        )

    def test_no_forward_price_fields(self):
        fields = dataclasses.fields(BacktestMarketData)
        for f in fields:
            assert "forward" not in f.name.lower(), (
                f"BacktestMarketData must not contain forward-price fields: {f.name}"
            )
            assert "return" not in f.name.lower(), (
                f"BacktestMarketData must not contain return fields: {f.name}"
            )

    def test_five_fields_raises_type_error(self):
        with pytest.raises(TypeError):
            BacktestMarketData(
                adv_dollar=1.0,
                float_shares=1.0,
                price=1.0,
                market_cap=1.0,
                extra_field=1.0,  # type: ignore[call-arg]
            )
