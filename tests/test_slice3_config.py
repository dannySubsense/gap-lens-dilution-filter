"""
Slice 3: Config Extension — Acceptance Tests

Done-when criteria verified:
- edgar_poll_interval default is 90
- setup_quality dict has keys A-E with correct values
- setup_quality individual keys A/B/C/D/E are correct (parametrized)
- edgar_efts_url starts with "https://efts.sec.gov"
- score_normalization_ceiling is 1.0
- adv_min_threshold is 500_000
- default_borrow_cost is 0.30
- duckdb_path is a non-empty string ending in .duckdb
- lifecycle_check_interval is 300
- ibkr_borrow_cost_enabled default is False
- DilutionService still imports cleanly after config extension
- setup_quality is a computed property that reflects setup_quality_a changes
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings  # noqa: E402


# ---------------------------------------------------------------------------
# AC-S3-01: edgar_poll_interval default is 90
# ---------------------------------------------------------------------------

def test_edgar_poll_interval_default():
    """settings.edgar_poll_interval must equal 90 (AC-01: poller interval default)."""
    assert settings.edgar_poll_interval == 90


# ---------------------------------------------------------------------------
# AC-S3-02: setup_quality dict has keys A-E with correct values
# ---------------------------------------------------------------------------

def test_setup_quality_is_dict_with_all_keys():
    """settings.setup_quality must be a dict with keys A, B, C, D, E."""
    sq = settings.setup_quality
    assert isinstance(sq, dict), f"Expected dict, got {type(sq)}"
    assert set(sq.keys()) == {"A", "B", "C", "D", "E"}, (
        f"setup_quality keys mismatch: {set(sq.keys())}"
    )


def test_setup_quality_correct_values():
    """setup_quality dict must have the exact Phase 1 default values per spec."""
    sq = settings.setup_quality
    expected = {"A": 0.65, "B": 0.55, "C": 0.60, "D": 0.45, "E": 0.50}
    assert sq == expected, f"setup_quality values mismatch: {sq} != {expected}"


# ---------------------------------------------------------------------------
# AC-S3-03: setup_quality individual keys (parametrized)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("setup_key,expected_value", [
    ("A", 0.65),
    ("B", 0.55),
    ("C", 0.60),
    ("D", 0.45),
    ("E", 0.50),
])
def test_setup_quality_individual_key(setup_key, expected_value):
    """Each setup_quality[key] must equal the Phase 1 configured win rate."""
    assert settings.setup_quality[setup_key] == expected_value, (
        f"setup_quality['{setup_key}'] = {settings.setup_quality[setup_key]}, "
        f"expected {expected_value}"
    )


# ---------------------------------------------------------------------------
# AC-S3-04: edgar_efts_url starts with https://efts.sec.gov
# ---------------------------------------------------------------------------

def test_edgar_efts_url_starts_correctly():
    """settings.edgar_efts_url must start with 'https://efts.sec.gov'."""
    assert settings.edgar_efts_url.startswith("https://efts.sec.gov"), (
        f"edgar_efts_url does not start with 'https://efts.sec.gov': "
        f"{settings.edgar_efts_url!r}"
    )


# ---------------------------------------------------------------------------
# AC-S3-05: score_normalization_ceiling is 1.0
# ---------------------------------------------------------------------------

def test_score_normalization_ceiling():
    """settings.score_normalization_ceiling must equal 1.0."""
    assert settings.score_normalization_ceiling == 1.0


# ---------------------------------------------------------------------------
# AC-S3-06: adv_min_threshold is 500_000
# ---------------------------------------------------------------------------

def test_adv_min_threshold():
    """settings.adv_min_threshold must equal 500_000 (Filter 6 ADV threshold)."""
    assert settings.adv_min_threshold == 500_000


# ---------------------------------------------------------------------------
# AC-S3-07: default_borrow_cost is 0.30
# ---------------------------------------------------------------------------

def test_default_borrow_cost():
    """settings.default_borrow_cost must equal 0.30 (30% annualized fallback)."""
    assert settings.default_borrow_cost == 0.30


# ---------------------------------------------------------------------------
# AC-S3-08: duckdb_path is a non-empty string ending in .duckdb
# ---------------------------------------------------------------------------

def test_duckdb_path_has_valid_default():
    """settings.duckdb_path must be a non-empty string ending in '.duckdb'."""
    path = settings.duckdb_path
    assert isinstance(path, str) and len(path) > 0, (
        "duckdb_path must be a non-empty string"
    )
    assert path.endswith(".duckdb"), (
        f"duckdb_path '{path}' does not end with '.duckdb'"
    )


# ---------------------------------------------------------------------------
# AC-S3-09: lifecycle_check_interval is 300
# ---------------------------------------------------------------------------

def test_lifecycle_check_interval():
    """settings.lifecycle_check_interval must equal 300."""
    assert settings.lifecycle_check_interval == 300


# ---------------------------------------------------------------------------
# AC-S3-10: ibkr_borrow_cost_enabled default is False
# ---------------------------------------------------------------------------

def test_ibkr_borrow_cost_enabled_default():
    """settings.ibkr_borrow_cost_enabled must default to False."""
    assert settings.ibkr_borrow_cost_enabled is False


# ---------------------------------------------------------------------------
# AC-S3-11: DilutionService still imports cleanly after config extension
# ---------------------------------------------------------------------------

def test_dilution_service_still_imports():
    """DilutionService must remain importable after config.py was extended."""
    from app.services.dilution import DilutionService  # noqa: PLC0415
    assert DilutionService is not None


# ---------------------------------------------------------------------------
# AC-S3-12: setup_quality is a computed property reflecting attribute changes
# ---------------------------------------------------------------------------

def test_setup_quality_is_computed_property():
    """Modifying setup_quality_a on a fresh Settings instance must produce
    an updated value in setup_quality dict."""
    from app.core.config import Settings  # noqa: PLC0415

    custom = Settings(setup_quality_a=0.99)
    assert custom.setup_quality["A"] == 0.99, (
        f"setup_quality['A'] did not reflect modified setup_quality_a: "
        f"{custom.setup_quality['A']}"
    )
