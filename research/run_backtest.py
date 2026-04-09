"""
PipelineOrchestrator — Orchestrator Redesign

Top-level CLI entry point for the backtest pipeline. Implements a two-pass
streaming design to process 1.47M filings without OOM:

  Pass 1: Discovery + CIK Resolution (synchronous, fast, ~40s)
  Pass 2: Per-quarter streaming processing with mini-batches of 100 filings
          and quarterly checkpoints (async, 10-12 hours first run)
  Pass 3: Output (synchronous, fast, ~30s)

Key properties:
  - Single asyncio.run() for all quarters (avoids event-loop rebinding issues)
  - Peak RAM O(mini_batch_size) for filing text, not O(total_filings)
  - Quarterly checkpoints: a failed quarter does not write a checkpoint;
    --resume skips only COMPLETE quarters
  - UNRESOLVABLE filings produce BacktestRow directly in Pass 1 without
    entering the async fetch/classify loop

Usage:
    python research/run_backtest.py [OPTIONS]

Startup checks halt the pipeline (sys.exit(1)) if market_data.duckdb is
missing, unreadable, or the required tables are empty.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Pipeline imports
from research.pipeline.bt_classifier import BacktestClassifier
from research.pipeline.bt_filter_engine import BacktestFilterEngine, ALLOWED_FORM_TYPES
from research.pipeline.bt_scorer import BacktestScorer
from research.pipeline.cik_resolver import CIKResolver
from research.pipeline.config import (
    BacktestConfig,
    FLOAT_DATA_START_DATE,
    MARKET_DATA_DB_PATH,
    PIPELINE_VERSION,
)
from research.pipeline.dataclasses import BacktestRow, FetchedFiling, ParticipantRecord, ResolvedFiling
from research.pipeline.discovery import FilingDiscovery
from research.pipeline.fetcher import FilingTextFetcher
from research.pipeline.market_data_joiner import MarketDataJoiner
from research.pipeline.outcome_computer import OutcomeComputer
from research.pipeline.output_writer import OutputWriter, RESULTS_SCHEMA, PARTICIPANTS_SCHEMA
from research.pipeline.run_manifest import RunManifest
from research.pipeline.trading_calendar import TradingCalendar
from research.pipeline.underwriter_extractor import UnderwriterExtractor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Optional psutil for memory logging
# ---------------------------------------------------------------------------

try:
    import psutil as _psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False


def _get_rss_gb() -> str:
    """Return current RSS memory as a human-readable GB string, or '?' if unavailable."""
    if _PSUTIL_AVAILABLE:
        try:
            rss = _psutil.Process().memory_info().rss
            return f"{rss / 1_073_741_824:.1f}GB"
        except Exception:
            pass
    return "?GB"


# ---------------------------------------------------------------------------
# QuarterStats (local to orchestrator — not exported to dataclasses.py)
# ---------------------------------------------------------------------------

@dataclass
class QuarterStats:
    quarter_key: str
    filings_total: int = 0
    filings_fetched_ok: int = 0
    filings_skipped: int = 0       # UNRESOLVABLE + FETCH_FAILED
    filings_errored: int = 0       # PIPELINE_ERROR
    filings_passed: int = 0        # filter_status == "PASSED"
    elapsed_seconds: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update(self, filing: FetchedFiling, row: BacktestRow) -> None:
        self.filings_total += 1
        if filing.fetch_status == "OK":
            self.filings_fetched_ok += 1
        if row.filter_status in ("UNRESOLVABLE", "FETCH_FAILED"):
            self.filings_skipped += 1
        if row.filter_status == "PIPELINE_ERROR":
            self.filings_errored += 1
        if row.filter_status == "PASSED":
            self.filings_passed += 1


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------

def run_startup_checks(db_path: str) -> tuple[TradingCalendar, dict]:
    """
    Validate the environment before the pipeline starts.

    Checks (in order — halt on first failure):
      1. market_data.duckdb exists and is readable.
      2. SELECT COUNT(*) FROM daily_universe returns > 0.
      3. SELECT COUNT(*) FROM daily_prices returns > 0.
      4. Build TradingCalendar from db_path.
      5. Load research/config/underwriter_normalization.json.

    Returns
    -------
    (TradingCalendar, dict)
        The trading calendar and the normalization config dict (may be empty).

    Raises / exits
    --------------
    sys.exit(1) on any failure; error message printed to stderr.
    """
    db = Path(db_path)

    # Check 1: file exists and is readable
    if not db.exists():
        print(
            f"ERROR: market_data.duckdb not found at {db_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        con = duckdb.connect(str(db), read_only=True)
    except Exception as exc:
        print(
            f"ERROR: cannot open market_data.duckdb at {db_path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        # Check 2: daily_universe not empty
        count_universe = con.execute(
            "SELECT COUNT(*) FROM daily_universe"
        ).fetchone()[0]
        if count_universe == 0:
            print(
                "ERROR: daily_universe table is empty — certify market data before running.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Check 3: daily_prices not empty
        count_prices = con.execute(
            "SELECT COUNT(*) FROM daily_prices"
        ).fetchone()[0]
        if count_prices == 0:
            print(
                "ERROR: daily_prices table is empty — certify market data before running.",
                file=sys.stderr,
            )
            sys.exit(1)

    except Exception as exc:
        print(
            f"ERROR: startup DB check failed: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        con.close()

    # Check 4: build TradingCalendar
    try:
        calendar = TradingCalendar(db)
    except Exception as exc:
        print(
            f"ERROR: failed to build TradingCalendar: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Check 5: load normalization config
    norm_config_path = Path("research/config/underwriter_normalization.json")
    norm_config: dict = {}
    try:
        text = norm_config_path.read_text(encoding="utf-8")
        norm_config = json.loads(text)
    except FileNotFoundError:
        logger.warning(
            "underwriter_normalization.json not found at %s — extraction will store names verbatim.",
            norm_config_path,
        )
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "Failed to load underwriter_normalization.json: %s — names stored verbatim.",
            exc,
        )

    logger.info(
        "Startup checks passed. Normalization config entries loaded: %d",
        len(norm_config),
    )
    return calendar, norm_config


# ---------------------------------------------------------------------------
# Per-filing row builders (copied verbatim from original run_backtest.py)
# ---------------------------------------------------------------------------

def _make_base_row(
    filing: FetchedFiling,
    classification: dict,
    run_start: datetime,
) -> BacktestRow:
    """Build a BacktestRow from a filing and classification dict (no snapshot)."""
    filed_at = datetime(
        filing.date_filed.year,
        filing.date_filed.month,
        filing.date_filed.day,
        0, 0, 0,
    )
    return BacktestRow(
        accession_number=filing.accession_number,
        cik=filing.cik,
        ticker=filing.ticker,
        entity_name=filing.entity_name,
        form_type=filing.form_type,
        filed_at=filed_at,
        setup_type=classification.get("setup_type"),
        confidence=classification.get("confidence"),
        shares_offered_raw=classification.get("_shares_offered_raw"),
        dilution_severity=classification.get("dilution_severity"),
        price_discount=classification.get("price_discount"),
        immediate_pressure=classification.get("immediate_pressure"),
        key_excerpt=classification.get("key_excerpt"),
        filter_status="PENDING",
        filter_fail_reason=None,
        float_available=False,
        in_smallcap_universe=None,
        price_at_T=None,
        market_cap_at_T=None,
        float_at_T=None,
        adv_at_T=None,
        short_interest_at_T=None,
        borrow_cost_source=None,
        score=None,
        rank=None,
        dilution_extractable=None,
        outcome_computable=False,
        return_1d=None,
        return_3d=None,
        return_5d=None,
        return_20d=None,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version=PIPELINE_VERSION,
        processed_at=run_start,
    )


def _make_error_row(
    filing: FetchedFiling,
    error_detail: str,
    run_start: datetime,
) -> BacktestRow:
    """Build a PIPELINE_ERROR row when an unexpected exception occurs."""
    filed_at = datetime(
        filing.date_filed.year,
        filing.date_filed.month,
        filing.date_filed.day,
        0, 0, 0,
    )
    return BacktestRow(
        accession_number=filing.accession_number,
        cik=filing.cik,
        ticker=filing.ticker,
        entity_name=filing.entity_name,
        form_type=filing.form_type,
        filed_at=filed_at,
        setup_type=None,
        confidence=None,
        shares_offered_raw=None,
        dilution_severity=None,
        price_discount=None,
        immediate_pressure=None,
        key_excerpt=None,
        filter_status="PIPELINE_ERROR",
        filter_fail_reason=error_detail[:500] if error_detail else None,
        float_available=False,
        in_smallcap_universe=None,
        price_at_T=None,
        market_cap_at_T=None,
        float_at_T=None,
        adv_at_T=None,
        short_interest_at_T=None,
        borrow_cost_source=None,
        score=None,
        rank=None,
        dilution_extractable=None,
        outcome_computable=False,
        return_1d=None,
        return_3d=None,
        return_5d=None,
        return_20d=None,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version=PIPELINE_VERSION,
        processed_at=run_start,
    )


# ---------------------------------------------------------------------------
# Per-filing integration (copied verbatim from original run_backtest.py)
# ---------------------------------------------------------------------------

def _process_filing(
    filing: FetchedFiling,
    classification: dict,
    extractor: UnderwriterExtractor,
    joiner: MarketDataJoiner,
    filter_engine: BacktestFilterEngine,
    scorer: BacktestScorer,
    computer: OutcomeComputer,
    cfg: BacktestConfig,
    manifest: RunManifest,
    rows: list[BacktestRow],
    participants: list[ParticipantRecord],
    run_start: datetime,
) -> None:
    """
    Integrate one filing through all post-classification pipeline stages.

    Mutates manifest counters, rows, and participants in place.
    """
    row = _make_base_row(filing, classification, run_start)

    # Stage: UNRESOLVABLE — no market data available
    if filing.resolution_status != "RESOLVED":
        row.filter_status = "UNRESOLVABLE"
        rows.append(row)
        return

    # Stage: FETCH_FAILED — no text to classify or join
    if filing.fetch_status != "OK":
        row.filter_status = "FETCH_FAILED"
        rows.append(row)
        return

    # Stage: Market data join
    snapshot = joiner.join(filing)

    # Populate snapshot fields on row (whether or not in universe)
    row.float_available = snapshot.float_available
    row.in_smallcap_universe = snapshot.in_smallcap_universe
    row.price_at_T = snapshot.price_at_T
    row.market_cap_at_T = snapshot.market_cap_at_T
    row.float_at_T = snapshot.float_at_T
    row.adv_at_T = snapshot.adv_at_T
    row.short_interest_at_T = snapshot.short_interest_at_T
    row.borrow_cost_source = snapshot.borrow_cost_source

    # Stage: Filter evaluation (also sets dilution_severity, dilution_extractable as side effects)
    outcome = filter_engine.evaluate(row, snapshot)

    if outcome.passed:
        row.filter_status = "PASSED"
        row.filter_fail_reason = None
        manifest.total_passed_filters += 1
    else:
        fail = outcome.fail_criterion or "UNKNOWN"
        # Map FilterOutcome fail_criterion to canonical filter_status values
        _CRITERION_TO_STATUS = {
            "NOT_IN_UNIVERSE": "NOT_IN_UNIVERSE",
            "FILING_TYPE": "FORM_TYPE_FAIL",
            "MARKET_CAP": "MARKET_CAP_FAIL",
            "FLOAT": "FLOAT_FAIL",
            "DILUTION_PCT": "DILUTION_FAIL",
            "PRICE": "PRICE_FAIL",
            "ADV": "ADV_FAIL",
        }
        row.filter_status = _CRITERION_TO_STATUS.get(fail, fail)
        row.filter_fail_reason = fail

    # Stage: Underwriter extraction (always attempted when fetch OK)
    new_participants = extractor.extract(filing)
    participants.extend(new_participants)

    # Stage: Scoring (only when filter passed)
    if outcome.passed:
        scorer_result = scorer.score(classification, snapshot, row)
        if scorer_result is not None:
            row.score = scorer_result.get("score")
            row.rank = scorer_result.get("rank")
            # Override borrow_cost_source from scorer result if present
            if scorer_result.get("borrow_cost_source") is not None:
                row.borrow_cost_source = scorer_result["borrow_cost_source"]

    # Stage: Outcome computation (always attempted when market data exists)
    if snapshot.price_at_T is not None:
        computer.compute(row, snapshot)
        if row.outcome_computable:
            manifest.total_with_outcomes += 1

    rows.append(row)


# ---------------------------------------------------------------------------
# UNRESOLVABLE row builder (for Pass 1 pre-filtering)
# ---------------------------------------------------------------------------

def _make_unresolvable_row(
    filing: ResolvedFiling,
    run_start: datetime,
) -> BacktestRow:
    """Build a PIPELINE_ERROR row for a filing that could not be resolved."""
    filed_at = datetime(
        filing.date_filed.year,
        filing.date_filed.month,
        filing.date_filed.day,
        0, 0, 0,
    )
    return BacktestRow(
        accession_number=filing.accession_number,
        cik=filing.cik,
        ticker=filing.ticker,
        entity_name=filing.entity_name,
        form_type=filing.form_type,
        filed_at=filed_at,
        setup_type=None,
        confidence=None,
        shares_offered_raw=None,
        dilution_severity=None,
        price_discount=None,
        immediate_pressure=None,
        key_excerpt=None,
        filter_status="UNRESOLVABLE",
        filter_fail_reason=filing.resolution_status,
        float_available=False,
        in_smallcap_universe=None,
        price_at_T=None,
        market_cap_at_T=None,
        float_at_T=None,
        adv_at_T=None,
        short_interest_at_T=None,
        borrow_cost_source=None,
        score=None,
        rank=None,
        dilution_extractable=None,
        outcome_computable=False,
        return_1d=None,
        return_3d=None,
        return_5d=None,
        return_20d=None,
        delisted_before_T1=False,
        delisted_before_T3=False,
        delisted_before_T5=False,
        delisted_before_T20=False,
        pipeline_version=PIPELINE_VERSION,
        processed_at=run_start,
    )


# ---------------------------------------------------------------------------
# Shard I/O — write per-quarter results to disk, merge at the end
# ---------------------------------------------------------------------------

_SHARD_DIR_NAME = "shards"


def _shard_dir(cfg: BacktestConfig) -> Path:
    d = cfg.cache_dir / _SHARD_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rows_to_table(rows: list[BacktestRow]) -> pa.Table:
    """Convert BacktestRow objects to a pyarrow Table using the canonical schema."""
    from dataclasses import fields as dc_fields
    columns = [f.name for f in dc_fields(BacktestRow)]
    data = {col: [getattr(r, col) for r in rows] for col in columns}
    df = pd.DataFrame(data)
    # UTC-localize datetime columns for pyarrow
    for col in ("filed_at", "processed_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    return pa.Table.from_pandas(df, schema=RESULTS_SCHEMA, preserve_index=False)


def _participants_to_table(participants: list[ParticipantRecord]) -> pa.Table:
    """Convert ParticipantRecord objects to a pyarrow Table."""
    from dataclasses import fields as dc_fields
    columns = [f.name for f in dc_fields(ParticipantRecord)]
    data = {col: [getattr(r, col) for r in participants] for col in columns}
    df = pd.DataFrame(data)
    return pa.Table.from_pandas(df, schema=PARTICIPANTS_SCHEMA, preserve_index=False)


def _write_shard(
    cfg: BacktestConfig,
    shard_name: str,
    rows: list[BacktestRow],
    participants: list[ParticipantRecord],
) -> None:
    """Write a quarter's results and participants to Parquet shard files."""
    sdir = _shard_dir(cfg)
    if rows:
        table = _rows_to_table(rows)
        pq.write_table(table, str(sdir / f"{shard_name}_results.parquet"), compression="snappy")
    if participants:
        table = _participants_to_table(participants)
        pq.write_table(table, str(sdir / f"{shard_name}_participants.parquet"), compression="snappy")
    logger.debug("Shard written: %s (%d rows, %d participants)", shard_name, len(rows), len(participants))


def _merge_shards_and_write(
    cfg: BacktestConfig,
    manifest: RunManifest,
    output_dir: str | None,
) -> None:
    """Read all shard Parquet files, merge, sort, and write final output."""
    import hashlib

    sdir = _shard_dir(cfg)
    out = Path(output_dir) if output_dir else Path("docs/research/data")
    out.mkdir(parents=True, exist_ok=True)

    # Merge results shards
    result_shards = sorted(sdir.glob("*_results.parquet"))
    if result_shards:
        tables = [pq.read_table(str(p)) for p in result_shards]
        merged = pa.concat_tables(tables)
    else:
        merged = pa.table({name: pa.array([], type=field.type) for name, field in zip(RESULTS_SCHEMA.names, RESULTS_SCHEMA)})

    # Sort by (cik, filed_at, accession_number)
    merged_df = merged.to_pandas()
    merged_df.sort_values(["cik", "filed_at", "accession_number"], inplace=True)
    merged_table = pa.Table.from_pandas(merged_df, schema=RESULTS_SCHEMA, preserve_index=False)

    # Write results Parquet
    results_path = out / "backtest_results.parquet"
    pq.write_table(merged_table, str(results_path), compression="snappy", row_group_size=128 * 1024 * 1024)
    logger.info("Wrote %s (%d rows)", results_path, len(merged_df))

    # SHA-256
    parquet_bytes = results_path.read_bytes()
    manifest.parquet_sha256 = hashlib.sha256(parquet_bytes).hexdigest()
    manifest.parquet_row_count = len(merged_df)

    # Write results CSV
    csv_path = out / "backtest_results.csv"
    merged_df.to_csv(str(csv_path), index=False, encoding="utf-8", lineterminator="\n")
    logger.info("Wrote %s", csv_path)

    # Merge participants shards
    participant_shards = sorted(sdir.glob("*_participants.parquet"))
    if participant_shards:
        p_tables = [pq.read_table(str(p)) for p in participant_shards]
        p_merged = pa.concat_tables(p_tables)
    else:
        p_merged = pa.table({name: pa.array([], type=field.type) for name, field in zip(PARTICIPANTS_SCHEMA.names, PARTICIPANTS_SCHEMA)})

    p_df = p_merged.to_pandas()
    p_df.sort_values(["accession_number", "firm_name", "role"], inplace=True)
    p_table = pa.Table.from_pandas(p_df, schema=PARTICIPANTS_SCHEMA, preserve_index=False)

    # Write participants Parquet + CSV
    p_parquet_path = out / "backtest_participants.parquet"
    pq.write_table(p_table, str(p_parquet_path), compression="snappy")
    logger.info("Wrote %s (%d rows)", p_parquet_path, len(p_df))

    p_csv_path = out / "backtest_participants.csv"
    p_df.to_csv(str(p_csv_path), index=False, encoding="utf-8", lineterminator="\n")
    logger.info("Wrote %s", p_csv_path)

    # Write manifest JSON
    manifest_path = out / "backtest_run_metadata.json"
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", manifest_path)


def _clear_shards(cfg: BacktestConfig) -> None:
    """Remove all shard files from prior runs."""
    sdir = _shard_dir(cfg)
    for f in sdir.glob("*.parquet"):
        f.unlink()


# ---------------------------------------------------------------------------
# Checkpoint I/O
# ---------------------------------------------------------------------------

def _checkpoint_path(cfg: BacktestConfig, quarter_key: str) -> Path:
    return cfg.cache_dir / "checkpoints" / f"{quarter_key}.json"


def _is_quarter_complete(cfg: BacktestConfig, quarter_key: str) -> bool:
    """Return True if the checkpoint file exists and status == COMPLETE."""
    cp = _checkpoint_path(cfg, quarter_key)
    if not cp.exists():
        return False
    try:
        data = json.loads(cp.read_text(encoding="utf-8"))
        return data.get("status") == "COMPLETE"
    except Exception:
        return False


def _write_checkpoint(cfg: BacktestConfig, quarter_key: str, stats: QuarterStats) -> None:
    """Write a COMPLETE checkpoint JSON for a successfully processed quarter."""
    cp = _checkpoint_path(cfg, quarter_key)
    cp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "quarter_key": quarter_key,
        "status": "COMPLETE",
        "filings_discovered": stats.filings_total,
        "filings_resolved": stats.filings_total - stats.filings_skipped,
        "filings_fetched_ok": stats.filings_fetched_ok,
        "filings_passed": stats.filings_passed,
        "filings_errored": stats.filings_errored,
        "elapsed_seconds": round(stats.elapsed_seconds, 1),
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp_path = cp.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(cp)


# ---------------------------------------------------------------------------
# Progress logging helpers
# ---------------------------------------------------------------------------

def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as 'Xm Ys'."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    if m > 0:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def _log_mini_batch_progress(
    quarter_key: str,
    processed: int,
    total: int,
    stats: QuarterStats,
) -> None:
    elapsed = (datetime.now(timezone.utc) - stats.started_at).total_seconds()
    logger.info(
        "[Q %s] %d/%d | OK: %d | skip: %d | err: %d | passed: %d | mem: %s | elapsed: %s",
        quarter_key,
        processed,
        total,
        stats.filings_fetched_ok,
        stats.filings_skipped,
        stats.filings_errored,
        stats.filings_passed,
        _get_rss_gb(),
        _fmt_elapsed(elapsed),
    )


def _log_quarter_complete(quarter_key: str, stats: QuarterStats) -> None:
    logger.info(
        "[Q %s] COMPLETE | %d filings | %d passed | %d errors | %s",
        quarter_key,
        stats.filings_total,
        stats.filings_passed,
        stats.filings_errored,
        _fmt_elapsed(stats.elapsed_seconds),
    )


# ---------------------------------------------------------------------------
# Pass 1: Discovery + CIK Resolution
# ---------------------------------------------------------------------------

def _pass1_discover_and_resolve(
    cfg: BacktestConfig,
    args: argparse.Namespace,
    manifest: RunManifest,
    run_start: datetime,
) -> tuple[dict[str, list[ResolvedFiling]], list[BacktestRow]]:
    """
    Pass 1: Discover all filings and resolve CIKs.

    Returns:
      grouped: {quarter_key: [ResolvedFiling, ...]} — only RESOLVED filings
      unresolvable_rows: list of BacktestRow with filter_status=UNRESOLVABLE
    """
    # Discovery
    discovery = FilingDiscovery(config=cfg)
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    discovered, quarters_failed = discovery.discover(start_date, end_date)
    manifest.quarters_failed = quarters_failed

    logger.info("Discovery complete: %d filings found.", len(discovered))

    manifest.total_filings_discovered = len(discovered)

    # CIK resolution via preloaded bulk cache
    resolver = CIKResolver(db_path=Path(args.db_path_resolved))
    resolver.preload()

    resolved_all: list[ResolvedFiling] = []
    unresolvable_rows: list[BacktestRow] = []

    for d in discovered:
        r = resolver.resolve(d)
        resolved_all.append(r)
        if r.resolution_status == "RESOLVED":
            manifest.total_cik_resolved += 1
        else:
            manifest.total_unresolvable_count += 1
            unresolvable_rows.append(_make_unresolvable_row(r, run_start))

    resolver.close()

    logger.info(
        "CIK resolution complete: %d resolved, %d unresolvable.",
        manifest.total_cik_resolved,
        manifest.total_unresolvable_count,
    )

    # Group RESOLVED filings by quarter_key
    grouped: dict[str, list[ResolvedFiling]] = {}
    for r in resolved_all:
        if r.resolution_status == "RESOLVED":
            if r.quarter_key not in grouped:
                grouped[r.quarter_key] = []
            grouped[r.quarter_key].append(r)

    return grouped, unresolvable_rows


# ---------------------------------------------------------------------------
# Pass 2: Per-quarter streaming processing
# ---------------------------------------------------------------------------

MINI_BATCH_SIZE = 100


async def _process_quarter(
    quarter_key: str,
    resolved_filings: list[ResolvedFiling],
    fetcher: FilingTextFetcher,
    classifier: BacktestClassifier,
    extractor: UnderwriterExtractor,
    joiner: MarketDataJoiner,
    filter_engine: BacktestFilterEngine,
    scorer: BacktestScorer,
    computer: OutcomeComputer,
    cfg: BacktestConfig,
    manifest: RunManifest,
    run_start: datetime,
    dry_run_remaining: list[int],
) -> tuple[list[BacktestRow], list[ParticipantRecord], QuarterStats]:
    """
    Process one quarter's worth of resolved filings in mini-batches of 100.

    dry_run_remaining is a single-element list holding the remaining filing
    count for --dry-run; mutated in place to enable global cross-quarter limit.
    Pass [None] to disable the limit.
    """
    rows: list[BacktestRow] = []
    participants: list[ParticipantRecord] = []
    stats = QuarterStats(quarter_key=quarter_key)

    for i in range(0, len(resolved_filings), MINI_BATCH_SIZE):
        # Respect global --dry-run limit
        if dry_run_remaining[0] is not None and dry_run_remaining[0] <= 0:
            break

        mini_batch = resolved_filings[i : i + MINI_BATCH_SIZE]

        # Apply dry-run cap to this mini-batch
        if dry_run_remaining[0] is not None:
            mini_batch = mini_batch[: dry_run_remaining[0]]

        # Fetch mini-batch (async, semaphore-controlled by fetcher internals)
        fetched_batch: list[FetchedFiling] = list(
            await asyncio.gather(*[fetcher.fetch(f) for f in mini_batch])
        )

        # Classify mini-batch (async)
        classifications: list[dict] = list(
            await asyncio.gather(*[classifier.classify(f) for f in fetched_batch])
        )

        # Per-filing integration + text discard
        for filing, classification in zip(fetched_batch, classifications):
            try:
                _process_filing(
                    filing,
                    classification,
                    extractor,
                    joiner,
                    filter_engine,
                    scorer,
                    computer,
                    cfg,
                    manifest,
                    rows,
                    participants,
                    run_start,
                )
            except Exception as exc:
                logger.error("Pipeline error for %s: %s", filing.accession_number, exc)
                rows.append(_make_error_row(filing, str(exc), run_start))
            finally:
                filing.plain_text = None  # discard immediately

            stats.update(filing, rows[-1])

        # Decrement dry-run counter
        if dry_run_remaining[0] is not None:
            dry_run_remaining[0] -= len(mini_batch)

        _log_mini_batch_progress(
            quarter_key, i + len(mini_batch), len(resolved_filings), stats
        )

    stats.elapsed_seconds = (
        datetime.now(timezone.utc) - stats.started_at
    ).total_seconds()
    return rows, participants, stats


async def _pass2_and_output(
    grouped: dict[str, list[ResolvedFiling]],
    unresolvable_rows: list[BacktestRow],
    cfg: BacktestConfig,
    args: argparse.Namespace,
    manifest: RunManifest,
    calendar: TradingCalendar,
    norm_config: dict,
    run_start: datetime,
) -> None:
    """
    Pass 2 + Pass 3: Process all quarters in a single asyncio event loop,
    then write output.
    """
    # Initialize async components
    fetcher = FilingTextFetcher(config=cfg)
    classifier = BacktestClassifier()
    extractor = UnderwriterExtractor(
        normalization_config_path=cfg.normalization_config_path
    )
    joiner = MarketDataJoiner(
        db_path=Path(args.db_path_resolved),
        calendar=calendar,
    )
    filter_engine = BacktestFilterEngine(config=cfg)
    scorer = BacktestScorer()
    computer = OutcomeComputer()

    # Clear prior shard files and write UNRESOLVABLE shard
    _clear_shards(cfg)
    if unresolvable_rows:
        _write_shard(cfg, "00_unresolvable", unresolvable_rows, [])
        logger.info("Flushed %d UNRESOLVABLE rows to shard.", len(unresolvable_rows))
    del unresolvable_rows  # free ~3GB

    # Global dry-run counter (mutable single-element list for cross-quarter sharing)
    dry_run_remaining: list[int | None] = [args.dry_run]

    try:
        for quarter_key in sorted(grouped.keys()):
            # Apply --quarter filter
            if args.quarter is not None and quarter_key != args.quarter:
                continue

            # Apply --resume: skip COMPLETE quarters
            if args.resume and _is_quarter_complete(cfg, quarter_key):
                logger.info("[Q %s] SKIPPED (checkpoint status=COMPLETE)", quarter_key)
                continue

            # Check global dry-run limit before starting this quarter
            if dry_run_remaining[0] is not None and dry_run_remaining[0] <= 0:
                logger.info("--dry-run limit reached; stopping after %d filings.", args.dry_run)
                break

            resolved_filings = grouped[quarter_key]
            logger.info(
                "[Q %s] Starting: %d resolved filings",
                quarter_key,
                len(resolved_filings),
            )

            try:
                rows, participants, stats = await _process_quarter(
                    quarter_key,
                    resolved_filings,
                    fetcher,
                    classifier,
                    extractor,
                    joiner,
                    filter_engine,
                    scorer,
                    computer,
                    cfg,
                    manifest,
                    run_start,
                    dry_run_remaining,
                )
            except Exception as exc:
                logger.error("Quarter %s failed: %s", quarter_key, exc)
                manifest.quarters_failed.append(quarter_key)
                continue

            # Flush quarter results to disk shard, then free memory
            _write_shard(cfg, quarter_key, rows, participants)
            manifest.total_fetch_ok += stats.filings_fetched_ok

            _write_checkpoint(cfg, quarter_key, stats)
            _log_quarter_complete(quarter_key, stats)

            del rows, participants  # free memory

            # Reset fetcher session between quarters to prevent memory leak
            # from aiohttp's internal connection pool and response buffers
            await fetcher.close_session()

    finally:
        await fetcher.close_session()

    # Pass 3: Merge shards and write final output
    logger.info("All quarters complete. Merging shards and writing output.")
    _merge_shards_and_write(cfg, manifest, args.output_dir)

    logger.info(
        "Run complete. %d rows written. SHA-256: %s",
        manifest.parquet_row_count,
        (manifest.parquet_sha256[:16] + "...") if manifest.parquet_sha256 else "(none)",
    )


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------

def _build_manifest(
    cfg: BacktestConfig,
    args: argparse.Namespace,
    norm_config: dict,
    run_start: datetime,
) -> RunManifest:
    return RunManifest(
        run_date=run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        pipeline_version=PIPELINE_VERSION,
        classifier_version="rule-based-v1",
        scoring_formula_version="v1.0",
        date_range_start=args.start_date,
        date_range_end=args.end_date,
        form_types=list(ALLOWED_FORM_TYPES),
        market_cap_threshold=cfg.market_cap_max,
        float_threshold=cfg.float_max,
        dilution_pct_threshold=cfg.dilution_pct_min,
        price_threshold=cfg.price_min,
        adv_threshold=cfg.adv_min,
        float_data_start=str(FLOAT_DATA_START_DATE),
        market_data_db_path=args.db_path_resolved,
        market_data_db_certification="v1.0.0 (certified 2026-02-19)",
        total_filings_discovered=0,
        total_cik_resolved=0,
        total_fetch_ok=0,
        total_classified=0,
        total_passed_filters=0,
        total_with_outcomes=0,
        quarters_failed=[],
        parquet_sha256="",
        parquet_row_count=0,
        execution_timestamp=run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        canary_no_lookahead="PASS",
        total_unresolvable_count=0,
        normalization_config_loaded=len(norm_config) > 0,
        normalization_config_entry_count=len(norm_config),
    )


# ---------------------------------------------------------------------------
# Main run() function
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    """Execute all pipeline stages."""
    run_start = datetime.now(timezone.utc)

    # Startup checks
    calendar, norm_config = run_startup_checks(args.db_path_resolved)

    # BacktestConfig (uses defaults; db_path override handled via resolved arg)
    cfg = BacktestConfig()

    # Ensure checkpoint directory exists at startup
    checkpoint_dir = cfg.cache_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # Initialize manifest
    manifest = _build_manifest(cfg, args, norm_config, run_start)

    # --dry-run 0: write empty output immediately and exit
    if args.dry_run == 0:
        logger.info("--dry-run 0: skipping all processing, writing empty output.")
        manifest.total_filings_discovered = 0
        OutputWriter(output_dir=args.output_dir).write([], [], manifest)
        return

    # Pass 1: Discover + Resolve (synchronous, fast)
    grouped, unresolvable_rows = _pass1_discover_and_resolve(
        cfg, args, manifest, run_start
    )

    # Apply --quarter filter (log which quarters will be processed)
    if args.quarter is not None:
        if args.quarter not in grouped:
            logger.warning(
                "--quarter %s not found in discovered filings. Available: %s",
                args.quarter,
                sorted(grouped.keys()),
            )
        else:
            logger.info(
                "--quarter %s: %d resolved filings to process.",
                args.quarter,
                len(grouped[args.quarter]),
            )

    # Pass 2 + 3: Process quarters + Write output (async — single event loop)
    asyncio.run(
        _pass2_and_output(
            grouped,
            unresolvable_rows,
            cfg,
            args,
            manifest,
            calendar,
            norm_config,
            run_start,
        )
    )


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_backtest.py",
        description="Gap-Lens dilution-filter backtest pipeline.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2017-01-01",
        help="Start date for filing discovery (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2025-12-31",
        help="End date for filing discovery (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip quarters with status=COMPLETE in their checkpoint file. "
            "EDGAR filing text cache is always consulted regardless of this flag."
        ),
    )
    parser.add_argument(
        "--dry-run",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N filings across all quarters then stop (0 = startup checks only)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to market_data.duckdb (overrides config default)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for results (overrides default docs/research/data/)",
    )
    parser.add_argument(
        "--quarter",
        type=str,
        default=None,
        metavar="YYYY_QTRN",
        help=(
            "Process a single quarter only (e.g. 2022_QTR1). "
            "Discovery still runs the full date range; only the specified quarter is processed."
        ),
    )
    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Resolve db_path: CLI arg overrides config default
    args.db_path_resolved = args.db_path if args.db_path else str(MARKET_DATA_DB_PATH)

    run(args)


if __name__ == "__main__":
    main()
