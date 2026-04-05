import logging
from dataclasses import dataclass

from app.core.config import settings
from app.services.classifier.protocol import ClassificationResult
from app.services.fmp_client import FMPMarketData

logger = logging.getLogger(__name__)


def _clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(max_val, value))


@dataclass
class ScorerResult:
    score: int
    rank: str


class Scorer:
    @staticmethod
    def score(
        classification: ClassificationResult,
        fmp_data: FMPMarketData,
        borrow_cost: float,
    ) -> ScorerResult:
        if classification["setup_type"] == "NULL":
            return ScorerResult(score=0, rank="D")

        if classification["dilution_severity"] == 0.0:
            logger.warning(
                "dilution_severity is 0.0 — shares_offered not extractable; "
                "returning conservative low score"
            )

        effective_borrow_cost = borrow_cost
        if borrow_cost == 0.0:
            logger.warning(
                "borrow_cost is 0.0; substituting default_borrow_cost=%.4f",
                settings.default_borrow_cost,
            )
            effective_borrow_cost = settings.default_borrow_cost

        dilution_severity: float = classification["dilution_severity"]
        float_illiquidity: float = settings.adv_min_threshold / fmp_data.adv_dollar
        setup_quality: float = settings.setup_quality[classification["setup_type"]]

        raw_score = (
            dilution_severity * float_illiquidity * setup_quality
        ) / effective_borrow_cost

        pre_clamp = int(raw_score / settings.score_normalization_ceiling * 100)
        if pre_clamp > 100:
            logger.warning(
                "Score exceeds normalization ceiling before clamping: raw_score=%.6f, "
                "pre_clamp=%d; clamping to 100",
                raw_score,
                pre_clamp,
            )

        score = _clamp(pre_clamp, 0, 100)

        if score > 80:
            rank = "A"
        elif score >= 60:
            rank = "B"
        elif score >= 40:
            rank = "C"
        else:
            rank = "D"

        return ScorerResult(score=score, rank=rank)
