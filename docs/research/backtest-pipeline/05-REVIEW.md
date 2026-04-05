# Spec Review: Backtest Pipeline

**Feature name:** backtest-pipeline
**Review version:** 1.0
**Date:** 2026-04-05
**Author:** @spec-reviewer
**Documents reviewed:**
- `01-REQUIREMENTS.md` (v1.0)
- `02-ARCHITECTURE.md` (v1.0)
- `RESEARCH-CONTRACT.md` (v1.0)
- `04-ROADMAP.md` (v1.0)
- `docs/research/METHODOLOGY.md`
- `docs/research/HYPOTHESIS.md`

---

## PART 1: FUNCTIONAL SPEC REVIEW

---

### 1.1 Requirements Completeness

- [x] Summary is present and clear
- [x] User stories follow "As a... I want... so that..." format
- [x] Every user story has acceptance criteria (AC-01 through AC-10)
- [x] Edge cases table is populated (16 cases)
- [x] Out of scope section is comprehensive (14 items)
- [x] Constraints are concrete and testable
- [x] Hypotheses traceability table links each US to sub-claims
- [x] Output schema defined for both `backtest_results` and `backtest_participants`
- [x] Open questions documented with impact and status

**Assessment:** Requirements are thorough and well-structured. Two inconsistencies identified (see Gaps Table below).

---

### 1.2 Requirements -> Architecture Coverage

| Requirement | Architecture Coverage | Status |
|---|---|---|
| US-01: Filing Discovery | Section 6.1 FilingDiscovery | COVERED |
| US-02: CIK-to-Ticker Resolution | Section 6.2 CIKResolver | COVERED |
| US-03: Filing Text Fetching | Section 6.3 FilingTextFetcher | COVERED |
| US-04: Setup Type Classification | Section 6.4 BacktestClassifier | COVERED |
| US-05: Underwriter Extraction | Section 6.5 UnderwriterExtractor | COVERED |
| US-06: Market Data Join (PIT) | Section 6.7 MarketDataJoiner + Section 7 | COVERED |
| US-07: Six-Filter Application | Section 6.8 BacktestFilterEngine | COVERED |
| US-08: Scoring | Section 6.9 BacktestScorer | COVERED |
| US-09: Outcome Computation | Section 6.10 OutcomeComputer | COVERED |
| US-10: Survivorship Bias Inclusion | Section 8 Survivorship Bias Controls | COVERED |
| US-11: Output Dataset | Section 6.11 OutputWriter + Section 12 | COVERED |

**Assessment:** All requirements have direct architecture coverage. No orphaned requirements.

---

### 1.3 Architecture -> Roadmap Coverage

| Component | Slice | Status |
|---|---|---|
| Shared dataclasses + config | Slice 1 | COVERED |
| `TradingCalendar` | Slice 2 | COVERED |
| `FilingDiscovery` | Slice 3 | COVERED |
| `CIKResolver` | Slice 4 | COVERED |
| `FilingTextFetcher` | Slice 5 | COVERED |
| `BacktestClassifier` | Slice 6 | COVERED |
| `UnderwriterExtractor` | Slice 7 | COVERED |
| `MarketDataJoiner` | Slice 8 | COVERED |
| `BacktestFilterEngine` | Slice 9 | COVERED |
| `BacktestScorer` | Slice 10 | COVERED |
| `OutcomeComputer` | Slice 11 | COVERED |
| `OutputWriter` + `RunManifest` | Slice 12 | COVERED |
| `PipelineOrchestrator` | Slice 13 | COVERED |
| Research Contract validation | Slice 14 | COVERED |
| `underwriter_normalization.json` | Slice 1 (seed) + Slice 7 (consumer) | COVERED |

**Assessment:** All architecture components map to roadmap slices. No component is missing from the roadmap. Dependency chains are correctly represented.

---

### 1.4 Roadmap Quality

- [x] Every architecture component is in a slice
- [x] No circular dependencies (verified: dependency graph is a DAG)
- [x] Each slice has "Done When" criteria
- [x] File paths are concrete
- [x] Tests are enumerated per slice
- [x] Sequence rules are explicit (Section: Sequence Rules)
- [x] Parallel development opportunities called out (Slices 2-7)
- [x] Deferred items clearly separated

**Assessment:** Roadmap is well-structured with 14 slices, correct dependency ordering, and actionable done criteria.

---

## PART 2: RESEARCH VALIDITY REVIEW

---

### 2.1 Look-Ahead Bias Analysis

**Each data join was verified for point-in-time correctness:**

| Join | Method | Look-Ahead Risk | Assessment |
|---|---|---|---|
| Price at T | `trade_date = effective_trade_date` (exact match) | LOW | Correct: uses TradingCalendar-adjusted date |
| Market cap at T | `trade_date = effective_trade_date` (exact match) | LOW | Correct: same PIT date as price |
| ADV at T | 20-day window with `trade_date <= effective_trade_date` | LOW | Correct: bounded above by T |
| Universe membership | `trade_date = effective_trade_date` (exact match) | LOW | Correct: filing-date membership, not run-date |
| Float at T | `trade_date <= filing.date_filed ORDER BY DESC LIMIT 1` (AS-OF) | LOW | Correct: conservative upper bound uses raw filing date |
| Short interest at T | `settlement_date <= filing.date_filed ORDER BY DESC LIMIT 1` (AS-OF) | LOW | Correct: same AS-OF pattern as float |
| Forward prices (outcome) | `trade_date > effective_trade_date` via ROW_NUMBER | LOW | Correct: explicitly forward-looking, isolated to OutcomeComputer |
| Underwriter names | Extracted from filing text (the filing itself) | NONE | No future data involved |

**Canary test sufficiency:** The Research Contract (Section 2.8) defines a canary test that constructs two MarketSnapshot objects with different forward_prices and asserts that BacktestFilterEngine and BacktestScorer produce identical results. This is well-designed and sufficient to catch the most common form of look-ahead contamination (forward returns leaking into scoring). The test is required in three places: per-component tests (Slices 9, 10) and the standalone research contract validation (Slice 14).

**Float AS-OF vs effective_trade_date:** The architecture correctly uses `filing.date_filed` (raw filing date) as the upper bound for the float AS-OF join rather than `effective_trade_date`. This is documented and conservative: if a filing is submitted on Saturday and the prior trading day is Friday, the float AS-OF join uses Saturday as the ceiling, which could potentially pick up a float row from Saturday if one existed (unlikely but technically possible). Since float data is daily and market-hours-only, this distinction is immaterial in practice. No gap.

**UNDERWRITER_FACTOR prohibition:** The circularity prohibition (using backtest outputs as backtest inputs) is explicitly documented in Requirements (Out of Scope), Architecture (Section 6.5 Prohibition), and Research Contract (Section 2.7 Prohibition). This is correct.

**Assessment:** Look-ahead bias controls are thorough and architecturally enforced. No gaps found.

---

### 2.2 Survivorship Bias Analysis

**Universe definition:** Verified that `daily_universe` is used at `effective_trade_date` (point-in-time), not at current date. The Architecture (Section 8) explicitly states inclusion is gated on filing-date membership. The CIKResolver (Section 6.2) queries both active and inactive symbols.

**Delisted tickers:** Explicitly included per Requirements (US-10), Architecture (Section 8), and Research Contract (Section 3). Returns for delisted symbols are NULL with `delisted_before_TN = true`.

**Delisting disclosure threshold:** The Research Contract (Section 3.3) operationalizes the >10% threshold: if `delisted_before_T20 = true` exceeds 10% of the PASSED universe, the finding must disclose this in the white paper abstract and limitations section. This is concrete and verifiable.

**CIKResolver anti-survivorship test:** The Roadmap (Slice 4) includes a test confirming that a known-delisted symbol's CIK resolves successfully and the filing is not excluded due to delisting status.

**Assessment:** Survivorship bias controls are correctly designed and operationalized. No gaps found.

---

### 2.3 Hypothesis Traceability

**Output column -> hypothesis sub-claim mapping:**

| Hypothesis | Required data | Output column(s) | Testable? |
|---|---|---|---|
| H1a: Rank A > Rank B | Return distributions by rank | `rank`, `return_1d/3d/5d/20d`, `float_available` | YES |
| H1b: Setup type predicts | Return distributions by setup type | `setup_type`, `return_1d/3d/5d/20d` | YES |
| H1e: Underwriter identity predicts | Per-firm win rates | `backtest_participants.firm_name` + `return_5d` joined via `accession_number` | YES |
| H1f: Repeat firm concentration | Firm frequency distribution | `backtest_participants.firm_name` counts | YES |
| H1g: Sales agent vs lead UW | Win rates by role | `backtest_participants.role` + `return_5d` | YES |

**No untestable sub-claim was found.** Every hypothesis sub-claim (H1a, H1b, H1e, H1f, H1g) maps to output columns that make it empirically falsifiable.

**Deferred sub-claims (H1c, H1d):** Correctly excluded -- they require teacher labels and student model not yet built. Both are listed in Out of Scope.

**Assessment:** Full traceability. No gaps.

---

### 2.4 Research Contract Completeness

**Sections present:**

| # | Section | Present? | Complete? |
|---|---|---|---|
| 1 | Output Schema Contract | YES | YES -- column types, nullability, valid ranges, NULL semantics, 11 structural integrity checks |
| 2 | Look-Ahead Bias Constraints | YES | YES -- 8 data items analyzed, canary test defined |
| 3 | Survivorship Bias Constraints | YES | YES -- inclusion rule, delisting treatment, disclosure threshold, prohibition |
| 4 | Two-Tier Coverage Rules | YES | YES -- tier definitions, permitted claims per tier, tier mixing prohibition |
| 5 | Underwriter Extraction Validity | YES | YES -- 50-filing human-review sample, 85% accuracy threshold, hallucination limit |
| 6 | Sample Size Thresholds | YES | YES -- per-setup-type, per-firm, aggregate Sharpe, rank comparison, role-level |
| 7 | Reproducibility Requirements | YES | YES -- run ID, manifest fields, determinism, version pinning |
| 8 | Research Validity Acceptance Criteria | YES | YES -- 16 criteria (RC-01 through RC-16) mapped to hypothesis sub-claims |
| 9 | White Paper Citation Standard | YES | YES -- Wilson CI for win rates, Sharpe requirements, statistical significance rules, null result treatment |
| 10 | Contract Versioning | YES | YES -- change control process defined |

**16 acceptance criteria -> hypothesis mapping:** All 16 RC criteria (RC-01 through RC-16) have explicit hypothesis sub-claim mappings. Every hypothesis sub-claim is covered by at least one RC criterion.

**Sample size thresholds:**

| Claim type | Minimum N | Defined? |
|---|---|---|
| Per-setup-type win rate | 30 | YES |
| Per-firm win rate | 20 | YES |
| Aggregate Sharpe ratio | 100 | YES |
| Rank comparison (H1a) | 30 per rank | YES |
| Role-level comparison (H1g) | 20 per role | YES |

**Assessment:** The Research Contract is comprehensive. All 9+ required sections are present and substantive.

---

### 2.5 Methodology Alignment

| METHODOLOGY.md Standard | Pipeline Design Alignment | Status |
|---|---|---|
| Rule 1: No cherry-picking | Pipeline processes ALL filings in date range; below-threshold results flagged not omitted (RC Section 6.6) | ALIGNED |
| Rule 2: Honest about sample size | Minimum N thresholds defined per claim type; below-threshold flagging required | ALIGNED |
| Rule 3: Financial metrics primary | Output schema includes return columns for win rate, Sharpe computation | ALIGNED |
| Rule 4: Document failures | RC-11 requires null results documented with same detail as confirmations; RC Section 9.5 reiterates | ALIGNED |
| Rule 5: Separate signal from noise | Filter status tracks "filter fires" vs "price moves"; both captured in output | ALIGNED |
| Rule 6: Reproducible | Determinism requirement, run_id, SHA-256 hash, version pinning | ALIGNED |

**Null result handling:** Explicitly required at three levels: (1) METHODOLOGY.md Rule 4, (2) RC-11 in acceptance checklist, (3) RC Section 9.5 in white paper citation standard. Null results cannot be silently omitted.

**Reproducibility:** Byte-for-byte determinism is enforced via sorted output, fixed processed_at, Snappy compression, explicit pyarrow schema, and SHA-256 verification. This exceeds METHODOLOGY.md Rule 6.

**Assessment:** Pipeline design is fully consistent with METHODOLOGY.md standards. No gaps.

---

## GAPS TABLE

| Gap ID | Severity | Document | Description | Resolution |
|---|---|---|---|---|
| G-01 | HIGH | 01-REQUIREMENTS.md | `filter_status` is listed as **nullable** (YES) in the output schema, but it is described as always populated with one of five values. The Research Contract correctly marks it as **non-nullable** (NO) with seven valid values including `NOT_IN_UNIVERSE` and `PIPELINE_ERROR`. The requirements must align to non-nullable and include all seven valid values. | Update 01-REQUIREMENTS.md output schema: set `filter_status` nullable to `NO` and add `NOT_IN_UNIVERSE` and `PIPELINE_ERROR` to the allowed values set. |
| G-02 | MEDIUM | 01-REQUIREMENTS.md vs 02-ARCHITECTURE.md | The BacktestRow dataclass in 02-ARCHITECTURE.md Section 5.6 lists `filter_status` with five values (`PASSED`, `FILTERED_OUT`, `UNRESOLVABLE`, `FETCH_FAILED`, `NO_MATCH`) but the architecture's own error handling table (Section 13) adds `PIPELINE_ERROR`, and the filter engine spec (Section 6.8) returns `NOT_IN_UNIVERSE`. The BacktestRow dataclass definition should list all seven values for completeness. | Update BacktestRow comment in 02-ARCHITECTURE.md Section 5.6 to enumerate all seven valid filter_status values. |
| G-03 | MEDIUM | 02-ARCHITECTURE.md vs RESEARCH-CONTRACT.md | The `RunMetadata` dataclass in 02-ARCHITECTURE.md Section 5.7 has 17 fields. The Research Contract Section 7.2 requires 24 fields (adds `scoring_formula_version`, `float_data_start`, `market_data_db_path`, `market_data_db_certification`, `execution_timestamp`, `canary_no_lookahead`, and `classifier_version`). Since the Research Contract is the validity gate, the architecture's RunMetadata must include all 24 fields or the RC validation tests will fail. | Update `RunMetadata` dataclass in 02-ARCHITECTURE.md to include all fields required by Research Contract Section 7.2. |
| G-04 | LOW | 01-REQUIREMENTS.md | AC-01 states "all 32 quarterly master.gz files (2017 Q1 through 2025 Q4)." 2017 Q1 through 2025 Q4 is 9 years x 4 quarters = 36 quarterly files, not 32. If the intended range starts at 2017 Q1, the count is 36. If 32 quarters was intentional, the start date would need to be 2018 Q1 (8 years x 4 = 32). | Correct the count in AC-01 to 36 (covering 2017 Q1 through 2025 Q4) to match the stated date range of 2017-01-01 to 2025-12-31. |
| G-05 | LOW | 01-REQUIREMENTS.md vs 02-ARCHITECTURE.md | Requirements US-06 table says float join key is `(symbol, AS-OF filed_at)`. Architecture Section 6.7 uses `trade_date <= filing.date_filed` for the AS-OF ceiling. These are consistent, but requirements US-06 also says "Use most recent row with date <= filed_at" for float while using `filed_at date` (trading-day-adjusted) for price. The architecture clarifies that float uses the raw filing date while price uses the calendar-adjusted date. This asymmetry is intentional and conservative but is not explained in 01-REQUIREMENTS.md. | Add a note to US-06 in 01-REQUIREMENTS.md clarifying that the float and short interest AS-OF joins use the raw filing date as the ceiling, while daily snapshots (price, market cap, universe) use the trading-day-adjusted date. This matches the architecture and is the correct conservative approach. |
| G-06 | LOW | 04-ROADMAP.md | Slice 12 mentions writing `backtest_participants.parquet` and `backtest_participants.csv`, but 01-REQUIREMENTS.md AC-10 and US-11 only mention `backtest_results.parquet`, `backtest_results.csv`, and `backtest_run_metadata.json`. The participants output files are implied by the schema definition but not explicitly listed in the acceptance criteria. | Add participants output files (`backtest_participants.parquet` and `backtest_participants.csv`) to the output file list in US-11 and AC-10 in 01-REQUIREMENTS.md. |
| G-07 | LOW | 02-ARCHITECTURE.md | Section 5.7 header contains a typo: "backtrack_run_metadata.json" should be "backtest_run_metadata.json". | Fix the typo in the Section 5.7 header. |

---

## RISKS

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| R-01: OQ-1 (historical_float / short_interest schemas) resolved in architecture but not yet confirmed by live inspection of market_data.duckdb | LOW (architect states "confirmed") | HIGH if wrong (scoring and float filter would fail) | First action in Slice 2 or Slice 8: run `DESCRIBE historical_float` and `DESCRIBE short_interest` against the real DB and confirm column names match the architecture. |
| R-02: Memory pressure for full 2017-2025 run (~200K-500K rows in memory) | LOW | MEDIUM (pipeline may OOM on constrained machines) | Architecture estimates ~2GB peak. Monitor during first full run. If needed, implement a chunked write strategy in OutputWriter. |
| R-03: SEC rate-limit enforcement or temporary blocks during 5-6 hour fetch phase | MEDIUM | MEDIUM (incomplete filing corpus) | Mitigated by disk caching + resume; incomplete quarters logged in run manifest; re-run with --resume. |
| R-04: Underwriter extraction accuracy below 85% threshold | MEDIUM | HIGH (blocks H1e, H1f, H1g findings) | Mitigated by the 50-filing human-review validation gate (RC-10). Discovery of low accuracy triggers code revision before findings are accepted. |
| R-05: Insufficient sample size for certain setup types or underwriter firms | MEDIUM | MEDIUM (some sub-claims cannot be made) | Mitigated by sample size thresholds in Research Contract Section 6. Below-threshold results are flagged, not omitted. The pipeline design accommodates this explicitly. |
| R-06: 2017-2019 data has limited analytical value due to missing float | LOW | LOW (partial tier is documented and claims are constrained) | Mitigated by two-tier coverage design. H1a claims require `float_available = true`. Partial tier data adds volume context for H1b directional signal analysis only. |

---

## ASSUMPTIONS

| Assumption | Impact if Wrong |
|---|---|
| `market_data.duckdb` at `/home/d-tuned/market_data/duckdb/market_data.duckdb` is the certified v1.0.0 dataset (2026-02-19) | Pipeline joins would produce incorrect results. Mitigated by startup check that verifies the DB exists and daily_universe is non-empty. |
| `historical_float` and `short_interest` tables exist in `market_data.duckdb` with the schemas documented in 02-ARCHITECTURE.md OQ-1 resolution | Slices 8, 9, 10 would fail at build time. Discovery is early (Slice 8 implementation). |
| `RuleBasedClassifier.classify()` API signature is stable and importable from `research/` package | Slice 6 would fail if the import path or method signature changed. Mitigated by integration test in Slice 6. |
| `Scorer.score()` static method API is stable and accepts the BacktestMarketData adapter | Slice 10 would fail if the Scorer API changed. Mitigated by integration test in Slice 10. |
| Underwriter normalization config file will be provided by researcher before full pipeline run | UnderwriterExtractor degrades gracefully (all names stored as is_normalized=False). Quality of H1e/H1f/H1g findings depends on normalization quality. |
| US market trading calendar is derivable from `daily_prices` gaps (no external calendar file needed) | If `daily_prices` has unexpected gaps (missing trading days), TradingCalendar would misidentify trading days. Mitigated by the no-weekends invariant assertion in Slice 2 tests. |

---

## OPEN QUESTIONS

| Question | Status | Resolution Needed From |
|---|---|---|
| OQ-1 (from 01-REQUIREMENTS.md): Exact schemas of `historical_float` and `short_interest` | RESOLVED in 02-ARCHITECTURE.md Section 16 | Confirm by live inspection at Slice 8 build time |
| OQ-2 (from 01-REQUIREMENTS.md): Read-only vs copy of market_data.duckdb | RESOLVED in 02-ARCHITECTURE.md Section 16 | Read-only connection confirmed |
| OQ-3 (from 01-REQUIREMENTS.md): Wall-clock runtime budget | RESOLVED in 02-ARCHITECTURE.md Section 16 | ~7-8 hours first run; ~1-2 hours cached re-run |
| OQ-4 (from 01-REQUIREMENTS.md): Who provides the normalization table seed list | RESOLVED in 02-ARCHITECTURE.md Section 16 | Researcher provides; extractor fails gracefully if missing |

All four open questions from Requirements are resolved in the Architecture document. No new unresolved questions were generated during review.

---

## APPROVAL CHECKLIST

### Requirements (01-REQUIREMENTS.md)
- [ ] Reviewed by human
- [x] Acceptance criteria are testable (all 10 ACs are concrete and verifiable)
- [x] Out of scope is comprehensive
- [ ] G-01 resolved: `filter_status` nullability and value set corrected
- [x] G-04 resolved: quarterly file count corrected from 32 to 36
- [x] G-05 resolved: AS-OF join ceiling clarification added
- [x] G-06 resolved: participants output files added to AC-10 and US-11

### Architecture (02-ARCHITECTURE.md)
- [ ] Reviewed by human
- [x] Patterns are appropriate (documented in Section 17)
- [x] Schemas are concrete Python dataclasses (not pseudocode)
- [x] All SQL queries specified with exact syntax
- [x] Integration points documented (Section 15)
- [x] All open questions resolved (Section 16)
- [x] G-02 resolved: BacktestRow filter_status values updated (see re-review note below)
- [ ] G-03 resolved: RunMetadata fields synchronized with Research Contract
- [x] G-07 resolved: typo and stale count fixed

### Research Contract (RESEARCH-CONTRACT.md)
- [ ] Reviewed by human
- [x] All 9+ sections present and substantive
- [x] 16 acceptance criteria mapped to hypothesis sub-claims
- [x] Sample size thresholds defined for all claim types
- [x] Look-ahead and survivorship bias controls operationalized
- [x] White paper citation standards defined
- [x] Null result handling explicitly required

### Roadmap (04-ROADMAP.md)
- [ ] Reviewed by human
- [x] All architecture components covered
- [x] Dependency sequence is correct (DAG verified)
- [x] Slice sizing is appropriate (14 slices, each focused on one component)
- [x] Tests enumerated per slice
- [x] Done-when criteria are actionable

### Research Validity
- [x] Look-ahead bias: all data joins verified for PIT correctness
- [x] Survivorship bias: delisted symbols included; disclosure threshold operationalized
- [x] Hypothesis traceability: all sub-claims testable from output schema
- [x] Methodology alignment: all 6 standards of evidence addressed
- [x] Null result handling: explicitly required at three levels

### Overall
- [ ] All gaps resolved (7 gaps: 0 CRITICAL, 1 HIGH, 2 MEDIUM, 4 LOW)
- [ ] Ready for implementation after gap resolutions

---

## SUMMARY

**Functional review:** The four spec documents (Requirements, Architecture, Research Contract, Roadmap) are internally consistent and mutually reinforcing. The architecture fully covers all requirements, and the roadmap covers all architecture components. Seven gaps were found, all resolvable without scope changes.

**Research validity review:** The pipeline design is methodologically sound. Look-ahead bias is prevented by point-in-time joins with canary tests. Survivorship bias is prevented by filing-date universe inclusion with delisting disclosure thresholds. All hypothesis sub-claims are traceable to output columns. The Research Contract is comprehensive, with 16 acceptance criteria, sample size thresholds for every claim type, a two-tier coverage system for the 2017-2019 float data gap, and explicit null result requirements. The design is consistent with METHODOLOGY.md standards of evidence.

**Blocking issues:** None. The single HIGH gap (G-01: filter_status nullability and value set mismatch) does not block implementation since the Research Contract already has the correct definition and the architecture already uses all seven values. It is a documentation alignment issue, not a design flaw.

---

*End of Review*

---

## Re-review: Direct Fixes (2026-04-05)

Reviewer: @research-spec-reviewer
Scope: Verification of fixes G-02, G-05, G-06, G-07

---

### Fix 1 -- G-02: BacktestRow.filter_status values in 02-ARCHITECTURE.md

**Status: VERIFIED with observation**

The BacktestRow dataclass comment (Section 5.6, line 222) now reads:

```
filter_status: str  # "PASSED", "FORM_TYPE_FAIL", "MARKET_CAP_FAIL", "FLOAT_FAIL", "DILUTION_FAIL", "NOT_IN_UNIVERSE", "PIPELINE_ERROR", "UNRESOLVABLE", "FETCH_FAILED"
```

**Cross-reference checks:**

1. **vs. 01-REQUIREMENTS.md output schema (line 244):** Requirements lists 7 values: `PASSED, FORM_TYPE_FAIL, MARKET_CAP_FAIL, FLOAT_FAIL, DILUTION_FAIL, NOT_IN_UNIVERSE, PIPELINE_ERROR`. The architecture now lists 9 values, adding `UNRESOLVABLE` and `FETCH_FAILED`. These two additional values are architecturally legitimate -- they represent rows where CIK resolution failed or filing text could not be fetched, which are real pipeline states that produce output rows. However, the requirements output schema does not include them. This is a pre-existing discrepancy (requirements were under-specified on non-filter pipeline states) and is tracked as part of the still-open G-01 gap. The fix to G-02 did not introduce this inconsistency; it surfaced it by making the architecture more explicit.

2. **vs. Section 13 error table:** The error table (line 734) uses `filter_status = "UNRESOLVABLE"` for CIK failures and `filter_status = "PIPELINE_ERROR"` for unexpected exceptions -- both now present in BacktestRow. However, the error table (line 735) says `filter_status = "FILTERED_OUT"` for NOT_IN_UNIVERSE, while Section 6.8 (line 549) says `filter_status = "NOT_IN_UNIVERSE"` for the same case. This is a pre-existing internal inconsistency within the architecture (Section 13 vs. Section 6.8), not introduced by this fix.

3. **vs. Section 6.8 filter engine:** Section 6.8 returns `NOT_IN_UNIVERSE` (line 549) and the various `*_FAIL` values via filter criteria. All are now in BacktestRow. Consistent.

4. **Previously listed values now removed:** The old values `FILTERED_OUT`, `NO_MATCH` are no longer in the BacktestRow comment. `NO_MATCH` is correctly a `classification_status` (per AC-04), not a `filter_status`. `FILTERED_OUT` was a vague catch-all replaced by specific fail reasons. Both removals are correct.

**Verdict:** The fix is correct. The BacktestRow comment now lists all 9 valid filter_status values that appear in the architecture's component specifications and error table. The observation about the requirements schema having only 7 values is part of the still-open G-01 gap and does not block this fix.

---

### Fix 2 -- G-05: AS-OF join ceiling clarification in 01-REQUIREMENTS.md US-06

**Status: VERIFIED**

The note added after the US-06 joins table (line 92) reads:

> **Note on join ceiling asymmetry:** Daily snapshot joins (universe, price, market cap) use the trading-day-adjusted date (i.e., if filing date is a weekend or holiday, roll back to the prior trading day). AS-OF joins (float, short interest) use the raw `filed_at` date as the ceiling -- these tables are not trading-day-constrained, so rolling back would incorrectly exclude same-day data. This asymmetry is intentional and conservative.

**Cross-reference checks:**

1. **vs. 02-ARCHITECTURE.md Section 6.7 MarketDataJoiner:** Architecture line 451 states "All joins use `effective_trade_date`" but then the float AS-OF query (lines 492-499) uses `trade_date <= ?` where the `?` is `filing.date_filed` (raw), not `effective_trade_date`. This is confirmed by Section 7 (Look-Ahead Bias Controls, lines 657-658) which explicitly shows float uses `filing.date_filed` and short interest uses `filing.date_filed`, while price/market_cap/universe use `effective_trade_date`. The note accurately describes this behavior.

2. **vs. other statements in 01-REQUIREMENTS.md:** The US-06 joins table (lines 84-90) already describes the same asymmetry in different terms: daily snapshots say "if market is closed, use the prior trading day" while float and short interest say "Use most recent row with date <= filed_at." The note makes the distinction explicit without contradicting the table.

3. **Placement:** The note is placed immediately after the joins table in US-06, which is the correct location for discoverability.

**Verdict:** The fix is correct, complete, and introduces no new inconsistencies.

---

### Fix 3 -- G-06: backtest_participants output files in AC-10 and US-11

**Status: VERIFIED**

**US-11 (lines 149-154):** Now explicitly lists all four output files:
- `docs/research/data/backtest_results.parquet` (with companion CSV)
- `docs/research/data/backtest_participants.parquet` (with companion CSV)

**AC-10 (line 219):** Now reads: "...then `docs/research/data/backtest_results.parquet`, `docs/research/data/backtest_results.csv`, `docs/research/data/backtest_participants.parquet`, and `docs/research/data/backtest_participants.csv` are all created with the schemas defined below."

**Cross-reference checks:**

1. **Participants schema table (line 269):** The `Table: backtest_participants` schema definition is still present and unchanged. The five columns (`accession_number`, `firm_name`, `role`, `is_normalized`, `raw_text_snippet`) are fully defined.

2. **Constraint reference (line 333):** The constraint "Must: All backtest_participants rows include the source filing's accession_number" is consistent with the schema.

3. **Architecture OutputWriter (Section 6.11, line 616):** Says "Write `backtest_participants.parquet` and `backtest_participants.csv` alongside the main output." Consistent with the requirements update.

4. **Architecture directory structure (Section 4, lines 116-119):** The output file tree still only lists 3 files (backtest_results.parquet, backtest_results.csv, backtest_run_metadata.json) and does not include participants files. This is a pre-existing omission in the architecture that was not part of the G-06 fix scope (G-06 targeted the requirements). It does not block implementation since the OutputWriter spec (Section 6.11) explicitly includes them.

**Verdict:** The fix is correct and complete. US-11 and AC-10 now cover all four output files. No orphaned references.

---

### Fix 4 -- G-07: Typo and stale count in 02-ARCHITECTURE.md

**Status: VERIFIED**

**Typo fix -- Section 5.7 header (line 248):** Now reads `### 5.7 Output: RunMetadata (backtest_run_metadata.json)`. The typo "backtrack" has been corrected to "backtest".

**Count fix -- FilingDiscovery (line 300):** Now reads "(36 total for 2017-2025)". Previously said "32 total."

**Cross-reference checks for filename consistency:**

1. **System context diagram (line 56):** `docs/research/data/backtest_run_metadata.json` -- correct.
2. **Directory structure (line 119):** `backtest_run_metadata.json` -- correct.
3. **Section 5.7 header (line 248):** `backtest_run_metadata.json` -- correct (the fix).
4. **OutputWriter (line 606):** `docs/research/data/backtest_run_metadata.json` -- correct.
5. **Section 12 Reproducibility Design (line 717):** `backtest_run_metadata.json` -- correct.

All five references to the metadata filename in 02-ARCHITECTURE.md are consistent.

**Cross-reference check for "36" count:**

1. **01-REQUIREMENTS.md AC-01 (line 162):** "all 36 quarterly master.gz files (2017 Q1 through 2025 Q4)" -- consistent.
2. **02-ARCHITECTURE.md Section 6.1 (line 300):** "36 total for 2017-2025" -- consistent.
3. **Arithmetic verification:** 2017 through 2025 inclusive = 9 years. 9 years x 4 quarters = 36. Correct.

**Verdict:** The fix is correct and complete. No residual typos or stale counts found.

---

### Summary of Re-review

| Fix | Gap | Status | Notes |
|---|---|---|---|
| Fix 1 | G-02 | VERIFIED | BacktestRow now lists 9 values (superset of requirements' 7); the delta is part of still-open G-01 |
| Fix 2 | G-05 | VERIFIED | Note accurately describes architecture behavior; well-placed |
| Fix 3 | G-06 | VERIFIED | All four output files now in US-11 and AC-10; schema table intact |
| Fix 4 | G-07 | VERIFIED | Typo fixed; count corrected to 36; all 5 filename references consistent |

### Pre-existing Issues Observed (Not Introduced by Fixes)

| Issue | Location | Severity | Notes |
|---|---|---|---|
| Section 13 line 735 says `filter_status = "FILTERED_OUT"` for NOT_IN_UNIVERSE; Section 6.8 line 549 says `filter_status = "NOT_IN_UNIVERSE"` | 02-ARCHITECTURE.md | LOW | Internal inconsistency; Section 6.8 is authoritative since it defines the component behavior |
| Architecture Section 4 directory tree omits `backtest_participants.parquet` and `backtest_participants.csv` | 02-ARCHITECTURE.md line 116-119 | LOW | OutputWriter spec (Section 6.11 line 616) correctly includes them; tree is illustrative |
| 01-REQUIREMENTS.md filter_status enum has 7 values; BacktestRow has 9 (adds UNRESOLVABLE, FETCH_FAILED) | 01-REQUIREMENTS.md line 244 vs 02-ARCHITECTURE.md line 222 | Covered by G-01 | G-01 (HIGH) remains open and should address the full value set alignment |

### Approval Checklist Items Updated

The following checklist items in the Approval Checklist above have been checked off based on this re-review:
- G-02: checked (BacktestRow filter_status values updated)
- G-04: checked (was already fixed in prior round)
- G-05: checked (AS-OF join ceiling clarification added)
- G-06: checked (participants output files added to AC-10 and US-11)
- G-07: checked (typo and stale count fixed)

### Remaining Open Gaps

| Gap ID | Status |
|---|---|
| G-01 (HIGH) | OPEN -- filter_status nullability and full value set alignment in 01-REQUIREMENTS.md |
| G-03 (MEDIUM) | OPEN -- RunMetadata fields not yet synchronized with Research Contract |
