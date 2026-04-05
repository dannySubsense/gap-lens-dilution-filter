from typing import Protocol, TypedDict, runtime_checkable


class ClassificationResult(TypedDict):
    setup_type: str           # "A", "B", "C", "D", "E", or "NULL"
    confidence: float         # 0.0 to 1.0; rule-based: 1.0 on match, 0.0 on NULL
    dilution_severity: float  # shares_offered / pre_float; 0.0 if not extractable
    immediate_pressure: bool  # True for setup types B and C
    price_discount: float | None  # offering_price / last_close - 1; None if not extractable
    short_attractiveness: int     # 0-100; pre-scorer classifier estimate
    key_excerpt: str          # <= 500 characters
    reasoning: str            # one sentence


@runtime_checkable
class ClassifierProtocol(Protocol):
    async def classify(
        self, filing_text: str, form_type: str
    ) -> ClassificationResult:
        ...
