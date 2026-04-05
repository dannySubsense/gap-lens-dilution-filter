# Spec Review: dilution-short-filter

- **Project**: gap-lens-dilution-filter
- **Phase**: Phase 1 (Rule-Based Pipeline)
- **Review Date**: 2026-04-05
- **Review Pass**: Final (second review)
- **Reviewer**: @spec-reviewer
- **Documents Reviewed**:
  - 01-REQUIREMENTS.md
  - 02-ARCHITECTURE.md
  - 03-UI-SPEC.md
  - 04-ROADMAP.md

---

## Overall Assessment: APPROVED

The four-document spec set is comprehensive, well-structured, and ready for implementation. All five previously identified issues (C-01, C-02, G-01, G-02, G-03) from the first review have been resolved:

- C-01: TypeScript `SignalDetailResponse` now includes `ticker: string` and `entity_name: string | null` (Architecture Section 7, line 849-850).
- C-02: Roadmap Slice 6 now correctly states `TickerResolver.refresh()` is called from the FastAPI lifespan handler, not from `init_db()`.
- G-01: The "Surface UNRESOLVABLE count in the health endpoint" statement has been removed from Architecture Section 3.2 (human decision: DuckDB/logs only).
- G-02: Roadmap Slice 3 now explicitly includes `adv_min_threshold: float = 500_000` in its config field list.
- G-03: Roadmap Slice 3 `edgar_efts_url` default is now the base URL only, without template parameters.

Cross-document alignment is strong across the scoring formula, filter criteria, classifier rules, config variables, and data flow. The architecture faithfully implements all 16 user stories, the UI spec covers every user-facing requirement, and the roadmap covers every file in the architecture tree with clear slice boundaries and done-when criteria. No blocking contradictions, gaps, or open questions remain.

**Summary Counts**:
- Blocking contradictions: 0
- Blocking gaps: 0
- Non-blocking notes: 3 (informational only -- do not block implementation)
- Open questions: 1 (deferred to operational monitoring -- does not block implementation)
- Risks: 6

---

## 1. Contradictions

None. All previously identified contradictions (C-01, C-02) have been resolved.

---

## 2. Non-Blocking Notes

The following are informational observations. None require changes before implementation begins.

| ID | Description | Documents | Recommendation |
|----|-------------|-----------|----------------|
| N-01 | **Roadmap Slice 3 `edgar_efts_url` omits the `forms=` parameter that is present in Architecture Section 9 config code block.** Architecture Section 9 code block (line 1021-1023) defines the default as `"https://efts.sec.gov/LATEST/search-index?forms=S-1,S-1%2FA,S-3,424B2,424B4,8-K,13D%2FA"` (includes static `forms` parameter). Roadmap Slice 3 defines it as `"https://efts.sec.gov/LATEST/search-index"` (base URL only, with a note that `forms`, `startdt`, `enddt`, `from` are all appended at runtime). Either approach is valid. During implementation, follow the Architecture code block (include `forms=` in the config default, append only `startdt/enddt/from` at runtime) as the canonical reference, since the forms list is static configuration. | 02-ARCHITECTURE (Section 9 code block), 04-ROADMAP (Slice 3) | Implementers should use the Architecture Section 9 code block as the canonical config definition. The Roadmap note is a simplification that does not affect correctness either way. |
| N-02 | **Roadmap Slice 2 implementation notes enumerate "all five tables: filings, filter_results, market_data, labels, signals. Plus poll_state" (6 tables) but omit `cik_ticker_map` from the prose list.** The done-when criterion correctly expects 7 tables (including `cik_ticker_map`), and the note says "Full DDL is specified verbatim in Section 6 of 02-ARCHITECTURE.md; copy it exactly." Since the DDL and done-when are both correct, implementers will create all 7 tables. | 04-ROADMAP (Slice 2) | No action needed. The DDL reference and done-when criteria are correct. |
| N-03 | **Requirements `filings` table high-level schema does not include `entity_name` column.** The Architecture DDL (Section 6) and EFTS response parsing (Section 3.1) include `entity_name` on the `filings` table. The Requirements Data Requirements section does not list it. Architecture DDL is the authoritative schema reference. | 01-REQUIREMENTS (Data Requirements), 02-ARCHITECTURE (Section 6) | No action needed. Architecture DDL is authoritative for implementation. |

---

## 3. Scoring Formula Consistency

### Requirements (01-REQUIREMENTS.md, AC-04):

```
SCORE = (DILUTION_SEVERITY x FLOAT_ILLIQUIDITY x SETUP_QUALITY) / BORROW_COST
FLOAT_ILLIQUIDITY = settings.adv_min_threshold / fmp_data.adv_dollar
```

Normalization: "The raw SCORE value is normalized to a 0-100 integer scale before assignment of rank."

### Architecture (02-ARCHITECTURE.md, Section 3.6):

```
DILUTION_SEVERITY  = classification_result["dilution_severity"]
FLOAT_ILLIQUIDITY  = settings.adv_min_threshold / fmp_data.adv_dollar
SETUP_QUALITY      = settings.setup_quality[setup_type]
BORROW_COST        = borrow_cost (default settings.default_borrow_cost = 0.30)

raw_score = (DILUTION_SEVERITY * FLOAT_ILLIQUIDITY * SETUP_QUALITY) / BORROW_COST
normalized_score = clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)
```

Worked example: `(0.50 * 0.83 * 0.65) / 0.30 = 0.90` -> `clamp(int(0.90 / 1.0 * 100), 0, 100) = 90`

### Roadmap (04-ROADMAP.md, Slice 10):

```python
DILUTION_SEVERITY  = classification["dilution_severity"]
FLOAT_ILLIQUIDITY  = settings.adv_min_threshold / fmp_data.adv_dollar
SETUP_QUALITY      = settings.setup_quality[classification["setup_type"]]
raw_score = (DILUTION_SEVERITY * FLOAT_ILLIQUIDITY * SETUP_QUALITY) / borrow_cost
score = clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)
```

**Verdict: All three documents are consistent.** The FLOAT_ILLIQUIDITY formula is `settings.adv_min_threshold / fmp_data.adv_dollar` in all three. The normalization formula is `clamp(int(raw_score / settings.score_normalization_ceiling * 100), 0, 100)` in both Architecture and Roadmap. The Requirements describes normalization narratively and does not contradict the formula. Rank thresholds (A > 80, B 60-80, C 40-59, D < 40) are identical across all documents.

---

## 4. Setup Type E / 13D/A Reachability

Tracing 13D/A through the full pipeline:

| Checkpoint | Document | 13D/A Present? | Evidence |
|------------|----------|----------------|----------|
| EDGAR EFTS URL forms parameter | 01-REQUIREMENTS (Integration), 02-ARCHITECTURE (Section 3.1, Section 9) | Yes | `forms=...13D%2FA` in the URL |
| Filter 1 allowed form types | 01-REQUIREMENTS (AC-02), 02-ARCHITECTURE (Section 3.4 filter table) | Yes | AC-02: "filings of types S-1, S-1/A, S-3, 424B2, 424B4, 8-K, and 13D/A"; Architecture filter table: "S-1/S-1A/S-3/424B2/424B4/8-K/13D/A" |
| Classifier rule table (Setup E) | 01-REQUIREMENTS (AC-03), 02-ARCHITECTURE (Section 3.5.3) | Yes | AC-03: "form type 13D/A or S-1 containing keywords 'cashless exercise' or 'warrant'"; Architecture: "E | 13D/A, S-1 | 'cashless exercise' OR 'warrant'" |
| Roadmap Slice 8 (Filter Engine) | 04-ROADMAP (Slice 8) | Yes (by reference) | Slice 8 references "from requirements AC-02" which includes 13D/A |
| Roadmap Slice 9 (Classifier) | 04-ROADMAP (Slice 9) | Yes (by reference) | Slice 9 references "Rules applied in precedence order A > E > B > C > D (spec Section 3.5.3)" |

**Verdict: Setup Type E for 13D/A filings is fully reachable end-to-end.** 13D/A appears consistently in the EFTS URL, Filter 1 allowed form types, classifier rules, and Roadmap slice references.

---

## 5. Config Variable Coverage

Cross-check of Architecture Section 9 config variables against Roadmap Slice 3.

| Config Variable (Architecture Section 9) | Listed in Roadmap Slice 3 | Status |
|------------------------------------------|--------------------------|--------|
| `FMP_API_KEY` | Noted as "likely already exists" | COVERED (pre-existing) |
| `ASKEDGAR_API_KEY` | Not listed (pre-existing) | COVERED (pre-existing) |
| `CLASSIFIER_NAME` | Yes (`classifier_name`) | COVERED |
| `EDGAR_POLL_INTERVAL` | Yes (`edgar_poll_interval`) | COVERED |
| `EDGAR_EFTS_URL` | Yes (`edgar_efts_url`) | COVERED (see N-01 for default value note) |
| `DUCKDB_PATH` | Yes (`duckdb_path`) | COVERED |
| `FILING_TEXT_MAX_BYTES` | Yes (`filing_text_max_bytes`) | COVERED |
| `DEFAULT_BORROW_COST` | Yes (`default_borrow_cost`) | COVERED |
| `ADV_MIN_THRESHOLD` | Yes (`adv_min_threshold`) | COVERED |
| `SCORE_NORMALIZATION_CEILING` | Yes (`score_normalization_ceiling`) | COVERED |
| `SETUP_QUALITY_A` through `_E` | Yes (referenced as range + `setup_quality` computed property) | COVERED |
| `LIFECYCLE_CHECK_INTERVAL` | Yes (`lifecycle_check_interval`) | COVERED |
| `IBKR_BORROW_COST_ENABLED` | Yes (`ibkr_borrow_cost_enabled`) | COVERED |
| `NEXT_PUBLIC_REFRESH_INTERVAL_MS` | Not in Slice 3 (frontend env var; referenced in Slice 15) | COVERED (frontend scope) |

All config variables are accounted for. The previous gap (G-02, `ADV_MIN_THRESHOLD` omitted from Slice 3) has been resolved.

---

## 6. Requirement-to-Architecture Coverage

Every user story (US-01 through US-16) and its acceptance criteria are covered by architecture components.

| User Story | Architecture Coverage | Status |
|------------|----------------------|--------|
| US-01: EDGAR Filing Ingestion | EdgarPoller (Section 3.1), poll_state table, filings table | COVERED |
| US-02: Filing Filter | FilterEngine (Section 3.4), filter_results table, FMPClient (Section 3.3) | COVERED |
| US-03: Setup Classification | ClassifierProtocol + RuleBasedClassifier (Section 3.5), labels table | COVERED |
| US-04: Short Attractiveness Scoring | Scorer (Section 3.6), labels.short_attractiveness, labels.rank | COVERED |
| US-05: Rank-A Alert | SignalManager (Section 3.7), signals table with status=LIVE | COVERED |
| US-06: Watchlist Visibility | SignalManager (Section 3.7), signals table with status=WATCHLIST | COVERED |
| US-07: Dashboard Overview | API Routes (Section 5), Frontend hierarchy (Section 7), LiveNowPanel, WatchlistPanel, RecentClosedPanel | COVERED |
| US-08: Setup Detail View | GET /signals/{id} route, SignalDetailResponse, SetupDetailModal | COVERED |
| US-09: Position Tracking | POST /signals/{id}/position, PositionRequest, SignalManager.record_position() | COVERED |
| US-10: Setup Lifecycle Management | SignalManager.run_lifecycle_loop() (Section 3.7), hold_time mapping | COVERED |
| US-11: Alert Type Differentiation | signals.alert_type column (NEW_SETUP, SETUP_UPDATE, TIME_EXCEEDED), SETUP_UPDATE detection logic | COVERED |
| US-12: Market Data Enrichment | FMPClient (Section 3.3), market_data table | COVERED |
| US-13: AskEdgar Enrichment | DilutionService (Section 3.8), askedgar_partial flag, PARTIAL data_source | COVERED |
| US-14: Classifier Abstraction | ClassifierProtocol (Section 4), get_classifier factory (Section 3.5.2) | COVERED |
| US-15: Training Data Logging | filings.filing_text, labels table with classifier_version, market_data snapshots, Phase 2 export query (Section 10.2) | COVERED |
| US-16: Polling Health Visibility | GET /health route, HealthResponse, HealthBar component | COVERED |

All 16 user stories and their acceptance criteria have corresponding architecture components.

---

## 7. Architecture-to-Roadmap Coverage

Every file listed in Architecture Section 2 (Directory Structure) appears in at least one roadmap slice.

| Architecture File | Roadmap Slice | Status |
|-------------------|---------------|--------|
| `.env` | Slice 1 | COVERED |
| `requirements.txt` | Slice 1 (copy), Slice 3 (extend) | COVERED |
| `app/__init__.py` | Slice 1 | COVERED |
| `app/main.py` | Slice 12 (create), Slice 13 (modify) | COVERED |
| `app/core/__init__.py` | Slice 1 | COVERED |
| `app/core/config.py` | Slice 1 (copy), Slice 3 (extend) | COVERED |
| `app/api/v1/__init__.py` | Slice 13 | COVERED |
| `app/api/v1/routes.py` | Slice 13 | COVERED |
| `app/models/__init__.py` | Slice 1 | COVERED |
| `app/models/responses.py` | Slice 1 | COVERED |
| `app/models/signals.py` | Slice 4 | COVERED |
| `app/services/__init__.py` | Slice 1 | COVERED |
| `app/services/dilution.py` | Slice 1 (copy, never modified) | COVERED |
| `app/services/edgar_poller.py` | Slice 7 (create), Slice 12 (modify) | COVERED |
| `app/services/filing_fetcher.py` | Slice 6 | COVERED |
| `app/services/filter_engine.py` | Slice 8 | COVERED |
| `app/services/fmp_client.py` | Slice 5 | COVERED |
| `app/services/scorer.py` | Slice 10 | COVERED |
| `app/services/signal_manager.py` | Slice 11 | COVERED |
| `app/services/db.py` | Slice 2 | COVERED |
| `app/services/classifier/__init__.py` | Slice 9 | COVERED |
| `app/services/classifier/protocol.py` | Slice 9 | COVERED |
| `app/services/classifier/rule_based.py` | Slice 9 | COVERED |
| `app/utils/__init__.py` | Slice 1 | COVERED |
| `app/utils/errors.py` | Slice 1 (copy), Slices 5 and 6 (extend) | COVERED |
| `app/utils/formatting.py` | Slice 1 | COVERED |
| `app/utils/validation.py` | Slice 1 | COVERED |
| `app/utils/ticker_resolver.py` | Slice 6 | COVERED |
| `frontend/src/app/globals.css` | Slice 1 (copy), Slice 14 (extend) | COVERED |
| `frontend/src/app/layout.tsx` | Slice 14 | COVERED |
| `frontend/src/app/page.tsx` | Slice 14 (create), Slice 16 (modify) | COVERED |
| `frontend/src/components/Header.tsx` | Slice 14 | COVERED |
| `frontend/src/components/HealthBar.tsx` | Slice 14 | COVERED |
| `frontend/src/components/LiveNowPanel.tsx` | Slice 14 (create), Slice 15 (modify) | COVERED |
| `frontend/src/components/WatchlistPanel.tsx` | Slice 14 (create), Slice 15 (modify) | COVERED |
| `frontend/src/components/RecentClosedPanel.tsx` | Slice 14 (create), Slice 15 (modify) | COVERED |
| `frontend/src/components/SignalRow.tsx` | Slice 15 (create), Slice 16 (modify) | COVERED |
| `frontend/src/components/SetupDetailModal.tsx` | Slice 16 | COVERED |
| `frontend/src/components/PositionForm.tsx` | Slice 16 | COVERED |
| `frontend/src/services/api.ts` | Slice 14 | COVERED |
| `frontend/src/types/signals.ts` | Slice 4 | COVERED |
| `frontend/package.json` | Slice 1 | COVERED |
| `frontend/tsconfig.json` | Slice 1 | COVERED |

No orphaned files. Every architecture file has a roadmap home.

---

## 8. Requirements-to-UI Coverage

| User Story | UI Coverage | Status |
|------------|-------------|--------|
| US-05: Rank-A Alert | Live Now panel shows Rank A signals immediately (UI Spec Section 3, Flow 6) | COVERED |
| US-06: Watchlist Visibility | Watchlist panel shows Rank B signals (UI Spec Section 3, Section 4.2) | COVERED |
| US-07: Dashboard Overview | Three-panel layout: Live Now, Watchlist, Recent Closed (UI Spec Section 3.2) | COVERED |
| US-08: Setup Detail View | SetupDetailModal with all 8 classification fields (UI Spec Section 5) | COVERED |
| US-09: Position Tracking | PositionForm with 3 states (UI Spec Section 5.4) | COVERED |
| US-10: Setup Lifecycle | TIME_EXCEEDED signals appear in Recent Closed (UI Spec Flow 7) | COVERED |
| US-11: Alert Differentiation | Watchlist status labels differentiate NEW_SETUP vs SETUP_UPDATE (UI Spec Section 4.2) | COVERED |
| US-16: Polling Health | HealthBar with 4 status dot states (UI Spec Section 6) | COVERED |

All user-facing requirements have corresponding UI spec coverage.

---

## 9. Open Questions

| ID | Question | Impact | Status |
|----|----------|--------|--------|
| Q-01 | **Should `score_normalization_ceiling` be calibrated before go-live?** The default of 1.0 means a raw score of 1.0 maps to 100. Extreme combinations (e.g., dilution_severity=1.0, FLOAT_ILLIQUIDITY=1.0, setup_quality=0.65, borrow_cost=0.10) produce raw_score=6.5, which clamps to 100. The ceiling may need adjustment after observing real-world score distributions. | Medium -- if the ceiling is too low, most qualifying setups will clamp to 100 and all become Rank A, reducing discrimination. | Deferred to operational monitoring. The value is configurable via `SCORE_NORMALIZATION_CEILING` env var. Architecture requires logging raw pre-normalization values when clamping occurs. Monitor the score distribution during the first week of operation and adjust as needed. Does not block implementation. |

---

## 10. Risks Register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|------------|
| R-01 | **EDGAR EFTS endpoint changes format or rate-limits automated access.** SEC has historically changed endpoint structures. The system depends on a specific JSON response shape. | Medium | High | EFTS response parsing is isolated in EdgarPoller. Monitor for 403/429 responses. Required User-Agent header is specified. SEC provides no uptime SLA. |
| R-02 | **FMP API returns incomplete or delayed data for small-cap tickers.** Small-cap stocks may have stale or missing float/ADV data in FMP, especially for recent IPOs or SPACs. | Medium | Medium | Conservative defaults: missing FMP data fails the filter. System logs DATA_UNAVAILABLE events. A future enhancement could add a secondary data source. |
| R-03 | **Rule-based classifier produces excessive NULL classifications.** S-3 filings will always classify as NULL (documented in Architecture Section 3.5.3). Other filings with atypical language may also NULL. | Medium | Low | NULL filings are logged for training data. Phase 2 ML classifier will improve recall. Phase 1 is intentionally conservative. |
| R-04 | **Score normalization ceiling (1.0) causes most qualifying setups to clamp at 100.** If typical qualifying filings have high dilution severity and low ADV (both likely for small-cap dilution events), raw scores may routinely exceed 1.0. | Medium | Medium | Log raw pre-normalization scores. Monitor score distribution in first week. `SCORE_NORMALIZATION_CEILING` is configurable via env var and can be adjusted without code changes. |
| R-05 | **DuckDB single-writer model may cause contention if pipeline processing overlaps with API reads.** DuckDB supports concurrent reads but only one writer at a time. | Low | Low | Phase 1 throughput is low (EDGAR volume is ~O(10) qualifying filings/day). Architecture uses `asyncio.to_thread` for writes, preventing event loop blocking. |
| R-06 | **AskEdgar API availability may degrade enrichment quality.** If AskEdgar is frequently unavailable, most filings will be scored with FMP-only data (PARTIAL enrichment). | Low | Low | Pipeline continues with PARTIAL flag. AskEdgar enrichment improves scoring but is not required. DilutionService already has retry logic and 30-minute cache. |

---

## 11. Assumptions

| Assumption | Impact if Wrong |
|------------|-----------------|
| EDGAR EFTS JSON endpoint remains publicly accessible and continues to index the required form types. | Pipeline cannot ingest filings. Requires finding an alternative EDGAR data source. |
| FMP Ultimate API provides accurate float, market cap, price, and ADV for small-cap US equities. | Filter criteria and scoring would use stale/inaccurate data; conservative filter defaults mitigate by failing filings with missing data. |
| SETUP_QUALITY placeholder values (A: 0.65, B: 0.55, C: 0.60, D: 0.45, E: 0.50) are reasonable starting estimates. | Score distribution may be skewed; values are configurable via env vars and can be adjusted without code changes. |
| Single-user deployment; no concurrent session or multi-tenancy requirements. | Architecture would need auth layer, session management, and DuckDB concurrency changes for multi-user. |
| DilutionService from gap-lens-dilution works without modification in the new project. | Would require debugging import chain or API compatibility issues; mitigated by Slice 1 import verification test. |

---

## 12. Approval Checklist

### Requirements (01)
- [x] Summary is present and clear
- [x] All 16 user stories follow "As a... I want... so that..." format
- [x] Every user story has acceptance criteria
- [x] Edge cases table is populated (13 cases)
- [x] Out of scope section is comprehensive (15 items)
- [x] Constraints are concrete and measurable
- [x] Data requirements include DuckDB schema (7 tables)
- [x] Integration requirements specify endpoints, auth, and retry behavior
- [x] Phase 2 accommodation requirements are explicit

### Architecture (02)
- [x] System overview diagram is complete
- [x] Directory structure covers all files with COPY/EXTEND/NEW labels
- [x] Every service has documented responsibility, inputs, outputs, dependencies, and key behaviors
- [x] ClassifierProtocol is fully defined with code blocks
- [x] Scoring formula has worked examples that validate correctly
- [x] API routes are enumerated with response schemas
- [x] DuckDB DDL is provided verbatim
- [x] Frontend component hierarchy maps to UI spec
- [x] TypeScript interfaces are complete (including `ticker` and `entity_name` on `SignalDetailResponse`)
- [x] Async background task design is specified with code blocks
- [x] Config extensions are enumerated with types and defaults
- [x] Phase 2 seams are documented

### UI Spec (03)
- [x] Design system tokens are comprehensive (colors, typography, spacing, shape)
- [x] Screen inventory covers both views (dashboard, detail panel)
- [x] Main dashboard layout is specified with ASCII diagram
- [x] All three panel types have distinct row layouts
- [x] Setup detail panel covers all 8 classification fields
- [x] Position tracking covers all 3 states (no entry, entry recorded, closed)
- [x] Status indicator has 4 states with conditions
- [x] Auto-refresh behavior is specified (30s signals, 15s health)
- [x] State matrix covers loading/empty/error/data for all panels
- [x] User flows cover 7 scenarios including error paths
- [x] Interaction specification table is complete
- [x] Component hierarchy matches architecture

### Roadmap (04)
- [x] 17 slices with clear dependency map
- [x] Every slice has goal, dependencies, files, implementation notes, and done-when criteria
- [x] Sequence rules are explicit (complete each slice, no skipping)
- [x] File ownership summary confirms no file created in multiple slices
- [x] Deferred items list matches requirements out-of-scope
- [x] All architecture files appear in at least one slice
- [x] Config variable coverage is complete (ADV_MIN_THRESHOLD now listed in Slice 3)
- [x] TickerResolver.refresh() call site matches Architecture (lifespan handler, not init_db)
- [x] edgar_efts_url default is base URL only in Slice 3

### Overall
- [x] No blocking contradictions
- [x] No blocking gaps
- [x] All previously identified issues resolved
- [x] All risks have mitigations
- [x] Scoring formula is consistent across all three documents
- [x] 13D/A (Setup Type E) is reachable end-to-end
- [x] All 16 user stories covered by architecture
- [x] All architecture files covered by roadmap
- [x] All user-facing requirements covered by UI spec
- [x] Ready for implementation
