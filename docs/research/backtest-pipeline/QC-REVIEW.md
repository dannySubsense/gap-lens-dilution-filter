# QC Review: Backtest Pipeline

**Pipeline:** backtest-pipeline v1.0
**Review date:** 2026-04-05
**Reviewer:** @spec-reviewer (risk-averse QC pass)
**Review type:** Pre-implementation research integrity audit
**Documents reviewed:**
- `01-REQUIREMENTS.md` (v1.0)
- `02-ARCHITECTURE.md` (v1.0)
- `RESEARCH-CONTRACT.md` (v1.0)
- `04-ROADMAP.md` (v1.0)
- `docs/research/HYPOTHESIS.md`
- `docs/research/METHODOLOGY.md`
- `docs/research/RESEARCH_LOG.md`
- `app/services/classifier/rule_based.py` (live code)
- `app/services/scorer.py` (live code)
- `app/core/config.py` (live code)
- `app/services/filter_engine.py` (live code)
- `app/services/fmp_client.py` (live code)
- `app/services/classifier/protocol.py` (live code)
- `05-REVIEW.md` (prior functional review)

---

## Executive Summary

The spec suite is unusually thorough for a research pipeline -- the four documents plus the Research Contract form a coherent and largely self-consistent design. The prior functional review (05-REVIEW.md) correctly identified the major cross-document inconsistencies and most have been resolved. However, this risk-focused QC pass has identified **3 BLOCKING issues**, **7 HIGH issues**, **8 MEDIUM issues**, and **8 LOW issues** that were not caught or were incompletely addressed by the prior review. The most critical findings are: (1) the Scorer formula in the live code uses `adv_min_threshold / fmp_data.adv_dollar` for FLOAT_ILLIQUIDITY, which is an ADV ratio, not a float-based illiquidity measure -- the architecture's description of the scoring formula is inconsistent with the actual code and this directly affects H1a claims; (2) the RuleBasedClassifier returns `setup_type="NULL"` (the string) not `setup_type=None` (the Python None), creating a type mismatch that will propagate through the entire pipeline if the BacktestClassifier does not handle it; (3) the borrow cost proxy mapping from short interest to borrow cost is specified differently in the architecture vs the scorer code, with no clear specification of what value actually reaches the scorer.

**Recommendation: PROCEED WITH CAUTION.** The BLOCKING issues must be resolved before implementation begins. The HIGH issues must be resolved before the first full pipeline run. The design is sound in structure but has enough ambiguities in the exact numerical paths that two independent implementers could produce different scores for the same filing.

---

## Findings Table

### BLOCKING Issues

| ID | Category | Document(s) | Description | Required Resolution |
|---|---|---|---|---|
| B-01 | Scoring Formula Integrity | 02-ARCHITECTURE.md vs `app/services/scorer.py` | **The architecture describes the scoring formula as `DILUTION_SEVERITY x FLOAT_ILLIQUIDITY x SETUP_QUALITY / BORROW_COST` and says FLOAT_ILLIQUIDITY is "computed from `float_at_T`" (Section 9, line 682).** But the actual `Scorer.score()` code (scorer.py line 46) computes `float_illiquidity = settings.adv_min_threshold / fmp_data.adv_dollar`. This is an ADV-based liquidity measure, not a float-based one. The variable name `float_illiquidity` in the code is misleading -- it divides the ADV threshold ($500K) by the actual ADV, producing a ratio that has nothing to do with float shares. This means: (a) the "FLOAT_ILLIQUIDITY" component does not actually use float data at all in the current formula; (b) the architecture's claim that 2017-2019 partial-fidelity tier sets "FLOAT_ILLIQUIDITY = 1.0 (neutral)" because float is unavailable is based on a misunderstanding of the code -- the code never uses float for this component; (c) the two-tier coverage design's entire rationale (float availability creates two tiers of analytical validity) may be overstated since float enters the formula only through dilution_severity (shares_offered / float), not through a separate FLOAT_ILLIQUIDITY multiplier. **If the backtest is built to the architecture spec rather than the actual code, the scores will be different from what the live pipeline produces, invalidating the research claim that "the backtest signal universe is identical to what the live pipeline would have produced."** | The architect must inspect `Scorer.score()`, reconcile the variable name `float_illiquidity` with its actual computation (`adv_min_threshold / adv_dollar`), and update the architecture to describe the formula as it actually is in code. The two-tier design rationale must be re-examined: if float only enters through dilution_severity, then the partial tier's limitation is specifically about dilution_severity being uncomputable (not about a separate FLOAT_ILLIQUIDITY component being unavailable). The BacktestScorer adapter must be specified to pass the correct field (`adv_at_T`) to produce the same `float_illiquidity` ratio the live scorer computes. |
| B-02 | Classifier Integration | 02-ARCHITECTURE.md, `app/services/classifier/rule_based.py`, `app/services/classifier/protocol.py` | **`RuleBasedClassifier.classify()` returns `setup_type="NULL"` (the string literal "NULL") for no-match cases (rule_based.py line 88), not `setup_type=None` (Python None).** The BacktestRow dataclass (02-ARCHITECTURE.md line 216) declares `setup_type: str | None` and the output schema (01-REQUIREMENTS.md line 236) says the column is "VARCHAR, YES (nullable)" with values "A, B, C, D, E, or NULL". The architecture's BacktestClassifier spec (Section 6.4, line 369) says: `return a stub ClassificationResult with setup_type="NULL"`. This conflates two things: (a) the classifier returns the string "NULL", and (b) the output schema expects a SQL/Parquet NULL. If the pipeline writes the string "NULL" to the Parquet file, downstream analysis queries like `WHERE setup_type IS NULL` will not match -- they will only match if the value is actually None/null. The Research Contract structural integrity checks do not test for this. Any analysis that filters on NULL setup_type will silently produce wrong counts. | The architect must specify an explicit mapping in BacktestClassifier: if `classification["setup_type"] == "NULL"`, then `BacktestRow.setup_type = None` (Python None, which becomes Parquet null). This must be documented and tested. The same issue applies to the `Scorer.score()` code (line 28) which checks `classification["setup_type"] == "NULL"` -- the BacktestScorer must be aware that by the time scoring runs, the canonical representation may have changed. Add a structural integrity check to the Research Contract: "Zero rows may have `setup_type` equal to the string literal 'NULL'." |
| B-03 | Scoring Formula Integrity | 02-ARCHITECTURE.md Section 6.9, `app/services/scorer.py` | **The BacktestScorer borrow cost derivation is specified as `short_interest_at_T / float_at_T` (architecture line 581), but the live Scorer.score() receives `borrow_cost` as a direct parameter and does not compute it internally from short interest and float.** The architecture says: "If `snapshot.short_interest_at_T` is not None and `snapshot.float_at_T` is not None and `snapshot.float_at_T > 0`: `borrow_cost = snapshot.short_interest_at_T / snapshot.float_at_T`." This proxy (short interest as a fraction of float) is a reasonable concept, but the mapping is not specified precisely enough. The live system currently passes `borrow_cost=0.0` universally (IBKR borrow cost is disabled per config.py line 52: `ibkr_borrow_cost_enabled: bool = False`), meaning `Scorer.score()` always substitutes `settings.default_borrow_cost = 0.30`. The backtest introduces a new borrow cost computation (SI/float) that has never been validated against the live system, and the exact numerical range is unspecified. Short interest as a fraction of float could be 0.01 (1%) to 2.0+ (200% -- heavily shorted). If this raw ratio is passed as `borrow_cost`, the scorer will divide by it, producing wildly different scores than the live pipeline (which always divides by 0.30). **Two implementers could reasonably interpret "borrow_cost proxy" differently and produce incomparable results.** | The architect must specify the exact formula for converting short_interest_at_T to the borrow_cost parameter passed to Scorer.score(), including: (a) whether the raw SI/float ratio is used directly, or whether it is scaled/clamped to the same range as the live default_borrow_cost (0.30); (b) what the expected range of the proxy is; (c) whether the research intention is to test the scoring formula AS-IS (always using default_borrow_cost=0.30) or to test an enhanced formula using actual short interest data. If the latter, this is a formula change that violates the constraint "no modifications to core classification/scoring logic" and must be explicitly acknowledged. Recommend: for Phase R1, always pass borrow_cost=0.0 to the scorer (letting it substitute default_borrow_cost=0.30) so the backtest formula exactly matches the live formula. Short interest data can still be stored in the output for Phase R4 analysis. |

---

### HIGH Issues

| ID | Category | Document(s) | Description | Required Resolution |
|---|---|---|---|---|
| H-01 | filter_status Enum Mismatch | 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, RESEARCH-CONTRACT.md | **Three documents define three different sets of valid `filter_status` values.** Requirements (line 244): 7 values (`PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR`). Architecture BacktestRow (line 224): 9 values (adds `UNRESOLVABLE, FETCH_FAILED`). Research Contract (line 40): 7 values (`PASSED, FILTERED_OUT, UNRESOLVABLE, FETCH_FAILED, NO_MATCH, NOT_IN_UNIVERSE, PIPELINE_ERROR`) -- a completely different 7 that includes `FILTERED_OUT` and `NO_MATCH` but excludes all the specific `*_FAIL` values. This is the previously identified G-01 gap, still unresolved. An implementer following the Research Contract would use `FILTERED_OUT` as a catch-all; an implementer following the Architecture would use specific fail reasons. The Research Contract's structural integrity checks validate against its own enum, so a pipeline built to the architecture spec would fail RC validation. | Agree on one canonical enum across all three documents. Recommendation: use the Architecture's 9-value set (most specific). Update Requirements and Research Contract to match. The Research Contract value `FILTERED_OUT` should be removed or redefined as a parent category. `NO_MATCH` should be removed from filter_status (it is a classification_status per AC-04). |
| H-02 | Survivorship Bias | 02-ARCHITECTURE.md Section 6.2, 01-REQUIREMENTS.md AC-02 | **CIK-to-ticker resolution via `raw_symbols_massive` is the sole path for linking filings to market data. Any filing whose CIK is not in this table becomes UNRESOLVABLE and is excluded from all market data joins, filtering, scoring, and outcome computation.** The architecture states the table covers "99.2% of in-scope NYSE/NASDAQ/AMEX stocks" (from RESEARCH_LOG.md). But the 0.8% that are missing could systematically be the most distressed, smallest, or most recently delisted companies -- exactly the companies most likely to have dilution filings. This is a form of survivorship bias that is not acknowledged in the survivorship bias controls section. The UNRESOLVABLE filings are logged but never analyzed for systematic patterns. | Add a Research Contract requirement: "Before accepting findings, the researcher must inspect the distribution of UNRESOLVABLE filings by year, form_type, and (where entity_name is available) industry. If the UNRESOLVABLE rate exceeds 5% of total discovered filings for any year, the survivorship bias disclosure must state this and discuss potential impact." Also add an output column or manifest field for total_unresolvable_count. |
| H-03 | Look-ahead Bias | 02-ARCHITECTURE.md Section 6.7 | **The ADV computation uses `close * volume` from daily_prices, but the architecture does not specify whether `close` is the raw close or `adjusted_close`.** If `adjusted_close` is used (which incorporates split adjustments), and a stock split occurs between the ADV window and the filing date, the ADV computed from adjusted prices would reflect the post-split price level, not the actual dollar volume that was traded on those historical days. This could materially understate or overstate ADV. The live pipeline uses FMP's ADV figure which is presumably computed from actual historical dollar volume. If the backtest computes ADV differently, Filter 6 (ADV > $500K) could produce different pass/fail decisions than the live pipeline would have. | Specify whether ADV is computed from `close * volume` or `adjusted_close * volume` in the SQL query. For ADV, raw `close * volume` is more appropriate because ADV measures actual dollar volume traded, not split-adjusted volume. If `daily_prices` only contains adjusted_close (not raw close), document this limitation and assess the impact of stock splits on the ADV filter. |
| H-04 | Outcome Computation | 01-REQUIREMENTS.md US-09, 02-ARCHITECTURE.md Section 6.10 | **Returns are computed using `adjusted_close`, but the adjustment methodology is not specified.** Adjusted close typically accounts for splits and sometimes dividends. For a short-selling strategy, the relevant return is the actual price change an investor would experience, which includes splits but should NOT include dividend adjustments (a short seller must pay dividends, which is a cost, not a return). If `adjusted_close` includes dividend adjustments, the computed returns will overstate the actual returns for stocks that paid dividends during the holding period. For small-cap stocks in dilution scenarios this is likely a minor effect, but it should be documented. More critically: **reverse splits** are common in distressed small-caps and create large apparent price changes in adjusted_close data. A 1-for-10 reverse split would show the pre-split adjusted_close as 1/10th of the actual traded price, making the T+20 return appear to be +900% when the stock was actually flat. | Document in the Research Contract that returns are computed from `adjusted_close` and state the adjustment methodology used by the market_data source (split-adjusted only, or split+dividend adjusted). Add a data quality check: flag any return_20d > +500% or < -99% as a potential corporate action artifact. If reverse splits are present in the data, they would systematically bias the return distribution for the worst-performing stocks. |
| H-05 | Underwriter Validation | RESEARCH-CONTRACT.md Section 5.2 | **The 85% accuracy threshold validated on a 50-filing sample has a wide confidence interval.** With N=50 and observed accuracy p=0.85, the 95% Wilson confidence interval is approximately [0.726, 0.928]. This means the true accuracy could plausibly be as low as 72.6%. A 72.6% extraction accuracy means roughly 1 in 4 firm-filing associations is wrong, which could materially distort per-firm win rates (H1e). The 50-filing sample is stratified (20+ for 424B4/S-1, 15+ for 8-K), but within each stratum the sample size is even smaller, making per-stratum accuracy estimates unreliable. | Increase the validation sample to at least 100 filings (yielding a CI width of roughly +/-7% at 85% accuracy) or document the wide CI explicitly in the Research Contract and require that the confidence interval be disclosed alongside the accuracy figure. Add per-stratum accuracy reporting (424B4/S-1 accuracy separately from 8-K accuracy) since the extraction patterns are fundamentally different for these form types. |
| H-06 | Classifier Side Effects | `app/services/classifier/rule_based.py`, 02-ARCHITECTURE.md Section 6.4 | **The RuleBasedClassifier.classify() method is async (`async def classify`).** The backtest pipeline calls this in a batch loop over 200K+ filings. While the classifier itself does not make any external API calls (confirmed by code inspection -- no HTTP, no DB, no FMP calls), the async nature means the BacktestClassifier must either: (a) run an event loop for each call, or (b) batch calls in an async context. The architecture (Section 6.4, line 371) says "call `await classifier.classify(...)`" but does not specify how the async context is managed in the batch processing loop. If the orchestrator is synchronous (the roadmap's PipelineOrchestrator does not mention async for classification), calling an async method from sync code requires `asyncio.run()` or equivalent, which has performance implications at 200K+ calls. | Specify in the architecture how the async RuleBasedClassifier.classify() is called from the batch context. Options: (a) the orchestrator runs an async event loop for the classification stage; (b) BacktestClassifier wraps the async call in `asyncio.run()` per-call (expensive but simple); (c) BacktestClassifier extracts the synchronous logic from RuleBasedClassifier and calls it directly (violates the "no modifications" constraint). Recommend option (a) -- the fetch stage already uses asyncio, so the orchestrator likely has an event loop. |
| H-07 | Scoring Interface Mismatch | `app/services/scorer.py`, 02-ARCHITECTURE.md Section 6.9 | **The Scorer.score() method accesses `classification["dilution_severity"]` (line 45) which is always 0.0 as returned by RuleBasedClassifier (rule_based.py line 108: `dilution_severity=0.0`).** The architecture says the backtest computes dilution_severity as `shares_offered_raw / float_at_T` in the BacktestFilterEngine (Section 6.8, line 553). But this computed value must somehow reach Scorer.score() via the `classification` parameter. The live pipeline has a "step 7.5" (referenced in rule_based.py line 117: "pipeline step 7.5 resolves it") that presumably patches dilution_severity into the ClassificationResult before scoring. The backtest architecture does not specify this patching step. If the BacktestScorer passes the raw ClassificationResult from the classifier (with dilution_severity=0.0), the scorer will always produce score=0 for every filing (since the numerator `dilution_severity * float_illiquidity * setup_quality` will be zero). | The architect must specify how dilution_severity flows from the BacktestFilterEngine's computation into the ClassificationResult before it reaches BacktestScorer.score(). The architecture must either: (a) specify that BacktestScorer creates a modified copy of ClassificationResult with the computed dilution_severity patched in, or (b) specify that BacktestScorer calls Scorer.score() with a pre-patched classification dict. Without this, every filing will score 0 and H1a is untestable. |

---

### MEDIUM Issues

| ID | Category | Document(s) | Description | Required Resolution |
|---|---|---|---|---|
| M-01 | Market Data Join | 02-ARCHITECTURE.md Section 6.7 | **ADV computation returns NULL if fewer than 20 trading days of history exist** (architecture line 483: "Returns None if fewer than 20 rows available"). For recently-IPO'd companies or companies that changed ticker symbols, this could systematically exclude filings near IPO dates from passing Filter 6 (ADV > $500K). These early-stage companies are disproportionately likely to have dilution filings (post-IPO capital raises are common). The pipeline would classify and join them but silently filter them out at ADV. This is not survivorship bias per se, but it is a sample selection effect that could understate the number of qualifying signals in the first months post-IPO. | Document this as a known limitation. Consider computing ADV with a minimum of 5 trading days (with a flag indicating the window was shorter than 20 days) rather than returning NULL. Alternatively, keep the 20-day requirement but add a manifest counter for "filings excluded due to insufficient ADV history." |
| M-02 | Market Data Join | 02-ARCHITECTURE.md Section 6.7 | **For the float AS-OF join: when `historical_float` has no row at all for a ticker (never covered by FMP), the pipeline sets `float_at_T = None` and `float_available = True` for post-2020 filings.** This means the filing proceeds to Filter 3 (float < 50M) and fails with `FLOAT_NOT_AVAILABLE` (per AC-06 line 196). This is correct behavior. However, this is distinct from the case where `historical_float` has rows that all post-date the filing (data backfill arrived late). In that case, the AS-OF query also returns NULL, but the reason is different. Both cases produce the same output -- there is no way to distinguish "FMP never covered this symbol" from "FMP data for this symbol starts after the filing date" in the output. | Add a field or manifest counter to distinguish these two cases. Not critical for Phase R1, but important for interpreting coverage gaps. |
| M-03 | Delisting Definition | 01-REQUIREMENTS.md US-09, 02-ARCHITECTURE.md Section 6.10 | **The operational definition of "delisted" is implicit, not explicit.** The architecture derives `delisted_before_TN` from whether fewer than N forward price rows exist in `daily_prices` after the effective_trade_date (line 528). This means "delisted" is operationally defined as "no more price rows in the database." But this could also occur if: (a) the stock was halted for an extended period (still listed but not trading), (b) the stock changed its ticker symbol (old ticker stops appearing in daily_prices), or (c) the market_data database has a gap in coverage for that ticker. All three would incorrectly set `delisted_before_TN = True`. Ticker changes are particularly concerning since they are common after reverse splits and mergers in small-cap stocks. | Document the operational definition of "delisted" explicitly in the Research Contract. State that `delisted_before_TN = True` means "fewer than N price rows after filing date in daily_prices" and that this may include ticker changes and trading halts, not just delistings. Add to the delisting disclosure: if `delisted_before_T20 = true` exceeds 10%, investigate whether ticker changes account for a material fraction. |
| M-04 | Acquisitions | 01-REQUIREMENTS.md US-09 | **If a stock is acquired (tender offer, merger), the T+20 return could show a large positive move (acquirer pays a premium).** For a short-selling research strategy, this is a real adverse outcome -- the short seller would experience a loss. The pipeline correctly includes this return in the distribution. However, acquisitions are fundamentally different from the signal the strategy targets (dilution-driven price decline). A finding that shows "Rank A signals have 65% negative T+5 returns" could be contaminated by a few large positive acquisition returns that increase the standard deviation and reduce the Sharpe ratio without reflecting the signal's predictive quality for dilution events. | Add a note to the Research Contract that acquisition events are not excluded from returns and represent a real risk to the short strategy. In the findings analysis, recommend computing win rates and Sharpe ratios both with and without returns > +50% at T+20 as a sensitivity analysis. This is an analysis-stage concern, not a pipeline-stage concern -- no code change needed, but the contract should acknowledge it. |
| M-05 | Normalization Config | 02-ARCHITECTURE.md Section 6.5, 04-ROADMAP.md Slice 7 | **If the underwriter_normalization.json config is missing or empty, the extractor operates with `is_normalized = False` for all firms.** This means H1e, H1f, and H1g analysis would proceed on unnormalized firm names. "H.C. Wainwright & Co., LLC" and "H.C. Wainwright" would be counted as separate firms, fragmenting the win rate computation and understating firm concentration. There is no pipeline-level warning or manifest flag indicating that normalization was not applied. The Research Contract (Section 5) requires the 50-filing validation but does not check whether normalization was active during the validated run. | Add a manifest field: `normalization_config_loaded: bool` and `normalization_config_entry_count: int`. Add a Research Contract check: "If `normalization_config_entry_count = 0`, H1e/H1f/H1g findings must not be cited." The Roadmap Slice 7 tests should include a test that verifies the warning is logged when the config is empty. |
| M-06 | Parallel Slice Development | 04-ROADMAP.md Sequence Rules | **Slices 2-7 are declared parallelizable, but Slices 4 (CIKResolver) and 6 (BacktestClassifier) both depend on Slice 1's dataclasses.py.** If two developers modify dataclasses.py simultaneously (e.g., one adds a field to ResolvedFiling while another adds a field to FetchedFiling), merge conflicts will occur. More subtly, Slice 6 depends on `app.services.classifier.rule_based` and `app.services.classifier.protocol` -- if any other work on the main app modifies these files concurrently with backtest pipeline development, the BacktestClassifier integration tests will break. | Treat Slice 1 as a hard prerequisite that must be fully merged before any of Slices 2-7 start. Document that `app/services/classifier/` and `app/services/scorer.py` are frozen during backtest pipeline development (no modifications to these files). This is already implied by the "rule-based-v1" version constraint but is not operationalized as a development process rule. |
| M-07 | Research Contract Gate Enforcement | 04-ROADMAP.md Slice 14 | **Slice 14 (Research Contract Validation) is a test suite, not a hard gate.** There is no mechanism preventing a researcher from running the analysis (examining the output files) without first running Slice 14's tests. The pipeline orchestrator does not run RC validation as part of its output stage. The Research Contract says "all 16 criteria must pass" but this is enforced by convention, not by code. A researcher under time pressure could skip the validation and produce findings that cite an invalid run. | Add an RC validation summary to the pipeline's output stage: after writing output files, run the structural integrity checks (RC-01 items 1-11) automatically and write the results to `backtest_run_metadata.json` as a `structural_checks_passed: bool` field. The full RC validation (Slice 14) remains a separate test suite, but the critical checks run inline. |
| M-08 | 424B3 Coverage Gap | 01-REQUIREMENTS.md US-05, US-01, 02-ARCHITECTURE.md | **US-05 lists 424B3 as an extraction target for sales agent roles, and the architecture (Section 6.5) specifies extraction patterns for 424B3. But US-01 (Filing Discovery) does not include 424B3 in the form_type filter set: `{S-1, S-1/A, S-3, 424B2, 424B4, 8-K, 13D/A}`.** This means 424B3 filings will never be discovered by the pipeline, so the extraction patterns for 424B3 are dead code. If 424B3 ATM prospectus supplements are relevant to H1g (sales agent role analysis), they must be added to the discovery form_type set. If they are intentionally excluded (the Out of Scope section says "424B3 underwriter extraction beyond sales agent identification" is deferred), then the extraction spec for 424B3 should be removed to avoid confusion. | Either: (a) add 424B3 to the discovery form_type filter set in US-01, the ALLOWED_FORM_TYPES constant, and the Research Contract's form_types list; or (b) remove the 424B3 extraction specification from US-05 and Architecture Section 6.5 and explicitly note that 424B3 is out of scope for Phase R1 discovery. Recommend option (b) since the Out of Scope section already defers this. |

---

### LOW Issues

| ID | Category | Document(s) | Description | Required Resolution |
|---|---|---|---|---|
| L-01 | Cross-document Consistency | 02-ARCHITECTURE.md Section 4, 01-REQUIREMENTS.md US-11 | The directory structure in Architecture Section 4 (line 116-121) lists only 3 output files but the actual output includes 5 files (adding backtest_participants.parquet and backtest_participants.csv). The prior review (05-REVIEW.md Fix 3) noted this but classified it as a pre-existing omission that does not block implementation. | Update the directory tree in Architecture Section 4 to include all 5 output files for completeness. |
| L-02 | Accession Number Format | 02-ARCHITECTURE.md Section 6.1, RESEARCH-CONTRACT.md Section 1.1 | The Research Contract specifies accession_number format as "20-char EDGAR accession number, format `XXXXXXXXXX-YY-ZZZZZZ`" (line 27). The architecture says accession_number is "Derived from filename: last 20 chars, dashes normalized" (line 141) and later "basename, strip `.txt`, normalize dashes" (line 299). The phrase "normalize dashes" is ambiguous -- EDGAR accession numbers contain hyphens (e.g., `0001234567-22-000123`), and the filename path uses slashes, not hyphens, as separators. The derivation logic should be more precise. | Specify the exact derivation: given a filename like `edgar/data/1234567/0001234567-22-000123.txt`, extract the basename (`0001234567-22-000123.txt`), strip the `.txt` extension, yielding `0001234567-22-000123`. State that hyphens in the accession number are preserved (they are part of the EDGAR format). |
| L-03 | Prior Review Gap Still Open | 05-REVIEW.md | G-01 (HIGH) from the prior functional review remains unresolved: `filter_status` value set alignment in 01-REQUIREMENTS.md. G-03 (MEDIUM) also remains open: RunMetadata fields not synchronized with Research Contract. These are tracked here as H-01 (escalated to include the Research Contract's third variant) and should not be forgotten. | Resolve as part of H-01 above. |
| L-04 | S-3 Filing Handling | 02-ARCHITECTURE.md Section 6.5 | S-3 filings are in the discovery form_type set and will be discovered, resolved, fetched, and classified. The architecture says "For S-3: no extraction" of underwriter names. But S-3 filings can still be classified as having a setup_type (if the RuleBasedClassifier's rules match -- currently no rule has S-3 in its form_types, so all S-3 filings will return setup_type="NULL"). These S-3 filings will consume fetch bandwidth and processing time but will never produce a classified signal. This is not wrong, but it is wasteful. | Document explicitly that S-3 filings are included in discovery for completeness (they may feed future classifier rules) but are expected to produce zero classified signals under rule-based-v1. Consider adding an optimization note: if fetch bandwidth is a concern, S-3 filings could be deferred to a second pass. |
| L-05 | METHODOLOGY.md Data Sources Stale | docs/research/METHODOLOGY.md | The Data Sources table (line 48) says "Historical EDGAR filings: EDGAR EFTS historical search, Not yet built" and "Historical OHLCV: FMP or Polygon.io, Not yet sourced." Both of these are now resolved -- the backtest pipeline uses EDGAR quarterly master.gz for discovery and market_data.duckdb for historical OHLCV. The METHODOLOGY.md has not been updated to reflect the current design. | Update the Data Sources table in METHODOLOGY.md to reflect the actual data sources: EDGAR quarterly master.gz for historical filings, market_data.duckdb (certified v1.0.0) for historical OHLCV/market data. |
| L-06 | Trading Calendar Edge Case | 02-ARCHITECTURE.md Section 6.6 | The TradingCalendar derives trading days from `SELECT DISTINCT trade_date FROM daily_prices`. If the market_data database has a trading day where only a subset of symbols traded (e.g., a half-day before a holiday), that day would appear in the calendar. A filing on such a day would use that day's prices, but some symbols might not have prices for that half-day. This is a minor edge case -- daily_prices should have rows for all symbols on any trading day -- but the architecture does not address it. | No code change needed. Add a note acknowledging that the trading calendar is derived from the union of all symbols' trade dates, which should be complete for all NYSE/NASDAQ/AMEX trading days in the certified dataset. |
| L-07 | Fetcher Skip Logic | 02-ARCHITECTURE.md Section 6.3 | The fetcher skips fetch if `resolution_status != "RESOLVED"` (line 341). But the Roadmap Slice 5 test (line 231) says a `ResolvedFiling` with `resolution_status = "UNRESOLVABLE"` returns `fetch_status = "FETCH_FAILED"`. The architecture says the fetch is skipped entirely, which is correct -- but the Roadmap test implies a FetchedFiling object is still created (with fetch_status = "FETCH_FAILED"). These are consistent if "skip" means "create a stub FetchedFiling without making an HTTP call." This is a minor clarity issue. | Add a note: "skip fetch" means "create a FetchedFiling with fetch_status = 'FETCH_FAILED' and fetch_error = 'UNRESOLVABLE' without making any HTTP request." This is implied but should be explicit. |
| L-08 | historical_float Column Name | 02-ARCHITECTURE.md Section 6.7 | The float AS-OF query uses `SELECT float_shares, trade_date AS float_effective_date FROM historical_float WHERE symbol = ? AND trade_date <= ?`. This assumes the historical_float table has columns named `float_shares`, `trade_date`, and `symbol`. OQ-1 from the requirements asked for schema confirmation. The architecture resolved this but the actual column names have not been verified against the live database. If the column names differ (e.g., `shares_float` instead of `float_shares`), every float query will fail. | Verify column names against the live market_data.duckdb before Slice 8 implementation begins. This is already noted as Risk R-01 in the prior review, but it remains unresolved. |

---

## Assumptions

| # | Assumption | Impact if Wrong |
|---|---|---|
| A-01 | `daily_prices.adjusted_close` reflects split adjustments only (not dividend adjustments) | If dividend-adjusted, computed returns would overstate actual returns for dividend-paying stocks. Impact is likely small for distressed small-caps but should be verified. |
| A-02 | `raw_symbols_massive` contains CIK data for all historically-listed NYSE/NASDAQ/AMEX symbols, including those delisted before 2025 | If only currently-active symbols have CIK mappings, survivorship bias would be introduced. The 99.2% coverage figure from the research log gives confidence, but the figure should be verified for the specific time period (2017-2025). |
| A-03 | The `symbol_history` table's `start_date` and `end_date` ranges are populated for all symbols, including those that were never delisted (end_date = NULL for active symbols) | If `end_date` defaults to a specific date rather than NULL for active symbols, the CIKResolver date-range filter would incorrectly exclude active symbols whose `end_date` is before the filing date. |
| A-04 | No filing in EDGAR master.gz has a DateFiled that falls outside the quarter boundaries of the file it appears in (e.g., a Q1 file does not contain a filing dated in Q2) | If cross-quarter filings exist, the date range filtering in FilingDiscovery could miss or duplicate filings at quarter boundaries. |
| A-05 | The scoring formula `raw_score / settings.score_normalization_ceiling * 100` with `score_normalization_ceiling = 1.0` means the score is simply `raw_score * 100`, clamped to [0, 100]. This means any raw_score > 1.0 produces score = 100. The backtest might produce many scores at the ceiling if the formula inputs are in their typical ranges. | If most qualifying filings score 100 after clamping, the rank distribution will be heavily skewed toward Rank A, making H1a (Rank A vs Rank B) difficult to test due to insufficient Rank B/C/D events. |

---

## Open Questions

| # | Question | Impact | Resolution Needed From |
|---|---|---|---|
| OQ-QC-1 | Is `score_normalization_ceiling = 1.0` the intended value for the backtest, or was it set as a placeholder? With typical inputs (dilution_severity ~0.2-2.0, float_illiquidity ~0.5-2.0, setup_quality ~0.45-0.65, borrow_cost ~0.30), raw_score can easily exceed 1.0, meaning many scores would clamp to 100 and most filings would be Rank A. This would make H1a untestable. | HIGH -- directly affects whether H1a (Rank A vs Rank B) can be tested | Principal or architect |
| OQ-QC-2 | The live `Scorer.score()` computes `float_illiquidity = settings.adv_min_threshold / fmp_data.adv_dollar`. This is labeled "float_illiquidity" but is actually an ADV ratio. Is this the intended formula, or is it a bug in the live code that was supposed to use float? The architecture describes a separate FLOAT_ILLIQUIDITY concept that does not match the code. | BLOCKING -- see B-01 | Architect and principal |
| OQ-QC-3 | For the borrow cost proxy: should the backtest use the actual short_interest_at_T / float_at_T ratio, or should it always use default_borrow_cost = 0.30 to match the live pipeline's current behavior (IBKR disabled)? | BLOCKING -- see B-03 | Principal (research design decision) |
| OQ-QC-4 | The `ClassificationResult` TypedDict uses `_shares_offered_raw` as a `NotRequired` field with a leading underscore (indicating it is "transient"). Does the backtest pipeline rely on this field being present? If so, it must always be set by RuleBasedClassifier -- and the code confirms it is (line 98 and 117). But the `NotRequired` typing means a caller cannot assume its presence without a `.get()` check. | MEDIUM -- could cause KeyError at scale | Architect |
| OQ-QC-5 | The Research Contract (Section 3.2) says conservative treatment of delisted symbols requires treating NULL returns "as the worst-observed return in the sample for that horizon." But this treatment is specified for the analysis stage, not the pipeline stage. Who implements this? Is it the researcher doing manual analysis, or should the pipeline output include a column with the conservative return imputation? | LOW -- analysis-stage concern | Researcher |

---

## Risk Register (Addendum to Prior Review)

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| R-QC-1: Score ceiling saturation -- if score_normalization_ceiling = 1.0, most qualifying filings score 100 and rank A, making H1a untestable | MEDIUM | HIGH | Inspect the scoring formula with representative backtest inputs. If >80% of qualifying filings score 100, adjust score_normalization_ceiling before citing findings. |
| R-QC-2: Ticker symbol changes during holding period cause false delisting flags | MEDIUM | MEDIUM | Cross-reference `delisted_before_T20 = true` filings against `symbol_history` to check whether the symbol was actually delisted vs. renamed. |
| R-QC-3: RuleBasedClassifier's keyword matching is case-insensitive but the OFFERING_KEYWORDS check in filter_engine.py is also case-insensitive (`text_lower` vs `kw`). If the backtest re-implements this check differently, Filter 1 pass rates could differ. | LOW | MEDIUM | Import OFFERING_KEYWORDS from filter_engine.py (as specified in Roadmap Slice 9) rather than re-implementing. |
| R-QC-4: The async `classify()` method, if called 200K+ times via `asyncio.run()` per call, could create significant overhead (event loop creation/teardown per call) | MEDIUM | MEDIUM | Use a persistent event loop or batch the async calls. See H-06. |
| R-QC-5: Snappy compression may not be fully deterministic across different versions of the pyarrow library | LOW | MEDIUM | Pin pyarrow version in requirements.txt. Run determinism verification (RC-04) before citing any run. |

---

## Approval Checklist (Updated for QC Review)

### Requirements (01-REQUIREMENTS.md)
- [ ] Reviewed by human
- [ ] H-01 resolved: filter_status value set canonicalized across all documents
- [ ] B-02 resolved: setup_type "NULL" string vs None handling specified
- [ ] M-08 resolved: 424B3 extraction spec removed or 424B3 added to discovery

### Architecture (02-ARCHITECTURE.md)
- [ ] Reviewed by human
- [ ] B-01 resolved: Scoring formula reconciled with actual Scorer.score() code
- [ ] B-03 resolved: Borrow cost proxy specification made precise
- [ ] H-03 resolved: ADV computation specifies raw close vs adjusted_close
- [ ] H-06 resolved: Async classify() calling convention specified
- [ ] H-07 resolved: dilution_severity flow from filter engine to scorer specified

### Research Contract (RESEARCH-CONTRACT.md)
- [ ] Reviewed by human
- [ ] H-01 resolved: filter_status enum matches canonical set
- [ ] H-02 resolved: UNRESOLVABLE survivorship bias analysis required
- [ ] H-04 resolved: adjusted_close methodology documented
- [ ] H-05 resolved: 50-filing sample confidence interval documented or sample increased
- [ ] M-05 resolved: normalization_config_loaded manifest field added
- [ ] B-02 resolved: structural check added for string "NULL" in setup_type

### Roadmap (04-ROADMAP.md)
- [ ] Reviewed by human
- [ ] M-06 resolved: Slice 1 treated as hard prerequisite, frozen files documented
- [ ] M-07 resolved: inline structural checks added to pipeline output stage

### Overall
- [ ] All BLOCKING issues resolved (3 issues: B-01, B-02, B-03)
- [ ] All HIGH issues resolved (7 issues: H-01 through H-07)
- [ ] MEDIUM issues resolved or explicitly accepted (8 issues)
- [ ] Open questions OQ-QC-1 through OQ-QC-3 answered by human
- [ ] Ready for implementation

---

## Verification Pass -- BLOCKING and HIGH Fixes (2026-04-05)

**Verifier:** @spec-reviewer
**Scope:** Targeted verification of fixes applied by three fix agents to 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, and RESEARCH-CONTRACT.md in response to QC findings B-01 through B-03, H-01 through H-07, M-05, M-08.

### B-01: Scoring formula (FLOAT_ILLIQUIDITY is ADV-based)

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.9 now correctly states: `float_illiquidity = settings.adv_min_threshold / fmp_data.adv_dollar` and explicitly names it as an ADV ratio. The `BacktestMarketData` adapter specifies `adv_dollar = snapshot.adv_at_T` (not `snapshot.float_at_T`). The note at line 597 reads: "despite its name, `float_illiquidity` is an ADV-based ratio (`adv_min_threshold / adv_dollar`); float data does not enter this computation."
- 02-ARCHITECTURE.md Section 9 (Two-Tier Coverage Design) line 719 now correctly states the partial fidelity rationale: "For 2017-2019 filings, `float_at_T` is unavailable [...]. As a result, `dilution_severity` cannot be computed (`shares_offered / float_at_T` requires float). The `float_illiquidity` term in the scoring formula is unaffected -- it is computed as `adv_min_threshold / adv_dollar` (an ADV ratio) and does not depend on float data."
- This matches the live `Scorer.score()` code at `scorer.py` line 46: `float_illiquidity: float = settings.adv_min_threshold / fmp_data.adv_dollar`.
- The `BacktestScorer` spec guards against `adv_at_T` being None or zero: "If `snapshot.adv_at_T` is None or zero, do not call the scorer -- set `score = None`, `rank = None`."

### B-02: NULL string mapping

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.4 (BacktestClassifier) now explicitly specifies the mapping: "After receiving the result, apply the NULL sentinel mapping: if `result["setup_type"] == "NULL"`, set `backtest_row.setup_type = None`." The rationale for this mapping is documented.
- 02-ARCHITECTURE.md Section 6.9 (BacktestScorer) includes a guard: "Before calling `Scorer.score()`, check that `patched_classification["setup_type"]` is not `None`. If `setup_type` is `None` (i.e., the no-match sentinel was already mapped to `None` per Section 6.4), do not call the scorer -- set `score = None`, `rank = None`. Note: the scorer internally guards against the string `"NULL"`, but the backtest pipeline stores `None` (not `"NULL"`) as the sentinel, so this guard must check for `None`."
- RESEARCH-CONTRACT.md Section 1.3 structural integrity check #12 now reads: "Zero rows in `backtest_results` may have `setup_type` equal to the string literal `'NULL'`. All no-match cases must be represented as Parquet null (Python None), not the string `'NULL'`."
- RESEARCH-CONTRACT.md Section 1.1 setup_type column definition now states: "`{A, B, C, D, E}` | NULL = classifier returned NO_MATCH or fetch failed" -- confirming valid values exclude the string "NULL".

### B-03: Borrow cost

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.9 now states: "Always pass `borrow_cost=0.0` to `Scorer.score()`. This matches the live pipeline exactly -- IBKR is disabled (`ibkr_borrow_cost_enabled = False` in `config.py`) and the live pipeline always passes `borrow_cost=0.0`, which causes `Scorer.score()` to substitute `settings.default_borrow_cost = 0.30`."
- The SI proxy formula (`short_interest_at_T / float_at_T`) has been removed from the scoring path. The only remnant is in Slice 10 notes (Roadmap line 389) which correctly describes the fallback as `borrow_cost = 0.0`.
- `short_interest_at_T` is explicitly preserved for Phase R4: "Short interest data is preserved in `BacktestRow.short_interest_at_T` for Phase R4 borrow cost sensitivity analysis but is not used in Phase R1 scoring."
- The Roadmap Slice 10 test for short_interest (line 395) correctly specifies: "returns `borrow_cost_source = "DEFAULT"` and score matches what `Scorer.score()` produces with `borrow_cost = settings.default_borrow_cost`."

### H-01: filter_status canonical set

**Status: VERIFIED**

The same 9-value set now appears in all three documents:

- **01-REQUIREMENTS.md** (line 244): `PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR, UNRESOLVABLE, FETCH_FAILED`
- **02-ARCHITECTURE.md** BacktestRow comment (line 224): `"PASSED", "FORM_TYPE_FAIL", "MARKET_CAP_FAIL", "FLOAT_FAIL", "DILUTION_FAIL", "NOT_IN_UNIVERSE", "PIPELINE_ERROR", "UNRESOLVABLE", "FETCH_FAILED"`
- **RESEARCH-CONTRACT.md** (line 40): `{PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR, UNRESOLVABLE, FETCH_FAILED}`

All three match exactly. The old `FILTERED_OUT` and `NO_MATCH` values from the Research Contract have been removed.

### H-02: UNRESOLVABLE survivorship bias

**Status: VERIFIED**

- RESEARCH-CONTRACT.md Section 3.4 (new section) requires distribution analysis of UNRESOLVABLE filings by year and form_type, with a 5%-per-year threshold.
- `total_unresolvable_count` is present in the run manifest spec at RESEARCH-CONTRACT.md Section 7.2 (line 420): "`total_unresolvable_count` | integer | >= 0; count of filings assigned `filter_status = UNRESOLVABLE`".
- The section provides the SQL query for breaking out the UNRESOLVABLE distribution and states the threshold clearly.

### H-03: ADV raw close

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.7, ADV SQL (line 475-486) now specifies `close * volume` and includes an explicit note: "The `close` column is the raw (unadjusted) closing price, not `adjusted_close`. Using raw close is correct for ADV because it reflects the actual dollar volume traded; using `adjusted_close` would distort ADV when stock splits occur. If `daily_prices` does not store a separate raw close column and only has `adjusted_close`, split effects on ADV are accepted as a known approximation and must be documented in the run metadata."

### H-04: adjusted_close methodology

**Status: VERIFIED**

- RESEARCH-CONTRACT.md Section 1.1 now includes a "Note on return computation methodology" (line 59) documenting that returns use `adjusted_close` (split-adjusted) and describing the reverse split artifact problem.
- The flag criterion `|return_20d| > 500%` is specified in the note: "Any row where `return_20d > +500%` or `return_20d < -99%` must be flagged in findings analysis as a potential corporate action artifact."
- RC-17 has been added (line 474): "The count of rows where `ABS(return_20d) > 500%` is documented in the findings and each such row has been investigated for corporate action artifacts (reverse splits) before being cited."

### H-05: Underwriter extraction CI

**Status: VERIFIED**

- RESEARCH-CONTRACT.md Section 5.2 (line 328) now documents the Wilson CI: "At N=50 and an observed accuracy of 85%, the 95% Wilson confidence interval is approximately [72.6%, 92.8%]."
- Mandatory CI reporting requirement is stated: "If the validation sample size is 50 filings, the confidence interval must be reported alongside the accuracy figure in the white paper. All underwriter win rate claims (H1e) must acknowledge the extraction accuracy lower bound."
- The section also recommends increasing to 100 filings to narrow the CI.

### H-06: Async classify() calling convention

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.4 (line 374) now specifies: "The classification stage must run inside a single shared async context -- do not call `asyncio.run()` per filing, as that creates a new event loop per call and is prohibitively expensive at 200K+ iterations."
- 02-ARCHITECTURE.md Section 6.12 (PipelineOrchestrator, line 657-670) includes the recommended pattern with `asyncio.run()` called once for the entire classification batch, with sample code showing `async def _classify_batch(filings)` and `classified = asyncio.run(_classify_batch(fetched_filings))`.

### H-07: dilution_severity patching

**Status: VERIFIED**

- 02-ARCHITECTURE.md Section 6.9 (line 582-593) now specifies the patching step explicitly under the heading "Dilution severity patching (mirrors live pipeline 'step 7.5')." The spec includes sample code:
  ```python
  patched_classification = dict(classification)
  patched_classification["dilution_severity"] = (
      backtest_row.dilution_severity
      if backtest_row.dilution_severity is not None
      else 0.0
  )
  ```
- The rationale is documented: "Without this step, every filing scores 0 because `dilution_severity=0.0` produces `raw_score=0` regardless of other factors."
- The `dilution_severity` value is sourced from `BacktestFilterEngine` computation (`shares_offered_raw / float_at_T`) as documented in Section 6.8 (line 556): "`dilution_severity = shares_offered_raw / float_at_T`. This is the value stored in `BacktestRow.dilution_severity` and passed to the scorer."

### M-05: Normalization config manifest fields

**Status: VERIFIED**

- RESEARCH-CONTRACT.md Section 7.2 run manifest (lines 425-426) now includes both fields:
  - `normalization_config_loaded | boolean | true if underwriter_normalization.json was loaded and non-empty; false if the file was missing or empty`
  - `normalization_config_entry_count | integer | Number of normalization mappings loaded; 0 if config was missing or empty`
- RC-18 has been added (line 475): "If `normalization_config_entry_count = 0` in the run manifest, H1e, H1f, and H1g findings must not be cited; the run manifest must disclose this."

### M-08: 424B3 removed from extraction scope

**Status: VERIFIED**

- 01-REQUIREMENTS.md US-05 extraction table (line 70) now marks 424B3 explicitly: "424B3 | Not applicable -- 424B3 filings are not discovered in Phase R1 (not in the form_type filter set). 424B3 extraction is deferred to a future phase. | N/A (deferred)"
- 01-REQUIREMENTS.md edge cases table (line 296) includes: "424B3 filing encountered | Not applicable -- 424B3 is not in the Phase R1 discovery form_type set and will not be encountered; 424B3 extraction is deferred to a future phase"
- 02-ARCHITECTURE.md Section 6.5 still contains 424B3 extraction patterns (line 391): "For 424B3: scan the first 2,000 characters (cover page) and any section matching `(?i)distribution` header." This is dead code since 424B3 is not in the discovery set, but it is retained for forward compatibility with a future phase. **Minor inconsistency: the requirements mark 424B3 as deferred/N/A but the architecture still specifies extraction patterns. This is not blocking -- the patterns will never execute in Phase R1 -- but it creates confusion for implementers.** See new inconsistency NI-01 below.

---

### Cross-Document Consistency Checks (New Inconsistencies Introduced by Fixes)

**NI-01: 424B3 extraction spec retained in architecture despite requirements deferral**
- **Severity: LOW**
- 01-REQUIREMENTS.md correctly marks 424B3 as deferred/N/A. But 02-ARCHITECTURE.md Section 6.5 still includes a 424B3 extraction line: "For 424B3: scan the first 2,000 characters (cover page)..." This is dead code in Phase R1 since 424B3 is not in the discovery form_type set. Not blocking, but an implementer reading Section 6.5 might write 424B3 extraction code that can never be reached. Recommend adding a "(Phase R2, deferred)" annotation to the 424B3 line in Section 6.5.

**NI-02: Two-tier coverage table does not mention FLOAT_ILLIQUIDITY correction**
- **Severity: LOW**
- 02-ARCHITECTURE.md Section 9 table (line 712) shows: Full fidelity tier includes "FLOAT_ILLIQUIDITY analysis" in the "Valid claims" column of the Research Contract Section 4.1 (line 242). The Section 9 rationale paragraph (line 719) correctly clarifies that `float_illiquidity` is ADV-based, but the table header at line 712 still says "Scoring: Complete formula" for full fidelity without noting that the partial tier has the same `float_illiquidity` computation available (since it is ADV-based, not float-based). The table correctly identifies the gap as the `dilution_severity component` column, so the table is not wrong, but it could be misleading. The text paragraph overrides the ambiguity.

**NI-03: Roadmap Slice 14 references RC-01 through RC-16 but contract now has 18 criteria**
- **Severity: MEDIUM**
- 04-ROADMAP.md Slice 14 (line 526) says: "Each assertion maps to a numbered Research Contract criterion (RC-01 through RC-16 where testable in code)." But RC-17 and RC-18 have now been added to the Research Contract. Slice 14's test list (lines 530-548) does not include tests for RC-17 or RC-18. RC-17 (corporate action artifact investigation) is an analysis-stage check that may not be programmatically testable against pipeline output alone. RC-18 (normalization_config_entry_count = 0 blocks H1e/H1f/H1g) is programmatically testable: verify the manifest field exists and flag it. The Roadmap should be updated to reference "RC-01 through RC-18" and add an RC-18 test assertion.

**NI-04: RunMetadata dataclass in architecture does not include new manifest fields**
- **Severity: MEDIUM**
- 02-ARCHITECTURE.md Section 5.7 RunMetadata dataclass (lines 253-281) does not include `total_unresolvable_count`, `normalization_config_loaded`, or `normalization_config_entry_count`. These fields were added to the Research Contract's Section 7.2 manifest requirements but the architecture's data structure was not updated. An implementer building from the architecture's dataclass definition would miss these three fields, causing RC-02 validation to fail (missing required manifest fields).

**NI-05: Research Contract Section 4.2 partial tier claims still references "FLOAT_ILLIQUIDITY = 1.0 neutral"**
- **Severity: LOW**
- RESEARCH-CONTRACT.md Section 4.2 (line 252) says: "Rank is computed for 2017-2019 filings and stored in the output, but rank in this tier is based on a partial scorer (FLOAT_ILLIQUIDITY = 1.0 neutral, no dilution severity if float unavailable)." The B-01 fix corrected the architecture to clarify that `float_illiquidity` is an ADV-based ratio (not float-based), so it is never "1.0 neutral" due to missing float data. The partial tier limitation is that `dilution_severity = 0.0` (not that `float_illiquidity` is set to neutral). The Research Contract text should be updated to match: "rank in this tier is based on a partial scorer (`dilution_severity = 0.0` because float unavailable for `shares_offered / float` computation; `float_illiquidity` is unaffected as it uses ADV)."

---

### Summary

| Fix ID | Description | Status |
|--------|-------------|--------|
| B-01 | Scoring formula (FLOAT_ILLIQUIDITY is ADV-based) | VERIFIED |
| B-02 | NULL string mapping | VERIFIED |
| B-03 | Borrow cost (always 0.0) | VERIFIED |
| H-01 | filter_status canonical 9-value set | VERIFIED |
| H-02 | UNRESOLVABLE survivorship bias | VERIFIED |
| H-03 | ADV raw close | VERIFIED |
| H-04 | adjusted_close methodology | VERIFIED |
| H-05 | Underwriter extraction CI | VERIFIED |
| H-06 | Async classify() calling convention | VERIFIED |
| H-07 | dilution_severity patching | VERIFIED |
| M-05 | Normalization config manifest fields | VERIFIED |
| M-08 | 424B3 removed from extraction scope | VERIFIED |
| Cross-check: consistency | 5 new inconsistencies identified | See NI-01 through NI-05 |

**Fixes verified: 12/12** (all BLOCKING and HIGH fixes, plus M-05 and M-08)

**New issues introduced: 5**
- NI-01 (LOW): 424B3 extraction spec retained in architecture despite requirements deferral
- NI-02 (LOW): Two-tier coverage table header slightly misleading but overridden by corrected text
- NI-03 (MEDIUM): Roadmap Slice 14 references RC-01 through RC-16 but contract now has 18 criteria
- NI-04 (MEDIUM): RunMetadata dataclass in architecture missing 3 new manifest fields
- NI-05 (LOW): Research Contract Section 4.2 still references "FLOAT_ILLIQUIDITY = 1.0 neutral"

**Remaining unresolved issues from original QC:**
- M-01, M-02, M-03, M-04, M-06, M-07: These MEDIUM issues were not in the fix scope for this pass. They remain as documented above with their original resolutions.
- L-01 through L-08: LOW issues remain as documented.
- OQ-QC-1 through OQ-QC-5: Open questions remain for human resolution.
- R-QC-1 through R-QC-5: Risks remain as documented.
- NI-03 and NI-04 are new MEDIUM issues that should be addressed before implementation.

**Overall status: NEEDS_CORRECTION** -- All 12 targeted fixes are verified and correctly applied. However, 2 new MEDIUM inconsistencies (NI-03: Roadmap RC count, NI-04: RunMetadata dataclass missing fields) were introduced by independent agents working on different files. These are straightforward to fix (update the Roadmap reference and add three fields to the RunMetadata dataclass) but must be resolved before implementation begins to prevent RC validation failures.

---

*End of QC Review*
