import logging
import re
from typing import Any

from app.services.classifier.protocol import ClassificationResult

_SHARES_OFFERED_PATTERNS = [
    re.compile(r"(\d[\d,]*)\s+shares?\s+of\s+common\s+stock", re.IGNORECASE),
    re.compile(r"offering\s+of\s+(\d[\d,]*)\s+shares?", re.IGNORECASE),
    re.compile(r"(\d[\d,]*)\s+shares?\s+(?:are\s+)?being\s+offered", re.IGNORECASE),
    re.compile(r"aggregate\s+of\s+(\d[\d,]*)\s+shares?", re.IGNORECASE),
]


def _extract_shares_offered(text: str) -> int:
    for pattern in _SHARES_OFFERED_PATTERNS:
        m = pattern.search(text)
        if m:
            return int(m.group(1).replace(",", ""))
    return 0


logger = logging.getLogger(__name__)

PRICE_PATTERNS = [
    re.compile(r"at\s+\$(\d+\.?\d*)\s+per\s+share", re.IGNORECASE),
    re.compile(r"offering\s+price\s+of\s+\$(\d+\.?\d*)", re.IGNORECASE),
    re.compile(r"price\s+of\s+\$(\d+\.?\d*)\s+per\s+share", re.IGNORECASE),
    re.compile(r"per\s+share\s+price\s+of\s+\$(\d+\.?\d*)", re.IGNORECASE),
    re.compile(r"priced\s+at\s+\$(\d+\.?\d*)", re.IGNORECASE),
]

_RULES: list[dict[str, Any]] = [
    {
        "setup_type": "A",
        "form_types": {"S-1", "S-1/A"},
        "keywords": ["effective date", "commence offering"],
        "immediate_pressure": False,
    },
    {
        "setup_type": "E",
        "form_types": {"13D/A", "S-1"},
        "keywords": ["cashless exercise", "warrant"],
        "immediate_pressure": False,
    },
    {
        "setup_type": "B",
        "form_types": {"424B4"},
        "keywords": ["supplement", "takedown"],
        "immediate_pressure": True,
    },
    {
        "setup_type": "C",
        "form_types": {"424B2"},
        "keywords": ["priced", "underwritten"],
        "immediate_pressure": True,
    },
    {
        "setup_type": "D",
        "form_types": {"8-K"},
        "keywords": ["at-the-market", "sales agent"],
        "immediate_pressure": False,
    },
]


class RuleBasedClassifier:
    """Rule-based classifier implementing ClassifierProtocol."""

    async def classify(self, filing_text: str, form_type: str) -> ClassificationResult:
        text_lower = filing_text.lower()
        matched_patterns: list[str] = []
        winner: dict[str, Any] | None = None
        matched_keyword: str = ""

        for rule in _RULES:
            if form_type not in rule["form_types"]:
                continue
            for kw in rule["keywords"]:
                if kw.lower() in text_lower:
                    pattern_label = f"{rule['setup_type']}:{kw}"
                    matched_patterns.append(pattern_label)
                    if winner is None:
                        winner = rule
                        matched_keyword = kw

        if winner is None:
            return ClassificationResult(
                setup_type="NULL",
                confidence=0.0,
                dilution_severity=0.0,
                immediate_pressure=False,
                price_discount=None,
                short_attractiveness=0,
                key_excerpt="",
                reasoning="No rule matched.",
                _shares_offered_raw=0,
            )

        setup_type = winner["setup_type"]
        key_excerpt = _extract_excerpt(filing_text, matched_keyword)
        price_discount = _extract_price_discount(filing_text)
        shares_offered_raw = _extract_shares_offered(filing_text)

        return ClassificationResult(
            setup_type=setup_type,
            confidence=1.0,
            dilution_severity=0.0,  # scored using FMP data in Scorer
            immediate_pressure=winner["immediate_pressure"],
            price_discount=price_discount,
            short_attractiveness=0,  # computed by Scorer
            key_excerpt=key_excerpt,
            reasoning=(
                f"Setup {setup_type}: {form_type} filing with "
                f"'{matched_keyword}' language."
            ),
            _shares_offered_raw=shares_offered_raw,  # dilution_severity stays 0.0 — pipeline step 7.5 resolves it
        )


def _extract_excerpt(text: str, keyword: str) -> str:
    idx = text.lower().find(keyword.lower())
    if idx == -1:
        return text[:500]
    start = max(0, idx - 100)
    return text[start : start + 500]


def _extract_price_discount(text: str) -> float | None:
    for pattern in PRICE_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                return float(
                    m.group(1)
                )  # offering price (not yet ratio — Scorer handles ratio)
            except ValueError:
                continue
    return None
