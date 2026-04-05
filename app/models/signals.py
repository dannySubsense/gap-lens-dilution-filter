from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


class SignalRow(BaseModel):
    id: int
    accession_number: str
    ticker: str
    setup_type: str
    score: int
    rank: str
    alert_type: str
    status: str
    alerted_at: datetime
    price_at_alert: Optional[float] = None
    entry_price: Optional[float] = None
    cover_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None
    price_move_pct: Optional[float] = None
    elapsed_seconds: Optional[int] = None


class ClassificationDetail(BaseModel):
    setup_type: str
    confidence: float
    dilution_severity: float
    immediate_pressure: bool
    price_discount: Optional[float] = None
    short_attractiveness: int
    key_excerpt: str
    reasoning: str
    classifier_version: str
    scored_at: datetime


class SignalDetailResponse(BaseModel):
    signal: SignalRow
    ticker: str
    entity_name: Optional[str] = None
    classification: ClassificationDetail
    filing_url: str
    form_type: str
    filed_at: datetime
    current_price: Optional[float] = None


class SignalListResponse(BaseModel):
    signals: list[SignalRow]
    count: int


class PositionRequest(BaseModel):
    entry_price: Optional[float] = None
    cover_price: Optional[float] = None

    @field_validator("entry_price")
    @classmethod
    def entry_price_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0:
            raise ValueError("entry_price must be greater than $0.00")
        return v

    @field_validator("cover_price")
    @classmethod
    def cover_price_above_threshold(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v <= 0.01:
            raise ValueError("Cover price must be at least $0.01")
        return v


class PositionResponse(BaseModel):
    id: int
    entry_price: Optional[float] = None
    cover_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: str


class HealthResponse(BaseModel):
    status: str
    last_poll_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    poll_interval_seconds: int
    fmp_configured: bool
    askedgar_configured: bool
    db_path: str
