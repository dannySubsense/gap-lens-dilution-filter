"""
Slice 2: DuckDB Foundation — Acceptance Tests

Done-when criteria verified:
- All 7 tables created after init_db()
- init_db() is idempotent (no exception, no duplicate data)
- poll_state seed row: exactly one row with id=1
- data/filter.duckdb file created on disk after init_db()
- get_db() returns a duckdb.DuckDBPyConnection instance
- filings table has required columns
- market_data table has accession_number column
- poll_state table has exactly columns id, last_poll_at, last_success_at
- INSERT to filings works and can be read back
"""

import sys
from pathlib import Path

import duckdb
import pytest
from unittest.mock import patch

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

# Ensure project root on path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.db import _create_schema  # noqa: E402


# ---------------------------------------------------------------------------
# Shared fixture: in-memory DuckDB with schema applied
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    """In-memory DuckDB connection with the full schema applied."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# File-on-disk fixture using tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture
def disk_db(tmp_path):
    """Fixture that calls init_db() against a temporary file path and yields
    the db_path string. Resets the module-level _conn singleton before and after."""
    import app.services.db as db_module

    db_path = str(tmp_path / "test_filter.duckdb")
    original_conn = db_module._conn
    db_module._conn = None

    with patch("app.services.db.settings") as mock_settings:
        mock_settings.duckdb_path = db_path
        from app.services.db import init_db
        init_db()
        yield db_path

    # Teardown: close connection and restore original state
    if db_module._conn is not None:
        try:
            db_module._conn.close()
        except Exception:
            pass
    db_module._conn = original_conn


# ---------------------------------------------------------------------------
# AC-S2-01: All 7 tables created after init_db()
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "filings",
    "filter_results",
    "market_data",
    "labels",
    "signals",
    "poll_state",
    "cik_ticker_map",
}


def test_all_seven_tables_created(mem_db):
    """After _create_schema(), SHOW TABLES returns all 7 expected tables."""
    rows = mem_db.execute("SHOW TABLES").fetchall()
    actual_tables = {row[0] for row in rows}
    assert EXPECTED_TABLES == actual_tables, (
        f"Missing tables: {EXPECTED_TABLES - actual_tables}; "
        f"unexpected tables: {actual_tables - EXPECTED_TABLES}"
    )


# ---------------------------------------------------------------------------
# AC-S2-02: Idempotency — calling _create_schema twice raises no exception
# ---------------------------------------------------------------------------

def test_create_schema_is_idempotent():
    """Calling _create_schema() twice on the same connection must not raise."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    _create_schema(conn)  # Must not raise
    conn.close()


def test_create_schema_idempotent_does_not_duplicate_poll_state():
    """Calling _create_schema() twice must not produce more than one poll_state row."""
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    _create_schema(conn)
    count = conn.execute("SELECT COUNT(*) FROM poll_state").fetchone()[0]
    assert count == 1, f"Expected 1 poll_state row after double init, got {count}"
    conn.close()


# ---------------------------------------------------------------------------
# AC-S2-03: poll_state seed row — exactly one row with id=1
# ---------------------------------------------------------------------------

def test_poll_state_has_exactly_one_row_with_id_one(mem_db):
    """After schema creation, poll_state contains exactly one row with id=1."""
    rows = mem_db.execute("SELECT id FROM poll_state").fetchall()
    assert len(rows) == 1, f"Expected 1 row in poll_state, got {len(rows)}"
    assert rows[0][0] == 1, f"Expected id=1, got id={rows[0][0]}"


# ---------------------------------------------------------------------------
# AC-S2-04: DuckDB file created on disk after init_db()
# ---------------------------------------------------------------------------

def test_duckdb_file_created_on_disk(disk_db):
    """data/filter.duckdb file (or tmp equivalent) must exist after init_db()."""
    db_path = Path(disk_db)
    assert db_path.exists(), f"DuckDB file not found at {db_path}"


# ---------------------------------------------------------------------------
# AC-S2-05: get_db() returns a duckdb.DuckDBPyConnection instance
# ---------------------------------------------------------------------------

def test_get_db_returns_duckdb_connection(disk_db):
    """get_db() must return an instance of duckdb.DuckDBPyConnection."""
    import app.services.db as db_module
    conn = db_module.get_db()
    assert isinstance(conn, duckdb.DuckDBPyConnection), (
        f"get_db() returned {type(conn)}, expected duckdb.DuckDBPyConnection"
    )


# ---------------------------------------------------------------------------
# AC-S2-06: Schema correctness — filings table columns
# ---------------------------------------------------------------------------

FILINGS_REQUIRED_COLUMNS = {
    "accession_number",
    "entity_name",
    "ticker",
    "form_type",
    "filed_at",
    "filter_status",
    "processing_status",
}


def test_filings_table_has_required_columns(mem_db):
    """filings table must include all required columns from the spec."""
    result = mem_db.execute("DESCRIBE filings").fetchall()
    actual_columns = {row[0] for row in result}
    missing = FILINGS_REQUIRED_COLUMNS - actual_columns
    assert not missing, f"filings table missing columns: {missing}"


# ---------------------------------------------------------------------------
# AC-S2-07: Schema correctness — market_data table has accession_number column
# ---------------------------------------------------------------------------

def test_market_data_has_accession_number_column(mem_db):
    """market_data table must include an accession_number column (nullable FK per spec)."""
    result = mem_db.execute("DESCRIBE market_data").fetchall()
    actual_columns = {row[0] for row in result}
    assert "accession_number" in actual_columns, (
        "market_data table is missing the accession_number column"
    )


# ---------------------------------------------------------------------------
# AC-S2-08: Schema correctness — poll_state has exactly the three spec columns
# ---------------------------------------------------------------------------

POLL_STATE_EXPECTED_COLUMNS = {"id", "last_poll_at", "last_success_at"}


def test_poll_state_has_exactly_spec_columns(mem_db):
    """poll_state must have exactly the columns id, last_poll_at, last_success_at."""
    result = mem_db.execute("DESCRIBE poll_state").fetchall()
    actual_columns = {row[0] for row in result}
    assert actual_columns == POLL_STATE_EXPECTED_COLUMNS, (
        f"poll_state columns mismatch. "
        f"Extra: {actual_columns - POLL_STATE_EXPECTED_COLUMNS}, "
        f"Missing: {POLL_STATE_EXPECTED_COLUMNS - actual_columns}"
    )


# ---------------------------------------------------------------------------
# AC-S2-09: INSERT to filings works and can be read back
# ---------------------------------------------------------------------------

def test_insert_and_read_filings_row(mem_db):
    """A minimal row inserted into filings must be readable with the correct values."""
    mem_db.execute("""
        INSERT INTO filings (accession_number, form_type, filed_at, ingested_at)
        VALUES ('0001234567-26-000001', 'S-1', '2026-04-01 12:00:00', '2026-04-01 12:01:00')
    """)
    row = mem_db.execute(
        "SELECT accession_number, form_type FROM filings WHERE accession_number = ?",
        ["0001234567-26-000001"]
    ).fetchone()
    assert row is not None, "Inserted row not found in filings table"
    assert row[0] == "0001234567-26-000001"
    assert row[1] == "S-1"
