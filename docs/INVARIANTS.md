# Invariants: dilution-short-filter

These rules are inviolable. Any agent that would violate one must HALT and escalate.

---

## I-01: Source Repo Immutability
`/home/d-tuned/projects/gap-lens-dilution/` must never be modified. All development is in `/home/d-tuned/projects/gap-lens-dilution-filter/`. Verify with `git status` in the source repo after any copy operation.

## I-02: ClassifierProtocol Seam
No pipeline code (FilterEngine, Scorer, SignalManager, routes, main.py) may import `RuleBasedClassifier` directly. All classifier access goes through `get_classifier()` factory. This is the Phase 2 swap point.

## I-03: AskEdgar Trigger Point
`DilutionService.get_dilution_data_v2()` is called only after all six filter criteria pass. It must never be called before Filter 6 completes. Calling it earlier wastes paid API credits.

## I-04: Filter Stop-on-Fail
FilterEngine evaluates criteria in order 1→6 and stops at the first failure. A filing must pass ALL six to reach the classifier. No partial passes.

## I-05: DuckDB as Sole Persistence
All data is stored in DuckDB. No other database, cache layer, or file-based persistence (other than DuckDB's own `.duckdb` file) is permitted in Phase 1.

## I-06: Score Normalization Ceiling
`score_normalization_ceiling` defaults to `1.0`. The worked examples in 02-ARCHITECTURE.md Section 3.6 are the ground truth. A raw_score of 0.90 must normalize to 90 (Rank A), not 9.

## I-07: Rank D Not Surfaced
Setups scoring < 40 (Rank D) are written to the `labels` table but never inserted into `signals`, never returned by the API, and never displayed on the dashboard.

## I-08: poll_state Single Row
The `poll_state` table always contains exactly one row (`id = 1`). It is seeded at `init_db()` with `INSERT OR IGNORE` and updated in-place via `UPDATE`. Never insert a second row.

## I-09: DilutionService Unchanged
`app/services/dilution.py` is copied from gap-lens-dilution and never modified. If a bug is found in it, HALT and escalate — do not patch it.

## I-10: FLOAT_ILLIQUIDITY Formula
```
FLOAT_ILLIQUIDITY = settings.adv_min_threshold / fmp_data.adv_dollar
```
Any other formulation is wrong. The formula in Architecture Section 3.6 is canonical.

## I-11: entity_name Stored
`entity_name` from the EFTS response must be stored in the `filings` table and returned in `SignalDetailResponse`. The UI detail panel depends on it.

## I-12: TickerResolver Initialization Order
`TickerResolver.refresh()` is called from the FastAPI `lifespan` handler after `init_db()` completes. It must not be called from within `init_db()`.
