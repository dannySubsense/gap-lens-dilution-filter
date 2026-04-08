# Orchestrator Redesign: research/run_backtest.py

**Document version:** 1.0
**Date:** 2026-04-07
**Author:** @architect
**Status:** BLUEPRINT — ready for implementation by @code-executor

---

## 1. Problem Statement

The current orchestrator (`research/run_backtest.py`) processes 1.47M filings in five sequential all-or-nothing phases:

1. Discover ALL filings → 1.47M `DiscoveredFiling` objects
2. Resolve ALL CIKs → 1.47M `ResolvedFiling` objects
3. Fetch ALL texts from EDGAR → 1.47M `FetchedFiling` objects with `plain_text` in memory
4. Classify ALL → 1.47M classification dicts in memory simultaneously
5. Join + filter + score + outcome for ALL → `BacktestRow` list

**Why it fails:**

- **OOM in Phase 3.** Holding 433K fetched filing texts in memory simultaneously requires 29GB+. The system cannot complete this phase.
- **No checkpoint.** Phase 3 runs 12+ hours at SEC's 10 req/s rate limit. A failure at hour 11 forces a full restart from zero. The 57K files already cached to disk are preserved, but the in-memory accumulation is lost.
- **No progress visibility.** No structured per-filing or per-quarter progress reporting during long phases.

Note: Phase 2 originally had a second O(N) DB query problem (1.47M individual lookups). This was already fixed via a bulk preload in `cik_resolver.py` — that optimization is preserved in the redesign.

---

## 2. Design Principles

1. **Stream per-filing.** Each filing is fetched, classified, joined, filtered, scored, and outcome-computed before the next batch begins. `plain_text` is discarded immediately after classification.
2. **Quarterly batching with checkpointing.** The 36 quarters (2017-Q1 through 2025-Q4) are processed one at a time. Completed quarters write a JSON checkpoint. A resumed run skips COMPLETE quarters.
3. **Observability.** Structured progress log line every mini-batch (100 filings). Quarter-completion summary log line after each of the 36 quarters.
4. **Resilience.** A failed quarter does not write a checkpoint. On `--resume`, only COMPLETE quarters are skipped. Any incomplete or missing quarter is re-processed.
5. **Memory ceiling.** Peak RAM is O(`mini_batch_size`) for text, not O(total_filings). At most 100 `plain_text` strings are live simultaneously.

---

## 3. Architecture

### 3.1 Two-Pass Design

**Pass 1: Discovery + CIK Resolution (fast, in-memory)**

Sequence:
1. `FilingDiscovery.discover(start_date, end_date)` → `list[DiscoveredFiling]`, `list[str]` (failed quarters). ~20s.
2. `CIKResolver.preload()` — bulk-loads the full CIK→ticker mapping into a dict. ~1s.
3. `CIKResolver.resolve(d)` for each discovered filing — pure dict lookups. ~15s for 1.47M.
4. Group `ResolvedFiling` objects by `quarter_key` into `dict[str, list[ResolvedFiling]]`. Filter out UNRESOLVABLE filings from each quarter's list — they produce a BacktestRow with `filter_status="UNRESOLVABLE"` directly in Pass 2 without entering the fetch/classify loop. This avoids 413K unnecessary async gather calls.
5. Update `manifest.total_filings_discovered`, `manifest.total_cik_resolved`, `manifest.total_unresolvable_count`.

Memory: ~500-750MB (1.47M `ResolvedFiling` objects at ~300-500 bytes each, no `plain_text`).

This pass is identical to the current implementation. No behavioral changes.

---

**Pass 2: Per-Quarter Streaming Processing (checkpointed)**

For each `quarter_key` in chronological order across the 36 quarters:

- If `--resume` is set and `research/cache/checkpoints/{quarter_key}.json` exists with `status == "COMPLETE"`: the quarter is still re-processed (classification, join, filter, score, outcome all re-run from cached filing text — this is fast, ~2-3 hours for a full re-run). The checkpoint signals that all EDGAR HTTP fetches for this quarter are cached, so no network requests are needed. The `--resume` flag's primary value is skipping EDGAR fetches (the 10+ hour bottleneck), not skipping computation.
- Otherwise, process the quarter:

  For filings grouped into mini-batches of 100:
  1. `await asyncio.gather(*[fetcher.fetch(f) for f in mini_batch])` — respects the existing semaphore + rate limiter in `FilingTextFetcher`.
  2. `await asyncio.gather(*[classifier.classify(f) for f in mini_batch])` — async classify all 100.
  3. For each `(fetched_filing, classification)` pair:
     - Call `_process_filing(...)` — the existing per-filing integration function (unchanged).
     - Append resulting `BacktestRow` to the quarter's `rows` list.
     - Extend `participants` list with any `ParticipantRecord` objects.
     - Set `fetched_filing.plain_text = None` after classification completes.
  4. Log the mini-batch progress line (see Section 3.4).

  After all mini-batches in the quarter complete:
  - Write checkpoint JSON to `research/cache/checkpoints/{quarter_key}.json` (see Section 3.5).
  - Log the quarter-completion summary line (see Section 3.4).
  - Extend the run-level `all_rows` and `all_participants` accumulators with this quarter's results.

Memory during Pass 2:
- At most 100 `FetchedFiling` objects with `plain_text` live at once (~50MB peak per mini-batch).
- Accumulated `BacktestRow` objects grow throughout but contain no text (~500MB for ~30K–50K passed filings across all quarters).

---

**Pass 3: Output (fast)**

After all quarters complete:
1. Call `OutputWriter(output_dir=args.output_dir).write(all_rows, all_participants, manifest)`.
2. `OutputWriter.write()` populates `manifest.parquet_sha256` and `manifest.parquet_row_count` (unchanged behavior).
3. Log final summary.

Memory: same as the accumulated results plus Parquet write buffer.

---

### 3.2 Memory Budget

| Phase | Peak RAM | What is held |
|---|---|---|
| Pass 1 complete | ~500-750MB | 1.47M `ResolvedFiling` objects (no text), CIK dict |
| Pass 2 mini-batch peak | ~50MB additional | 100 `FetchedFiling` with `plain_text`, 100 classification dicts |
| Pass 2 accumulated results | ~500MB | All `BacktestRow` objects for passed+failed filings (no text) |
| Pass 3 (write) | ~600MB | Above + Parquet write buffer |

Total ceiling: ~1.5GB. Previous design: 29GB+.

---

### 3.3 Fetch Batching Within a Quarter

```python
MINI_BATCH_SIZE = 100  # at most 100 plain_text strings live at once

async def _process_quarter(
    quarter_key: str,
    resolved_filings: list[ResolvedFiling],
    fetcher: FilingTextFetcher,
    classifier: BacktestClassifier,
    ...
) -> tuple[list[BacktestRow], list[ParticipantRecord], QuarterStats]:

    rows: list[BacktestRow] = []
    participants: list[ParticipantRecord] = []
    stats = QuarterStats(quarter_key=quarter_key)

    for i in range(0, len(resolved_filings), MINI_BATCH_SIZE):
        mini_batch = resolved_filings[i : i + MINI_BATCH_SIZE]

        # Fetch (async, semaphore-controlled by fetcher internals)
        fetched_batch: list[FetchedFiling] = list(
            await asyncio.gather(*[fetcher.fetch(f) for f in mini_batch])
        )

        # Classify (async)
        classifications: list[dict] = list(
            await asyncio.gather(*[classifier.classify(f) for f in fetched_batch])
        )

        # Per-filing integration + text discard
        for filing, classification in zip(fetched_batch, classifications):
            try:
                _process_filing(filing, classification, ..., rows, participants, run_start)
            except Exception as exc:
                logger.error("Pipeline error for %s: %s", filing.accession_number, exc)
                rows.append(_make_error_row(filing, str(exc), run_start))
            finally:
                filing.plain_text = None  # discard immediately

            stats.update(filing, rows[-1])

        _log_mini_batch_progress(quarter_key, i + len(mini_batch), len(resolved_filings), stats)

    return rows, participants, stats
```

The existing `_process_filing`, `_make_base_row`, and `_make_error_row` functions are used without modification.

---

### 3.4 Progress Logging

**Every mini-batch (100 filings):**
```
[Q 2022_QTR1] 1200/12453 | OK: 890 | skip: 210 | err: 3 | passed: 45 | mem: 1.2GB | elapsed: 3m12s
```

Fields:
- `OK` = `fetch_status == "OK"` count (cumulative within quarter)
- `skip` = `UNRESOLVABLE` + `FETCH_FAILED` count (cumulative)
- `err` = `PIPELINE_ERROR` count (cumulative)
- `passed` = `filter_status == "PASSED"` count (cumulative)
- `mem` = `psutil.Process().memory_info().rss` converted to GB
- `elapsed` = wall-clock time since quarter start

**Every quarter completion:**
```
[Q 2022_QTR1] COMPLETE | 12453 filings | 4521 passed | 89 errors | 28m15s | cache: 9200 hits
```

`cache hits` is derived from `fetch_status == "OK"` where `plain_text` came from disk (fetcher already logs this internally; aggregate from fetcher stats if available, otherwise omit).

Both log lines use `logger.info()` (not print).

---

### 3.5 Checkpoint Format

File path: `research/cache/checkpoints/{quarter_key}.json`

```json
{
  "quarter_key": "2022_QTR1",
  "status": "COMPLETE",
  "filings_discovered": 43210,
  "filings_resolved": 12453,
  "filings_fetched_ok": 11200,
  "filings_passed": 4521,
  "filings_errored": 89,
  "elapsed_seconds": 1695,
  "completed_at": "2026-04-08T10:30:00Z"
}
```

Rules:
- Written only after a quarter completes all filings without a catastrophic exception (DB lost, process killed, etc.).
- `status` is always `"COMPLETE"` when present — no partial checkpoints.
- On `--resume`: a quarter is skipped if and only if its checkpoint file exists and `status == "COMPLETE"`.
- The checkpoint directory is created at startup if it does not exist: `research/cache/checkpoints/`.
- Checkpoint files are runtime artifacts — not committed to git (already covered by `research/cache/` in `.gitignore`).

---

### 3.6 CLI Interface

All existing arguments are preserved with identical semantics:

| Argument | Default | Description |
|---|---|---|
| `--start-date YYYY-MM-DD` | `2017-01-01` | Start of filing discovery range |
| `--end-date YYYY-MM-DD` | `2025-12-31` | End of filing discovery range |
| `--dry-run N` | `None` | Process only first N filings (0 = startup checks only) |
| `--db-path PATH` | config default | Override market_data.duckdb path |
| `--output-dir PATH` | `docs/research/data/` | Override output directory |

**New arguments:**

| Argument | Default | Description |
|---|---|---|
| `--resume` | `False` | Skip quarters with `status=COMPLETE` in their checkpoint file. Previously this flag only controlled EDGAR cache file reuse (fetcher behavior); that behavior is preserved — the flag now also controls quarter-level skipping. |
| `--quarter YYYY_QTRN` | `None` | Process a single quarter only (e.g. `2022_QTR1`). Useful for testing a specific quarter or retrying a failed one. Ignores `--start-date`/`--end-date` for processing; discovery still runs the full range to build the grouped dict, then filters to the single requested quarter. |

`--quarter` and `--resume` are independent. Both can be specified (retry a single failed quarter).

---

### 3.7 Error Handling

**Per-filing errors** (classify throws, joiner throws, etc.):
- `try/except Exception` wraps the call to `_process_filing(...)`.
- On exception: `logger.error(...)`, append `_make_error_row(filing, str(exc), run_start)`.
- Processing continues with the next filing.
- `filing.plain_text = None` in `finally` block regardless of outcome.

**Per-quarter catastrophic errors** (DB connection lost, asyncio event loop error, etc.):
- `try/except Exception` wraps the entire `_process_quarter(...)` call.
- On exception: `logger.error("Quarter %s failed: %s", quarter_key, exc)`, append `quarter_key` to `manifest.quarters_failed`.
- Do NOT write a checkpoint for the failed quarter.
- Continue to the next quarter.
- The failed quarter can be retried by re-running with `--resume` (all COMPLETE quarters are skipped, the failed one is re-processed).

**Fetch errors** (HTTP failures after retries):
- Handled entirely within `FilingTextFetcher.fetch()` — no change to fetcher behavior.
- `FetchedFiling.fetch_status == "FETCH_FAILED"` propagates to `_process_filing()`, which produces a row with `filter_status = "FETCH_FAILED"`.
- No exception is raised; this is not a pipeline error.

---

## 4. What Changes vs What Stays

### Stays unchanged

- All 12 component modules: `trading_calendar`, `discovery`, `cik_resolver`, `fetcher`, `bt_classifier`, `underwriter_extractor`, `market_data_joiner`, `bt_filter_engine`, `bt_scorer`, `outcome_computer`, `output_writer`, `run_manifest`.
- `dataclasses.py` — all shared dataclasses.
- `config.py` — `BacktestConfig` and all constants.
- All 193 existing tests.
- The CIK bulk preload optimization (`CIKResolver.preload()` called once before the per-filing loop).
- The aiohttp session pooling (already in `FilingTextFetcher`).
- The `_process_filing`, `_make_base_row`, `_make_error_row` helper functions (copy verbatim, no modification).
- The `run_startup_checks` function (copy verbatim, no modification).
- The `RunManifest` initialization block (copy verbatim, adjust only for new `--quarter` arg if needed).

### Changes

- `research/run_backtest.py` — complete rewrite. The new orchestrator introduces the two-pass structure, per-quarter async loop, and checkpoint I/O. All top-level logic changes; component calls do not.

### New

- `research/cache/checkpoints/` — directory for quarterly checkpoint JSON files (runtime artifact).
- `research/tests/test_orchestrator.py` — updated smoke tests covering:
  - `--dry-run 0` still produces empty output (existing test behavior preserved)
  - `--dry-run 5` processes 5 filings and exits cleanly
  - `--quarter 2022_QTR1` processes a single quarter
  - Checkpoint is written after a successful quarter
  - `--resume` skips a quarter whose checkpoint has `status=COMPLETE`
  - Catastrophic quarter failure does not write checkpoint; run continues

---

## 5. QuarterStats Internal Dataclass

Used only within the orchestrator — not a shared pipeline dataclass.

```python
@dataclass
class QuarterStats:
    quarter_key: str
    filings_total: int = 0
    filings_fetched_ok: int = 0
    filings_skipped: int = 0       # UNRESOLVABLE + FETCH_FAILED
    filings_errored: int = 0       # PIPELINE_ERROR
    filings_passed: int = 0        # filter_status == "PASSED"
    elapsed_seconds: float = 0.0
    started_at: datetime = field(default_factory=datetime.utcnow)

    def update(self, filing: FetchedFiling, row: BacktestRow) -> None:
        self.filings_total += 1
        if filing.fetch_status == "OK":
            self.filings_fetched_ok += 1
        if row.filter_status in ("UNRESOLVABLE", "FETCH_FAILED"):
            self.filings_skipped += 1
        if row.filter_status == "PIPELINE_ERROR":
            self.filings_errored += 1
        if row.filter_status == "PASSED":
            self.filings_passed += 1
```

`QuarterStats` is local to `run_backtest.py`. It is not exported and not added to `dataclasses.py`.

---

## 6. Estimated Runtime

| Phase | Duration | Notes |
|---|---|---|
| Pass 1 (discover + resolve) | ~40s | 20s discovery + 1s preload + 15s resolve |
| Pass 2 (36 quarters, streaming) | ~10–12 hours | Network-bound at 10 req/s for ~376K uncached filings |
| — per quarter average | ~17–20 min | Varies by quarter filing volume (2K–15K filings) |
| — with full cache (re-run) | ~2–3 hours | Classify + join + filter + score + outcome only |
| Pass 3 (write output) | ~30s | Parquet write + SHA-256 |

The 57K files already cached from the prior partial run reduce the remaining HTTP fetches from 433K to ~376K, saving approximately 1.5 hours on first re-run.

Checkpoint granularity means any interrupted run resumes from the last incomplete quarter, not from the beginning. Worst-case re-work on a crash mid-quarter: ~20 minutes.

---

## 7. Implementation Notes for Code Executor

1. The new `run()` function replaces the five-phase sequential structure with two calls: `_pass1_discover_and_resolve()` and `_pass2_process_quarters()`. Pass 3 remains the `OutputWriter.write()` call.

2. **Single `asyncio.run()` wrapping all quarters.** One event loop for the process lifetime. The per-quarter `asyncio.run()` approach was rejected because the fetcher's rate limiter (`asyncio.Lock`), semaphore, and `TokenBucketRateLimiter` bind to the first event loop they're used in — creating a new loop per quarter causes `RuntimeError: attached to a different event loop`. The outer async function iterates quarters within one event loop.

3. The `fetcher.close_session()` call should happen once after all quarters complete (in a `finally` block), not per-quarter.

4. `psutil` is required for the memory logging. Add to `requirements.txt` if not already present. The memory log field can be omitted if `psutil` import fails (non-fatal `ImportError` guard).

5. The checkpoint directory path is `cfg.cache_dir / "checkpoints"` (uses the existing `BacktestConfig.cache_dir` field, defaulting to `research/cache`). Create with `mkdir(parents=True, exist_ok=True)` at startup.

6. `--resume` does not load data from checkpoints into the manifest. All quarters are re-processed from cached text (fast path). Checkpoints exist only to signal that EDGAR fetches are cached — the fetcher's disk cache handles the actual skip logic. Manifest counts are computed from the live processing run, ensuring consistency.

7. `--dry-run N` behavior with the new design: apply the limit globally across all quarters during Pass 2, not per-quarter. Stop processing once N total filings have been processed. This preserves the existing `--dry-run` semantics.
