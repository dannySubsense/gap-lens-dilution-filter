"""
Tests for Slice 3: FilingDiscovery.

All HTTP calls are mocked — no live SEC requests are made.
"""

import gzip
import io
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from research.pipeline.config import BacktestConfig
from research.pipeline.dataclasses import DiscoveredFiling
from research.pipeline.discovery import (
    FilingDiscovery,
    _derive_accession_number,
    _parse_line,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MASTER_GZ_HEADER = (
    "CIK|Company Name|Form Type|Date Filed|Filename\n"
    "--------------------------------------------------------------------------------\n"
    "Full-Index of EDGAR Filing\n"
    "CIK|Company Name|Form Type|Date Filed|Filename\n"
    "--------------------------------------------------------------------------------\n"
)


def _make_master_gz(data_lines: list[str]) -> bytes:
    """
    Build a realistic master.gz bytes object from a list of pipe-delimited
    data lines. Prepends the standard header section.
    """
    content = _MASTER_GZ_HEADER + "\n".join(data_lines) + "\n"
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(content.encode("latin-1"))
    return buf.getvalue()


def _make_config(tmp_path: Path) -> BacktestConfig:
    cfg = BacktestConfig()
    cfg.cache_dir = tmp_path / "cache"
    return cfg


def _make_mock_response(gz_bytes: bytes, status_code: int = 200) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.content = gz_bytes
    if status_code >= 400:
        from requests import HTTPError
        mock_resp.raise_for_status.side_effect = HTTPError(
            f"HTTP {status_code}", response=mock_resp
        )
    else:
        mock_resp.raise_for_status.return_value = None
    return mock_resp


# ---------------------------------------------------------------------------
# Test 1: parse_master_line correctly extracts all five fields
# ---------------------------------------------------------------------------

class TestParseMasterLine:
    def test_extracts_all_five_fields(self):
        line = "1234567|Acme Corp|S-1|2022-03-15|edgar/data/1234567/0001234567-22-000123.txt"
        start = date(2017, 1, 1)
        end = date(2025, 12, 31)
        allowed = {"S-1", "S-1/A", "S-3", "424B2", "424B4", "8-K", "13D/A"}

        result = _parse_line(line, start, end, allowed, "2022_QTR1")

        assert result is not None
        assert result.cik == "0001234567"        # zero-padded to 10 digits
        assert result.entity_name == "Acme Corp"
        assert result.form_type == "S-1"
        assert result.date_filed == date(2022, 3, 15)
        assert result.filename == "edgar/data/1234567/0001234567-22-000123.txt"
        assert result.accession_number == "0001234567-22-000123"
        assert result.quarter_key == "2022_QTR1"


# ---------------------------------------------------------------------------
# Test 2: form-type filtering — 13D/A included, DEF 14A excluded
# ---------------------------------------------------------------------------

class TestFormTypeFilter:
    def _run(self, form_type: str) -> DiscoveredFiling | None:
        line = (
            f"9876543|Test Inc|{form_type}|2022-06-01|"
            "edgar/data/9876543/0009876543-22-000001.txt"
        )
        return _parse_line(
            line,
            date(2017, 1, 1),
            date(2025, 12, 31),
            {"S-1", "S-1/A", "S-3", "424B2", "424B4", "8-K", "13D/A"},
            "2022_QTR2",
        )

    def test_13d_a_is_included(self):
        result = self._run("13D/A")
        assert result is not None
        assert result.form_type == "13D/A"

    def test_def_14a_is_excluded(self):
        result = self._run("DEF 14A")
        assert result is None

    def test_s1_is_included(self):
        result = self._run("S-1")
        assert result is not None

    def test_424b4_is_included(self):
        result = self._run("424B4")
        assert result is not None

    def test_10k_is_excluded(self):
        result = self._run("10-K")
        assert result is None


# ---------------------------------------------------------------------------
# Test 3: accession_number derived correctly from filename
# ---------------------------------------------------------------------------

class TestDeriveAccessionNumber:
    def test_standard_filename(self):
        filename = "edgar/data/1234567/0001234567-22-000123.txt"
        result = _derive_accession_number(filename)
        assert result == "0001234567-22-000123"

    def test_dashes_preserved(self):
        # Hyphens in accession number are part of the EDGAR format
        result = _derive_accession_number(
            "edgar/data/9999999/0009999999-21-000001.txt"
        )
        assert result == "0009999999-21-000001"

    def test_non_txt_returns_none(self):
        result = _derive_accession_number(
            "edgar/data/1234567/0001234567-22-000123.htm"
        )
        assert result is None


# ---------------------------------------------------------------------------
# Test 4: DateFiled before start_date is excluded
# ---------------------------------------------------------------------------

class TestDateRangeFiltering:
    def test_filing_before_start_date_excluded(self):
        line = (
            "1234567|Old Corp|S-1|2016-12-31|"
            "edgar/data/1234567/0001234567-16-000001.txt"
        )
        result = _parse_line(
            line,
            date(2017, 1, 1),
            date(2025, 12, 31),
            {"S-1"},
            "2016_QTR4",
        )
        assert result is None


# ---------------------------------------------------------------------------
# Test 5: DateFiled after end_date is excluded
# ---------------------------------------------------------------------------

    def test_filing_after_end_date_excluded(self):
        line = (
            "1234567|Future Corp|S-1|2026-01-01|"
            "edgar/data/1234567/0001234567-26-000001.txt"
        )
        result = _parse_line(
            line,
            date(2017, 1, 1),
            date(2025, 12, 31),
            {"S-1"},
            "2026_QTR1",
        )
        assert result is None

    def test_filing_on_end_date_is_included(self):
        line = (
            "1234567|Edge Corp|S-1|2025-12-31|"
            "edgar/data/1234567/0001234567-25-000001.txt"
        )
        result = _parse_line(
            line,
            date(2017, 1, 1),
            date(2025, 12, 31),
            {"S-1"},
            "2025_QTR4",
        )
        assert result is not None
        assert result.date_filed == date(2025, 12, 31)

    def test_filing_on_start_date_is_included(self):
        line = (
            "1234567|Start Corp|S-1|2017-01-01|"
            "edgar/data/1234567/0001234567-17-000001.txt"
        )
        result = _parse_line(
            line,
            date(2017, 1, 1),
            date(2025, 12, 31),
            {"S-1"},
            "2017_QTR1",
        )
        assert result is not None
        assert result.date_filed == date(2017, 1, 1)


# ---------------------------------------------------------------------------
# Test 6: Cache hit — no HTTP request when file already exists on disk
# ---------------------------------------------------------------------------

class TestCacheHit:
    def test_no_http_request_on_cache_hit(self, tmp_path):
        cfg = _make_config(tmp_path)
        discovery = FilingDiscovery(cfg)

        # Pre-populate cache with a minimal master.gz
        gz_data = _make_master_gz([
            "1234567|Cached Corp|S-1|2021-02-15|"
            "edgar/data/1234567/0001234567-21-000001.txt"
        ])
        cache_file = cfg.cache_dir / "master_gz" / "2021_QTR1.gz"
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(gz_data)

        with patch("research.pipeline.discovery.requests.get") as mock_get:
            filings, failures = discovery.discover(
                date(2021, 1, 1), date(2021, 3, 31)
            )

        mock_get.assert_not_called()
        assert len(failures) == 0
        assert len(filings) == 1
        assert filings[0].form_type == "S-1"


# ---------------------------------------------------------------------------
# Test 7: HTTP 500 — quarter skipped, failure recorded in quarters_failed
# ---------------------------------------------------------------------------

class TestHttpFailure:
    def test_http_500_skipped_and_recorded(self, tmp_path):
        cfg = _make_config(tmp_path)
        discovery = FilingDiscovery(cfg)

        mock_resp = _make_mock_response(b"", status_code=500)

        with patch("research.pipeline.discovery.requests.get", return_value=mock_resp):
            filings, failures = discovery.discover(
                date(2021, 1, 1), date(2021, 3, 31)
            )

        # No exception raised — quarter silently skipped
        assert "2021_QTR1" in failures
        assert filings == []

    def test_multiple_quarters_one_failure(self, tmp_path):
        cfg = _make_config(tmp_path)
        discovery = FilingDiscovery(cfg)

        q1_gz = _make_master_gz([
            "1234567|Good Corp|S-1|2021-02-01|"
            "edgar/data/1234567/0001234567-21-000001.txt"
        ])
        good_resp = _make_mock_response(q1_gz, status_code=200)
        bad_resp = _make_mock_response(b"", status_code=500)

        # Q1 succeeds, Q2 fails
        with patch(
            "research.pipeline.discovery.requests.get",
            side_effect=[good_resp, bad_resp],
        ):
            filings, failures = discovery.discover(
                date(2021, 1, 1), date(2021, 6, 30)
            )

        assert "2021_QTR2" in failures
        assert "2021_QTR1" not in failures
        assert len(filings) == 1


# ---------------------------------------------------------------------------
# Integration-style: discover returns correct quarter_key
# ---------------------------------------------------------------------------

class TestDiscover:
    def test_quarter_key_on_discovered_filing(self, tmp_path):
        cfg = _make_config(tmp_path)
        discovery = FilingDiscovery(cfg)

        gz_data = _make_master_gz([
            "9876543|Q3 Corp|424B4|2022-08-10|"
            "edgar/data/9876543/0009876543-22-000100.txt"
        ])

        with patch(
            "research.pipeline.discovery.requests.get",
            return_value=_make_mock_response(gz_data),
        ):
            filings, failures = discovery.discover(
                date(2022, 7, 1), date(2022, 9, 30)
            )

        assert failures == []
        assert len(filings) == 1
        assert filings[0].quarter_key == "2022_QTR3"
        assert filings[0].accession_number == "0009876543-22-000100"

    def test_only_in_range_form_types_returned(self, tmp_path):
        cfg = _make_config(tmp_path)
        discovery = FilingDiscovery(cfg)

        gz_data = _make_master_gz([
            "1000001|Corp A|S-1|2022-01-15|edgar/data/1000001/0001000001-22-000001.txt",
            "1000002|Corp B|DEF 14A|2022-01-20|edgar/data/1000002/0001000002-22-000002.txt",
            "1000003|Corp C|13D/A|2022-01-25|edgar/data/1000003/0001000003-22-000003.txt",
            "1000004|Corp D|10-K|2022-02-01|edgar/data/1000004/0001000004-22-000004.txt",
        ])

        with patch(
            "research.pipeline.discovery.requests.get",
            return_value=_make_mock_response(gz_data),
        ):
            filings, _ = discovery.discover(date(2022, 1, 1), date(2022, 3, 31))

        form_types = {f.form_type for f in filings}
        assert "S-1" in form_types
        assert "13D/A" in form_types
        assert "DEF 14A" not in form_types
        assert "10-K" not in form_types
        assert len(filings) == 2
