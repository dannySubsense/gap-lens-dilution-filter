"""
Slice 10: BacktestScorer

Adapter that calls the live Scorer.score() using point-in-time market data
assembled from a MarketSnapshot. Mirrors the live pipeline's dilution_severity
patching ("step 7.5") and borrow cost behaviour exactly so backtest scores are
directly comparable to production scores.

Design invariants
-----------------
- Never reads MarketSnapshot.forward_prices — those are outcome data.
- Always passes borrow_cost=0.0 to Scorer.score(); Scorer substitutes
  settings.default_borrow_cost (0.30) internally.
- borrow_cost_source is always "DEFAULT" (IBKR disabled in live pipeline).
"""

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.services.scorer import Scorer

from research.pipeline.dataclasses import BacktestMarketData, BacktestRow, MarketSnapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# raw_score helper — mirrors Scorer.score() formula so we can surface it
# without modifying app/services/scorer.py (which has no raw_score field on
# its ScorerResult).
# ---------------------------------------------------------------------------

def _compute_raw_score(
    dilution_severity: float,
    adv_dollar: float,
    setup_type: str,
) -> float:
    """Compute the raw score using the same formula as Scorer.score()."""
    float_illiquidity = settings.adv_min_threshold / adv_dollar
    setup_quality = settings.setup_quality[setup_type]
    effective_borrow_cost = settings.default_borrow_cost  # borrow_cost=0.0 path
    return (dilution_severity * float_illiquidity * setup_quality) / effective_borrow_cost


# ---------------------------------------------------------------------------
# BacktestScorer
# ---------------------------------------------------------------------------

class BacktestScorer:
    """
    Adapter that calls the live Scorer.score() with point-in-time market data.

    Returns a dict with keys: score (int), rank (str), raw_score (float),
    borrow_cost_source (str). Returns None when scoring is not applicable.
    """

    def score(
        self,
        classification: dict,
        snapshot: MarketSnapshot,
        row: BacktestRow,
    ) -> dict | None:
        """
        Score a filing using the live Scorer with point-in-time market data.

        Parameters
        ----------
        classification:
            ClassificationResult dict (may have setup_type=None for no-match
            filings; dilution_severity here is the raw classifier value before
            step-7.5 patching).
        snapshot:
            Point-in-time market data from MarketDataJoiner.
        row:
            BacktestRow with dilution_severity already computed by
            BacktestFilterEngine (shares_offered_raw / float_at_T, or None).

        Returns
        -------
        dict with keys score, rank, raw_score, borrow_cost_source, or None.
        """

        # ------------------------------------------------------------------
        # Step 1 — Guard conditions: return None for un-scoreable filings.
        # ------------------------------------------------------------------
        if classification.get("setup_type") is None:
            logger.debug(
                "BacktestScorer: setup_type is None — skipping score for %s",
                row.accession_number,
            )
            return None

        if snapshot.adv_at_T is None or snapshot.adv_at_T <= 0:
            logger.debug(
                "BacktestScorer: adv_at_T=%s — skipping score for %s",
                snapshot.adv_at_T,
                row.accession_number,
            )
            return None

        # ------------------------------------------------------------------
        # Step 2 — Dilution severity patching (mirrors live "step 7.5").
        # RuleBasedClassifier always returns dilution_severity=0.0; the live
        # pipeline patches the computed value before calling Scorer.score().
        # ------------------------------------------------------------------
        patched_classification = dict(classification)
        patched_classification["dilution_severity"] = (
            row.dilution_severity
            if row.dilution_severity is not None
            else 0.0  # matches live pipeline fallback when float is unavailable
        )

        # ------------------------------------------------------------------
        # Step 3 — Build BacktestMarketData adapter.
        # ------------------------------------------------------------------
        fmp_data = BacktestMarketData(
            adv_dollar=snapshot.adv_at_T,
            float_shares=snapshot.float_at_T or 0.0,
            price=snapshot.price_at_T or 0.0,
            market_cap=snapshot.market_cap_at_T or 0.0,
        )

        # ------------------------------------------------------------------
        # Step 4 — Borrow cost: always 0.0 (IBKR disabled in live pipeline).
        # Scorer.score() internally substitutes settings.default_borrow_cost.
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # Step 5 — Compute raw_score before calling Scorer (Scorer does not
        # expose raw_score on its result dataclass).
        # ------------------------------------------------------------------
        raw_score = _compute_raw_score(
            dilution_severity=patched_classification["dilution_severity"],
            adv_dollar=fmp_data.adv_dollar,
            setup_type=patched_classification["setup_type"],
        )

        # ------------------------------------------------------------------
        # Step 6 — Call Scorer.score() with the patched classification and
        # the BacktestMarketData adapter.
        # ------------------------------------------------------------------
        result = Scorer.score(patched_classification, fmp_data, borrow_cost=0.0)

        return {
            "score": result.score,
            "rank": result.rank,
            "raw_score": raw_score,
            "borrow_cost_source": "DEFAULT",
        }
