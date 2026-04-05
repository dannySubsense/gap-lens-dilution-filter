"""
Cleanup script: remove Playwright QC test signal from the live DuckDB.
Run AFTER stopping the backend (DuckDB requires exclusive access).

Usage:
    python3 scripts/cleanup_playwright_qc.py
"""
from pathlib import Path
import duckdb

DUCKDB_PATH = Path(__file__).resolve().parent.parent / "data" / "filter.duckdb"
TEST_ACCESSION = "TEST-PW-QC-001"


def cleanup():
    conn = duckdb.connect(str(DUCKDB_PATH))
    conn.execute("DELETE FROM labels  WHERE accession_number = ?", [TEST_ACCESSION])
    conn.execute("DELETE FROM signals WHERE accession_number = ?", [TEST_ACCESSION])
    conn.execute("DELETE FROM filings WHERE accession_number = ?", [TEST_ACCESSION])
    conn.close()
    print(f"Removed test signal: accession={TEST_ACCESSION}")


if __name__ == "__main__":
    cleanup()
