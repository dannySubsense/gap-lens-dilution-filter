# White Paper Outline — Gap Lens Dilution Filter

**Working title:** "Distilling a Short-Selling Signal: A Systematic Approach to SEC Dilution Filing Classification"  
**Last updated:** 2026-04-05  
**Status:** Outline only — sections will be drafted as findings accumulate

---

## Abstract (to be written last)

---

## 1. Introduction

### 1.1 The Problem
Small-cap equity dilution events (secondary offerings, ATM programs, warrant exercises) are systematically under-monitored by retail and semi-institutional participants. The information is public — SEC filings are free — but the volume and technical language make manual review impractical. Most signals arrive and decay within hours.

### 1.2 The Opportunity
Large language models can classify SEC filings with high accuracy, but at $0.025-0.03 per filing, the inference cost at production volume is prohibitive for systematic deployment. Model distillation — training a small (1B parameter) domain-specific model on teacher-labeled data — offers a path to the same classification quality at 1/30th the cost.

### 1.3 The Research Question
Does a systematic, model-driven approach to identifying SEC dilution short-selling setups produce a statistically valid and financially exploitable signal? And can that signal be distilled into a cost-efficient deployable model?

### 1.4 Contributions
- A taxonomy of five SEC dilution setup types with filter and scoring criteria
- A live EDGAR ingestion and classification pipeline
- A historical backtest of rule-based vs teacher-labeled signal quality
- A distilled 1B model validated on financial metrics, not NLP metrics alone
- An open-source implementation

---

## 2. Background

### 2.1 SEC Filing Landscape
- Filing types relevant to dilution: S-1, S-3, 424B2, 424B4, 8-K (ATM), 13D/A
- Volume and timing characteristics
- Why small-cap equities are the relevant universe

### 2.2 Model Distillation in Financial NLP
- NVIDIA-KxSystems blueprint: teacher → student via LoRA
- Financial validation requirement: NLP metrics alone are insufficient
- Prior work: financial news classification, earnings call summarization

### 2.3 Short Selling Mechanics
- Borrow cost, locate requirements, timing constraints
- Why dilution events create systematic short opportunities
- Hold time characteristics by setup type

---

## 3. System Architecture

### 3.1 Live Pipeline (Phase 1)
- EDGAR EFTS polling
- Filter chain (6 criteria)
- Rule-based classifier
- Scorer and ranker
- Signal management and lifecycle

### 3.2 Research Infrastructure
- Historical backfill mechanism
- Backtest engine
- Teacher labeling pipeline
- Student training pipeline (LoRA, RTX 4090)

### 3.3 Data Model
- DuckDB schema: filings, labels, market_data, signals
- As-of join pattern for price enrichment

---

## 4. Setup Taxonomy

### 4.1 Setup A: IPO/Primary Offering (S-1, S-1/A)
### 4.2 Setup B: Shelf Tap (424B4)
### 4.3 Setup C: Priced Deal (424B2)
### 4.4 Setup D: ATM Active (8-K)
### 4.5 Setup E: Warrant Exercise (13D/A)
### 4.6 NULL: No dilution signal

*Each section: definition, trigger text, filter criteria, typical price action, hold time*

---

## 5. Scoring Formula

### 5.1 Formula derivation
### 5.2 Component analysis
- Dilution severity
- Float illiquidity
- Setup quality (from backtest win rates)
- Borrow cost adjustment

### 5.3 Rank thresholds and calibration

---

## 6. Historical Backtest (Finding 001)

*To be written after experiment RQ1 completes*

### 6.1 Data and methodology
### 6.2 Results by setup type
### 6.3 Results by rank (A vs B)
### 6.4 Win rate, average return, Sharpe, max drawdown
### 6.5 Interpretation and limitations

---

## 7. Rule-Based vs Teacher Classification (Finding 002)

*To be written after teacher labeling campaign*

### 7.1 Agreement rate
### 7.2 Confusion matrix
### 7.3 Qualitative analysis of disagreements
### 7.4 Implications for distillation

---

## 8. Model Distillation (Finding 003)

*To be written after student training*

### 8.1 Training corpus construction
### 8.2 Fine-tuning procedure (LoRA, RTX 4090)
### 8.3 F1 per setup type: student vs teacher
### 8.4 Financial validation: student Sharpe vs teacher Sharpe
### 8.5 Cost analysis: rule-based vs teacher vs student

---

## 9. Production Comparison (Finding 004)

*To be written after live A/B*

### 9.1 Rule-based vs student signals over live weeks
### 9.2 Signal volume, quality, latency
### 9.3 Flywheel: how production traffic improves the student over time

---

## 10. Discussion

### 10.1 What worked and what didn't
### 10.2 Limitations
- Data availability constraints
- Sample size and statistical power
- Market regime dependency
- Borrow cost not modeled (Phase 1)

### 10.3 Extensions
- IBKR borrow cost integration
- Portfolio optimization layer (NVIDIA cuOpt)
- Multi-factor signal combination
- Real-time rebalancing

---

## 11. Conclusion

---

## Appendices

### A. Filter Criteria Rationale
### B. Scoring Formula Derivation
### C. Teacher Prompt (exact text)
### D. Student Training Configuration
### E. Backtest Methodology (full detail)
### F. Data Sources and Licenses

---

*Sections 6-9 will be drafted as each research phase completes. The white paper is written from findings, not assumptions.*
