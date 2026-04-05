"""
Tests for Slice 12: OutputWriter and RunManifest.

Tests:
1. OutputWriter.write() with 3 synthetic BacktestRow objects produces a
   readable Parquet file (pyarrow.parquet.read_table() succeeds).
2. The written Parquet contains exactly the columns listed in the schema
   (no extra, no missing columns).
3. Rows are sorted by (cik, filed_at, accession_number) in the output Parquet.
4. processed_at is identical across all rows.
5. pipeline_version is identical across all rows and matches the value in the
   metadata JSON.
6. SHA-256 in backtest_run_metadata.json matches hashlib.sha256 of the written
   Parquet file.
7. RunManifest with zero quarters_failed writes "quarters_failed": [] in JSON.
8. Writing backtest_participants with zero rows produces a valid empty Parquet
   file (not an error).
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from research.pipeline.dataclasses import BacktestRow, ParticipantRecord
from research.pipeline.output_writer import OutputWriter, RESULTS_SCHEMA
from research.pipeline.run_manifest import RunManifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manifest(**overrides) -> RunManifest:
    defaults = dict(
        run_date="2026-04-05T00:00:00Z",
        pipeline_version="backtest-v1.0.0",
        classifier_version="rule-based-v1",
        scoring_formula_version="v1.0",
        date_range_start="2022-01-01",
        date_range_end="2022-12-31",
        form_types=["424B4", "S-1"],
        market_cap_threshold=2_000_000_000,
        float_threshold=50_000_000,
        dilution_pct_threshold=0.10,
        price_threshold=1.00,
        adv_threshold=500_000.0,
        float_data_start="2020-03-04",
        market_data_db_path="/home/d-tuned/market_data/duckdb/market_data.duckdb",
        market_data_db_certification="v1.0.0 (certified 2026-02-19)",
        total_filings_discovered=100,
        total_cik_resolved=90,
        total_fetch_ok=85,
        total_classified=80,
        total_passed_filters=30,
        total_with_outcomes=28,
        quarters_failed=[],
        parquet_sha256="",   # populated by write()
        parquet_row_count=0,  # populated by write()
        execution_timestamp="2026-04-05T00:00:00Z",
        canary_no_lookahead="PASS",
        total_unresolvable_count=10,
        normalization_config_loaded=True,
        normalization_config_entry_count=42,
    )
    defaults.update(overrides)
    return RunManifest(**defaults)


def _make_row(
    accession_number: str = "0001234567-22-000001",
    cik: str = "0001234567",
    ticker: str = "TEST",
) -> BacktestRow:
    """Build a synthetic BacktestRow with valid data."""
    return BacktestRow(
        accession_number=accession_number,
        cik=cik,
        ticker=ticker,
        entity_name="Test Corp",
        form_type="424B4",
        filed_at=datetime(2022, 3, 15, 0, 0, 0),
        setup_type="DILUTION_PLAY",
        confidence=0.90,
        shares_offered_raw=1_000_000,
        dilution_severity=0.25,
        price_discount=0.10,
        immediate_pressure=True,
        key_excerpt="sold 1M shares at a discount",
        filter_status="PASSED",
        filter_fail_reason=None,
        float_available=True,
        in_smallcap_universe=True,
        price_at_T=3.50,
        market_cap_at_T=50_000_000.0,
        float_at_T=5_000_000.0,
        adv_at_T=750_000.0,
        short_interest_at_T=500_000.0,
        borrow_cost_source="DEFAULT",
        score=7,
        rank="B",
        dilution_extractable=True,
        outcome_computable=True,
        return_1d=-0.05,
        return_3d=-0.08,
        return_5d=-0.10,
        return_20d=-0.20,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version="backtest-v1.0.0",
        processed_at=datetime(2022, 3, 15, 0, 0, 0),
    )


def _make_three_rows() -> list[BacktestRow]:
    """
    Return 3 BacktestRow objects with distinct (cik, filed_at, accession_number)
    in deliberately unsorted order so the sort test is meaningful.
    """
    return [
        _make_row(
            accession_number="0009999999-22-000003",
            cik="0009999999",
            ticker="ZZZ",
        ),
        _make_row(
            accession_number="0001111111-22-000001",
            cik="0001111111",
            ticker="AAA",
        ),
        _make_row(
            accession_number="0005555555-22-000002",
            cik="0005555555",
            ticker="MMM",
        ),
    ]


# ---------------------------------------------------------------------------
# Test 1: Parquet file is readable
# ---------------------------------------------------------------------------

class TestOutputWriterParquetReadable:
    """Test 1: write() produces a readable Parquet file."""

    def test_parquet_readable(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()
        manifest = _make_manifest()

        writer.write(rows, [], manifest)

        parquet_path = tmp_path / "backtest_results.parquet"
        assert parquet_path.exists()
        table = pq.read_table(parquet_path)
        assert table.num_rows == 3


# ---------------------------------------------------------------------------
# Test 2: Parquet contains exactly the expected columns
# ---------------------------------------------------------------------------

class TestOutputWriterParquetColumns:
    """Test 2: Parquet column set matches the declared schema exactly."""

    def test_exact_columns(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()
        manifest = _make_manifest()

        writer.write(rows, [], manifest)

        table = pq.read_table(tmp_path / "backtest_results.parquet")
        expected_columns = [field.name for field in RESULTS_SCHEMA]
        assert list(table.schema.names) == expected_columns


# ---------------------------------------------------------------------------
# Test 3: Rows are sorted by (cik, filed_at, accession_number)
# ---------------------------------------------------------------------------

class TestOutputWriterRowSort:
    """Test 3: Output rows are sorted by (cik, filed_at, accession_number)."""

    def test_rows_sorted(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()  # deliberately unsorted CIKs: 9999, 1111, 5555
        manifest = _make_manifest()

        writer.write(rows, [], manifest)

        table = pq.read_table(tmp_path / "backtest_results.parquet")
        cik_values = table.column("cik").to_pylist()
        assert cik_values == sorted(cik_values), (
            f"CIK column is not sorted: {cik_values}"
        )


# ---------------------------------------------------------------------------
# Test 4: processed_at is identical across all rows
# ---------------------------------------------------------------------------

class TestOutputWriterProcessedAt:
    """Test 4: processed_at is identical for all rows."""

    def test_processed_at_identical(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()
        manifest = _make_manifest()

        writer.write(rows, [], manifest)

        table = pq.read_table(tmp_path / "backtest_results.parquet")
        processed_at_values = table.column("processed_at").to_pylist()
        assert len(set(processed_at_values)) == 1, (
            f"processed_at values differ across rows: {processed_at_values}"
        )


# ---------------------------------------------------------------------------
# Test 5: pipeline_version is identical across rows and matches metadata JSON
# ---------------------------------------------------------------------------

class TestOutputWriterPipelineVersion:
    """Test 5: pipeline_version matches across rows and metadata JSON."""

    def test_pipeline_version_consistent(self, tmp_path: Path) -> None:
        expected_version = "backtest-v1.0.0"
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()
        manifest = _make_manifest(pipeline_version=expected_version)

        writer.write(rows, [], manifest)

        table = pq.read_table(tmp_path / "backtest_results.parquet")
        versions = table.column("pipeline_version").to_pylist()
        assert all(v == expected_version for v in versions), (
            f"Not all pipeline_version values equal '{expected_version}': {versions}"
        )

        metadata = json.loads(
            (tmp_path / "backtest_run_metadata.json").read_text(encoding="utf-8")
        )
        assert metadata["pipeline_version"] == expected_version


# ---------------------------------------------------------------------------
# Test 6: SHA-256 in metadata JSON matches actual Parquet bytes
# ---------------------------------------------------------------------------

class TestOutputWriterSha256:
    """Test 6: SHA-256 in JSON matches hashlib.sha256 of the Parquet file."""

    def test_sha256_matches(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        rows = _make_three_rows()
        manifest = _make_manifest()

        writer.write(rows, [], manifest)

        parquet_path = tmp_path / "backtest_results.parquet"
        expected_sha256 = hashlib.sha256(parquet_path.read_bytes()).hexdigest()

        metadata = json.loads(
            (tmp_path / "backtest_run_metadata.json").read_text(encoding="utf-8")
        )
        assert metadata["parquet_sha256"] == expected_sha256


# ---------------------------------------------------------------------------
# Test 7: RunManifest with zero quarters_failed writes [] in JSON
# ---------------------------------------------------------------------------

class TestRunManifestQuartersFailed:
    """Test 7: quarters_failed=[] serialises correctly to JSON."""

    def test_empty_quarters_failed(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        manifest = _make_manifest(quarters_failed=[])

        writer.write(_make_three_rows(), [], manifest)

        metadata = json.loads(
            (tmp_path / "backtest_run_metadata.json").read_text(encoding="utf-8")
        )
        assert metadata["quarters_failed"] == []


# ---------------------------------------------------------------------------
# Test 8: Zero-row participants produces a valid empty Parquet file
# ---------------------------------------------------------------------------

class TestOutputWriterEmptyParticipants:
    """Test 8: Writing zero ParticipantRecord objects produces a valid Parquet."""

    def test_empty_participants_parquet(self, tmp_path: Path) -> None:
        writer = OutputWriter(output_dir=tmp_path)
        manifest = _make_manifest()

        writer.write(_make_three_rows(), [], manifest)

        participants_path = tmp_path / "backtest_participants.parquet"
        assert participants_path.exists()
        table = pq.read_table(participants_path)
        assert table.num_rows == 0
        # Schema must still have the expected columns
        assert "accession_number" in table.schema.names
        assert "firm_name" in table.schema.names
        assert "role" in table.schema.names
        assert "is_normalized" in table.schema.names
        assert "raw_text_snippet" in table.schema.names
