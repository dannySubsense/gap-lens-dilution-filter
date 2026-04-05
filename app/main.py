import asyncio
import contextlib
import logging
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.services.db import init_db, get_db
from app.services.edgar_poller import EdgarPoller
from app.services.filing_fetcher import FilingFetcher
from app.services.fmp_client import FMPClient, FMPDataUnavailableError
from app.services.filter_engine import FilterEngine
from app.services.dilution import DilutionService
from app.services.classifier import get_classifier
from app.services.scorer import Scorer
from app.services.signal_manager import SignalManager
from app.utils.ticker_resolver import TickerResolver

logger = logging.getLogger(__name__)


async def process_filing(
    accession_number: str,
    cik: str,
    form_type: str,
    filed_at: datetime,
    filing_url: str,
    entity_name: str | None = None,
    efts_ticker: str | None = None,
) -> None:
    """
    Full pipeline coroutine: ingest a single filing through filter, classify,
    score, and signal stages.  All exceptions are caught and logged so the
    poller loop is never disrupted.
    """
    pending_written = False
    try:
        db = get_db()

        # Step 1: INSERT PENDING row
        await asyncio.to_thread(
            db.execute,
            """INSERT INTO filings
               (accession_number, cik, form_type, filed_at, filing_url,
                entity_name, ticker, processing_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
               ON CONFLICT (accession_number) DO NOTHING""",
            [
                accession_number,
                cik,
                form_type,
                filed_at,
                filing_url,
                entity_name,
                efts_ticker,
            ],
        )
        pending_written = True

        # Step 2: Resolve ticker
        ticker = TickerResolver.resolve(cik, efts_ticker, entity_name)
        if ticker is None:
            await asyncio.to_thread(
                db.execute,
                """UPDATE filings
                   SET filter_status = 'UNRESOLVABLE',
                       processing_status = 'ERROR'
                   WHERE accession_number = ?""",
                [accession_number],
            )
            return

        # Update ticker on the filings row (resolve may differ from efts_ticker)
        await asyncio.to_thread(
            db.execute,
            "UPDATE filings SET ticker = ? WHERE accession_number = ?",
            [ticker, accession_number],
        )

        # Step 3: Fetch filing text
        fetcher = FilingFetcher()
        filing_text = await fetcher.fetch(filing_url)

        # Step 4: FMP market data (may be None on failure)
        fmp_client = FMPClient()
        fmp_data = None
        try:
            fmp_data = await fmp_client.get_market_data(ticker)
        except FMPDataUnavailableError:
            logger.warning(
                "FMP data unavailable for ticker=%s accession=%s",
                ticker,
                accession_number,
            )

        # Write market_data row (FMP snapshot) for later use
        if fmp_data is not None:
            await asyncio.to_thread(
                db.execute,
                """INSERT INTO market_data
                   (ticker, price, market_cap, float_shares, adv_dollar,
                    data_source, accession_number)
                   VALUES (?, ?, ?, ?, ?, 'FMP', ?)""",
                [
                    ticker,
                    fmp_data.price,
                    fmp_data.market_cap,
                    fmp_data.float_shares,
                    fmp_data.adv_dollar,
                    accession_number,
                ],
            )

        # Step 5: FilterEngine (I-04: stops at first failure)
        engine = FilterEngine()
        outcome = await engine.evaluate(
            accession_number,
            form_type,
            filing_text,
            ticker,
            fmp_data,
        )
        if not outcome.passed:
            await asyncio.to_thread(
                db.execute,
                """UPDATE filings
                   SET filter_status = 'FILTERED_OUT',
                       processing_status = 'ERROR'
                   WHERE accession_number = ?""",
                [accession_number],
            )
            return

        # Step 6: AskEdgar enrichment (I-03: ONLY after all 6 filters pass)
        dilution_svc = DilutionService()
        _ask_edgar_data = None  # noqa: F841 — result unused in Phase 1 scoring
        try:
            _ask_edgar_data = await dilution_svc.get_dilution_data_v2(ticker)  # noqa: F841
        except Exception:
            logger.warning(
                "ASKEDGAR_PARTIAL_ENRICHMENT: ticker=%s accession=%s",
                ticker,
                accession_number,
            )
            await asyncio.to_thread(
                db.execute,
                "UPDATE filings SET askedgar_partial = TRUE WHERE accession_number = ?",
                [accession_number],
            )
            await asyncio.to_thread(
                db.execute,
                "UPDATE market_data SET data_source = 'PARTIAL' WHERE accession_number = ?",
                [accession_number],
            )
        finally:
            try:
                await dilution_svc.close()
            except Exception:
                pass

        # Step 7: Classify (I-02: use get_classifier(), never import RuleBasedClassifier)
        classifier = get_classifier()
        classification = await classifier.classify(filing_text, form_type)

        # Step 7.5: Resolve dilution_severity (see Architecture Section 3.5.4)
        shares_offered_raw: int = classification.pop("_shares_offered_raw", 0)
        if (
            shares_offered_raw > 0
            and fmp_data is not None
            and fmp_data.float_shares > 0
        ):
            raw_ratio = shares_offered_raw / fmp_data.float_shares
            if raw_ratio > 1.0:
                logger.warning(
                    "DILUTION_SEVERITY_CLAMPED: ticker=%s raw_ratio=%.4f",
                    ticker,
                    raw_ratio,
                )
            classification["dilution_severity"] = min(raw_ratio, 1.0)
        else:
            classification["dilution_severity"] = 0.0

        # Step 8: NULL setup_type -> CLASSIFIED, no score/signal
        if classification["setup_type"] == "NULL":
            await asyncio.to_thread(
                db.execute,
                "UPDATE filings SET processing_status = 'CLASSIFIED' WHERE accession_number = ?",
                [accession_number],
            )
            return

        # Step 9: Score
        # fmp_data is guaranteed non-None here because filters 2-6 require it;
        # if it were None, FilterEngine would have returned passed=False above.
        assert fmp_data is not None, (
            "fmp_data must be non-None after passing all filters"
        )
        borrow_cost = settings.default_borrow_cost  # Phase 1: IBKR disabled
        scorer_result = Scorer.score(classification, fmp_data, borrow_cost)

        # Step 10: Emit signal
        signal_manager = SignalManager()
        await signal_manager.emit(
            scorer_result,
            classification,
            fmp_data,
            accession_number,
            ticker,
        )

        # Step 11: Mark ALERTED
        await asyncio.to_thread(
            db.execute,
            "UPDATE filings SET processing_status = 'ALERTED' WHERE accession_number = ?",
            [accession_number],
        )

    except Exception:
        logger.exception(
            "process_filing failed for accession_number=%s",
            accession_number,
        )
        if pending_written:
            try:
                db = get_db()
                await asyncio.to_thread(
                    db.execute,
                    "UPDATE filings SET processing_status = 'ERROR' WHERE accession_number = ?",
                    [accession_number],
                )
            except Exception:
                logger.exception(
                    "Failed to mark ERROR for accession_number=%s",
                    accession_number,
                )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: start DB, ticker cache, poller, and lifecycle loop."""
    # I-12: init_db() first, then TickerResolver.refresh()
    init_db()
    await TickerResolver.refresh()

    signal_manager = SignalManager()
    poller = EdgarPoller()
    poller.set_process_filing(process_filing)

    task_poller = asyncio.create_task(poller.run_forever())
    task_lifecycle = asyncio.create_task(signal_manager.run_lifecycle_loop())
    try:
        yield
    finally:
        task_poller.cancel()
        task_lifecycle.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(task_poller, task_lifecycle)


async def health() -> dict:
    """Minimal health endpoint (full HealthResponse added in Slice 13)."""
    return {"status": "ok"}


def create_app() -> FastAPI:
    """Factory function for the FastAPI application."""
    from app.api.v1.routes import router as v1_router

    fastapi_app = FastAPI(title="gap-lens-dilution-filter", lifespan=lifespan)
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", f"http://100.70.21.69:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    fastapi_app.add_api_route("/health", health, methods=["GET"])
    fastapi_app.include_router(v1_router, prefix="/api/v1")
    return fastapi_app


app = create_app()
