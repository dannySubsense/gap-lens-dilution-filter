"""
Tests for Slice 7: UnderwriterExtractor

All tests use hardcoded sample strings — no live HTTP calls.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from research.pipeline.dataclasses import FetchedFiling, ParticipantRecord
from research.pipeline.underwriter_extractor import UnderwriterExtractor


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_filing(
    plain_text: str,
    form_type: str = "424B4",
    accession_number: str = "0001234567-22-000001",
    fetch_status: str = "OK",
) -> FetchedFiling:
    """Minimal FetchedFiling for testing."""
    return FetchedFiling(
        cik="0001234567",
        entity_name="Test Corp",
        form_type=form_type,
        date_filed=date(2022, 3, 15),
        filename="edgar/data/1234567/0001234567-22-000001.txt",
        accession_number=accession_number,
        quarter_key="2022_QTR1",
        ticker="TEST",
        resolution_status="RESOLVED",
        permanent_id=None,
        plain_text=plain_text,
        fetch_status=fetch_status,
        fetch_error=None,
    )


def _make_extractor(
    normalization: dict | None = None,
    *,
    missing_file: bool = False,
) -> UnderwriterExtractor:
    """
    Return an UnderwriterExtractor backed by a temporary JSON config.

    If missing_file=True, points to a path that does not exist.
    If normalization is None and missing_file is False, uses an empty config.
    """
    if missing_file:
        return UnderwriterExtractor(Path("/tmp/nonexistent_normalization_xyz.json"))

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as fh:
        json.dump(normalization if normalization is not None else {}, fh)
        tmp_path = Path(fh.name)

    return UnderwriterExtractor(tmp_path)


# ---------------------------------------------------------------------------
# Test 1: 424B4 with lead underwriter in Plan of Distribution section
# ---------------------------------------------------------------------------

class TestLeadUnderwriterIn424B4:
    def test_returns_lead_underwriter_record(self):
        """
        A 424B4 filing with 'lead underwriter, Maxim Group LLC' in the
        Plan of Distribution section returns at least one ParticipantRecord
        with role='lead_underwriter'.
        """
        text = (
            "COVER PAGE\n"
            "Some cover page content.\n\n"
            "PLAN OF DISTRIBUTION\n\n"
            "We are offering these shares through the lead underwriter, Maxim Group LLC, "
            "pursuant to an underwriting agreement dated March 15, 2022.\n\n"
            "USE OF PROCEEDS\n\n"
            "We intend to use the net proceeds...\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)

        assert len(results) >= 1
        roles = [r.role for r in results]
        assert "lead_underwriter" in roles

        lead_records = [r for r in results if r.role == "lead_underwriter"]
        assert any("Maxim Group LLC" in r.firm_name for r in lead_records)


# ---------------------------------------------------------------------------
# Test 2: 8-K with sales agent language
# ---------------------------------------------------------------------------

class TestSalesAgentIn8K:
    def test_returns_sales_agent_record(self):
        """
        An 8-K filing with 'equity distribution agreement with H.C. Wainwright'
        returns a ParticipantRecord with role='sales_agent'.
        """
        text = (
            "ITEM 1.01  Entry into a Material Definitive Agreement\n\n"
            "On March 14, 2022, the Company entered into an equity distribution "
            "agreement with H.C. Wainwright & Co., LLC, as sales agent, pursuant "
            "to which the Company may sell up to $10,000,000 of common stock.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="8-K")
        results = extractor.extract(filing)

        assert len(results) >= 1
        roles = [r.role for r in results]
        assert "sales_agent" in roles


# ---------------------------------------------------------------------------
# Test 3: Filing with no financial intermediary language returns []
# ---------------------------------------------------------------------------

class TestNoMatchReturnsEmptyList:
    def test_no_patterns_no_error(self):
        """
        A filing text with no matching patterns returns an empty list,
        not an exception.
        """
        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "The shares will be sold through various channels.  "
            "No specific firm is named here.\n\n"
            "USE OF PROCEEDS\n\n"
            "Proceeds will be used for general corporate purposes.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)
        assert results == []


# ---------------------------------------------------------------------------
# Test 4: Normalization — HC Wainwright → H.C. Wainwright & Co.
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_normalized_firm_name_and_flag(self):
        """
        When normalization_config contains a mapping whose key matches the extracted
        firm name (after legal-suffix stripping), the record is returned with
        firm_name equal to the canonical value and is_normalized=True.

        The regex captures text up to the first comma, so the raw extracted name is
        "H.C. Wainwright & Co." (without ", LLC").  After stripping the "& Co."
        suffix the lookup key becomes "H.C. Wainwright".  The config therefore maps
        that stripped form to the canonical name.
        """
        norm = {"H.C. Wainwright": "H.C. Wainwright & Co."}
        extractor = _make_extractor(norm)

        text = (
            "ITEM 1.01\n\n"
            "The Company entered into an equity distribution agreement with "
            "H.C. Wainwright & Co., LLC, as sales agent.\n"
        )
        filing = _make_filing(text, form_type="8-K")
        results = extractor.extract(filing)

        assert len(results) >= 1
        # Find the record for this firm
        wainwright_records = [
            r for r in results
            if "Wainwright" in r.firm_name
        ]
        assert len(wainwright_records) >= 1
        rec = wainwright_records[0]
        assert rec.firm_name == "H.C. Wainwright & Co."
        assert rec.is_normalized is True


# ---------------------------------------------------------------------------
# Test 5: Missing normalization config — loads with config_loaded=False
# ---------------------------------------------------------------------------

class TestMissingNormalizationConfig:
    def test_loads_without_raising(self):
        """
        When the normalization config file does not exist, the extractor
        instantiates without raising, config_loaded=False, config_entry_count=0.
        """
        extractor = _make_extractor(missing_file=True)
        assert extractor.config_loaded is False
        assert extractor.config_entry_count == 0

    def test_extraction_runs_with_is_normalized_false(self):
        """
        With a missing config, extraction still runs and stores names
        verbatim with is_normalized=False.
        """
        extractor = _make_extractor(missing_file=True)
        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "We are offering these shares through the lead underwriter, "
            "Roth Capital Partners LLC.\n\n"
            "USE OF PROCEEDS\n\n"
            "Proceeds will be used for general corporate purposes.\n"
        )
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)

        assert len(results) >= 1
        for rec in results:
            assert rec.is_normalized is False


# ---------------------------------------------------------------------------
# Test 6: Same firm+role appearing twice is deduplicated
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_duplicate_firm_role_deduplicated(self):
        """
        The same firm appearing twice in the same role is extracted only once.
        """
        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "The offering is made through the lead underwriter, Maxim Group LLC.  "
            "The lead underwriter, Maxim Group LLC, has agreed to purchase the shares "
            "at a discount.\n\n"
            "USE OF PROCEEDS\n\n"
            "Proceeds will be used for general corporate purposes.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)

        lead_records = [r for r in results if r.role == "lead_underwriter"]
        maxim_records = [r for r in lead_records if "Maxim Group LLC" in r.firm_name]
        assert len(maxim_records) == 1


# ---------------------------------------------------------------------------
# Test 7: S-3 filing returns []
# ---------------------------------------------------------------------------

class TestS3Skipped:
    def test_s3_returns_empty_list(self):
        """
        An S-3 filing returns an empty list regardless of content.
        """
        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "We are offering these shares through the lead underwriter, Goldman Sachs.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="S-3")
        results = extractor.extract(filing)
        assert results == []


# ---------------------------------------------------------------------------
# Test 8: 13D/A with placement agent language
# ---------------------------------------------------------------------------

class TestPlacementAgentIn13DA:
    def test_returns_placement_agent_record(self):
        """
        A 13D/A filing with placement agent language returns a ParticipantRecord
        with role='placement_agent'.
        """
        text = (
            "ITEM 4.  Purpose of Transaction\n\n"
            "The Reporting Person participated in a private placement.  "
            "The Company engaged Dawson James Securities, Inc., as placement agent, "
            "in connection with the offering.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="13D/A")
        results = extractor.extract(filing)

        assert len(results) >= 1
        roles = [r.role for r in results]
        assert "placement_agent" in roles


# ---------------------------------------------------------------------------
# Additional coverage: co-manager comma-separated list
# ---------------------------------------------------------------------------

class TestCoManagerList:
    def test_comma_separated_co_managers(self):
        """
        'co-managers: Oppenheimer & Co., Roth Capital Partners' returns two
        ParticipantRecord objects with role='co_manager'.
        """
        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "The offering is being made through the book-running managers.  "
            "co-managers: Oppenheimer & Co., Roth Capital Partners\n\n"
            "USE OF PROCEEDS\n\n"
            "Proceeds will be used for working capital.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)

        co_mgr_records = [r for r in results if r.role == "co_manager"]
        firm_names = [r.firm_name for r in co_mgr_records]
        assert len(co_mgr_records) >= 2
        assert any("Oppenheimer" in n for n in firm_names)
        assert any("Roth Capital" in n for n in firm_names)


# ---------------------------------------------------------------------------
# Additional coverage: 8-K section isolation (extraction limited as specified)
# ---------------------------------------------------------------------------

class TestSectionIsolation8K:
    def test_8k_extracts_from_full_body(self):
        """
        8-K: sales agent language appearing beyond 5,000 chars is still extracted
        (spec says 'full body'; the 5,000-char note is informational context only).
        """
        padding = "X " * 3000  # ~6,000 chars of filler
        text = (
            padding
            + "\n\nThe Company entered into an equity distribution agreement with "
            "Ladenburg Thalmann & Co. Inc., as sales agent.\n"
        )
        extractor = _make_extractor()
        filing = _make_filing(text, form_type="8-K")
        results = extractor.extract(filing)

        assert any(r.role == "sales_agent" for r in results)


# ---------------------------------------------------------------------------
# Additional coverage: unrecognized firm stored verbatim, is_normalized=False
# ---------------------------------------------------------------------------

class TestUnrecognizedFirmVerbatim:
    def test_verbatim_storage(self):
        """
        An unrecognized firm name is stored verbatim with is_normalized=False.
        """
        norm = {"Known Firm LLC": "Known Firm"}
        extractor = _make_extractor(norm)

        text = (
            "PLAN OF DISTRIBUTION\n\n"
            "We are offering shares through the lead underwriter, "
            "Totally Unknown Securities Corp.\n\n"
            "USE OF PROCEEDS\n\n"
            "Proceeds will be used for general corporate purposes.\n"
        )
        filing = _make_filing(text, form_type="424B4")
        results = extractor.extract(filing)

        unknown_records = [
            r for r in results if "Unknown Securities" in r.firm_name
        ]
        assert len(unknown_records) >= 1
        assert all(r.is_normalized is False for r in unknown_records)
