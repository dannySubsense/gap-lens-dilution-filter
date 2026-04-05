import duckdb
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

_conn: duckdb.DuckDBPyConnection | None = None


def get_db() -> duckdb.DuckDBPyConnection:
    """Return the singleton DuckDB connection. init_db() must be called first."""
    if _conn is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _conn


def init_db() -> None:
    """Initialize the DuckDB connection and create all tables. Idempotent."""
    global _conn
    if _conn is None:
        _conn = duckdb.connect(settings.duckdb_path)
    _create_schema(_conn)
    logger.info("DuckDB initialized at %s", settings.duckdb_path)


def _create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE SEQUENCE IF NOT EXISTS filter_results_id_seq;
        CREATE SEQUENCE IF NOT EXISTS market_data_id_seq;
        CREATE SEQUENCE IF NOT EXISTS signals_id_seq;

        CREATE TABLE IF NOT EXISTS cik_ticker_map (
            cik      INTEGER PRIMARY KEY,
            ticker   TEXT NOT NULL,
            name     TEXT,
            exchange TEXT
        );

        CREATE TABLE IF NOT EXISTS filings (
            accession_number     TEXT PRIMARY KEY,
            cik                  TEXT,
            ticker               TEXT,
            entity_name          TEXT,
            form_type            TEXT NOT NULL,
            filed_at             TIMESTAMP NOT NULL,
            ingested_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            filing_url           TEXT,
            filing_text          TEXT,
            filter_status        TEXT NOT NULL DEFAULT 'PENDING',
            filter_fail_reason   TEXT,
            processing_status    TEXT NOT NULL DEFAULT 'PENDING',
            askedgar_partial     BOOLEAN NOT NULL DEFAULT FALSE,
            all_matched_patterns TEXT
        );

        CREATE TABLE IF NOT EXISTS filter_results (
            id                   INTEGER PRIMARY KEY DEFAULT nextval('filter_results_id_seq'),
            accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
            criterion            TEXT NOT NULL,
            passed               BOOLEAN NOT NULL,
            value_observed       REAL,
            evaluated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS market_data (
            id                   INTEGER PRIMARY KEY DEFAULT nextval('market_data_id_seq'),
            ticker               TEXT NOT NULL,
            snapshot_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            price                REAL,
            market_cap           REAL,
            float_shares         REAL,
            adv_dollar           REAL,
            data_source          TEXT NOT NULL DEFAULT 'FMP',
            accession_number     TEXT
        );

        CREATE TABLE IF NOT EXISTS labels (
            accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
            classifier_version   TEXT NOT NULL,
            setup_type           TEXT,
            confidence           REAL,
            dilution_severity    REAL,
            immediate_pressure   BOOLEAN,
            price_discount       REAL,
            short_attractiveness INTEGER,
            rank                 TEXT,
            key_excerpt          TEXT,
            reasoning            TEXT,
            scored_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (accession_number, classifier_version)
        );

        CREATE TABLE IF NOT EXISTS signals (
            id                   INTEGER PRIMARY KEY DEFAULT nextval('signals_id_seq'),
            accession_number     TEXT NOT NULL REFERENCES filings(accession_number),
            ticker               TEXT NOT NULL,
            setup_type           TEXT,
            score                INTEGER,
            rank                 TEXT,
            alert_type           TEXT NOT NULL,
            status               TEXT NOT NULL DEFAULT 'LIVE',
            alerted_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            price_at_alert       REAL,
            entry_price          REAL,
            cover_price          REAL,
            pnl_pct              REAL,
            closed_at            TIMESTAMP,
            close_reason         TEXT
        );

        CREATE TABLE IF NOT EXISTS poll_state (
            id              INTEGER PRIMARY KEY,
            last_poll_at    TIMESTAMP,
            last_success_at TIMESTAMP
        );

        INSERT OR IGNORE INTO poll_state (id) VALUES (1);
    """)
