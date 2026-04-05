"""
Smoke-level integration tests for the PipelineOrchestrator (run_backtest.py).

Tests:
  1. --help exits 0 and mentions --dry-run
  2. --dry-run 0 with a valid tmp DuckDB exits 0
  3. Non-existent DB path exits non-zero
  4. --dry-run 0 writes output files (verified in test 2)
  5. --dry-run 1 with cached EDGAR fixtures (skipped in CI)
"""

import subprocess
import sys

import pytest

# Use the same Python interpreter that is running pytest, and set PYTHONPATH
# so that `research` resolves as a top-level package from the project root.
_PYTHON = sys.executable
_PROJECT_ROOT = "/home/d-tuned/projects/gap-lens-dilution-filter"


def _run_script(*extra_args):
    """Run research/run_backtest.py with PYTHONPATH set to the project root."""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT
    return subprocess.run(
        [_PYTHON, "research/run_backtest.py", *extra_args],
        capture_output=True,
        cwd=_PROJECT_ROOT,
        env=env,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Create a minimal DuckDB with the two required tables."""
    import duckdb

    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(
        "CREATE TABLE daily_universe (trade_date DATE, symbol VARCHAR)"
    )
    con.execute(
        "INSERT INTO daily_universe VALUES ('2022-01-03', 'TEST')"
    )
    con.execute(
        "CREATE TABLE daily_prices ("
        "  trade_date DATE,"
        "  symbol VARCHAR,"
        "  close DOUBLE,"
        "  adjusted_close DOUBLE,"
        "  volume BIGINT"
        ")"
    )
    con.execute(
        "INSERT INTO daily_prices VALUES ('2022-01-03', 'TEST', 5.0, 5.0, 1000000)"
    )
    con.close()
    return db_path


# ---------------------------------------------------------------------------
# Test 1: --help
# ---------------------------------------------------------------------------

def test_help_exits_0():
    result = _run_script("--help")
    assert result.returncode == 0
    assert b"--dry-run" in result.stdout


# ---------------------------------------------------------------------------
# Test 2: --dry-run 0 with valid DB exits 0
# ---------------------------------------------------------------------------

def test_dry_run_0_exits_0(tmp_db, tmp_path):
    result = _run_script(
        "--dry-run", "0",
        "--db-path", tmp_db,
        "--output-dir", str(tmp_path / "output"),
    )
    assert result.returncode == 0, result.stderr.decode()


# ---------------------------------------------------------------------------
# Test 3: non-existent DB path exits non-zero
# ---------------------------------------------------------------------------

def test_nonexistent_db_exits_nonzero(tmp_path):
    result = _run_script(
        "--dry-run", "0",
        "--db-path", str(tmp_path / "nonexistent.duckdb"),
        "--output-dir", str(tmp_path / "output"),
    )
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# Test 4: --dry-run 0 writes output files
# ---------------------------------------------------------------------------

def test_dry_run_0_writes_output_files(tmp_db, tmp_path):
    """Verify that at least the metadata JSON is written when dry-run is 0."""
    output_dir = tmp_path / "output"
    result = _run_script(
        "--dry-run", "0",
        "--db-path", tmp_db,
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stderr.decode()
    # OutputWriter always writes the metadata JSON
    assert (output_dir / "backtest_run_metadata.json").exists(), (
        "backtest_run_metadata.json was not written"
    )


# ---------------------------------------------------------------------------
# Test 5: --dry-run 1 with cached EDGAR fixtures (manual only)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason="requires cached EDGAR fixtures — run manually after cache is populated"
)
def test_dry_run_1_with_cached_fixtures(tmp_db, tmp_path):
    """
    Full single-filing integration test.

    Requires:
      - research/cache/master_gz/ populated with at least one real .gz file
      - research/cache/filing_text/ with the corresponding filing .txt cache

    Run manually:
        pytest research/tests/test_orchestrator.py::test_dry_run_1_with_cached_fixtures -v
    """
    output_dir = tmp_path / "output"
    result = _run_script(
        "--dry-run", "1",
        "--resume",
        "--db-path", tmp_db,
        "--output-dir", str(output_dir),
    )
    assert result.returncode == 0, result.stderr.decode()
    assert (output_dir / "backtest_results.parquet").exists()
    assert (output_dir / "backtest_run_metadata.json").exists()
