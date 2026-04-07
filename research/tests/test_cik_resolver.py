"""
Tests for Slice 4: CIKResolver.

All tests use an in-memory DuckDB fixture — no connection to the real
market_data.duckdb is made. This is required because the real DB may hold an
exclusive write lock during backfill operations.

The schema mirrors the real market_data.duckdb tables:
    - raw_symbols_massive: ticker, name, primary_exchange, cik, ..., active, raw_json
    - symbol_history:      permanent_id, symbol, ..., start_date, end_date, security_type
    - raw_symbols_fmp:     symbol, name
"""

from datetime import date
from pathlib import Path

import duckdb
import pytest

from research.pipeline.dataclasses import DiscoveredFiling, ResolvedFiling
from research.pipeline.cik_resolver import CIKResolver, _is_non_common


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(tmp_path: Path) -> Path:
    """
    Build a temporary DuckDB file with the minimal schema and test data needed
    to exercise all CIKResolver code paths.
    """
    db_path = tmp_path / "test_market_data.duckdb"
    con = duckdb.connect(str(db_path))

    # --- Schema (mirrors real market_data.duckdb) ---
    con.execute("""
        CREATE TABLE raw_symbols_massive (
            ticker           VARCHAR,
            name             VARCHAR,
            primary_exchange VARCHAR,
            cik              VARCHAR,
            composite_figi   VARCHAR,
            share_class_figi VARCHAR,
            active           BOOLEAN,
            raw_json         JSON
        )
    """)
    con.execute("""
        CREATE TABLE symbol_history (
            permanent_id VARCHAR,
            symbol       VARCHAR,
            exchange     VARCHAR,
            start_date   DATE,
            end_date     DATE,
            source       VARCHAR,
            raw_json     JSON,
            name         VARCHAR,
            cik          VARCHAR,
            sector       VARCHAR,
            industry     VARCHAR,
            security_type VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE raw_symbols_fmp (
            symbol VARCHAR,
            name   VARCHAR
        )
    """)

    # --- Test data ---

    # CIK 0000111111 — single active ticker, currently active (no end_date).
    # Used by: test_single_active_ticker_resolves
    con.execute("""
        INSERT INTO raw_symbols_massive (ticker, cik, active, raw_json) VALUES
            ('ACME', '0000111111', TRUE, '{"type":"CS"}')
    """)
    con.execute("""
        INSERT INTO symbol_history (symbol, start_date, end_date, permanent_id) VALUES
            ('ACME', '2015-01-01', NULL, 'perm-ACME-001')
    """)

    # CIK 0000222222 — no entry at all in raw_symbols_massive.
    # Used by: test_unknown_cik_is_unresolvable

    # CIK 0000333333 — delisted symbol (end_date in the past).
    # Filing date within the active window → must still resolve.
    # Used by: test_delisted_symbol_resolves_within_active_window
    con.execute("""
        INSERT INTO raw_symbols_massive (ticker, cik, active, raw_json) VALUES
            ('DELT', '0000333333', FALSE, '{"type":"CS"}')
    """)
    con.execute("""
        INSERT INTO symbol_history (symbol, start_date, end_date, permanent_id) VALUES
            ('DELT', '2010-01-01', '2020-12-31', 'perm-DELT-001')
    """)

    # CIK 0000444444 — common share + warrant for the same CIK.
    # Resolver must prefer the common share and suppress the warrant.
    # Used by: test_common_share_preferred_over_warrant
    con.execute("""
        INSERT INTO raw_symbols_massive (ticker, cik, active, raw_json) VALUES
            ('MIXS',  '0000444444', TRUE, '{"type":"CS"}'),
            ('MIXSW', '0000444444', TRUE, '{"type":"WARRANT"}')
    """)
    con.execute("""
        INSERT INTO symbol_history (symbol, start_date, end_date, permanent_id) VALUES
            ('MIXS',  '2019-01-01', NULL, 'perm-MIXS-001'),
            ('MIXSW', '2019-01-01', NULL, 'perm-MIXSW-001')
    """)

    # CIK 0000555555 — symbol only active in 2018-2020.
    # A filing dated 2023 must NOT resolve (date-range filter).
    # Used by: test_expired_symbol_does_not_resolve_for_later_filing
    con.execute("""
        INSERT INTO raw_symbols_massive (ticker, cik, active, raw_json) VALUES
            ('OLD1', '0000555555', FALSE, '{"type":"CS"}')
    """)
    con.execute("""
        INSERT INTO symbol_history (symbol, start_date, end_date, permanent_id) VALUES
            ('OLD1', '2018-01-01', '2020-12-31', 'perm-OLD1-001')
    """)

    # Entity name for fallback lookup tests (CIK not in raw_symbols_massive).
    # Used by: test_fallback_entity_name_lookup
    con.execute("""
        INSERT INTO raw_symbols_fmp VALUES
            ('FMPX', 'Fallback Corp Inc')
    """)

    con.close()
    return db_path


def _make_filing(
    cik: str,
    entity_name: str = "Test Corp",
    filing_date: date = date(2021, 6, 15),
) -> DiscoveredFiling:
    """Build a minimal DiscoveredFiling for test use."""
    return DiscoveredFiling(
        cik=cik,
        entity_name=entity_name,
        form_type="S-1",
        date_filed=filing_date,
        filename="edgar/data/1/0000000001-21-000001.txt",
        accession_number="0000000001-21-000001",
        quarter_key="2021_QTR2",
    )


# ---------------------------------------------------------------------------
# Test 1: Known CIK with single active ticker resolves correctly
# ---------------------------------------------------------------------------

def test_single_active_ticker_resolves(mock_db: Path) -> None:
    """A CIK mapped to one active ticker returns RESOLVED with that ticker."""
    filing = _make_filing("0000111111", filing_date=date(2021, 6, 15))

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert isinstance(result, ResolvedFiling)
    assert result.resolution_status == "RESOLVED"
    assert result.ticker == "ACME"
    assert result.permanent_id == "perm-ACME-001"
    # All DiscoveredFiling fields must be propagated unchanged.
    assert result.cik == filing.cik
    assert result.entity_name == filing.entity_name
    assert result.form_type == filing.form_type
    assert result.date_filed == filing.date_filed
    assert result.accession_number == filing.accession_number
    assert result.quarter_key == filing.quarter_key


# ---------------------------------------------------------------------------
# Test 2: CIK not in raw_symbols_massive → UNRESOLVABLE
# ---------------------------------------------------------------------------

def test_unknown_cik_is_unresolvable(mock_db: Path) -> None:
    """A CIK absent from raw_symbols_massive (and no FMP match) is UNRESOLVABLE."""
    filing = _make_filing("0000222222", entity_name="Ghost Corp")

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert result.resolution_status == "UNRESOLVABLE"
    assert result.ticker is None
    assert result.permanent_id is None


# ---------------------------------------------------------------------------
# Test 3: Delisted symbol resolves within its active window (anti-survivorship)
# ---------------------------------------------------------------------------

def test_delisted_symbol_resolves_within_active_window(mock_db: Path) -> None:
    """
    A symbol with symbol_history.end_date in the past (delisted) must still
    resolve for a filing whose date_filed falls within the active window.

    This is the anti-survivorship invariant: the active flag is used only in
    ORDER BY, never to exclude rows.
    """
    # Filing date within DELT's active window (2010-01-01 to 2020-12-31).
    filing = _make_filing("0000333333", entity_name="Delta Co", filing_date=date(2019, 3, 1))

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert result.resolution_status == "RESOLVED"
    assert result.ticker == "DELT"
    assert result.permanent_id == "perm-DELT-001"


# ---------------------------------------------------------------------------
# Test 4: CIK with common share + warrant → common share ticker returned
# ---------------------------------------------------------------------------

def test_common_share_preferred_over_warrant(mock_db: Path) -> None:
    """
    When a CIK maps to both a common share and a warrant, the resolver must
    return the common share ticker and exclude the warrant.
    """
    filing = _make_filing("0000444444", filing_date=date(2021, 6, 15))

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert result.resolution_status == "RESOLVED"
    assert result.ticker == "MIXS"   # common share, not 'MIXSW' (warrant)


# ---------------------------------------------------------------------------
# Test 5: filing_date used — expired symbol does not resolve for later filing
# ---------------------------------------------------------------------------

def test_expired_symbol_does_not_resolve_for_later_filing(mock_db: Path) -> None:
    """
    A symbol whose symbol_history.end_date is 2020-12-31 must NOT resolve for
    a filing dated 2023-01-01. The date-range filter must exclude it.
    """
    filing = _make_filing("0000555555", filing_date=date(2023, 1, 1))

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    # Symbol was only active through 2020-12-31; 2023 filing must not resolve.
    assert result.resolution_status == "UNRESOLVABLE"
    assert result.ticker is None


# ---------------------------------------------------------------------------
# Test 6: Fallback entity-name lookup via raw_symbols_fmp
# ---------------------------------------------------------------------------

def test_fallback_entity_name_lookup(mock_db: Path) -> None:
    """
    When the primary CIK lookup produces no rows, the resolver falls back to
    an exact entity-name match in raw_symbols_fmp.
    """
    # CIK not in raw_symbols_massive, but entity name matches raw_symbols_fmp.
    filing = _make_filing("0000999999", entity_name="Fallback Corp Inc")

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert result.resolution_status == "RESOLVED"
    assert result.ticker == "FMPX"


# ---------------------------------------------------------------------------
# Test 7: Empty entity name does not cause fallback crash
# ---------------------------------------------------------------------------

def test_empty_entity_name_does_not_crash(mock_db: Path) -> None:
    """An empty entity_name with an unknown CIK returns UNRESOLVABLE cleanly."""
    filing = _make_filing("0000777777", entity_name="")

    with CIKResolver(mock_db) as resolver:
        result = resolver.resolve(filing)

    assert result.resolution_status == "UNRESOLVABLE"
    assert result.ticker is None


# ---------------------------------------------------------------------------
# Test 8: _is_non_common helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("security_type,expected", [
    ("Common Stock", False),
    ("warrant", True),         # lowercase
    ("WARRANT", True),
    ("Right",  True),          # case-insensitive
    ("Unit", True),
    ("Preferred Stock", False),
    (None, False),
    ("", False),
    ("COMMON WARRANT HYBRID", True),  # contains WARRANT
])
def test_is_non_common(security_type: str | None, expected: bool) -> None:
    assert _is_non_common(security_type) == expected


# ---------------------------------------------------------------------------
# Test 9: Resolver does not write to the DB (read_only enforcement)
# ---------------------------------------------------------------------------

def test_resolver_does_not_write(mock_db: Path) -> None:
    """
    Attempting to write via the read-only connection must raise an exception.
    This confirms the anti-write invariant is enforced at the DB level.
    """
    with CIKResolver(mock_db) as resolver:
        with pytest.raises(Exception):
            resolver._con.execute(
                "INSERT INTO raw_symbols_massive (ticker, cik, active) VALUES ('X', 'Y', TRUE)"
            )
