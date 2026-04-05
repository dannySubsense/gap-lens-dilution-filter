# Working Hypothesis — Gap Lens Dilution Filter Research

**Last updated:** 2026-04-05  
**Status:** Active — not yet tested

---

## The Central Claim

SEC dilution filings (S-1, S-3, 424B, 8-K ATM, 13D/A warrant exercise) in small-cap equities, when filtered by market cap, float, dilution percentage, price, and ADV, and classified into five setup types by a rule-based or learned model, produce a statistically meaningful and exploitable predictive signal for short-term price declines.

Furthermore, this classification task can be distilled from a large language model (teacher) into a 1B-parameter fine-tuned model (student) at 1/30th the inference cost, without material loss of signal quality — as measured by financial validation metrics (win rate, Sharpe ratio, max drawdown), not NLP metrics alone.

---

## Hypothesis Tree

```
H1: Setup-filtered dilution filings predict price declines
│
├── H1a: Rank A > Rank B in magnitude and consistency of decline
├── H1b: Setup type is a meaningful predictor (C and B > D in edge)
├── H1c: Rule-based classifier agrees with teacher model (Claude) > 70%
│         └── H1c-alt: Where they disagree, teacher is more accurate
├── H1d: Student model (Llama 1B LoRA) achieves F1 > 0.90 per setup type
│         └── H1d-fin: Student model preserves Sharpe ratio vs teacher
├── H1e: Underwriter/placement agent identity is a statistically significant
│         predictor of post-filing price decline, independent of setup type
├── H1f: A small set of repeat firms accounts for a disproportionate share
│         of the highest-conviction signals (skewed, not uniform distribution)
└── H1g: Sales agent role in ATM programs carries distinct predictive value
          from lead underwriter role in traditional offerings — must be tracked
          separately and in combination
```

---

## What Must Be True for This to Work

1. Dilution events reliably precede price pressure (not already priced in)
2. Small-cap equities are sufficiently inefficient that the signal persists long enough to act on
3. The filter criteria are calibrated correctly (not too broad, not too narrow)
4. The setup definitions (A-E) reflect meaningfully different market dynamics
5. Historical EDGAR data is sufficient in volume and quality to train a 1B model
6. Underwriter/placement agent names are extractable reliably from filing text across form types
7. The same firms appear with sufficient frequency to compute statistically meaningful win rates

---

## What Would Kill This

| Finding | Implication |
|---------|-------------|
| Historical backtest shows random returns | H1 falsified — setup definitions have no edge |
| All setup types behave identically | H1b falsified — setup type is not a useful feature |
| Rule-based labels disagree with teacher > 50% | H1c falsified — rule-based classifier is unreliable as a foundation |
| Student F1 < 0.80 even with 25K samples | H1d falsified — task too complex for 1B model |
| Win rate good but Sharpe < 0.5 | Not exploitable — returns don't justify execution risk |
| Underwriter win rates are uniform across firms | H1e falsified — firm identity adds no information beyond setup type |
| Top 5 underwriters account for < 30% of events | H1f falsified — distribution is not meaningfully skewed |
| Sales agent and lead underwriter have identical win rate distributions | H1g falsified — role distinction doesn't matter |

---

## Current Confidence Level

| Hypothesis | Confidence | Basis |
|------------|------------|-------|
| H1 | Low-Medium | Theoretical — not yet tested against data |
| H1a | Unknown-ready | Infrastructure confirmed: market_data daily_prices + float 2020+ |
| H1b | Unknown-ready | Infrastructure confirmed |
| H1c | Medium | Rule-based classifier was designed to approximate expert judgment |
| H1d | Medium | NVIDIA KxSystems: 1B model achieves 0.95 F1 on analogous task with 25K samples |
| H1e | Unknown-ready | Underwriter names are in filing text; extraction not yet built |
| H1f | Low-Medium | Community practice strongly suggests skewed distribution; unquantified |
| H1g | Unknown-ready | Role distinction (lead vs sales agent) requires extraction + backtest |

**Updated 2026-04-05 (initial):** Confidence in testability of H1a/H1b upgraded — market_data infrastructure confirmed. Full fidelity 2020-2025, partial 2017-2019.

**Updated 2026-04-05 (underwriter expansion):** H1e, H1f, H1g added based on principal domain knowledge. The small-cap short-selling community tracks underwriter and placement agent identity as a signal. H.C. Wainwright, Maxim Group, Spartan Capital, Dawson James, Palladium Capital are known repeat participants. Both lead underwriter (424B4, S-1 cover page + Plan of Distribution) and sales agent (8-K ATM equity distribution agreement) levels must be extracted. A `filing_participants` table with role normalization is required in the backtest pipeline.

---

## How Confidence Updates

This document is updated each time a finding is logged in `RESEARCH_LOG.md`. Confidence levels are revised based on evidence, not assumptions.

---
