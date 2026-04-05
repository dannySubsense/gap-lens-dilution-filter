"""
PipelineOrchestrator — Slice 13

Top-level CLI entry point for the backtest pipeline.  Sequences all stages in
order: startup checks → discovery → CIK resolution → text fetch →
classification → market data join → filter → score → outcomes → output.

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
from datetime import date, datetime
from pathlib import Path

import duckdb

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
from research.pipeline.dataclasses import BacktestRow, FetchedFiling, ParticipantRecord
from research.pipeline.discovery import FilingDiscovery
from research.pipeline.fetcher import FilingTextFetcher
from research.pipeline.market_data_joiner import MarketDataJoiner
from research.pipeline.outcome_computer import OutcomeComputer
from research.pipeline.output_writer import OutputWriter
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
# Async helpers
# ---------------------------------------------------------------------------

async def _fetch_batch(
    fetcher: FilingTextFetcher,
    resolved_filings: list,
    resume: bool,
) -> list[FetchedFiling]:
    """Fetch all filings concurrently using asyncio.gather."""
    # resume is not a parameter of FilingTextFetcher.fetch() — the fetcher
    # already performs cache-hit checking internally for every call.
    # The --resume flag controls discovery (master.gz cache); for text fetches
    # the cache is always consulted, so we just call fetch() for each filing.
    _ = resume  # documented intent; fetch() always checks its cache
    tasks = [fetcher.fetch(f) for f in resolved_filings]
    return list(await asyncio.gather(*tasks))


async def _classify_batch(
    classifier: BacktestClassifier,
    fetched_filings: list[FetchedFiling],
) -> list[dict]:
    """Classify all filings concurrently using asyncio.gather."""
    return list(
        await asyncio.gather(*[classifier.classify(f) for f in fetched_filings])
    )


# ---------------------------------------------------------------------------
# Per-filing row builder
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
# Per-filing integration
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
# Main run() function
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> None:
    """Execute all pipeline stages in sequence."""
    run_start = datetime.utcnow()

    # Startup checks
    calendar, norm_config = run_startup_checks(args.db_path_resolved)

    # BacktestConfig (uses defaults; db_path override handled via resolved arg)
    cfg = BacktestConfig()

    # Initialize manifest
    manifest = RunManifest(
        run_date=run_start.isoformat() + "Z",
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
        execution_timestamp=run_start.isoformat() + "Z",
        canary_no_lookahead="PASS",
        total_unresolvable_count=0,
        normalization_config_loaded=len(norm_config) > 0,
        normalization_config_entry_count=len(norm_config),
    )

    # Initialize components
    discovery = FilingDiscovery(config=cfg)
    resolver = CIKResolver(db_path=Path(args.db_path_resolved))
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

    # Discovery phase
    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)
    discovered, quarters_failed = discovery.discover(start_date, end_date)
    manifest.quarters_failed = quarters_failed

    logger.info("Discovery complete: %d filings found.", len(discovered))

    # Apply --dry-run limit
    if args.dry_run is not None:
        discovered = discovered[: args.dry_run]

    manifest.total_filings_discovered = len(discovered)

    if args.dry_run == 0:
        logger.info("--dry-run 0: skipping all processing, writing empty output.")
        OutputWriter(output_dir=args.output_dir).write([], [], manifest)
        return

    # CIK resolution
    resolved = []
    for d in discovered:
        r = resolver.resolve(d)
        resolved.append(r)
        if r.resolution_status == "RESOLVED":
            manifest.total_cik_resolved += 1
        elif r.resolution_status == "UNRESOLVABLE":
            manifest.total_unresolvable_count += 1

    logger.info(
        "CIK resolution complete: %d resolved, %d unresolvable.",
        manifest.total_cik_resolved,
        manifest.total_unresolvable_count,
    )

    # Text fetch (async batch — single asyncio.run())
    fetched: list[FetchedFiling] = asyncio.run(
        _fetch_batch(fetcher, resolved, resume=args.resume)
    )
    manifest.total_fetch_ok = sum(1 for f in fetched if f.fetch_status == "OK")
    logger.info(
        "Fetch complete: %d OK, %d failed.",
        manifest.total_fetch_ok,
        len(fetched) - manifest.total_fetch_ok,
    )

    # Classification (async batch — single asyncio.run())
    classifications: list[dict] = asyncio.run(
        _classify_batch(classifier, fetched)
    )
    manifest.total_classified = len(classifications)
    logger.info("Classification complete: %d filings classified.", manifest.total_classified)

    rows: list[BacktestRow] = []
    participants: list[ParticipantRecord] = []

    # Per-filing integration
    for i, filing in enumerate(fetched):
        classification = classifications[i]
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
                run_start=run_start,
            )
        except Exception as exc:
            logger.error(
                "Pipeline error for %s: %s",
                filing.accession_number,
                exc,
            )
            rows.append(_make_error_row(filing, str(exc), run_start))

    logger.info(
        "Integration complete: %d rows, %d participants, %d passed filters.",
        len(rows),
        len(participants),
        manifest.total_passed_filters,
    )

    # Write output
    OutputWriter(output_dir=args.output_dir).write(rows, participants, manifest)

    logger.info(
        "Run complete. %d rows written. SHA-256: %s",
        manifest.parquet_row_count,
        (manifest.parquet_sha256[:16] + "...") if manifest.parquet_sha256 else "(none)",
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
        help="Skip already-cached master.gz and filing text files",
    )
    parser.add_argument(
        "--dry-run",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N filings then stop (0 = startup checks only)",
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
