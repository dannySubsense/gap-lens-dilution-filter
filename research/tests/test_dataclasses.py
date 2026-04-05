"""
Tests for Slice 1: Directory Scaffold and Shared Dataclasses.

Validates that all nine dataclasses instantiate without error and that
BacktestConfig loads correctly with the expected constants.
"""

from datetime import date, datetime

import pytest


# ---------------------------------------------------------------------------
# Dataclass instantiation tests
# ---------------------------------------------------------------------------

class TestDiscoveredFiling:
    def test_instantiates(self):
        from research.pipeline.dataclasses import DiscoveredFiling

        obj = DiscoveredFiling(
            cik="0001234567",
            entity_name="Acme Corp",
            form_type="S-1",
            date_filed=date(2022, 3, 15),
            filename="edgar/data/1234567/0001234567-22-000123.txt",
            accession_number="0001234567-22-000123",
            quarter_key="2022_QTR1",
        )
        assert obj.cik == "0001234567"
        assert obj.form_type == "S-1"


class TestResolvedFiling:
    def test_instantiates(self):
        from research.pipeline.dataclasses import ResolvedFiling

        obj = ResolvedFiling(
            cik="0001234567",
            entity_name="Acme Corp",
            form_type="424B4",
            date_filed=date(2022, 3, 15),
            filename="edgar/data/1234567/0001234567-22-000124.txt",
            accession_number="0001234567-22-000124",
            quarter_key="2022_QTR1",
            ticker="ACME",
            resolution_status="RESOLVED",
            permanent_id="PERM-001",
        )
        assert obj.ticker == "ACME"
        assert obj.resolution_status == "RESOLVED"

    def test_unresolvable(self):
        from research.pipeline.dataclasses import ResolvedFiling

        obj = ResolvedFiling(
            cik="0009999999",
            entity_name="Unknown Corp",
            form_type="S-1",
            date_filed=date(2021, 6, 1),
            filename="edgar/data/9999999/0009999999-21-000001.txt",
            accession_number="0009999999-21-000001",
            quarter_key="2021_QTR2",
            ticker=None,
            resolution_status="UNRESOLVABLE",
            permanent_id=None,
        )
        assert obj.ticker is None
        assert obj.resolution_status == "UNRESOLVABLE"


class TestFetchedFiling:
    def test_instantiates(self):
        from research.pipeline.dataclasses import FetchedFiling

        obj = FetchedFiling(
            cik="0001234567",
            entity_name="Acme Corp",
            form_type="S-1",
            date_filed=date(2022, 3, 15),
            filename="edgar/data/1234567/0001234567-22-000123.txt",
            accession_number="0001234567-22-000123",
            quarter_key="2022_QTR1",
            ticker="ACME",
            resolution_status="RESOLVED",
            permanent_id=None,
            plain_text="Plan of Distribution...",
            fetch_status="OK",
            fetch_error=None,
        )
        assert obj.fetch_status == "OK"
        assert obj.plain_text is not None


class TestMarketSnapshot:
    def test_instantiates(self):
        from research.pipeline.dataclasses import MarketSnapshot

        obj = MarketSnapshot(
            symbol="ACME",
            effective_trade_date=date(2022, 3, 14),
            price_at_T=5.00,
            market_cap_at_T=50_000_000.0,
            float_at_T=10_000_000.0,
            float_available=True,
            float_effective_date=date(2022, 3, 14),
            short_interest_at_T=0.15,
            short_interest_effective_date=date(2022, 3, 14),
            borrow_cost_source="SHORT_INTEREST",
            adv_at_T=750_000.0,
            in_smallcap_universe=True,
            forward_prices={1: None, 3: 0.95, 5: None, 20: 0.80},
            delisted_before={1: False, 3: False, 5: False, 20: False},
        )
        assert obj.symbol == "ACME"
        assert obj.borrow_cost_source == "SHORT_INTEREST"

    def test_forward_prices_accepts_none_values(self):
        from research.pipeline.dataclasses import MarketSnapshot

        obj = MarketSnapshot(
            symbol="TEST",
            effective_trade_date=date(2022, 1, 3),
            price_at_T=1.50,
            market_cap_at_T=10_000_000.0,
            float_at_T=None,
            float_available=False,
            float_effective_date=None,
            short_interest_at_T=None,
            short_interest_effective_date=None,
            borrow_cost_source="DEFAULT",
            adv_at_T=600_000.0,
            in_smallcap_universe=None,
            forward_prices={1: None, 3: 0.95, 5: None, 20: 0.80},
            delisted_before={1: False, 3: False, 5: False, 20: True},
        )
        assert obj.forward_prices[1] is None
        assert obj.forward_prices[3] == pytest.approx(0.95)
        assert obj.forward_prices[5] is None
        assert obj.forward_prices[20] == pytest.approx(0.80)


class TestParticipantRecord:
    def test_instantiates(self):
        from research.pipeline.dataclasses import ParticipantRecord

        obj = ParticipantRecord(
            accession_number="0001234567-22-000123",
            firm_name="Goldman Sachs",
            role="lead_underwriter",
            is_normalized=True,
            raw_text_snippet="Goldman Sachs & Co. LLC acting as lead underwriter",
        )
        assert obj.firm_name == "Goldman Sachs"
        assert obj.role == "lead_underwriter"


class TestBacktestRow:
    def _make_row(self, **overrides):
        from research.pipeline.dataclasses import BacktestRow

        defaults = dict(
            accession_number="0001234567-22-000123",
            cik="0001234567",
            ticker="ACME",
            entity_name="Acme Corp",
            form_type="424B4",
            filed_at=datetime(2022, 3, 15, 0, 0, 0),
            setup_type="A",
            confidence=0.90,
            shares_offered_raw=5_000_000,
            dilution_severity=0.25,
            price_discount=0.10,
            immediate_pressure=True,
            key_excerpt="offering of 5,000,000 shares",
            filter_status="PASSED",
            filter_fail_reason=None,
            float_available=True,
            in_smallcap_universe=True,
            price_at_T=5.00,
            market_cap_at_T=50_000_000.0,
            float_at_T=10_000_000.0,
            adv_at_T=750_000.0,
            short_interest_at_T=0.15,
            borrow_cost_source="SHORT_INTEREST",
            score=8,
            rank="B",
            dilution_extractable=True,
            outcome_computable=True,
            return_1d=-0.05,
            return_3d=-0.08,
            return_5d=-0.12,
            return_20d=-0.20,
            delisted_before_T1=False,
            delisted_before_T3=False,
            delisted_before_T5=False,
            delisted_before_T20=False,
            pipeline_version="backtest-v1.0.0",
            processed_at=datetime(2026, 4, 5, 12, 0, 0),
        )
        defaults.update(overrides)
        return BacktestRow(**defaults)

    def test_instantiates(self):
        row = self._make_row()
        assert row.filter_status == "PASSED"
        assert row.outcome_computable is True

    def test_pipeline_error_status(self):
        row = self._make_row(filter_status="PIPELINE_ERROR")
        assert row.filter_status == "PIPELINE_ERROR"

    def test_setup_type_none_not_string_null(self):
        row = self._make_row(setup_type=None)
        assert row.setup_type is None
        assert row.setup_type != "NULL"


class TestBacktestMarketData:
    def test_instantiates(self):
        from research.pipeline.dataclasses import BacktestMarketData

        obj = BacktestMarketData(
            adv_dollar=750_000.0,
            float_shares=10_000_000.0,
            price=5.00,
            market_cap=50_000_000.0,
        )
        assert obj.adv_dollar == pytest.approx(750_000.0)
        assert obj.price == pytest.approx(5.00)


class TestFilterOutcome:
    def test_instantiates_passed(self):
        from research.pipeline.dataclasses import FilterOutcome

        obj = FilterOutcome(passed=True)
        assert obj.passed is True
        assert obj.fail_criterion is None

    def test_instantiates_failed(self):
        from research.pipeline.dataclasses import FilterOutcome

        obj = FilterOutcome(passed=False, fail_criterion="MARKET_CAP_FAIL")
        assert obj.passed is False
        assert obj.fail_criterion == "MARKET_CAP_FAIL"


class TestScorerResult:
    def test_instantiates(self):
        from research.pipeline.dataclasses import ScorerResult

        obj = ScorerResult(score=7, rank="B", raw_score=0.72)
        assert obj.score == 7
        assert obj.rank == "B"
        assert obj.raw_score == pytest.approx(0.72)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestBacktestConfig:
    def test_instantiates(self):
        from research.pipeline.config import BacktestConfig

        cfg = BacktestConfig()
        assert cfg is not None

    def test_float_data_start_date_constant(self):
        from research.pipeline.config import FLOAT_DATA_START_DATE

        assert FLOAT_DATA_START_DATE == date(2020, 3, 4)

    def test_pipeline_version(self):
        from research.pipeline.config import PIPELINE_VERSION

        assert PIPELINE_VERSION == "backtest-v1.0.0"

    def test_default_thresholds(self):
        from research.pipeline.config import BacktestConfig

        cfg = BacktestConfig()
        assert cfg.market_cap_max == 2_000_000_000
        assert cfg.float_max == 50_000_000
        assert cfg.dilution_pct_min == pytest.approx(0.10)
        assert cfg.price_min == pytest.approx(1.00)
        assert cfg.adv_min == pytest.approx(500_000)

    def test_live_settings_loaded(self):
        from research.pipeline.config import (
            DEFAULT_BORROW_COST,
            SCORE_NORMALIZATION_CEILING,
            SETUP_QUALITY,
        )

        assert isinstance(DEFAULT_BORROW_COST, float)
        assert isinstance(SCORE_NORMALIZATION_CEILING, float)
        assert isinstance(SETUP_QUALITY, dict)
        assert "A" in SETUP_QUALITY
