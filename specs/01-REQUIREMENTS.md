# Gap Lens Dilution Filter — Requirements Specification
**Version:** 1.0  
**Date:** 2026-03-25  
**Status:** Draft

---

## 1. Functional Requirements

### 1.1 Data Ingestion (FR-DATA-001 → FR-DATA-006)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-DATA-001 | System shall ingest SEC filings via EDGAR RSS feed or SEC Insights API | P0 |
| FR-DATA-002 | System shall parse 8-K, S-1, S-3, 424B2, 424B4, 13D/A filing types | P0 |
| FR-DATA-003 | System shall fetch and store price/volume data (OHLCV) from Polygon.io | P0 |
| FR-DATA-004 | System shall ingest float data from Finviz/Ortex | P0 |
| FR-DATA-005 | System shall store raw filings, labels, market data, and signals in KDB-X (or SQLite/DuckDB for MVP) | P0 |
| FR-DATA-006 | System shall support fetching 5+ years of historical filings for training/validation | P0 |

### 1.2 Teacher Model Labeling (FR-TEACH-001 → FR-TEACH-004)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-TEACH-001 | System shall use GPT-4 or Claude 3.5 Sonnet as teacher model for classification | P0 |
| FR-TEACH-002 | System shall classify filings into Setup Types A, B, C, D, or E | P0 |
| FR-TEACH-003 | System shall score short attractiveness (0-100) for each labeled filing | P0 |
| FR-TEACH-004 | System shall generate labeled training set of minimum 2,000 examples | P0 |

### 1.3 Student Model Training (FR-STUD-001 → FR-STUD-005)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-STUD-001 | System shall use Llama 3.2 1B as base student model | P0 |
| FR-STUD-002 | System shall fine-tune via LoRA (Low-Rank Adaptation) | P0 |
| FR-STUD-003 | System shall train on teacher-generated labels | P0 |
| FR-STUD-004 | System shall achieve classification F1 score ≥ 0.85 on validation set | P0 |
| FR-STUD-005 | System shall support local training on RTX 4090 (2-4 hours for 10K samples) | P0 |

### 1.4 Classification & Scoring (FR-CLASS-001 → FR-CLASS-006)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-CLASS-001 | System shall classify new filings into Setup Types A-E using distilled model | P0 |
| FR-CLASS-002 | System shall calculate dilution severity as shares_offered / pre_float | P0 |
| FR-CLASS-003 | System shall calculate float illiquidity factor | P0 |
| FR-CLASS-004 | System shall calculate short attractiveness score using weighted formula | P0 |
| FR-CLASS-005 | System shall identify key excerpts from filing text | P0 |
| FR-CLASS-006 | System shall provide classification confidence score | P0 |

### 1.5 Scoring Formula (FR-SCORE-001 → FR-SCORE-003)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-SCORE-001 | System shall implement dilution severity calculation | P0 |
| FR-SCORE-002 | System shall implement SETUP_QUALITY lookup (historical win rates) | P1 |
| FR-SCORE-003 | System shall optionally factor in borrow cost if IBKR API available | P1 |

**Scoring Formula:**
```
SCORE = (DILUTION_SEVERITY × FLOAT_ILLIQUIDITY × SETUP_QUALITY) / BORROW_COST
```

### 1.6 Filtering & Alerting (FR-FILTER-001 → FR-FILTER-006)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-FILTER-001 | System shall filter for market cap < $2B | P0 |
| FR-FILTER-002 | System shall filter for float < 50M shares | P0 |
| FR-FILTER-003 | System shall filter for dilution % > 10% | P0 |
| FR-FILTER-004 | System shall filter for price > $1 | P0 |
| FR-FILTER-005 | System shall filter for ADV > $500K | P0 |
| FR-FILTER-006 | System shall generate tiered alerts: A (>80), B (60-80), C (40-60), D (<40) | P0 |

### 1.7 Deployment & Inference (FR-DEPLOY-001 → FR-DEPLOY-004)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-DEPLOY-001 | System shall deploy via NVIDIA NIM (local or cloud) | P1 |
| FR-DEPLOY-002 | System shall achieve inference cost of ≤ $0.001 per filing | P0 |
| FR-DEPLOY-003 | System shall support local deployment (zero inference cost) | P1 |
| FR-DEPLOY-004 | System shall process filings within 60 seconds of EDGAR publication | P0 |

### 1.8 Output Schema (FR-OUT-001 → FR-OUT-002)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-OUT-001 | System shall produce JSON output matching classification schema (see below) | P0 |
| FR-OUT-002 | System shall expose results via API and/or file export | P1 |

**Classification Output Schema:**
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

### 1.9 Flywheel & Retraining (FR-FLY-001 → FR-FLY-003)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-FLY-001 | System shall log all predictions and outcomes | P1 |
| FR-FLY-002 | System shall support monthly retraining pipeline | P1 |
| FR-FLY-003 | System shall handle distribution shift detection | P2 |

---

## 2. Non-Functional Requirements

### 2.1 Performance Requirements (NFR-PERF-001 → NFR-PERF-004)

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-PERF-001 | Inference latency per filing | < 5 seconds |
| NFR-PERF-002 | End-to-end processing time (EDGAR → Alert) | < 60 seconds |
| NFR-PERF-003 | Training time (10K samples on RTX 4090) | 2-4 hours |
| NFR-PERF-004 | System throughput | ≥ 100 filings/hour |

### 2.2 Cost Requirements (NFR-COST-001 → NFR-COST-003)

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-COST-001 | Inference cost per filing (cloud) | ≤ $0.001 |
| NFR-COST-002 | Inference cost per filing (local deployment) | $0 |
| NFR-COST-003 | Monthly operational cost (development) | < $100 |

### 2.3 Quality Requirements (NFR-QUAL-001 → NFR-QUAL-003)

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-QUAL-001 | Classification F1 score (student vs teacher) | ≥ 0.85 |
| NFR-QUAL-002 | Teacher label accuracy (human-verified sample) | ≥ 95% |
| NFR-QUAL-003 | False positive rate for Tier A alerts | < 10% |

### 2.4 Reliability Requirements (NFR-REL-001 → NFR-REL-003)

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-REL-001 | EDGAR/RSS feed uptime | ≥ 99% |
| NFR-REL-002 | Data persistence | All filings logged |
| NFR-REL-003 | Recovery time from failure | < 5 minutes |

### 2.5 Maintainability Requirements (NFR-MAINT-001 → NFR-MAINT-003)

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-MAINT-001 | Modular architecture (separate ingest/classify/score) | P0 |
| NFR-MAINT-002 | Configuration-driven filtering criteria | P1 |
| NFR-MAINT-003 | Comprehensive logging at each pipeline stage | P1 |

### 2.6 Security Requirements (NFR-SEC-001 → NFR-SEC-002)

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-SEC-001 | API keys stored securely (environment variables) | P0 |
| NFR-SEC-002 | No PII in logs or training data | P0 |

---

## 3. Acceptance Criteria

### 3.1 Data Pipeline Acceptance Criteria

**AC-DATA-001:** Successfully ingest and parse 100 historical 8-K/S-1/424B filings with zero parsing errors.

**AC-DATA-002:** KDB-X/SQLite database contains all required tables: filings, labels, market_data, signals.

**AC-DATA-003:** Data pipeline runs end-to-end without manual intervention for a 7-day period.

### 3.2 Model Acceptance Criteria

**AC-MODEL-001:** Teacher model produces 2,000 labeled examples within 48 hours of runtime.

**AC-MODEL-002:** Student model achieves F1 ≥ 0.85 on stratified test set (by year and sector).

**AC-MODEL-003:** Student model inference is ≥ 30x cheaper per filing than GPT-4 API.

**AC-MODEL-004:** Classification schema output validates against JSON schema 100% of test cases.

