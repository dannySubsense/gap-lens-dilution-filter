"""
Seed script: insert Playwright QC test signal into the live DuckDB.
Run BEFORE starting the backend (DuckDB requires exclusive access).

Usage:
    python3 scripts/seed_playwright_qc.py
"""
from pathlib import Path
import duckdb

DUCKDB_PATH = Path(__file__).resolve().parent.parent / "data" / "filter.duckdb"
TEST_ACCESSION = "TEST-PW-QC-001"
TEST_TICKER = "PWQC"


def seed():
    conn = duckdb.connect(str(DUCKDB_PATH))

    conn.execute(
        """
        INSERT INTO filings (
            accession_number, cik, form_type, filed_at,
            filing_url, entity_name, processing_status
        )
        VALUES (?, '8888888', '424B4', NOW(),
                'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=8888888',
                'Playwright QC Corp', 'ALERTED')
        ON CONFLICT (accession_number) DO NOTHING
        """,
        [TEST_ACCESSION],
    )

    conn.execute(
        """
        INSERT INTO signals (
            accession_number, ticker, setup_type, score, rank,
            status, alert_type, alerted_at
        )
        VALUES (?, ?, 'C', 76, 'B', 'WATCHLIST', 'NEW_SETUP', NOW())
        ON CONFLICT DO NOTHING
        """,
        [TEST_ACCESSION, TEST_TICKER],
    )

    conn.execute(
        """
        INSERT INTO labels (
            accession_number, classifier_version, setup_type,
            confidence, dilution_severity, immediate_pressure,
            price_discount, short_attractiveness, rank,
            key_excerpt, reasoning
        )
        VALUES (?, 'rule-based-v1', 'C',
                0.95, 0.50, true,
                0.03, 0, 'B',
                '2,000,000 shares of common stock at $3.97 per share.',
                'Playwright QC: Setup C with priced offering.')
        ON CONFLICT (accession_number, classifier_version) DO NOTHING
        """,
        [TEST_ACCESSION],
    )

    conn.close()
    print(f"Seeded test signal: ticker={TEST_TICKER} accession={TEST_ACCESSION}")


if __name__ == "__main__":
    seed()
