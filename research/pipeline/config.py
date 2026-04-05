"""
Pipeline configuration for the backtest pipeline.

Module-level constants are hardcoded. Three values (DEFAULT_BORROW_COST,
SCORE_NORMALIZATION_CEILING, SETUP_QUALITY) are read from the live app
settings at import time so they stay in sync with production.
"""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

FLOAT_DATA_START_DATE = date(2020, 3, 4)
MARKET_DATA_DB_PATH = Path("/home/d-tuned/market_data/duckdb/market_data.duckdb")
PIPELINE_VERSION = "backtest-v1.0.0"
CLASSIFIER_VERSION = "rule-based-v1"
SCORING_FORMULA_VERSION = "v1.0"


# ---------------------------------------------------------------------------
# BacktestConfig dataclass
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    # Date range
    date_range_start: date = date(2017, 1, 1)
    date_range_end: date = date(2025, 12, 31)

    # Form types
    allowed_form_types: list[str] = field(default_factory=lambda: [
        "S-1", "S-1/A", "S-3", "424B2", "424B4", "8-K", "13D/A"
    ])

    # Filter thresholds (must match live settings and 01-REQUIREMENTS.md filter table)
    market_cap_max: int = 2_000_000_000    # $2B (Filter 2: market_cap < $2B)
    float_max: int = 50_000_000            # 50M shares (Filter 3: float < 50M)
    dilution_pct_min: float = 0.10         # 10% (Filter 4: dilution > 10%)
    price_min: float = 1.00                # $1.00 (Filter 5: price > $1.00)
    adv_min: float = 500_000               # $500K dollar volume (Filter 6: ADV > $500K)

    # Pipeline settings
    filing_text_max_bytes: int = 512_000
    fetch_concurrency: int = 8
    fetch_rate_limit_per_sec: int = 10
    fetch_timeout_sec: int = 30

    # Paths
    market_data_db_path: Path = field(default_factory=lambda: MARKET_DATA_DB_PATH)
    cache_dir: Path = field(default_factory=lambda: Path("research/cache"))
    output_dir: Path = field(default_factory=lambda: Path("docs/research/data"))
    normalization_config_path: Path = field(
        default_factory=lambda: Path("research/config/underwriter_normalization.json")
    )


# ---------------------------------------------------------------------------
# Values read from live app settings
# ---------------------------------------------------------------------------

from app.core.config import settings as _live_settings  # noqa: E402

DEFAULT_BORROW_COST: float = _live_settings.default_borrow_cost
SCORE_NORMALIZATION_CEILING: float = _live_settings.score_normalization_ceiling
SETUP_QUALITY: dict = _live_settings.setup_quality
