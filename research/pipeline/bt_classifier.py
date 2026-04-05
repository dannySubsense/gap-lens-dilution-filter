"""
Slice 6: BacktestClassifier

Thin adapter that wraps RuleBasedClassifier for batch backtest use.

Responsibilities:
- Holds a single shared RuleBasedClassifier instance.
- Returns a stub result (setup_type=None) for filings that failed fetch.
- Maps the string "NULL" sentinel returned by RuleBasedClassifier to Python
  None, so downstream Parquet queries using WHERE setup_type IS NULL work
  correctly.

Async calling convention: classify() is an async method. Callers must await
it inside an existing async context. Do NOT call asyncio.run() per filing.
"""

from app.services.classifier.rule_based import RuleBasedClassifier
from research.pipeline.dataclasses import FetchedFiling


class BacktestClassifier:
    """
    Wraps RuleBasedClassifier for batch backtest processing.

    A single instance of RuleBasedClassifier is created at init and reused
    across all classify() calls to avoid repeated setup overhead.
    """

    def __init__(self) -> None:
        self._classifier = RuleBasedClassifier()

    async def classify(self, filing: FetchedFiling) -> dict:
        """
        Classify a filing and return a dict with ClassificationResult fields.

        If the filing fetch failed or plain_text is None, returns a stub
        result with setup_type=None (Python None, not the string "NULL") and
        confidence=0.0.

        For successful fetches, calls RuleBasedClassifier.classify() and maps
        any "NULL" setup_type sentinel to Python None before returning.
        """
        if filing.fetch_status != "OK" or filing.plain_text is None:
            return {
                "setup_type": None,            # None (not "NULL") — no match
                "confidence": 0.0,
                "dilution_severity": 0.0,
                "immediate_pressure": False,
                "price_discount": None,
                "short_attractiveness": 0,
                "key_excerpt": "",
                "reasoning": filing.fetch_error or filing.fetch_status or "fetch failed",
                "_shares_offered_raw": None,   # underscore — consumed by BacktestScorer step 7.5
            }

        result = await self._classifier.classify(filing.plain_text, filing.form_type)

        # CRITICAL: Map string "NULL" sentinel to Python None.
        # RuleBasedClassifier returns setup_type="NULL" on no-match.
        # The output schema requires a true null, not the string "NULL".
        # Propagating "NULL" to Parquet causes WHERE setup_type IS NULL to
        # return zero rows.
        if result.get("setup_type") == "NULL":
            result = dict(result)
            result["setup_type"] = None

        return result
