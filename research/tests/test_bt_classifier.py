"""
Tests for Slice 6: BacktestClassifier.

Tests:
1. FetchedFiling with fetch_status="FETCH_FAILED" returns stub with
   setup_type=None (not "NULL") and no exception raised.
2. FetchedFiling with plain_text=None returns stub with setup_type=None.
3. Filing text with no matching rules causes RuleBasedClassifier to return
   setup_type="NULL"; BacktestClassifier maps it to Python None.
4. Filing text with 424B4 dilution language classifies to a non-None
   setup_type (integration test with real RuleBasedClassifier).
5. classify() is async — await bt_classifier.classify(filing) works.
6. setup_type is never the string "NULL" for any input.
"""

import asyncio
from datetime import date

import pytest

from research.pipeline.bt_classifier import BacktestClassifier
from research.pipeline.dataclasses import FetchedFiling, ResolvedFiling


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_fetched(
    fetch_status: str = "OK",
    plain_text: str | None = "sample text",
    fetch_error: str | None = None,
    form_type: str = "424B4",
    accession_number: str = "0001234567-22-000123",
) -> FetchedFiling:
    """Build a minimal FetchedFiling for testing."""
    return FetchedFiling(
        cik="0001234567",
        entity_name="Test Corp",
        form_type=form_type,
        date_filed=date(2022, 3, 15),
        filename="edgar/data/1234567/0001234567-22-000123.txt",
        accession_number=accession_number,
        quarter_key="2022_QTR1",
        ticker="TEST",
        resolution_status="RESOLVED",
        permanent_id="PERM-001",
        plain_text=plain_text,
        fetch_status=fetch_status,
        fetch_error=fetch_error,
    )


# ---------------------------------------------------------------------------
# Test 1: FETCH_FAILED → stub with setup_type=None
# ---------------------------------------------------------------------------

class TestFetchFailedStub:
    def test_fetch_failed_returns_stub_with_none_setup_type(self):
        filing = make_fetched(
            fetch_status="FETCH_FAILED",
            plain_text=None,
            fetch_error="HTTP_404",
        )
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        assert result["setup_type"] is None
        assert result["setup_type"] != "NULL"
        assert result["confidence"] == 0.0

    def test_fetch_failed_does_not_raise(self):
        filing = make_fetched(fetch_status="FETCH_FAILED", plain_text=None)
        classifier = BacktestClassifier()
        # Should not raise any exception.
        result = asyncio.run(classifier.classify(filing))
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 2: plain_text=None → stub with setup_type=None
# ---------------------------------------------------------------------------

class TestPlainTextNoneStub:
    def test_plain_text_none_returns_stub(self):
        filing = make_fetched(fetch_status="EMPTY_TEXT", plain_text=None)
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        assert result["setup_type"] is None
        assert result["confidence"] == 0.0

    def test_ok_status_but_none_plain_text_returns_stub(self):
        # Edge case: fetch_status="OK" but plain_text is still None.
        filing = make_fetched(fetch_status="OK", plain_text=None)
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        assert result["setup_type"] is None
        assert result["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Test 3: No-match text → "NULL" from classifier mapped to Python None
# ---------------------------------------------------------------------------

class TestNullSentinelMapping:
    def test_no_match_text_maps_null_string_to_none(self):
        # "Annual report for fiscal year" matches no setup rule for any form type.
        filing = make_fetched(
            fetch_status="OK",
            plain_text="Annual report for fiscal year ended December 31, 2021.",
            form_type="424B4",
        )
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        # Must be Python None, not the string "NULL".
        assert result["setup_type"] is None
        assert result.get("setup_type") != "NULL"

    def test_unrecognized_form_type_maps_null_to_none(self):
        # A form type not in any rule → no match → "NULL" → None.
        filing = make_fetched(
            fetch_status="OK",
            plain_text="supplement takedown offering shares common stock",
            form_type="10-K",  # Not in any rule's form_types set.
        )
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        assert result["setup_type"] is None
        assert result.get("setup_type") != "NULL"


# ---------------------------------------------------------------------------
# Test 4: 424B4 dilution language → non-None setup_type (integration test)
# ---------------------------------------------------------------------------

class TestIntegrationClassification:
    def test_424b4_with_dilution_language_returns_setup_type(self):
        # Text containing keywords that match rule B: form_type=424B4 with
        # "supplement" and "takedown".
        filing_text = (
            "This supplement relates to a takedown of 5,000,000 shares of "
            "common stock being offered at $2.50 per share by Maxim Group LLC "
            "as lead underwriter. The offering price of $2.50 represents a "
            "10% discount to the last closing price."
        )
        filing = make_fetched(
            fetch_status="OK",
            plain_text=filing_text,
            form_type="424B4",
        )
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        # Must be a non-None setup_type (rule B matches 424B4 + "supplement" or "takedown").
        assert result["setup_type"] is not None
        assert result["setup_type"] != "NULL"

    def test_s1_with_effective_date_language_classifies_correctly(self):
        # Rule A: form_type S-1 with "effective date" keyword.
        filing_text = (
            "Registration becomes effective date of this prospectus. "
            "We will commence offering 10,000,000 shares of common stock "
            "at an offering price of $5.00 per share."
        )
        filing = make_fetched(
            fetch_status="OK",
            plain_text=filing_text,
            form_type="S-1",
        )
        classifier = BacktestClassifier()
        result = asyncio.run(classifier.classify(filing))

        assert result["setup_type"] is not None
        assert result["setup_type"] != "NULL"


# ---------------------------------------------------------------------------
# Test 5: classify() is async — can be awaited
# ---------------------------------------------------------------------------

class TestAsyncCallingConvention:
    def test_classify_is_awaitable(self):
        filing = make_fetched()
        classifier = BacktestClassifier()

        # This test verifies that classify() returns a coroutine (is async def).
        import inspect
        coro = classifier.classify(filing)
        assert inspect.iscoroutine(coro)
        # Clean up the coroutine without running it.
        coro.close()

    def test_classify_can_be_awaited_via_asyncio_run(self):
        filing = make_fetched(fetch_status="FETCH_FAILED", plain_text=None)
        classifier = BacktestClassifier()
        # Must not raise — asyncio.run() wraps a single async call correctly.
        result = asyncio.run(classifier.classify(filing))
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 6: setup_type is never the string "NULL" for any input
# ---------------------------------------------------------------------------

class TestNullStringNeverReturned:
    def _run(self, filing: FetchedFiling) -> dict:
        return asyncio.run(BacktestClassifier().classify(filing))

    def test_fetch_failed_no_null_string(self):
        filing = make_fetched(fetch_status="FETCH_FAILED", plain_text=None)
        assert self._run(filing).get("setup_type") != "NULL"

    def test_empty_text_no_null_string(self):
        filing = make_fetched(fetch_status="EMPTY_TEXT", plain_text=None)
        assert self._run(filing).get("setup_type") != "NULL"

    def test_no_match_text_no_null_string(self):
        filing = make_fetched(
            fetch_status="OK",
            plain_text="Quarterly earnings report. Revenue increased 5%.",
            form_type="424B4",
        )
        assert self._run(filing).get("setup_type") != "NULL"

    def test_matched_text_no_null_string(self):
        filing_text = (
            "This supplement is a takedown of 2,000,000 shares at $3.00 per share."
        )
        filing = make_fetched(
            fetch_status="OK",
            plain_text=filing_text,
            form_type="424B4",
        )
        assert self._run(filing).get("setup_type") != "NULL"
