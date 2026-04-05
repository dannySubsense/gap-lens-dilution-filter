# Gap Lens Dilution Filter — Project Intake

**Project:** gap-lens-dilution-filter  
**Location:** `~/projects/gap-lens-dilution-filter/`  
**Created:** 2026-03-25  
**Status:** Ready for spec phase  

---

## Overview

SEC filing-based filter and strategy setup ID system for small-cap dilution short selling opportunities. Uses model distillation to classify filings into Setup A-E and score short attractiveness at 1/30th the cost of GPT-4.

---

## Core References

### Reference Repositories
| Repo | URL | Purpose |
|------|-----|---------|
| **NVIDIA-KDB-X** | https://github.com/KxSystems/nvidia-kx-samples/tree/main/ai-model-distillation-for-financial-data | Model distillation blueprint for financial data |
| **NVIDIA Quant Portfolio Optimization** | https://github.com/NVIDIA-AI-Blueprints/quantitative-portfolio-optimization | Portfolio optimization layer, cuOpt integration |

### Related Resources (AlgoTradingIdeas)
| Resource | Location | Contains |
|----------|----------|----------|
| SEC Filing Distillation Spec | `~/life/resources/AlgoTradingIdeas/sec-filing-distillation-spec.md` | Full distillation pipeline architecture |
| Dilution Short Filter System | `~/life/resources/AlgoTradingIdeas/dilution-short-filter-system.md` | Setup A-E definitions, scoring formula |
| NVIDIA KDB-X Model Distillation | `~/life/resources/AlgoTradingIdeas/nvidia-kdbx-model-distillation.md` | Teacher-student training details |
| NVIDIA Quant Portfolio Opt | `~/life/resources/AlgoTradingIdeas/nvidia-quant-portfolio-opt.md` | cuOpt, RAPIDS integration |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DILUTION SHORT FILTER SYSTEM                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐  │
│  │   INGEST    │ →  │   TEACHER   │ →  │   DISTILL   │ →  │   DEPLOY    │  │
│  │             │    │             │    │             │    │             │  │
│  │ EDGAR RSS   │    │ GPT-4/Claude│    │ Llama 3.2   │    │ 1B NIM      │  │
│  │ Parse 8-K   │    │ Classify +  │    │ 1B LoRA     │    │ Classify    │  │
│  │ S-1, 424B   │    │ Score       │    │ Fine-tune   │    │ $0.001/call │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘  │
│        │                   │                   │                  │         │
│        ▼                   ▼                   ▼                  ▼         │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                         KDB-X LAYER                                 │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│   │  │ filings     │  │ labels      │  │ market_data │  │ signals     │ │   │
│   │  │ (raw text)  │  │ (teacher    │  │ (OHLCV      │  │ (pred vs    │ │   │
│   │  │             │  │  output)    │  │  as-of)     │  │  actual)    │ │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Setup Types (A-E)

| Setup | Filing | Trigger | Typical Drop | Hold Time |
|-------|--------|---------|--------------|-----------|
| **A: IPO/Primary** | S-1, S-1/A | Effective date announced | -15% to -40% | 1-3 days |
| **B: Shelf Tap** | 424B4 | Unexpected offering | -10% to -25% | 1-2 days |
| **C: Priced Deal** | 424B2 | Below-market pricing | -8% to -20% | Same day |
| **D: ATM Active** | 8-K | Sales ongoing | Grind -2%/day | Ongoing |
| **E: Warrant Exercise** | 13D/A, S-1 | Exercise notice | -5% to -15% | 1 day |

---

## Filter Criteria

1. Filing type match (S-1, S-3, 424B, 8-K with offering language)
2. Market cap < $2B (small cap only)
3. Float < 50M shares (low float = violent)
4. Dilution % > 10% (material)
5. Price > $1 (avoid delist risk)
6. ADV > $500K (can get short)

---

## Scoring Formula

```
SCORE = (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY) / BORROW_COST

Where:
  DILUTION_SEVERITY = shares_offered / pre_float
  FLOAT_ILLIQUIDITY = 1 / (float_shares × price × ADV_ratio)
  SETUP_QUALITY = historical_win_rate_for_this_setup_type
  BORROW_COST = annualized borrow fee (if available)
```

**Rank Thresholds:**
- **A:** > 80 → Immediate alert, pre-borrow if possible
- **B:** 60-80 → Watchlist, monitor for entry
- **C:** 40-60 → Track, maybe paper trade
- **D:** < 40 → Ignore

---

## Classification Output Schema

```json
{
  "setup_type": "C",
  "confidence": 0.94,
  "dilution_severity": 0.35,
  "immediate_pressure": true,
  "price_discount": -0.18,
  "short_attractiveness": 82,
  "key_excerpt": "...offering 12.5M shares at $4.25...",
  "reasoning": "Priced overnight offering below market..."
}
```

---

## Cost Comparison

| Approach | Per Filing | 1000 filings/month | Annual Cost |
|----------|-----------|-------------------|-------------|
| **GPT-4 API** | $0.03 | $30 | $360 |
| **Claude 3.5** | $0.025 | $25 | $300 |
| **Distilled 1B (cloud)** | $0.001 | $1 | $12 |
| **Distilled 1B (local)** | $0 | $0 | $0 |

**Break-even:** After ~500 filings, local deployment pays off training cost.

---

## MVP Timeline (6 weeks)

| Week | Task | Deliverable |
|------|------|-------------|
| 1 | Historical data fetch | 5 years of filings in KDB-X |
| 2 | Teacher labeling | 2K labeled examples |
| 3 | Student training | Fine-tuned 1B model |
| 4 | Evaluation + backtest | F1 scores, trading validation |
| 5 | Integration | Live alerts from distilled model |
| 6 | Flywheel setup | Production logging, retrain pipeline |

---

## Data Sources

| Data | Source | Cost | Priority |
|------|--------|------|----------|
| SEC filings | EDGAR RSS / SEC Insights API | $0-500/mo | P0 |
| Float data | Finviz / Ortex / Manual | $0-150/mo | P0 |
| Price/volume | Polygon.io | Free tier | P0 |
| Short borrow | Interactive Brokers API | Free (if you trade) | P1 |
| Historical setups | Quiver Quant / Manual backfill | $0 | P1 |

---

## Tech Stack

- **Base Model:** Llama 3.2 1B
- **Fine-tuning:** LoRA (low-rank adaptation)
- **Training:** Local RTX 4090 (~2-4 hours for 10K samples)
- **Deployment:** NVIDIA NIM (local or cloud)
- **Data Layer:** KDB-X (or SQLite/DuckDB simplified)
- **Teacher Model:** GPT-4 or Claude 3.5 Sonnet (one-time labeling)

---

## Out of Scope (MVP)

| Not Building | Why | Future Phase |
|--------------|-----|--------------|
| NLP extraction | Start with filing type + manual review | Phase 2 |
| ML prediction | Use setup historical win rates first | Phase 2 |
| Auto-execution | Manual trade entry, system surfaces only | Phase 3 |
| Full backtest | Forward test with paper alerts | Phase 2 |
| GPU acceleration | CPU sufficient for filtering | Phase 3 (scale) |

---

## Key Risks

| Risk | Mitigation |
|------|------------|
| Teacher labels wrong | Human review sample, consensus labeling |
| Student doesn't generalize | Stratified train/test by year/sector |
| Distribution shift | Flywheel retraining monthly |
| KDB-X learning curve | Use SQLite/DuckDB first, migrate later |

---

## Next Steps

1. Confirm data source (EDGAR RSS vs SEC Insights API)
2. Define initial watchlist universe (sectors, market cap)
3. Begin Week 1 MVP (historical data fetch)
4. Paper trade for 1 month to validate setup definitions

---

**END OF INTAKE**
