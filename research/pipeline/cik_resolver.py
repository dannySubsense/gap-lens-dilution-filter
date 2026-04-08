"""
CIKResolver: Resolves a DiscoveredFiling CIK to a ticker using market_data.duckdb.

Handles multi-ticker CIKs via date-range disambiguation (symbol_history) and
share-class preference (prefer common shares over warrants, rights, units).

Anti-survivorship invariant: the active column is NEVER used in WHERE clauses.
Delisted symbols must resolve if they were active at the filing date. The active
flag is only used in ORDER BY for tie-breaking.
"""

import logging
from datetime import date
from pathlib import Path

import duckdb

from research.pipeline.dataclasses import DiscoveredFiling, ResolvedFiling

logger = logging.getLogger(__name__)

# Security type substrings that indicate non-common-share instruments.
# Case-insensitive match; rows containing any of these are deprioritised.
_NON_COMMON_TYPES = {"WARRANT", "RIGHT", "UNIT"}

# SQL for primary lookup (Step 1 + Step 2 date-range filter).
# Parameterised as (cik, filing_date, filing_date).
# NOTE: active is in ORDER BY only — never in WHERE (anti-survivorship rule).
_PRIMARY_SQL = """
SELECT rsm.ticker, rsm.raw_json->>'type' AS security_type, sh.permanent_id
FROM raw_symbols_massive rsm
JOIN symbol_history sh ON sh.symbol = rsm.ticker
WHERE rsm.cik = ?
  AND sh.start_date <= ?
  AND (sh.end_date >= ? OR sh.end_date IS NULL)
ORDER BY
    CASE WHEN rsm.active THEN 0 ELSE 1 END,
    sh.start_date ASC
LIMIT 5
"""

# SQL for fallback lookup against raw_symbols_fmp by entity name (exact match).
_FALLBACK_SQL = """
SELECT symbol
FROM raw_symbols_fmp
WHERE name = ?
LIMIT 1
"""

# SQL for bulk preload of the full CIK -> symbol_history mapping.
# Returns one row per (cik, ticker, symbol_history row) combination.
# Ordered so that active symbols come before delisted ones, and earlier
# start_dates come first within each CIK.
_PRELOAD_SQL = """
SELECT rsm.cik, rsm.ticker, rsm.raw_json->>'type' AS security_type,
       rsm.active, sh.permanent_id, sh.start_date, sh.end_date
FROM raw_symbols_massive rsm
JOIN symbol_history sh ON sh.symbol = rsm.ticker
WHERE rsm.cik IS NOT NULL
ORDER BY rsm.cik,
         CASE WHEN rsm.active THEN 0 ELSE 1 END,
         sh.start_date ASC
"""

# SQL to bulk-load entity-name -> ticker fallback mapping from raw_symbols_fmp.
_PRELOAD_FALLBACK_SQL = """
SELECT name, symbol
FROM raw_symbols_fmp
WHERE name IS NOT NULL
"""


class CIKResolver:
    """
    Resolves a DiscoveredFiling's CIK to a ticker symbol.

    Connects to market_data.duckdb in read-only mode. The connection is opened
    at construction time and reused for all resolve() calls.

    For bulk processing, call preload() once before the resolve() loop to load
    the full CIK->ticker mapping into memory. resolve() will use the in-memory
    cache when available, falling back to per-query SQL when preload() hasn't
    been called (backward compatibility with tests).
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        # Open once; read_only=True enforces the no-write invariant.
        self._con = duckdb.connect(str(db_path), read_only=True)
        # In-memory cache populated by preload().
        # Maps cik -> list of (ticker, security_type, permanent_id, active, start_date, end_date)
        self._cik_cache: dict[str, list[tuple]] | None = None
        # Maps entity_name.strip() -> ticker for fallback lookups.
        self._name_cache: dict[str, str] | None = None

    def close(self) -> None:
        """Release the DuckDB connection."""
        self._con.close()

    def __enter__(self) -> "CIKResolver":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Preload (bulk optimization)
    # ------------------------------------------------------------------

    def preload(self) -> None:
        """
        Bulk-load the full CIK->ticker mapping into memory using 2 SQL queries.

        After preload() is called, resolve() uses dict lookups instead of
        per-filing SQL queries. This reduces CIK resolution time from O(N) DB
        round-trips to O(N) pure-Python dict lookups.

        Stores:
          _cik_cache: {cik: [(ticker, security_type, permanent_id, active,
                               start_date, end_date), ...]}
          _name_cache: {entity_name.strip(): ticker}
        """
        # --- Query 1: bulk CIK -> symbol_history rows ---
        rows = self._con.execute(_PRELOAD_SQL).fetchall()

        cik_cache: dict[str, list[tuple]] = {}
        for cik, ticker, security_type, active, permanent_id, start_date, end_date in rows:
            if cik not in cik_cache:
                cik_cache[cik] = []
            cik_cache[cik].append(
                (ticker, security_type, permanent_id, active, start_date, end_date)
            )

        # --- Query 2: bulk entity-name fallback mapping ---
        fmp_rows = self._con.execute(_PRELOAD_FALLBACK_SQL).fetchall()
        name_cache: dict[str, str] = {}
        for name, symbol in fmp_rows:
            if name is not None:
                key = name.strip()
                if key and key not in name_cache:
                    name_cache[key] = symbol

        self._cik_cache = cik_cache
        self._name_cache = name_cache

        total_rows = len(rows)
        total_ciks = len(cik_cache)
        logger.info(
            "CIKResolver: loaded %d CIKs (%d symbol-history rows).",
            total_ciks,
            total_rows,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, filing: DiscoveredFiling) -> ResolvedFiling:
        """
        Resolve a DiscoveredFiling's CIK to a ticker.

        Returns a ResolvedFiling with ticker and resolution_status populated.
        Possible resolution_status values:
            "RESOLVED"          — exactly one ticker found after disambiguation
            "AMBIGUOUS_SKIPPED" — multiple tickers remain after share-class filter
            "UNRESOLVABLE"      — no ticker found in primary or fallback lookup
        """
        ticker, permanent_id, status = self._resolve_cik(
            filing.cik, filing.entity_name, filing.date_filed
        )

        return ResolvedFiling(
            # DiscoveredFiling fields (copied verbatim)
            cik=filing.cik,
            entity_name=filing.entity_name,
            form_type=filing.form_type,
            date_filed=filing.date_filed,
            filename=filing.filename,
            accession_number=filing.accession_number,
            quarter_key=filing.quarter_key,
            # ResolvedFiling fields
            ticker=ticker,
            resolution_status=status,
            permanent_id=permanent_id,
        )

    # ------------------------------------------------------------------
    # Internal resolution logic
    # ------------------------------------------------------------------

    def _resolve_cik(
        self,
        cik: str,
        entity_name: str,
        filing_date: date,
    ) -> tuple[str | None, str | None, str]:
        """
        Core resolution logic.

        When preload() has been called, uses in-memory cache with pure-Python
        date-range filtering and disambiguation. Falls back to per-query SQL
        when the cache is not available (backward compatibility with tests).

        Returns (ticker, permanent_id, resolution_status).
        """
        if self._cik_cache is not None:
            return self._resolve_cik_from_cache(cik, entity_name, filing_date)

        # --- Per-query path (no preload; backward-compatible) ---
        rows = self._primary_lookup(cik, filing_date)

        if rows:
            return self._disambiguate(rows, cik)

        # No rows from primary lookup — attempt entity-name fallback.
        fallback_ticker = self._fallback_lookup(entity_name)
        if fallback_ticker:
            logger.debug(
                "CIK %s resolved via fallback entity-name match: %s",
                cik,
                fallback_ticker,
            )
            return fallback_ticker, None, "RESOLVED"

        logger.debug("CIK %s is UNRESOLVABLE", cik)
        return None, None, "UNRESOLVABLE"

    def _resolve_cik_from_cache(
        self,
        cik: str,
        entity_name: str,
        filing_date: date,
    ) -> tuple[str | None, str | None, str]:
        """
        Resolve using the in-memory caches populated by preload().

        Applies the same date-range filter and share-class disambiguation
        as the SQL path, in pure Python.
        """
        all_entries = self._cik_cache.get(cik)  # type: ignore[union-attr]

        if all_entries:
            # Apply date-range filter (mirrors the WHERE clause of _PRIMARY_SQL).
            # Each entry: (ticker, security_type, permanent_id, active, start_date, end_date)
            filtered = [
                entry for entry in all_entries
                if entry[4] <= filing_date  # start_date <= filing_date
                and (entry[5] is None or entry[5] >= filing_date)  # end_date >= filing_date or NULL
            ]

            if filtered:
                # Convert to (ticker, security_type, permanent_id) tuples
                # for the existing _disambiguate() method.
                rows_for_disambiguate = [
                    (entry[0], entry[1], entry[2]) for entry in filtered
                ]
                return self._disambiguate(rows_for_disambiguate, cik)

        # No cache match — attempt entity-name fallback.
        fallback_ticker = None
        if entity_name and entity_name.strip() and self._name_cache is not None:
            fallback_ticker = self._name_cache.get(entity_name.strip())

        if fallback_ticker:
            logger.debug(
                "CIK %s resolved via fallback entity-name match: %s",
                cik,
                fallback_ticker,
            )
            return fallback_ticker, None, "RESOLVED"

        logger.debug("CIK %s is UNRESOLVABLE", cik)
        return None, None, "UNRESOLVABLE"

    def _primary_lookup(
        self,
        cik: str,
        filing_date: date,
    ) -> list[tuple]:
        """
        Execute the primary SQL lookup (Steps 1 + 2).

        Returns a list of (ticker, security_type, permanent_id) tuples.
        """
        result = self._con.execute(
            _PRIMARY_SQL,
            [cik, filing_date, filing_date],
        ).fetchall()
        return result

    def _disambiguate(
        self,
        rows: list[tuple],
        cik: str,
    ) -> tuple[str | None, str | None, str]:
        """
        Apply share-class preference and return (ticker, permanent_id, status).

        Prefer rows whose security_type does NOT contain WARRANT, RIGHT, or UNIT
        (case-insensitive). If still ambiguous, return AMBIGUOUS_SKIPPED.
        """
        # Filter out non-common-share types.
        common_rows = [
            row for row in rows
            if not _is_non_common(row[1])  # row[1] is security_type
        ]

        candidates = common_rows if common_rows else rows

        if len(candidates) == 1:
            ticker = candidates[0][0]
            permanent_id = candidates[0][2]
            logger.debug("CIK %s resolved to %s", cik, ticker)
            return ticker, permanent_id, "RESOLVED"

        # Check if all candidates have the same ticker (duplicate rows for same symbol).
        unique_tickers = {row[0] for row in candidates}
        if len(unique_tickers) == 1:
            ticker = candidates[0][0]
            permanent_id = candidates[0][2]
            logger.debug("CIK %s resolved to %s (deduplicated rows)", cik, ticker)
            return ticker, permanent_id, "RESOLVED"

        logger.debug(
            "CIK %s is AMBIGUOUS_SKIPPED — candidates: %s",
            cik,
            [row[0] for row in candidates],
        )
        return None, None, "AMBIGUOUS_SKIPPED"

    def _fallback_lookup(self, entity_name: str) -> str | None:
        """
        Attempt exact entity-name match against raw_symbols_fmp.

        Returns a ticker string or None.
        """
        if not entity_name or not entity_name.strip():
            return None

        result = self._con.execute(_FALLBACK_SQL, [entity_name.strip()]).fetchone()
        if result:
            return result[0]
        return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _is_non_common(security_type: str | None) -> bool:
    """Return True if security_type contains any non-common-share indicator."""
    if security_type is None:
        return False
    upper = security_type.upper()
    return any(nct in upper for nct in _NON_COMMON_TYPES)
