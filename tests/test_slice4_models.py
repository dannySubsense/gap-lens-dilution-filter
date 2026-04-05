"""
Slice 4: Pydantic Models & TypeScript Types — Acceptance Tests

Done-when criteria verified:
1.  SignalRow, HealthResponse, PositionRequest import successfully
2.  PositionRequest(cover_price=0.005) raises ValidationError (below $0.01)
3.  PositionRequest(cover_price=0.01) raises ValidationError (must be strictly > 0.01)
4.  PositionRequest(cover_price=0.02) validates successfully
5.  PositionRequest(entry_price=5.20) validates successfully
6.  PositionRequest(entry_price=0.0) raises ValidationError (must be > 0)
7.  PositionRequest(entry_price=-1.0) raises ValidationError
8.  PositionRequest() validates with both fields None (both optional)
9.  SignalRow can be constructed with all required fields; optional fields default to None
10. HealthResponse can be constructed with required fields
11. SignalDetailResponse has entity_name field that accepts None
12. signals.py has no imports from app.services.* (import cycle check)
13. TypeScript file exists at frontend/src/types/signals.ts
14. TypeScript file contains ApiResult type
15. TypeScript SignalDetailResponse contains entity_name field
"""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# AC-S4-01: SignalRow, HealthResponse, PositionRequest import successfully
# ---------------------------------------------------------------------------

def test_model_imports_succeed():
    """SignalRow, HealthResponse, and PositionRequest must be importable from app.models.signals."""
    from app.models.signals import SignalRow, HealthResponse, PositionRequest  # noqa: PLC0415
    assert SignalRow is not None
    assert HealthResponse is not None
    assert PositionRequest is not None


# ---------------------------------------------------------------------------
# AC-S4-02: cover_price=0.005 raises ValidationError (below $0.01)
# ---------------------------------------------------------------------------

def test_position_request_cover_price_below_minimum_raises():
    """PositionRequest with cover_price=0.005 must raise ValidationError."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    with pytest.raises(PydanticValidationError):
        PositionRequest(cover_price=0.005)


# ---------------------------------------------------------------------------
# AC-S4-03: cover_price=0.01 raises ValidationError (must be strictly > 0.01)
# ---------------------------------------------------------------------------

def test_position_request_cover_price_at_exact_minimum_raises():
    """PositionRequest with cover_price=0.01 must raise ValidationError (validator is strictly >)."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    with pytest.raises(PydanticValidationError):
        PositionRequest(cover_price=0.01)


# ---------------------------------------------------------------------------
# AC-S4-04: cover_price=0.02 validates successfully
# ---------------------------------------------------------------------------

def test_position_request_cover_price_above_minimum_is_valid():
    """PositionRequest with cover_price=0.02 must validate without error."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    req = PositionRequest(cover_price=0.02)
    assert req.cover_price == 0.02


# ---------------------------------------------------------------------------
# AC-S4-05: entry_price=5.20 validates successfully
# ---------------------------------------------------------------------------

def test_position_request_valid_entry_price():
    """PositionRequest with entry_price=5.20 must validate without error."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    req = PositionRequest(entry_price=5.20)
    assert req.entry_price == pytest.approx(5.20)


# ---------------------------------------------------------------------------
# AC-S4-06: entry_price=0.0 raises ValidationError (must be > 0)
# ---------------------------------------------------------------------------

def test_position_request_zero_entry_price_raises():
    """PositionRequest with entry_price=0.0 must raise ValidationError."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    with pytest.raises(PydanticValidationError):
        PositionRequest(entry_price=0.0)


# ---------------------------------------------------------------------------
# AC-S4-07: entry_price=-1.0 raises ValidationError
# ---------------------------------------------------------------------------

def test_position_request_negative_entry_price_raises():
    """PositionRequest with entry_price=-1.0 must raise ValidationError."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    with pytest.raises(PydanticValidationError):
        PositionRequest(entry_price=-1.0)


# ---------------------------------------------------------------------------
# AC-S4-08: PositionRequest() with no arguments is valid (both fields optional)
# ---------------------------------------------------------------------------

def test_position_request_defaults_to_none():
    """PositionRequest() with no arguments must be valid; both fields default to None."""
    from app.models.signals import PositionRequest  # noqa: PLC0415
    req = PositionRequest()
    assert req.entry_price is None
    assert req.cover_price is None


# ---------------------------------------------------------------------------
# AC-S4-09: SignalRow constructs with required fields; optional fields default to None
# ---------------------------------------------------------------------------

def test_signal_row_construction_with_required_fields():
    """SignalRow must accept all required fields and default optional fields to None."""
    from datetime import datetime, timezone  # noqa: PLC0415
    from app.models.signals import SignalRow  # noqa: PLC0415

    row = SignalRow(
        id=1,
        accession_number="0001234567-26-000001",
        ticker="AAPL",
        setup_type="DILUTION_SHORT",
        score=75,
        rank="A",
        alert_type="NEW_SETUP",
        status="LIVE",
        alerted_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert row.id == 1
    assert row.ticker == "AAPL"
    # Optional fields default to None
    assert row.price_at_alert is None
    assert row.entry_price is None
    assert row.cover_price is None
    assert row.pnl_pct is None
    assert row.closed_at is None
    assert row.close_reason is None
    assert row.price_move_pct is None
    assert row.elapsed_seconds is None


# ---------------------------------------------------------------------------
# AC-S4-10: HealthResponse constructs with required fields
# ---------------------------------------------------------------------------

def test_health_response_construction():
    """HealthResponse must construct successfully with all required fields."""
    from app.models.signals import HealthResponse  # noqa: PLC0415

    resp = HealthResponse(
        status="ok",
        poll_interval_seconds=90,
        fmp_configured=True,
        askedgar_configured=False,
        db_path="./data/filter.duckdb",
    )
    assert resp.status == "ok"
    assert resp.poll_interval_seconds == 90
    assert resp.fmp_configured is True
    assert resp.last_poll_at is None
    assert resp.last_success_at is None


# ---------------------------------------------------------------------------
# AC-S4-11: SignalDetailResponse has entity_name field that accepts None
# ---------------------------------------------------------------------------

def test_signal_detail_response_entity_name_accepts_none():
    """SignalDetailResponse.entity_name must be optional and accept None."""
    from datetime import datetime, timezone  # noqa: PLC0415
    from app.models.signals import (  # noqa: PLC0415
        SignalDetailResponse, SignalRow, ClassificationDetail,
    )

    signal = SignalRow(
        id=1,
        accession_number="0001234567-26-000001",
        ticker="AAPL",
        setup_type="DILUTION_SHORT",
        score=75,
        rank="A",
        alert_type="NEW_SETUP",
        status="LIVE",
        alerted_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    classification = ClassificationDetail(
        setup_type="DILUTION_SHORT",
        confidence=0.85,
        dilution_severity=0.70,
        immediate_pressure=True,
        short_attractiveness=80,
        key_excerpt="We intend to sell shares...",
        reasoning="High dilution risk detected",
        classifier_version="rule-based-v1",
        scored_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    detail = SignalDetailResponse(
        signal=signal,
        ticker="AAPL",
        entity_name=None,
        classification=classification,
        filing_url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001.htm",
        form_type="S-1",
        filed_at=datetime(2026, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert detail.entity_name is None


# ---------------------------------------------------------------------------
# AC-S4-12: signals.py has no imports from app.services.* (import cycle check)
# ---------------------------------------------------------------------------

def test_signals_py_has_no_services_imports():
    """app/models/signals.py must not import from app.services.* to avoid import cycles."""
    signals_path = PROJECT_ROOT / "app" / "models" / "signals.py"
    content = signals_path.read_text()
    import_lines = [
        line.strip() for line in content.splitlines()
        if line.strip().startswith("from app.services") or line.strip().startswith("import app.services")
    ]
    assert not import_lines, (
        f"signals.py contains app.services imports (import cycle risk): {import_lines}"
    )


# ---------------------------------------------------------------------------
# AC-S4-13: TypeScript file exists at frontend/src/types/signals.ts
# ---------------------------------------------------------------------------

def test_typescript_signals_file_exists():
    """frontend/src/types/signals.ts must exist."""
    ts_path = PROJECT_ROOT / "frontend" / "src" / "types" / "signals.ts"
    assert ts_path.exists(), f"TypeScript signals file not found at {ts_path}"


# ---------------------------------------------------------------------------
# AC-S4-14: TypeScript file contains ApiResult type
# ---------------------------------------------------------------------------

def test_typescript_file_contains_api_result_type():
    """frontend/src/types/signals.ts must contain an ApiResult type definition."""
    ts_path = PROJECT_ROOT / "frontend" / "src" / "types" / "signals.ts"
    content = ts_path.read_text()
    assert "ApiResult" in content, (
        "signals.ts does not contain 'ApiResult' type"
    )


# ---------------------------------------------------------------------------
# AC-S4-15: TypeScript SignalDetailResponse contains entity_name field
# ---------------------------------------------------------------------------

def test_typescript_signal_detail_response_has_entity_name():
    """TypeScript SignalDetailResponse interface must declare an entity_name field."""
    ts_path = PROJECT_ROOT / "frontend" / "src" / "types" / "signals.ts"
    content = ts_path.read_text()
    assert "entity_name" in content, (
        "signals.ts SignalDetailResponse does not contain 'entity_name' field"
    )
