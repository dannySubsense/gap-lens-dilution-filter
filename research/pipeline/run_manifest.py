"""
RunManifest — Slice 12 of the backtest pipeline.

Accumulates pipeline parameters and run statistics across the pipeline.
Finalized and written to backtest_run_metadata.json by OutputWriter.

All parameters affecting output are recorded here per Section 12 (Reproducibility Design)
of 02-ARCHITECTURE.md.
"""

from dataclasses import dataclass, field


@dataclass
class RunManifest:
    """
    Accumulates pipeline run parameters and statistics.

    Mutable throughout the pipeline run; finalized before OutputWriter.write()
    is called. parquet_sha256 and parquet_row_count are populated by
    OutputWriter after writing the results Parquet file.
    """

    run_date: str  # ISO 8601 UTC timestamp of pipeline run start
    pipeline_version: str  # e.g. "backtest-v1.0.0"
    classifier_version: str  # Always "rule-based-v1"
    scoring_formula_version: str  # e.g. "v1.0"
    date_range_start: str  # "2017-01-01"
    date_range_end: str  # "2025-12-31"
    form_types: list[str] = field(default_factory=list)
    market_cap_threshold: int = 0
    float_threshold: int = 0
    dilution_pct_threshold: float = 0.0
    price_threshold: float = 0.0
    adv_threshold: float = 0.0
    float_data_start: str = "2020-03-04"  # Must be "2020-03-04"
    market_data_db_path: str = ""
    market_data_db_certification: str = ""
    total_filings_discovered: int = 0
    total_cik_resolved: int = 0
    total_fetch_ok: int = 0
    total_classified: int = 0
    total_passed_filters: int = 0
    total_with_outcomes: int = 0
    quarters_failed: list[str] = field(default_factory=list)
    parquet_sha256: str = ""  # Populated by OutputWriter after writing
    parquet_row_count: int = 0  # Populated by OutputWriter after writing
    execution_timestamp: str = ""  # ISO 8601 UTC; same value as run_date
    canary_no_lookahead: str = "PASS"  # "PASS" or "FAIL"
    total_unresolvable_count: int = (
        0  # Filings where CIK not found in raw_symbols_massive
    )
    normalization_config_loaded: bool = False
    normalization_config_entry_count: int = 0

    def to_dict(self) -> dict:
        """
        Convert to a JSON-serializable dict.

        All fields are primitives or lists of primitives — no further
        conversion is required beyond returning the dataclass fields.
        """
        return {
            "run_date": self.run_date,
            "pipeline_version": self.pipeline_version,
            "classifier_version": self.classifier_version,
            "scoring_formula_version": self.scoring_formula_version,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "form_types": self.form_types,
            "market_cap_threshold": self.market_cap_threshold,
            "float_threshold": self.float_threshold,
            "dilution_pct_threshold": self.dilution_pct_threshold,
            "price_threshold": self.price_threshold,
            "adv_threshold": self.adv_threshold,
            "float_data_start": self.float_data_start,
            "market_data_db_path": self.market_data_db_path,
            "market_data_db_certification": self.market_data_db_certification,
            "total_filings_discovered": self.total_filings_discovered,
            "total_cik_resolved": self.total_cik_resolved,
            "total_fetch_ok": self.total_fetch_ok,
            "total_classified": self.total_classified,
            "total_passed_filters": self.total_passed_filters,
            "total_with_outcomes": self.total_with_outcomes,
            "quarters_failed": self.quarters_failed,
            "parquet_sha256": self.parquet_sha256,
            "parquet_row_count": self.parquet_row_count,
            "execution_timestamp": self.execution_timestamp,
            "canary_no_lookahead": self.canary_no_lookahead,
            "total_unresolvable_count": self.total_unresolvable_count,
            "normalization_config_loaded": self.normalization_config_loaded,
            "normalization_config_entry_count": self.normalization_config_entry_count,
        }
