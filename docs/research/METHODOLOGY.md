# Research Methodology — Gap Lens Dilution Filter

**Last updated:** 2026-04-05

---

## Research Type

Quantitative strategy development research. The goal is to determine whether a systematic, model-driven approach to identifying short-selling opportunities in SEC dilution filings produces a statistically valid and exploitable signal — and, if so, to build the most cost-efficient model that preserves that signal.

This is not academic research. The validation criterion is financial (Sharpe ratio, win rate, drawdown), not statistical (p-value, F1 alone). A model with 0.95 F1 that loses money is a failure. A model with 0.85 F1 that produces Sharpe > 1.5 is a success.

---

## Research Phases

### Phase R1: Signal Validation (Current)

**Question:** Does the hypothesis have empirical support?  
**Method:** Historical backtest against EDGAR filings (2020-2025) + price data  
**Output:** Backtest results by setup type and rank  
**Gate:** Before proceeding to R2, H1 must show at least preliminary support  

### Phase R2: Classifier Validation

**Question:** Is the rule-based classifier a reliable foundation for teacher labeling?  
**Method:** Teacher labeling campaign (Claude) on a sample of historical filings, compared against rule-based labels  
**Output:** Agreement rate, confusion matrix, qualitative analysis of disagreements  
**Gate:** H1c requires > 70% agreement to proceed with distillation  

### Phase R3: Distillation

**Question:** Can a 1B student model replicate the teacher at F1 > 0.90?  
**Method:** Fine-tune Llama 3.2 1B via LoRA on teacher-labeled corpus (target: 10K-25K samples)  
**Output:** Student model, F1 per setup type, financial backtest of student signals vs teacher signals  
**Gate:** Student Sharpe ratio must be within 20% of teacher Sharpe ratio  

### Phase R4: Production Integration

**Question:** Does the student model improve on the rule-based classifier in production?  
**Method:** A/B comparison — rule-based signals vs student signals over live trading weeks  
**Output:** Side-by-side signal quality comparison  

---

## Data Sources

| Data Type | Source | Status | Notes |
|-----------|--------|--------|-------|
| Live EDGAR filings | EDGAR EFTS (integrated) | Active | 90s poll interval |
| Historical EDGAR filings | EDGAR EFTS historical search | Not yet built | Needs date-range query |
| Real-time price/market data | FMP API (integrated) | Active | Used in live pipeline |
| Historical OHLCV | FMP or Polygon.io | Not yet sourced | Required for backtest |
| Short borrow cost | IBKR API | Disabled (Phase 1) | Phase R4 |

---

## Instrumentation

All research artifacts are stored in this project:

| Artifact | Location | Purpose |
|----------|----------|---------|
| Research log | `docs/research/RESEARCH_LOG.md` | Timestamped record of all hypotheses, experiments, findings, decisions |
| Working hypothesis | `docs/research/HYPOTHESIS.md` | Current hypothesis state, confidence levels |
| Findings | `docs/research/findings/NNN_title.md` | Individual finding documents, one per experiment |
| Backtest data | `docs/research/data/` | Raw CSVs, not committed if large |
| Research code | `research/` (to be created) | Scripts for backfill, backtest, teacher labeling |

---

## Standards of Evidence

1. **No cherry-picking.** Backtest results are reported for all signals in the date range, not a curated subset.

2. **Honest about sample size.** Small samples get wide confidence intervals. We do not claim statistical significance we do not have.

3. **Financial metrics, not NLP metrics.** Win rate, Sharpe ratio, max drawdown, average return are the primary measures. F1 score is secondary.

4. **Document failures.** If a hypothesis is falsified, it is recorded as a finding with the same detail as a confirmation. Null results are results.

5. **Separate signal from noise.** We distinguish between "the filter fires" and "the filter fires and the price moves as predicted." Both are measured.

6. **Reproducible.** Every finding references the exact data, code version, and parameters used to produce it.

---

## White Paper Contribution

Each finding document is written to be quotable in the white paper. The structure:

- **Abstract** (one paragraph, what was tested and what was found)
- **Background** (why this experiment was run, what hypothesis it tests)
- **Method** (exact procedure, data sources, parameters)
- **Results** (tables, numbers, charts if applicable)
- **Interpretation** (what the results mean for the hypothesis)
- **Limitations** (what this finding does not tell us)
- **Next question** (what this finding opens up)

---

## Research Governance

**Decision authority:** The principal (dannySubsense.art) approves all pivots, scope changes, and decisions to proceed past research gates.

**Research lead:** Claude — frames hypotheses, designs experiments, interprets findings, recommends decisions.

**Agents invoked as needed:**
- `research` — external data source investigation, literature
- `data-auditor` — pipeline data quality analysis
- `code-executor` — implements research scripts to exact specification
- `architect` — designs new components when a finding requires one

**Not using the spec-team workflow for research.** The spec team (requirements-analyst → architect → planner → code-executor → spec-reviewer) is reserved for building software to a confirmed design. Research outputs inform that workflow; they do not replace it.

---
