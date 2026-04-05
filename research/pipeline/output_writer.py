"""
OutputWriter — Slice 12 of the backtest pipeline.

Assembles all BacktestRow and ParticipantRecord objects into the final 5
output files:
  - backtest_results.parquet
  - backtest_results.csv
  - backtest_participants.parquet
  - backtest_participants.csv
  - backtest_run_metadata.json

Schema enforcement: explicit pyarrow.schema() — no inference from DataFrame.
SHA-256 of the results Parquet is computed after writing and stored in the
RunManifest before the JSON is written.
"""

import hashlib
import json
import logging
from dataclasses import fields as dc_fields
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from research.pipeline.dataclasses import BacktestRow, ParticipantRecord
from research.pipeline.run_manifest import RunManifest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Explicit schema declarations — must match 01-REQUIREMENTS.md exactly
# ---------------------------------------------------------------------------

RESULTS_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("cik", pa.string()),
        ("ticker", pa.string()),
        ("entity_name", pa.string()),
        ("form_type", pa.string()),
        ("filed_at", pa.timestamp("us", tz="UTC")),
        ("setup_type", pa.string()),
        ("confidence", pa.float32()),
        ("shares_offered_raw", pa.int64()),
        ("dilution_severity", pa.float32()),
        ("price_discount", pa.float32()),
        ("immediate_pressure", pa.bool_()),
        ("key_excerpt", pa.string()),
        ("filter_status", pa.string()),
        ("filter_fail_reason", pa.string()),
        ("float_available", pa.bool_()),
        ("in_smallcap_universe", pa.bool_()),
        ("price_at_T", pa.float32()),
        ("market_cap_at_T", pa.float32()),
        ("float_at_T", pa.float32()),
        ("adv_at_T", pa.float32()),
        ("short_interest_at_T", pa.float32()),
        ("borrow_cost_source", pa.string()),
        ("score", pa.int32()),
        ("rank", pa.string()),
        ("dilution_extractable", pa.bool_()),
        ("outcome_computable", pa.bool_()),
        ("return_1d", pa.float32()),
        ("return_3d", pa.float32()),
        ("return_5d", pa.float32()),
        ("return_20d", pa.float32()),
        ("delisted_before_T1", pa.bool_()),
        ("delisted_before_T3", pa.bool_()),
        ("delisted_before_T5", pa.bool_()),
        ("delisted_before_T20", pa.bool_()),
        ("pipeline_version", pa.string()),
        ("processed_at", pa.timestamp("us", tz="UTC")),
    ]
)

PARTICIPANTS_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("firm_name", pa.string()),
        ("role", pa.string()),
        ("is_normalized", pa.bool_()),
        ("raw_text_snippet", pa.string()),
    ]
)

# Column names in BacktestRow field declaration order (used to build the DF)
_RESULTS_COLUMNS = [f.name for f in dc_fields(BacktestRow)]

# Column names in ParticipantRecord field declaration order
_PARTICIPANTS_COLUMNS = [f.name for f in dc_fields(ParticipantRecord)]

# Default output directory relative to this file's location:
# research/pipeline/output_writer.py → project root is three levels up
_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent / "docs" / "research" / "data"


class OutputWriter:
    """
    Writes BacktestRow and ParticipantRecord objects to 5 output files.

    Output directory: docs/research/data/ (relative to project root)
    Files:
      - backtest_results.parquet
      - backtest_results.csv
      - backtest_participants.parquet
      - backtest_participants.csv
      - backtest_run_metadata.json
    """

    def __init__(self, output_dir: str | Path | None = None) -> None:
        """
        Parameters
        ----------
        output_dir:
            Absolute path to the output directory.
            Defaults to docs/research/data/ relative to the project root.
            The directory is created if it does not exist.
        """
        if output_dir is None:
            self._output_dir = _DEFAULT_OUTPUT_DIR
        else:
            self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        rows: list[BacktestRow],
        participants: list[ParticipantRecord],
        manifest: RunManifest,
    ) -> None:
        """
        Write all 5 output files.

        Populates manifest.parquet_sha256 and manifest.parquet_row_count
        after writing the results Parquet file, then writes the metadata JSON.

        Parameters
        ----------
        rows:
            All BacktestRow objects produced by the pipeline.
        participants:
            All ParticipantRecord objects produced by the pipeline.
            May be an empty list.
        manifest:
            RunManifest to be serialised; parquet_sha256 and
            parquet_row_count will be mutated in place.
        """
        results_df = self._build_results_df(rows)
        participants_df = self._build_participants_df(participants)

        # 1. Write results Parquet
        results_path = self._output_dir / "backtest_results.parquet"
        self._write_results_parquet(results_df, results_path)

        # 2. Compute SHA-256 of written Parquet bytes
        manifest.parquet_sha256 = hashlib.sha256(results_path.read_bytes()).hexdigest()
        manifest.parquet_row_count = len(rows)

        # 3. Write results CSV
        results_path_csv = self._output_dir / "backtest_results.csv"
        results_df.to_csv(
            results_path_csv, index=False, encoding="utf-8", lineterminator="\n"
        )
        logger.info("Wrote %s", results_path_csv)

        # 4. Write participants Parquet
        participants_parquet_path = self._output_dir / "backtest_participants.parquet"
        self._write_participants_parquet(participants_df, participants_parquet_path)

        # 5. Write participants CSV
        participants_csv_path = self._output_dir / "backtest_participants.csv"
        participants_df.to_csv(
            participants_csv_path,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
        )
        logger.info("Wrote %s", participants_csv_path)

        # 6. Write metadata JSON (parquet_sha256 now populated)
        metadata_path = self._output_dir / "backtest_run_metadata.json"
        metadata_path.write_text(
            json.dumps(manifest.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Wrote %s", metadata_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_results_df(self, rows: list[BacktestRow]) -> pd.DataFrame:
        """Convert BacktestRow list to a sorted DataFrame."""
        if rows:
            data = [
                {col: getattr(row, col) for col in _RESULTS_COLUMNS} for row in rows
            ]
            df = pd.DataFrame(data, columns=_RESULTS_COLUMNS)
        else:
            df = pd.DataFrame(columns=_RESULTS_COLUMNS)

        # UTC-localise timestamp columns (handles both naive and tz-aware datetimes)
        df["filed_at"] = pd.to_datetime(df["filed_at"], utc=True)
        df["processed_at"] = pd.to_datetime(df["processed_at"], utc=True)

        # Sort for deterministic output
        if not df.empty:
            df = df.sort_values(["cik", "filed_at", "accession_number"]).reset_index(
                drop=True
            )

        return df

    def _build_participants_df(
        self, participants: list[ParticipantRecord]
    ) -> pd.DataFrame:
        """Convert ParticipantRecord list to a sorted DataFrame."""
        if participants:
            data = [
                {col: getattr(p, col) for col in _PARTICIPANTS_COLUMNS}
                for p in participants
            ]
            df = pd.DataFrame(data, columns=_PARTICIPANTS_COLUMNS)
            df = df.sort_values(["accession_number", "firm_name", "role"]).reset_index(
                drop=True
            )
        else:
            df = pd.DataFrame(columns=_PARTICIPANTS_COLUMNS)

        return df

    def _write_results_parquet(self, df: pd.DataFrame, path: Path) -> None:
        """Write results DataFrame to Parquet with explicit schema."""
        table = pa.Table.from_pandas(df, schema=RESULTS_SCHEMA, preserve_index=False)
        pq.write_table(
            table,
            path,
            compression="snappy",
            row_group_size=128 * 1024 * 1024,
        )
        logger.info("Wrote %s (%d rows)", path, len(df))

    def _write_participants_parquet(self, df: pd.DataFrame, path: Path) -> None:
        """Write participants DataFrame to Parquet with explicit schema."""
        table = pa.Table.from_pandas(
            df, schema=PARTICIPANTS_SCHEMA, preserve_index=False
        )
        pq.write_table(
            table,
            path,
            compression="snappy",
            row_group_size=128 * 1024 * 1024,
        )
        logger.info("Wrote %s (%d rows)", path, len(df))
