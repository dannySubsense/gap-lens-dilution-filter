# Research Log — Gap Lens Dilution Filter

**Project:** gap-lens-dilution-filter  
**Research start date:** 2026-04-05  
**Principal:** dannySubsense.art  
**Research lead:** Claude (Sonnet 4.6)  

---

## Purpose

This log is the authoritative record of the research process. It documents hypotheses as they are formed, experiments as they are designed and run, findings as they emerge, and pivots as they are decided. It is written as the work happens — not reconstructed after the fact.

This log, together with the findings documents it references, is the primary source material for the white paper.

---

## Entry Format

Each entry follows this structure:

```
### [DATE] — [TITLE]
**Type:** Hypothesis | Experiment | Finding | Decision | Pivot
**Status:** Open | In Progress | Closed
**References:** [links to findings documents, code, data]

[Body]
```

---

## Log

---

### 2026-04-05 — Project Pivot: Build Mode → Research Mode

**Type:** Pivot  
**Status:** Closed  

**What happened:**

The project was initiated as a 6-week MVP build (see `INTAKE.md`, `docs/specs/dilution-short-filter/`). Phase 1 delivered a live EDGAR ingestion pipeline, a rule-based classifier (Setup A-E), a scorer, and a Next.js dashboard. 161 unit tests and 16 Playwright browser tests pass.

During post-sprint review, two problems surfaced:

1. **Manual position tracking was built that should not have been.** The spec process misread "position tracking (manual entry)" in the MVP build plan as a permanent feature. The original intent — per `INTAKE.md` and `dilution-short-filter-system.md` — was that position outcomes would come from systematic backtests, not from the principal's discretionary trades. The principal is not a systematic discretionary trader; using their trade journal as training labels would produce a model that reflects their individual mistakes, not signal quality. This is a fundamental labeling problem.

2. **The project goal was never to build a dashboard.** The dashboard is an observation surface. The goal, per `INTAKE.md`, is model distillation: a 1B-parameter model that classifies SEC filings into Setup A-E at 1/30th the cost of GPT-4, validated against actual market outcomes. The Phase 1 build is a precondition for that goal — not the goal itself.

**Decision:** Reframe as a strategy development research project. The outcome is not predetermined. The research will determine whether the hypothesis holds, and the findings will inform what gets built.

**What Phase 1 produced that is valuable for research:**
- Live EDGAR ingest pipeline (filings arriving every 90s)
- Rule-based classifier generating labeled signals in production
- DuckDB schema already structured around the distillation data model (`filings`, `labels`, `market_data`, `signals`)
- Scored, ranked signal feed observable over real market conditions

**What Phase 1 produced that will be replaced:**
- Manual position tracking UI — will be replaced by backtest outcome data
- Hardcoded `setup_quality` config values — will be replaced by historical win rates from backtest

---

### 2026-04-05 — Core Research Hypothesis

**Type:** Hypothesis  
**Status:** Open  

**Hypothesis H1:**

> The five setup types (A-E) defined in `dilution-short-filter-system.md`, when filtered by the six filter criteria and scored by the short attractiveness formula, produce a statistically meaningful predictive signal for short-term price declines in small-cap equities following SEC dilution filings.

**Sub-hypotheses:**

- **H1a:** Rank A signals (score > 80) produce larger and more consistent price declines than Rank B signals (score 60-80).
- **H1b:** The setup type distribution is not uniform — some setup types (likely C: Priced Deal, B: Shelf Tap) produce stronger signals than others (D: ATM Active).
- **H1c:** The rule-based classifier's labels agree substantially (>70%) with a teacher model (Claude) on setup type classification.
- **H1d:** A student model (Llama 1B, LoRA fine-tuned) can replicate teacher labels at F1 > 0.90 per setup type.

**What would falsify H1:**
- Historical backtest shows no consistent directional price movement following Rank A/B signals
- Win rate across all setup types is indistinguishable from random
- The filter criteria are too permissive (everything passes) or too restrictive (nothing passes)

**Dependencies:**
- H1a and H1b require the historical backtest (not yet built)
- H1c requires teacher labeling campaign (depends on H1a/H1b findings)
- H1d requires labeled training corpus (depends on H1c)

---

### 2026-04-05 — Research Question RQ1: Does the rule-based classifier have edge?

**Type:** Experiment design  
**Status:** Open  

**Question:** When a signal fires (Rank A or B), does the underlying equity actually decline over the next 1, 3, 5, and 20 trading days?

**Why this must be answered first:** If the answer is no, there is no point in building a teacher labeling campaign or training a student model. The distillation pipeline amplifies the classifier — it does not fix a broken classifier.

**Experiment design:**

1. Fetch historical EDGAR filings (2020-2025) matching the filter criteria (form types: S-1, S-3, 424B2, 424B4, 8-K with offering language, 13D/A)
2. Run each through the existing classifier and scorer pipeline (offline, not live)
3. For each signal that would have fired (Rank A or B):
   - Record: ticker, filing timestamp, setup_type, score, rank
   - Fetch historical OHLCV: closing price on day of filing (T), T+1, T+3, T+5, T+20
   - Compute: 1d_return, 3d_return, 5d_return, 20d_return
4. Aggregate by setup_type and rank
5. Compute: win rate (% negative returns), median return, Sharpe contribution, max favorable excursion

**Data sources needed:**
- EDGAR EFTS historical search (already integrated — needs date-range query)
- Historical OHLCV at filing timestamps — FMP (already integrated) or Polygon.io

**Output:** `docs/research/findings/001_backtest_results.md` + raw data CSV

**Open questions before starting:**
- How far back does EDGAR EFTS historical search reliably go?
- Does FMP have sufficient historical price coverage for small-cap tickers?
- Should we use closing price on filing day or next-open? (filing time of day matters)

*Note: Questions 1 and 2 answered by 2026-04-05 market_data finding below — see revised design.*

---

### 2026-04-05 — Finding: market_data project is the backtest infrastructure

**Type:** Finding  
**Status:** Closed  
**References:** `/home/d-tuned/market_data/docs/specs/`

**Summary:**

The market_data project (parallel session) contains the price and float infrastructure required for the dilution filter backtest. We do not need to build it. We need to consume it.

**What is available:**

| Data | Table | Coverage | Status |
|------|-------|----------|--------|
| Daily OHLCV (adjusted) | `daily_prices` | 2017-2025, NYSE/NASDAQ/AMEX, survivorship-bias-free | Certified v1.0.0 |
| Daily market cap | `daily_market_cap` | 2017-2025 | Certified |
| Per-day eligible universe | `daily_universe` | 2017-2025, with `in_smallcap_universe` flag | Certified |
| Daily float | `historical_float` | 2020-03-04 to present | 8.4M rows |
| Short interest | `short_interest` | 2021+ | Backfill running |
| Gap events | `gap_events_v2` | 2017-2025, 199K events | Complete |
| SEC filings | `filings_event` | Empty (403 from EDGAR on VM) | Available for our use |

**CIK coverage (critical for linking EDGAR filings to price data):**

99.2% of in-scope NYSE/NASDAQ/AMEX stocks have CIK in `raw_symbols_massive`. The 57% null rate in the full audit is across OTC, international, and warrants — irrelevant to our universe. The CIK→ticker bridge will work for virtually every signal the dilution filter produces.

**Hard constraint — float data:**

FMP's historical float endpoint starts 2020-03-04. No affordable alternative exists pre-2020 (Bloomberg/CapIQ: $5K-24K/year). This creates a two-tier backtest:

- **2020-2025 (full fidelity):** All 6 filter criteria + complete scoring formula (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY / BORROW_COST)
- **2017-2019 (partial fidelity):** No float → FLOAT_ILLIQUIDITY unavailable. Setup type classification and directional price signal still testable. ADV computable from `daily_prices` volume. Market cap available.

**Implication for H1:** The full scoring formula can only be backtested from 2020. The setup type classification and directional price hypothesis (H1a, H1b) can be tested back to 2017.

**The filings_event table in market_data:**

Empty, available, schema adaptable. Loading the dilution filter's historical EDGAR filing corpus there makes it shared infrastructure for both projects.

**Impact on H1 confidence:** Increases. The data required to test the hypothesis exists and is validated.

---

### 2026-04-05 — Revised Research Design: Backtest Architecture

**Type:** Experiment design (revised)  
**Status:** Open  

**Scope decision:** Primary backtest window is **2020-2025** (full fidelity). Secondary analysis 2017-2019 for setup type classification only.

**Pipeline:**

```
EDGAR EFTS (date-range query, 2017-2025)
  → Filter by form type: S-1, S-3, 424B2, 424B4, 8-K, 13D/A
  → Fetch filing text (AskEdgar or direct SEC URL)
  → Offline classifier (rule-based-v1)
  → For signals with setup_type != NULL:
      JOIN daily_prices      ON (ticker, filing_date) → T, T+1, T+3, T+5, T+20 returns
      JOIN daily_market_cap  ON (ticker, filing_date) → market cap filter check
      JOIN historical_float  ON (ticker, AS-OF filing_date) → FLOAT_ILLIQUIDITY (2020+)
      JOIN short_interest    ON (ticker, AS-OF filing_date) → borrow cost proxy (2021+)
      JOIN daily_universe    ON (ticker, filing_date) → in_smallcap_universe flag
  → Compute scorer (full formula 2020+, partial 2017-2019)
  → Output: CSV with (filing_date, ticker, setup_type, score, rank,
            1d_return, 3d_return, 5d_return, 20d_return,
            float_at_T, short_int_at_T)
```

**CIK→ticker resolution:** Use the dilution filter's existing `cik_ticker_map`.

**Output:** `docs/research/data/backtest_results.csv` + `docs/research/findings/001_backtest_results.md`

**Remaining open questions before building:**
1. EDGAR EFTS historical search: rate limits and reliable date range for bulk form-type queries? *(Answered: use quarterly master.gz for discovery, EFTS for live polling)*
2. AskEdgar vs direct SEC URL at scale: direct SEC Archives at 5-7 req/s with User-Agent. AskEdgar cost-prohibitive for backfill.
3. Should the offline classifier run `rule-based-v1` as-is? Yes for setup type detection; needs extension for underwriter extraction (see 2026-04-05 entry below).

---

### 2026-04-05 — Hypothesis Expansion: Underwriter Signal

**Type:** Hypothesis (expansion)
**Status:** Open
**Source:** Principal domain knowledge — small-cap short selling community practice

**New hypotheses added:**

> **H1e:** Underwriter/placement agent identity is a statistically significant predictor of post-filing price decline, independent of setup type. Certain repeat participants in small-cap dilution events have measurably worse post-filing price outcomes than others.

> **H1f:** A small set of repeat firms accounts for a disproportionate share of the highest-conviction dilution signals. The distribution of deal quality by firm is highly skewed, not uniform.

> **H1g:** The sales agent role in ATM programs (8-K equity distribution agreements) carries distinct predictive value from the lead underwriter role in traditional offerings (424B4, S-1). The two levels must be tracked separately and in combination.

**Domain context:**

The small-cap short-selling community actively tracks which underwriters and placement agents are involved in dilution deals. Certain firms are repeat facilitators of aggressive dilution programs:

- **Lead underwriters** appear on the cover page of 424B4 and S-1 filings (e.g., Maxim Group, Spartan Capital, Palladium Capital Advisors, Dawson James Securities)
- **Sales agents / placement agents** are named in the equity distribution agreement referenced in 8-K ATM program announcements (e.g., H.C. Wainwright & Co., B. Riley Securities, Lake Street Capital Markets, Canaccord Genuity)

H.C. Wainwright in particular is known for extremely high-frequency ATM facilitation in small-cap biotech and early-stage companies. Their presence as sales agent is used by the community as a near-standalone signal.

**What this means for the pipeline:**

The classifier must be extended to extract all named financial intermediaries and their roles from filing text. Extraction targets by form type:

| Form Type | Where to extract | What to extract |
|-----------|-----------------|-----------------|
| S-1, 424B4 | Cover page + "Plan of Distribution" section | Lead underwriter, co-managers |
| 8-K (ATM announcement) | Body text + exhibit reference | Sales agent / placement agent named in equity distribution agreement |
| 424B3 (ATM supplement) | Cover page + distribution plan | Sales agent (references the ATM agreement) |
| 424B2 | Cover page + distribution section | Underwriter, dealer-manager |
| 13D/A | Body — less structured | May name broker facilitating warrant exercise |

**Data model addition:**

```
filing_participants
  accession_number    FK → filings
  firm_name           normalized firm name
  role                ENUM: lead_underwriter | co_manager | sales_agent | placement_agent
  raw_text            original text snippet from which firm was extracted
```

This enables:
- Win rate per firm (all roles combined)
- Win rate per firm + role combination
- Co-appearance network (which firms collaborate repeatedly)
- Underwriter multiplier for SETUP_QUALITY score

**Scoring formula implication:**

The current formula:
```
SCORE = (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY) / BORROW_COST
```

Phase R1 target (after H1e/H1f tested):
```
SCORE = (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY × UNDERWRITER_FACTOR) / BORROW_COST

Where:
  UNDERWRITER_FACTOR = historical_win_rate_for_primary_firm
                       × role_weight (lead_underwriter vs sales_agent)
```

**White paper implication:**

Quantifying underwriter-level historical signal quality in small-cap dilution is not documented in public quant research. The community uses it as folk knowledge. Making it systematic and quantified is a novel contribution.

**Impact on backtest design:**

The backtest output schema must include `filing_participants` data alongside price outcomes. The aggregate analysis must produce an underwriter-level win rate table, not just a setup-type table.

---
