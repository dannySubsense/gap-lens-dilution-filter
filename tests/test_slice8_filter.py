"""
Slice 8: FilterEngine — Acceptance Tests

Done-when criteria verified:
1.  All-pass: valid S-1 with offering keyword, FMP data within thresholds,
    dilution_pct=0.25 → FilterOutcome(passed=True, fail_criterion=None),
    6 rows in filter_results all passed=True
2.  Market cap fail: market_cap=3e9 → fail_criterion="MARKET_CAP", 2 rows in filter_results
3.  fmp_data=None → fail_criterion="DATA_UNAVAILABLE", 1 row in filter_results
4.  ticker=None → fail_criterion="UNRESOLVABLE", filings.filter_status='UNRESOLVABLE'
5.  Passing filing → filings.filter_status='PASSED'
6.  Filter 1 form type fail: form_type="10-K" → fail_criterion="FILING_TYPE"
7.  Filter 1 keyword fail: valid form type, no offering keyword → fail_criterion="FILING_TYPE"
8.  All 7 offering keywords each pass Filter 1 (parametrized)
9.  13D/A + "warrant" keyword passes Filter 1
10. Dilution extracted from text: 5M offered / 10M float = 0.50 > 10% → passes Filter 4
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.db import _create_schema  # noqa: E402
from app.services.fmp_client import FMPMarketData  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mem_db():
    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    return conn


def insert_filing(conn, accession_number):
    conn.execute(
        """INSERT INTO filings (accession_number, cik, form_type, filed_at,
           filter_status, processing_status)
           VALUES (?, '123', 'S-1', CURRENT_TIMESTAMP, 'PENDING', 'PENDING')""",
        [accession_number],
    )


def _make_fmp_data(**kwargs) -> FMPMarketData:
    defaults = dict(
        price=5.0,
        market_cap=500_000_000,      # < $2B threshold
        float_shares=10_000_000,     # < 50M threshold
        adv_dollar=1_000_000,        # > $500K threshold
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return FMPMarketData(**defaults)


# ---------------------------------------------------------------------------
# AC-S8-01: All-pass — valid S-1, offering keyword, all FMP data within thresholds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_pass_returns_passed_outcome_and_six_filter_results(mem_db):
    """All filters passing: FilterOutcome(passed=True) with 6 filter_results rows."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000001"
    insert_filing(mem_db, acc)

    fmp = _make_fmp_data()  # all within thresholds

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="This is an offering of shares.",
            ticker="TEST",
            fmp_data=fmp,
            ask_edgar_dilution_pct=0.25,
        )

    assert outcome.passed is True, f"Expected passed=True, got {outcome}"
    assert outcome.fail_criterion is None, f"Expected fail_criterion=None, got {outcome.fail_criterion!r}"

    rows = mem_db.execute(
        "SELECT criterion, passed FROM filter_results WHERE accession_number = ? ORDER BY id",
        [acc],
    ).fetchall()
    assert len(rows) == 6, f"Expected 6 filter_results rows, got {len(rows)}: {rows}"
    for criterion, passed in rows:
        assert passed is True, f"Filter {criterion} expected passed=True, got passed={passed}"


# ---------------------------------------------------------------------------
# AC-S8-02: Market cap fail → fail_criterion="MARKET_CAP", 2 filter_results rows
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_cap_fail_stops_at_filter_2(mem_db):
    """market_cap=3e9 exceeds $2B threshold → fail_criterion='MARKET_CAP', 2 rows."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000002"
    insert_filing(mem_db, acc)

    fmp = _make_fmp_data(market_cap=3_000_000_000)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="This is an offering of shares.",
            ticker="TEST",
            fmp_data=fmp,
            ask_edgar_dilution_pct=0.25,
        )

    assert outcome.passed is False
    assert outcome.fail_criterion == "MARKET_CAP", (
        f"Expected fail_criterion='MARKET_CAP', got {outcome.fail_criterion!r}"
    )

    count = mem_db.execute(
        "SELECT COUNT(*) FROM filter_results WHERE accession_number = ?", [acc]
    ).fetchone()[0]
    assert count == 2, f"Expected 2 filter_results rows (F1 pass + F2 fail), got {count}"


# ---------------------------------------------------------------------------
# AC-S8-03: fmp_data=None → fail_criterion="DATA_UNAVAILABLE", 1 filter_results row
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fmp_data_none_returns_data_unavailable(mem_db):
    """fmp_data=None → fail_criterion='DATA_UNAVAILABLE', exactly 2 filter_results rows.

    Filter 1 (FILING_TYPE) is evaluated and passes; Filter 2 (MARKET_CAP) is evaluated
    with value=None and fails with DATA_UNAVAILABLE before further filters run.
    """
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000003"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="This is an offering of shares.",
            ticker="TEST",
            fmp_data=None,
        )

    assert outcome.passed is False
    assert outcome.fail_criterion == "DATA_UNAVAILABLE", (
        f"Expected 'DATA_UNAVAILABLE', got {outcome.fail_criterion!r}"
    )

    rows = mem_db.execute(
        "SELECT criterion, passed FROM filter_results WHERE accession_number = ? ORDER BY id",
        [acc],
    ).fetchall()
    assert len(rows) == 2, f"Expected exactly 2 filter_results rows (F1 pass + F2 fail), got {len(rows)}: {rows}"
    assert rows[0] == ("FILING_TYPE", True), (
        f"Row 1: expected ('FILING_TYPE', True), got {rows[0]}"
    )
    assert rows[1][0] == "MARKET_CAP", (
        f"Row 2: expected criterion='MARKET_CAP', got {rows[1][0]!r}"
    )
    assert rows[1][1] is False, (
        f"Row 2: expected passed=False, got {rows[1][1]}"
    )


# ---------------------------------------------------------------------------
# AC-S8-04: ticker=None → fail_criterion="UNRESOLVABLE", filter_status='UNRESOLVABLE'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ticker_none_returns_unresolvable_and_updates_filing(mem_db):
    """ticker=None → fail_criterion='UNRESOLVABLE', filings.filter_status='UNRESOLVABLE'."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000004"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="This is an offering of shares.",
            ticker=None,
            fmp_data=_make_fmp_data(),
        )

    assert outcome.passed is False
    assert outcome.fail_criterion == "UNRESOLVABLE", (
        f"Expected 'UNRESOLVABLE', got {outcome.fail_criterion!r}"
    )

    row = mem_db.execute(
        "SELECT filter_status FROM filings WHERE accession_number = ?", [acc]
    ).fetchone()
    assert row is not None
    assert row[0] == "UNRESOLVABLE", (
        f"Expected filter_status='UNRESOLVABLE', got {row[0]!r}"
    )


# ---------------------------------------------------------------------------
# AC-S8-05: Passing filing → filings.filter_status='PASSED'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_passing_filing_sets_filter_status_passed(mem_db):
    """All filters passing → filings.filter_status='PASSED'."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000005"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="This is an offering of shares.",
            ticker="TEST",
            fmp_data=_make_fmp_data(),
            ask_edgar_dilution_pct=0.25,
        )

    row = mem_db.execute(
        "SELECT filter_status FROM filings WHERE accession_number = ?", [acc]
    ).fetchone()
    assert row is not None
    assert row[0] == "PASSED", f"Expected filter_status='PASSED', got {row[0]!r}"


# ---------------------------------------------------------------------------
# AC-S8-06: Filter 1 form type fail — form_type="10-K" → fail_criterion="FILING_TYPE"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disallowed_form_type_fails_filter_1(mem_db):
    """form_type='10-K' is not allowed → fail_criterion='FILING_TYPE'."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000006"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="10-K",
            filing_text="This is an offering of shares.",
            ticker="TEST",
            fmp_data=_make_fmp_data(),
        )

    assert outcome.passed is False
    assert outcome.fail_criterion == "FILING_TYPE", (
        f"Expected 'FILING_TYPE', got {outcome.fail_criterion!r}"
    )


# ---------------------------------------------------------------------------
# AC-S8-07: Filter 1 keyword fail — valid form type but no offering keyword
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_offering_keyword_fails_filter_1(mem_db):
    """Valid form type but text with no offering keyword → fail_criterion='FILING_TYPE'."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000007"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="Annual report with no relevant keywords whatsoever.",
            ticker="TEST",
            fmp_data=_make_fmp_data(),
        )

    assert outcome.passed is False
    assert outcome.fail_criterion == "FILING_TYPE", (
        f"Expected 'FILING_TYPE', got {outcome.fail_criterion!r}"
    )


# ---------------------------------------------------------------------------
# AC-S8-08: All 7 offering keywords each pass Filter 1 (parametrized)
# ---------------------------------------------------------------------------

ALL_OFFERING_KEYWORDS = [
    "offering",
    "shares",
    "prospectus",
    "at-the-market",
    "sales agent",
    "underwritten",
    "priced",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("keyword", ALL_OFFERING_KEYWORDS)
async def test_each_offering_keyword_passes_filter_1(keyword):
    """Each of the 7 offering keywords must individually pass Filter 1 with a valid form type."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    conn = duckdb.connect(":memory:")
    _create_schema(conn)
    acc = f"0001111111-24-9{ALL_OFFERING_KEYWORDS.index(keyword):05d}"
    insert_filing(conn, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=conn):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text=f"This filing contains the word {keyword} in its text.",
            ticker="TEST",
            fmp_data=_make_fmp_data(),
            ask_edgar_dilution_pct=0.25,
        )

    # Check that Filter 1 was recorded as passed
    row = conn.execute(
        "SELECT passed FROM filter_results WHERE accession_number = ? AND criterion = 'FILING_TYPE'",
        [acc],
    ).fetchone()
    assert row is not None, f"No FILING_TYPE filter_results row for keyword={keyword!r}"
    assert row[0] is True, (
        f"FILING_TYPE filter expected passed=True for keyword={keyword!r}, got passed={row[0]}"
    )
    conn.close()


# ---------------------------------------------------------------------------
# AC-S8-09: 13D/A + "warrant" passes Filter 1
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_13da_with_warrant_passes_filter_1(mem_db):
    """13D/A form type with 'warrant' keyword must pass Filter 1."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000009"
    insert_filing(mem_db, acc)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="13D/A",
            filing_text="This filing discloses a warrant for the purchase of common shares.",
            ticker="TEST",
            fmp_data=_make_fmp_data(),
            ask_edgar_dilution_pct=0.25,
        )

    row = mem_db.execute(
        "SELECT passed FROM filter_results WHERE accession_number = ? AND criterion = 'FILING_TYPE'",
        [acc],
    ).fetchone()
    assert row is not None, "No FILING_TYPE filter_results row for 13D/A+warrant test"
    assert row[0] is True, f"Filter 1 expected passed=True for 13D/A+warrant, got {row[0]}"


# ---------------------------------------------------------------------------
# AC-S8-10: Dilution extracted from filing text: 5M / 10M float = 0.50 > 10%
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dilution_extracted_from_filing_text_passes_filter_4(mem_db):
    """'offering of 5,000,000 shares' with float_shares=10M → dilution=0.50 → passes Filter 4."""
    from app.services.filter_engine import FilterEngine  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    acc = "0001111111-24-000010"
    insert_filing(mem_db, acc)

    fmp = _make_fmp_data(float_shares=10_000_000)

    engine = FilterEngine()
    with patch("app.services.filter_engine.get_db", return_value=mem_db):
        outcome = await engine.evaluate(
            accession_number=acc,
            form_type="S-1",
            filing_text="Pursuant to this prospectus, the company is conducting an offering of 5,000,000 shares of common stock.",
            ticker="TEST",
            fmp_data=fmp,
            ask_edgar_dilution_pct=None,  # force extraction from text
        )

    row = mem_db.execute(
        "SELECT passed FROM filter_results WHERE accession_number = ? AND criterion = 'DILUTION_PCT'",
        [acc],
    ).fetchone()
    assert row is not None, "No DILUTION_PCT filter_results row found"
    assert row[0] is True, (
        f"DILUTION_PCT filter expected passed=True (dilution=0.50), got passed={row[0]}"
    )
