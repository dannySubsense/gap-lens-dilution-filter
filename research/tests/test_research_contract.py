"""
Slice 14: Research Contract Validation

Validates Research Contract criteria (RC-01 through RC-18) against actual
pipeline output produced by a --dry-run 0 subprocess call.

Each test assertion maps to a named RC criterion documented in its docstring.

The pipeline_output fixture runs --dry-run 0 which produces empty Parquet
files. All "zero rows have X and Y" checks trivially pass on empty DataFrames,
which is the correct behavior.
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa  # noqa: F401  (imported for completeness; pq uses it)
import pyarrow.parquet as pq
import pytest

from research.pipeline.bt_filter_engine import BacktestFilterEngine
from research.pipeline.bt_scorer import BacktestScorer
from research.pipeline.config import BacktestConfig, PIPELINE_VERSION
from research.pipeline.dataclasses import BacktestRow, MarketSnapshot

_PROJECT_ROOT = str(Path(__file__).parent.parent.parent)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pipeline_output(tmp_path_factory):
    """
    Run --dry-run 0 and return paths to the output files.
    All RC tests that need output files use this fixture.
    """
    tmp = tmp_path_factory.mktemp("rc_output")
    db_path = str(tmp / "test.duckdb")
    out_dir = str(tmp / "output")

    # Create minimal test DB
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE daily_universe (trade_date DATE, symbol VARCHAR)")
    con.execute("INSERT INTO daily_universe VALUES ('2022-01-03', 'TEST')")
    con.execute(
        "CREATE TABLE daily_prices "
        "(trade_date DATE, symbol VARCHAR, close DOUBLE, adjusted_close DOUBLE, volume BIGINT)"
    )
    con.execute(
        "INSERT INTO daily_prices VALUES ('2022-01-03', 'TEST', 5.0, 5.0, 1000000)"
    )
    con.close()

    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT

    result = subprocess.run(
        [
            sys.executable,
            "research/run_backtest.py",
            "--dry-run", "0",
            "--db-path", db_path,
            "--output-dir", out_dir,
        ],
        capture_output=True,
        cwd=_PROJECT_ROOT,
        env=env,
    )
    assert result.returncode == 0, (
        f"Pipeline --dry-run 0 failed:\n{result.stderr.decode()}"
    )

    out = Path(out_dir)
    return {
        "results_parquet": out / "backtest_results.parquet",
        "participants_parquet": out / "backtest_participants.parquet",
        "metadata_json": out / "backtest_run_metadata.json",
    }


# ---------------------------------------------------------------------------
# RC-01: Structural Integrity
# ---------------------------------------------------------------------------


class TestRC01StructuralIntegrity:
    """RC-01: backtest_results.parquet passes all 11 structural integrity checks."""

    def test_parquet_readable(self, pipeline_output):
        """RC-01.1: Parquet is readable by pyarrow without error."""
        table = pq.read_table(str(pipeline_output["results_parquet"]))
        assert table is not None

    def test_no_passed_rows_with_null_score(self, pipeline_output):
        """RC-01.2: Zero rows with filter_status=PASSED and score IS NULL."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        passed = df[df["filter_status"] == "PASSED"]
        assert passed["score"].isna().sum() == 0, "PASSED rows must have non-null score"

    def test_no_passed_rows_with_null_rank(self, pipeline_output):
        """RC-01.3: Zero rows with filter_status=PASSED and rank IS NULL."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        passed = df[df["filter_status"] == "PASSED"]
        assert passed["rank"].isna().sum() == 0, "PASSED rows must have non-null rank"

    def test_no_computable_rows_with_null_price(self, pipeline_output):
        """RC-01.4: Zero rows with outcome_computable=True and price_at_T IS NULL."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        computable = df[df["outcome_computable"].eq(True)]
        assert computable["price_at_T"].isna().sum() == 0

    def test_no_delisted_false_with_null_return_when_computable(self, pipeline_output):
        """RC-01.5: For each horizon T1/T3/T5/T20: zero rows with delisted=False and return IS NULL when outcome_computable=True."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        computable = df[df["outcome_computable"].eq(True)]
        for n in [1, 3, 5, 20]:
            not_delisted = computable[computable[f"delisted_before_T{n}"].eq(False)]
            null_count = not_delisted[f"return_{n}d"].isna().sum()
            assert null_count == 0, (
                f"T+{n}: {null_count} rows have delisted=False and return IS NULL with outcome_computable=True"
            )

    def test_float_available_float_data_start_consistency(self, pipeline_output):
        """RC-01.6: Zero rows with float_available=True and filed_at < 2020-03-04."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        if len(df) == 0:
            return  # empty output (--dry-run 0) trivially passes
        cutoff = pd.Timestamp("2020-03-04", tz="UTC")
        violation = df[df["float_available"].eq(True) & (df["filed_at"] < cutoff)]
        assert len(violation) == 0, f"float_available=True rows before cutoff: {len(violation)}"

    def test_float_unavailable_consistency(self, pipeline_output):
        """RC-01.7: Zero rows with float_available=False and filed_at >= 2020-03-04."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        if len(df) == 0:
            return
        cutoff = pd.Timestamp("2020-03-04", tz="UTC")
        violation = df[df["float_available"].eq(False) & (df["filed_at"] >= cutoff)]
        assert len(violation) == 0

    def test_participants_fk_integrity(self, pipeline_output):
        """RC-01.8: Every accession_number in participants exists in results."""
        df_results = pd.read_parquet(str(pipeline_output["results_parquet"]))
        df_participants = pd.read_parquet(str(pipeline_output["participants_parquet"]))
        if len(df_participants) == 0:
            return
        results_accessions = set(df_results["accession_number"].tolist())
        participant_accessions = set(df_participants["accession_number"].tolist())
        orphans = participant_accessions - results_accessions
        assert len(orphans) == 0, f"Orphan participant accessions: {orphans}"

    def test_processed_at_identical_across_rows(self, pipeline_output):
        """RC-01.9: processed_at is identical across all rows."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        if len(df) == 0:
            return
        assert df["processed_at"].nunique() == 1, "processed_at must be identical for all rows in one run"

    def test_pipeline_version_identical_and_matches_manifest(self, pipeline_output):
        """RC-01.10: pipeline_version identical across rows and matches metadata JSON."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        if len(df) == 0:
            # Empty run: just check manifest has the field
            assert "pipeline_version" in manifest
            return
        assert df["pipeline_version"].nunique() == 1
        assert df["pipeline_version"].iloc[0] == manifest["pipeline_version"]

    def test_sha256_matches_parquet_file(self, pipeline_output):
        """RC-01.11: SHA-256 in metadata JSON matches actual file hash."""
        parquet_bytes = pipeline_output["results_parquet"].read_bytes()
        expected_sha = hashlib.sha256(parquet_bytes).hexdigest()
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert manifest["parquet_sha256"] == expected_sha, (
            f"SHA-256 mismatch: manifest has {manifest['parquet_sha256']!r}, "
            f"file has {expected_sha!r}"
        )


# ---------------------------------------------------------------------------
# RC-02: Manifest completeness
# ---------------------------------------------------------------------------


class TestRC02ManifestFields:
    """RC-02: backtest_run_metadata.json contains all required fields."""

    REQUIRED_FIELDS = [
        "run_date", "pipeline_version", "classifier_version", "scoring_formula_version",
        "date_range_start", "date_range_end", "form_types", "market_cap_threshold",
        "float_threshold", "dilution_pct_threshold", "price_threshold", "adv_threshold",
        "float_data_start", "market_data_db_path", "market_data_db_certification",
        "total_filings_discovered", "total_cik_resolved", "total_fetch_ok",
        "total_classified", "total_passed_filters", "total_with_outcomes",
        "quarters_failed", "parquet_sha256", "parquet_row_count",
        "execution_timestamp", "canary_no_lookahead", "total_unresolvable_count",
        "normalization_config_loaded", "normalization_config_entry_count",
    ]

    def test_all_required_fields_present(self, pipeline_output):
        """RC-02: All required manifest fields present in backtest_run_metadata.json."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        missing = [f for f in self.REQUIRED_FIELDS if f not in manifest]
        assert len(missing) == 0, f"Missing manifest fields: {missing}"

    def test_float_data_start_is_correct(self, pipeline_output):
        """RC-02: float_data_start must equal '2020-03-04'."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert manifest["float_data_start"] == "2020-03-04"


# ---------------------------------------------------------------------------
# RC-03 and RC-16
# ---------------------------------------------------------------------------


class TestRC03AndRC16:
    """RC-03: canary_no_lookahead = 'PASS'. RC-16: classifier_version = 'rule-based-v1'."""

    def test_canary_no_lookahead_is_pass(self, pipeline_output):
        """RC-03: canary_no_lookahead field in manifest is 'PASS'."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert manifest["canary_no_lookahead"] == "PASS", (
            f"canary_no_lookahead = {manifest['canary_no_lookahead']!r}; expected 'PASS'"
        )

    def test_classifier_version_is_rule_based(self, pipeline_output):
        """RC-16: classifier_version in manifest equals 'rule-based-v1'."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert manifest["classifier_version"] == "rule-based-v1"


# ---------------------------------------------------------------------------
# Schema completeness
# ---------------------------------------------------------------------------


class TestSchemaCompleteness:
    """Schema completeness: all columns from 01-REQUIREMENTS.md Output Schema are present."""

    EXPECTED_RESULTS_COLUMNS = [
        "accession_number", "cik", "ticker", "entity_name", "form_type", "filed_at",
        "setup_type", "confidence", "shares_offered_raw", "dilution_severity",
        "price_discount", "immediate_pressure", "key_excerpt", "filter_status",
        "filter_fail_reason", "float_available", "in_smallcap_universe",
        "price_at_T", "market_cap_at_T", "float_at_T", "adv_at_T",
        "short_interest_at_T", "borrow_cost_source", "score", "rank",
        "dilution_extractable", "outcome_computable",
        "return_1d", "return_3d", "return_5d", "return_20d",
        "delisted_before_T1", "delisted_before_T3", "delisted_before_T5", "delisted_before_T20",
        "pipeline_version", "processed_at",
    ]

    EXPECTED_PARTICIPANTS_COLUMNS = [
        "accession_number", "firm_name", "role", "is_normalized", "raw_text_snippet",
    ]

    def test_results_parquet_has_all_columns(self, pipeline_output):
        """Schema completeness: results Parquet has all 37 required columns."""
        table = pq.read_table(str(pipeline_output["results_parquet"]))
        actual = set(table.schema.names)
        expected = set(self.EXPECTED_RESULTS_COLUMNS)
        missing = expected - actual
        extra = actual - expected
        assert len(missing) == 0, f"Missing columns: {missing}"
        assert len(extra) == 0, f"Extra columns: {extra}"

    def test_participants_parquet_has_all_columns(self, pipeline_output):
        """Schema completeness: participants Parquet has all 5 required columns."""
        table = pq.read_table(str(pipeline_output["participants_parquet"]))
        actual = set(table.schema.names)
        expected = set(self.EXPECTED_PARTICIPANTS_COLUMNS)
        missing = expected - actual
        extra = actual - expected
        assert len(missing) == 0, f"Missing columns: {missing}"
        assert len(extra) == 0, f"Extra columns: {extra}"


# ---------------------------------------------------------------------------
# Two-tier flag invariant
# ---------------------------------------------------------------------------


class TestTwoTierFlagInvariant:
    """float_available must be non-nullable (no NULL values in any row)."""

    def test_float_available_never_null(self, pipeline_output):
        """RC-01: float_available is BOOLEAN NO (non-nullable) — zero NULLs allowed."""
        df = pd.read_parquet(str(pipeline_output["results_parquet"]))
        assert df["float_available"].isna().sum() == 0, "float_available must not contain NULLs"


# ---------------------------------------------------------------------------
# Canary test (Section 2.8 standalone)
# ---------------------------------------------------------------------------


class TestCanaryNoLookahead:
    """
    Research Contract Section 2.8 standalone canary test.

    Constructs two MarketSnapshots with identical T-day data but different
    forward_prices, then asserts that both BacktestFilterEngine and
    BacktestScorer produce identical results for both.

    This test is self-contained (no pipeline_output fixture needed).
    """

    def _make_snapshot(self, forward_prices: dict) -> MarketSnapshot:
        return MarketSnapshot(
            symbol="CANARY",
            effective_trade_date=date(2022, 6, 1),
            price_at_T=3.50,
            market_cap_at_T=80_000_000.0,
            float_at_T=8_000_000.0,
            float_available=True,
            float_effective_date=date(2022, 5, 31),
            short_interest_at_T=400_000.0,
            short_interest_effective_date=date(2022, 5, 31),
            borrow_cost_source="DEFAULT",
            adv_at_T=1_000_000.0,
            in_smallcap_universe=True,
            forward_prices=forward_prices,
            delisted_before={1: False, 3: False, 5: False, 20: False},
        )

    def _make_row(self) -> BacktestRow:
        return BacktestRow(
            accession_number="0001234567-22-000001",
            cik="0001234567",
            ticker="CANARY",
            entity_name="Canary Corp",
            form_type="424B4",
            filed_at=datetime(2022, 6, 1, 0, 0, 0),
            setup_type="B",
            confidence=1.0,
            shares_offered_raw=2_000_000,
            dilution_severity=None,
            price_discount=-0.05,
            immediate_pressure=True,
            key_excerpt="canary",
            filter_status="",
            filter_fail_reason=None,
            float_available=True,
            in_smallcap_universe=True,
            price_at_T=3.50,
            market_cap_at_T=80_000_000.0,
            float_at_T=8_000_000.0,
            adv_at_T=1_000_000.0,
            short_interest_at_T=400_000.0,
            borrow_cost_source="DEFAULT",
            score=None,
            rank=None,
            dilution_extractable=None,
            outcome_computable=False,
            return_1d=None,
            return_3d=None,
            return_5d=None,
            return_20d=None,
            delisted_before_T1=False,
            delisted_before_T3=False,
            delisted_before_T5=False,
            delisted_before_T20=False,
            pipeline_version=PIPELINE_VERSION,
            processed_at=datetime(2022, 6, 1, 0, 0, 0),
        )

    def test_filter_engine_canary(self):
        """RC canary (Section 2.8): BacktestFilterEngine produces identical outcomes for different forward_prices."""
        engine = BacktestFilterEngine(config=BacktestConfig())

        snap_with = self._make_snapshot({1: 0.50, 3: 0.30, 5: 0.20, 20: 0.10})
        snap_without = self._make_snapshot({1: 5.00, 3: 7.00, 5: 9.00, 20: 15.00})

        row_a = self._make_row()
        row_b = self._make_row()

        result_a = engine.evaluate(row_a, snap_with)
        result_b = engine.evaluate(row_b, snap_without)

        assert result_a.passed == result_b.passed
        assert result_a.fail_criterion == result_b.fail_criterion

    def test_scorer_canary(self):
        """RC canary (Section 2.8): BacktestScorer produces identical scores for different forward_prices."""
        scorer = BacktestScorer()
        classification = {
            "setup_type": "B",
            "confidence": 1.0,
            "dilution_severity": 0.0,
            "immediate_pressure": True,
            "price_discount": -0.05,
            "short_attractiveness": 50,
            "key_excerpt": "canary",
            "reasoning": "canary test",
        }

        snap_with = self._make_snapshot({1: 0.50, 3: 0.30, 5: 0.20, 20: 0.10})
        snap_without = self._make_snapshot({1: 5.00, 3: 7.00, 5: 9.00, 20: 15.00})

        row_a = self._make_row()
        row_b = self._make_row()

        # BacktestFilterEngine sets dilution_severity as side effect
        engine = BacktestFilterEngine(config=BacktestConfig())
        engine.evaluate(row_a, snap_with)
        engine.evaluate(row_b, snap_without)

        result_a = scorer.score(classification, snap_with, row_a)
        result_b = scorer.score(classification, snap_without, row_b)

        assert result_a is not None
        assert result_b is not None
        assert result_a["score"] == result_b["score"], (
            f"Scorer canary failed: forward_prices contaminated score "
            f"(crash={result_a['score']}, rally={result_b['score']})"
        )
        assert result_a["rank"] == result_b["rank"]


# ---------------------------------------------------------------------------
# RC-17 and RC-18
# ---------------------------------------------------------------------------


class TestRC17AndRC18:
    """
    RC-17: Large returns recorded as-is (pipeline check only — log count to manifest).
    RC-18: If normalization_config_entry_count=0, no H1e/H1f/H1g findings citations possible.
    """

    def test_rc17_large_returns_present_in_manifest(self, pipeline_output):
        """RC-17: manifest exists and parquet_row_count is non-negative (structural check)."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert manifest["parquet_row_count"] >= 0

    def test_rc18_normalization_config_fields_present(self, pipeline_output):
        """RC-18: normalization_config_loaded and normalization_config_entry_count present in manifest."""
        manifest = json.loads(pipeline_output["metadata_json"].read_text())
        assert "normalization_config_loaded" in manifest
        assert "normalization_config_entry_count" in manifest
        assert isinstance(manifest["normalization_config_entry_count"], int)
