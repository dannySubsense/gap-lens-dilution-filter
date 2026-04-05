from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Inherited from gap-lens-dilution (preserve all existing fields)
    askedgar_api_key: str = "your-api-key-here"
    fmp_api_key: str = ""
    massive_api_key: str = ""
    askedgar_url: str = "https://eapi.askedgar.io"
    request_timeout: int = 30
    cors_origins: list[str] = ["http://localhost:3000", "http://100.70.21.69:3000"]

    # New: classifier
    classifier_name: str = "rule-based-v1"

    # New: EDGAR poller
    edgar_poll_interval: int = 90
    edgar_efts_url: str = "https://efts.sec.gov/LATEST/search-index"

    # New: storage
    duckdb_path: str = "./data/filter.duckdb"
    filing_text_max_bytes: int = 512_000

    # New: scoring
    default_borrow_cost: float = 0.30
    adv_min_threshold: float = 500_000
    score_normalization_ceiling: float = 1.0
    setup_quality_a: float = 0.65
    setup_quality_b: float = 0.55
    setup_quality_c: float = 0.60
    setup_quality_d: float = 0.45
    setup_quality_e: float = 0.50

    @property
    def setup_quality(self) -> dict[str, float]:
        return {
            "A": self.setup_quality_a,
            "B": self.setup_quality_b,
            "C": self.setup_quality_c,
            "D": self.setup_quality_d,
            "E": self.setup_quality_e,
        }

    # New: lifecycle
    lifecycle_check_interval: int = 300
    ibkr_borrow_cost_enabled: bool = False


settings = Settings()
