from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


class GapStatEntry(BaseModel):
    date: str
    gap_percentage: Optional[float] = None
    market_open: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    market_close: Optional[float] = None
    high_time: Optional[str] = None
    closed_over_vwap: Optional[bool] = None
    volume: Optional[int] = None


class OfferingEntry(BaseModel):
    headline: str
    offering_amount: Optional[float] = None
    share_price: Optional[float] = None
    shares_amount: Optional[float] = None
    warrants_amount: Optional[float] = None
    filed_at: Optional[str] = None


class OwnerEntry(BaseModel):
    owner_name: Optional[str] = None
    title: Optional[str] = None
    owner_type: Optional[str] = None
    common_shares_amount: Optional[int] = None
    document_url: Optional[str] = None


class OwnershipGroup(BaseModel):
    reported_date: Optional[str] = None
    owners: list[OwnerEntry]


class ChartAnalysis(BaseModel):
    rating: str


class WarrantItem(BaseModel):
    details: str
    warrants_remaining: Optional[float] = None
    warrants_exercise_price: Optional[float] = None
    registered: Optional[str] = None
    filed_at: Optional[str] = None
    askedgar_url: Optional[str] = None


class ConvertibleItem(BaseModel):
    details: str
    underlying_shares_remaining: Optional[float] = None
    conversion_price: Optional[float] = None
    registered: Optional[str] = None
    filed_at: Optional[str] = None
    askedgar_url: Optional[str] = None


class DilutionV2Response(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    offeringRisk: Optional[str] = None
    offeringAbility: Optional[str] = None
    offeringAbilityDesc: Optional[str] = None
    dilutionRisk: Optional[str] = None
    dilutionDesc: Optional[str] = None
    offeringFrequency: Optional[str] = None
    cashNeed: Optional[str] = None
    cashNeedDesc: Optional[str] = None
    cashRunway: Optional[float] = None
    cashBurn: Optional[float] = None
    estimatedCash: Optional[float] = None
    warrantExercise: Optional[str] = None
    warrantExerciseDesc: Optional[str] = None
    float_shares: Optional[float] = Field(
        default=None, alias="float", serialization_alias="float"
    )
    outstanding: Optional[float] = None
    marketCap: Optional[float] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    insiderOwnership: Optional[float] = None
    institutionalOwnership: Optional[float] = None
    news: list = []
    registrations: list = []
    warrants: list[WarrantItem] = []
    convertibles: list[ConvertibleItem] = []
    gapStats: list[GapStatEntry] = []
    offerings: list[OfferingEntry] = []
    ownership: Optional[OwnershipGroup] = None
    chartAnalysis: Optional[ChartAnalysis] = None
    stockPrice: Optional[float] = None
    mgmtCommentary: Optional[str] = None


class GainerEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ticker: str
    todaysChangePerc: float
    price: Optional[float] = None
    volume: Optional[int] = None
    float_shares: Optional[float] = Field(
        default=None, alias="float", serialization_alias="float"
    )
    marketCap: Optional[float] = None
    sector: Optional[str] = None
    country: Optional[str] = None
    risk: Optional[str] = None
    chartRating: Optional[str] = None
    newsToday: bool = False
