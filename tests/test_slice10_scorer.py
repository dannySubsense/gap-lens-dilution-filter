"""
Slice 10: Scorer — Acceptance Tests

Done-when criteria verified:
1.  Known inputs (Architecture Section 3.6 worked examples) produce expected integer output.
2.  borrow_cost=0.0 substitutes settings.default_borrow_cost and does not raise.
3.  A raw score producing a normalized value of 120 is clamped to 100.
4.  score > 80 → rank "A"; score 70 → rank "B"; score 50 → rank "C"; score 30 → rank "D".
5.  ScorerResult is importable from app.services.scorer.

Invariants verified:
  I-06: score_normalization_ceiling defaults to 1.0; raw_score 0.90 normalizes to 90, not 9.
  I-10: FLOAT_ILLIQUIDITY = settings.adv_min_threshold / fmp_data.adv_dollar.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.scorer import Scorer, ScorerResult  # noqa: E402
from app.services.fmp_client import FMPMarketData     # noqa: E402
from app.services.classifier.protocol import ClassificationResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_classification(**overrides) -> ClassificationResult:
    """Return a minimal valid ClassificationResult with caller-supplied overrides."""
    base: ClassificationResult = {
        "setup_type": "A",
        "confidence": 1.0,
        "dilution_severity": 0.50,
        "immediate_pressure": False,
        "price_discount": None,
        "short_attractiveness": 0,
        "key_excerpt": "test excerpt",
        "reasoning": "test",
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _make_fmp(adv_dollar: float) -> FMPMarketData:
    """Return a minimal FMPMarketData with the specified adv_dollar."""
    return FMPMarketData(
        price=5.00,
        market_cap=50_000_000.0,
        float_shares=10_000_000.0,
        adv_dollar=adv_dollar,
        fetched_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# AC-S10-01: Known inputs produce expected score (Architecture Section 3.6 worked examples)
# I-06: raw_score 0.90 normalizes to 90 (not 9) — score_normalization_ceiling defaults to 1.0
# I-10: FLOAT_ILLIQUIDITY = settings.adv_min_threshold / fmp_data.adv_dollar
# ---------------------------------------------------------------------------

def test_worked_example_high_conviction_rank_a():
    """
    Architecture Section 3.6, Example 1 (high-conviction, Rank A expected):
      DILUTION_SEVERITY = 0.50
      FLOAT_ILLIQUIDITY = 500000 / 600000 = 0.8333...
      SETUP_QUALITY     = 0.65  (setup type A)
      BORROW_COST       = 0.30
      RAW_SCORE         = (0.50 * 0.8333 * 0.65) / 0.30 = 0.90
      normalized_score  = clamp(int(0.90 / 1.0 * 100), 0, 100) = 90 → Rank A

    Also verifies I-06: raw_score 0.90 → score 90, not 9.
    Also verifies I-10: FLOAT_ILLIQUIDITY uses adv_min_threshold / adv_dollar.
    """
    classification = _make_classification(setup_type="A", dilution_severity=0.50)
    fmp_data = _make_fmp(adv_dollar=600_000.0)

    result = Scorer.score(classification, fmp_data, borrow_cost=0.30)

    assert result.score == 90, (
        f"Expected score=90 (Architecture Section 3.6 Worked Example 1), got {result.score}"
    )
    assert result.rank == "A", (
        f"Expected rank='A' for score 90, got {result.rank!r}"
    )


def test_worked_example_weak_setup_rank_d():
    """
    Architecture Section 3.6, Example 2 (weak setup, Rank D expected):
      DILUTION_SEVERITY = 0.25
      FLOAT_ILLIQUIDITY = 500000 / 2000000 = 0.25
      SETUP_QUALITY     = 0.55  (setup type B)
      BORROW_COST       = 0.30
      RAW_SCORE         = (0.25 * 0.25 * 0.55) / 0.30 = 0.115
      normalized_score  = clamp(int(0.115 / 1.0 * 100), 0, 100) = 11 → Rank D
    """
    classification = _make_classification(setup_type="B", dilution_severity=0.25)
    fmp_data = _make_fmp(adv_dollar=2_000_000.0)

    result = Scorer.score(classification, fmp_data, borrow_cost=0.30)

    assert result.score == 11, (
        f"Expected score=11 (Architecture Section 3.6 Worked Example 2), got {result.score}"
    )
    assert result.rank == "D", (
        f"Expected rank='D' for score 11, got {result.rank!r}"
    )


# ---------------------------------------------------------------------------
# AC-S10-02: borrow_cost=0.0 substitutes settings.default_borrow_cost, does not raise
# ---------------------------------------------------------------------------

def test_borrow_cost_zero_substitutes_default_and_does_not_raise():
    """
    borrow_cost=0.0 must not raise ZeroDivisionError.
    It substitutes settings.default_borrow_cost (0.30), producing the same
    result as passing 0.30 explicitly.
    """
    classification = _make_classification(setup_type="A", dilution_severity=0.50)
    fmp_data = _make_fmp(adv_dollar=600_000.0)

    result_with_zero = Scorer.score(classification, fmp_data, borrow_cost=0.0)
    result_with_default = Scorer.score(classification, fmp_data, borrow_cost=0.30)

    assert result_with_zero.score == result_with_default.score, (
        f"borrow_cost=0.0 should substitute default (0.30) and produce score "
        f"{result_with_default.score}, got {result_with_zero.score}"
    )


# ---------------------------------------------------------------------------
# AC-S10-03: A raw score producing a normalized value of 120 is clamped to 100
# ---------------------------------------------------------------------------

def test_pre_clamp_120_is_clamped_to_100(monkeypatch):
    """
    When raw_score / score_normalization_ceiling * 100 = 120 before clamping,
    the final score must be 100 (clamped at ceiling).

    Engineering the scenario using the worked-example-1 inputs (raw_score = 0.90)
    with score_normalization_ceiling = 0.75:
      pre_clamp = int(0.90 / 0.75 * 100) = int(120.0) = 120 → clamped to 100.
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "score_normalization_ceiling", 0.75)

    classification = _make_classification(setup_type="A", dilution_severity=0.50)
    fmp_data = _make_fmp(adv_dollar=600_000.0)

    result = Scorer.score(classification, fmp_data, borrow_cost=0.30)

    assert result.score == 100, (
        f"Expected score clamped to 100 when pre_clamp=120, got {result.score}"
    )


# ---------------------------------------------------------------------------
# AC-S10-04: Rank boundary tests
#   score > 80 → "A"
#   score 70   → "B"  (60 <= score <= 80)
#   score 50   → "C"  (40 <= score < 60)
#   score 30   → "D"  (score < 40)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target_score,expected_rank", [
    (81, "A"),  # score > 80
    (70, "B"),  # 60 <= score <= 80
    (50, "C"),  # 40 <= score < 60
    (30, "D"),  # score < 40
])
def test_rank_assignment_for_score_boundaries(target_score, expected_rank, monkeypatch):
    """
    Rank thresholds (Architecture Section 3.6):
      score > 80 → "A", 60-80 → "B", 40-59 → "C", < 40 → "D".

    Drives the scorer to the target_score by setting score_normalization_ceiling
    to a value such that:
      int(raw_score / ceiling * 100) == target_score

    Using raw_score = 0.90 (worked example 1):
      ceiling = 0.90 / (target_score / 100)  →  score = target_score exactly.
    """
    from app.core.config import settings

    raw_score = 0.90  # from worked example 1
    ceiling = raw_score / (target_score / 100)
    monkeypatch.setattr(settings, "score_normalization_ceiling", ceiling)

    classification = _make_classification(setup_type="A", dilution_severity=0.50)
    fmp_data = _make_fmp(adv_dollar=600_000.0)

    result = Scorer.score(classification, fmp_data, borrow_cost=0.30)

    assert result.score == target_score, (
        f"Expected score={target_score}, got {result.score}"
    )
    assert result.rank == expected_rank, (
        f"Expected rank={expected_rank!r} for score={target_score}, got {result.rank!r}"
    )


# ---------------------------------------------------------------------------
# AC-S10-05: ScorerResult is importable from app.services.scorer
# ---------------------------------------------------------------------------

def test_scorer_result_importable():
    """ScorerResult must be importable from app.services.scorer."""
    # The import at the top of this module already verifies importability;
    # this test makes the criterion explicit and fails loudly if the class vanishes.
    assert ScorerResult is not None, "ScorerResult could not be imported from app.services.scorer"
    result = ScorerResult(score=90, rank="A")
    assert result.score == 90
    assert result.rank == "A"
