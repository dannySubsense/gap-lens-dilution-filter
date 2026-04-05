"""
UnderwriterExtractor — Slice 7

Extracts named financial intermediaries (underwriters, placement agents, sales
agents) from filing plain text.  Normalizes firm names against a static JSON
config and returns a list[ParticipantRecord].

Section isolation strategy (per 02-ARCHITECTURE.md §6.5):
  - 424B4, S-1  : "Plan of Distribution" section + cover page (first 3 000 chars)
  - 8-K         : full body (equity-distribution agreement usually in first 5 000 chars)
  - 424B3       : NOT in Phase R1 discovery set — dead-code branch (no raise)
  - 424B2       : cover page region (first 3 000 chars)
  - 13D/A       : full body (best-effort)
  - S-3         : no extraction — skip
  - other       : no extraction — skip
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from research.pipeline.dataclasses import FetchedFiling, ParticipantRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex pattern constants (from 02-ARCHITECTURE.md §6.5)
# ---------------------------------------------------------------------------

LEAD_UW_PATTERNS: list[str] = [
    r"(?:lead|sole|book-running)\s+(?:managing\s+)?underwriter[,\s]+([A-Z][^,\n]{3,60})",
    r"([A-Z][^,\n]{3,60})\s+is\s+(?:acting\s+as\s+)?(?:the\s+)?(?:sole\s+)?(?:book-running\s+)?managing\s+underwriter",
    r"([A-Z][^,\n]{3,60}),?\s+as\s+(?:the\s+)?(?:sole\s+)?(?:lead\s+)?(?:book-running\s+)?underwriter",
]

# Note: the first co-manager pattern uses [^\n]{3,120} (allows dots) so that
# firm names like "Oppenheimer & Co." are captured within a comma-separated list.
CO_MANAGER_PATTERNS: list[str] = [
    r"co-(?:managers?|leads?)[:\s]+([A-Z][^\n]{3,120})",
    r"([A-Z][^,\n]{3,60}),?\s+as\s+co-manager",
]

SALES_AGENT_PATTERNS: list[str] = [
    r"(?:sales\s+agent|placement\s+agent)[,\s]+([A-Z][^,\n]{3,60})",
    r"([A-Z][^,\n]{3,60}),?\s+as\s+(?:our\s+)?(?:sales|placement)\s+agent",
    r"equity\s+distribution\s+agreement\s+with\s+([A-Z][^,\n]{3,60})",
]

# Header pattern to locate "Plan of Distribution" section
_PLAN_OF_DISTRIBUTION_RE = re.compile(r"(?i)plan\s+of\s+distribution")

# Pattern for the *next* all-caps section header after Plan of Distribution
_NEXT_SECTION_RE = re.compile(r"\n[A-Z][A-Z\s]{3,}\n")

# Trailing legal suffix normalization (strip before table lookup)
_LEGAL_SUFFIXES: tuple[str, ...] = (
    ", LLC",
    ", Inc.",
    ", Inc",
    "& Co.",
    "& Co",
    ", L.P.",
    ", Ltd.",
    ", Ltd",
    ", Corp.",
    ", Corp",
)

# Cover page size constants
_COVER_PAGE_CHARS = 3_000
_8K_SCAN_CHARS = 5_000  # 8-K: full body; constant documents the intent

# Roles
_ROLE_LEAD_UW = "lead_underwriter"
_ROLE_CO_MANAGER = "co_manager"
_ROLE_SALES_AGENT = "sales_agent"
_ROLE_PLACEMENT_AGENT = "placement_agent"

# snippet window
_SNIPPET_CHARS = 300


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _strip_legal_suffix(name: str) -> str:
    """Strip common trailing legal-entity suffixes for normalization lookup."""
    stripped = name.strip()
    for suffix in _LEGAL_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break
    return stripped


def _get_snippet(text: str, match: re.Match) -> str:
    """Return up to _SNIPPET_CHARS characters of context around a regex match."""
    start = max(0, match.start() - 50)
    end = min(len(text), match.end() + 250)
    return text[start:end][:_SNIPPET_CHARS]


def _isolate_text_region(plain_text: str, form_type: str) -> Optional[str]:
    """
    Return the text region to scan based on form_type.

    Returns None when the form type should be skipped entirely (S-3, unknown).
    """
    ft = form_type.upper().strip()

    if ft in ("S-3", "S-3/A"):
        # No extraction for S-3
        return None

    if ft in ("424B3",):
        # 424B3 is NOT in the Phase R1 discovery set — dead-code branch.
        # Return None silently (no raise).
        return None

    if ft in ("424B4", "S-1", "S-1/A"):
        # Plan of Distribution section + cover page
        pod_match = _PLAN_OF_DISTRIBUTION_RE.search(plain_text)
        if pod_match:
            pod_start = pod_match.start()
            next_section = _NEXT_SECTION_RE.search(plain_text, pod_match.end())
            pod_end = next_section.start() if next_section else len(plain_text)
            pod_text = plain_text[pod_start:pod_end]
        else:
            pod_text = ""
        cover_text = plain_text[:_COVER_PAGE_CHARS]
        # Combine; deduplication handles any overlap
        return cover_text + "\n" + pod_text

    if ft == "8-K":
        # Scan full body (distribution agreement usually in first 5 000 chars,
        # but spec says "full body" — scan all of it)
        return plain_text

    if ft == "424B2":
        return plain_text[:_COVER_PAGE_CHARS]

    if ft in ("13D/A", "SC 13D/A", "SC 13D"):
        return plain_text

    # All other form types: no extraction
    return None


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------

class UnderwriterExtractor:
    """
    Extracts and normalizes underwriter/placement-agent firm names from
    a FetchedFiling.

    Parameters
    ----------
    normalization_config_path:
        Path to the JSON file mapping raw name variants to canonical names.
        Format: {"raw variant": "canonical name"}
        Missing or empty file: logs a warning; all names stored verbatim with
        is_normalized=False.  No exception is raised.
    """

    def __init__(self, normalization_config_path: Path) -> None:
        self.normalization_map: dict[str, str] = {}
        self.config_loaded: bool = False
        self.config_entry_count: int = 0

        try:
            text = normalization_config_path.read_text(encoding="utf-8")
            raw: dict = json.loads(text)
            if raw:
                # Normalise keys to lower-case stripped for case-insensitive lookup
                self.normalization_map = {k.strip().lower(): v for k, v in raw.items()}
                self.config_loaded = True
                self.config_entry_count = len(self.normalization_map)
            else:
                logger.warning(
                    "underwriter_normalization.json is empty — all names stored verbatim."
                )
        except FileNotFoundError:
            logger.warning(
                "Normalization config not found at %s — "
                "all underwriter names will be stored verbatim (is_normalized=False).",
                normalization_config_path,
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to load normalization config at %s: %s — "
                "all underwriter names will be stored verbatim.",
                normalization_config_path,
                exc,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, filing: FetchedFiling) -> list[ParticipantRecord]:
        """
        Extract ParticipantRecord objects from a filing.

        Returns an empty list when:
        - form_type is S-3, 424B3, or any non-covered type
        - plain_text is None or empty
        - no patterns match
        """
        if not filing.plain_text:
            return []

        region = _isolate_text_region(filing.plain_text, filing.form_type)
        if region is None:
            return []

        records: list[ParticipantRecord] = []
        seen: set[tuple[str, str]] = set()  # (firm_name, role) deduplication

        # --- Lead underwriters ---
        for pattern in LEAD_UW_PATTERNS:
            for m in re.finditer(pattern, region):
                raw_name = m.group(1).strip()
                firm_name, is_normalized = self._normalize(raw_name)
                key = (firm_name, _ROLE_LEAD_UW)
                if key not in seen:
                    seen.add(key)
                    records.append(ParticipantRecord(
                        accession_number=filing.accession_number,
                        firm_name=firm_name,
                        role=_ROLE_LEAD_UW,
                        is_normalized=is_normalized,
                        raw_text_snippet=_get_snippet(region, m),
                    ))

        # --- Co-managers ---
        for pattern in CO_MANAGER_PATTERNS:
            for m in re.finditer(pattern, region):
                raw_group = m.group(1).strip()
                # Multi co-manager: first pattern may yield a comma-separated list
                names = [n.strip() for n in raw_group.split(",") if n.strip()]
                for raw_name in names:
                    if not raw_name:
                        continue
                    firm_name, is_normalized = self._normalize(raw_name)
                    key = (firm_name, _ROLE_CO_MANAGER)
                    if key not in seen:
                        seen.add(key)
                        records.append(ParticipantRecord(
                            accession_number=filing.accession_number,
                            firm_name=firm_name,
                            role=_ROLE_CO_MANAGER,
                            is_normalized=is_normalized,
                            raw_text_snippet=_get_snippet(region, m),
                        ))

        # --- Sales / placement agents ---
        for pattern in SALES_AGENT_PATTERNS:
            for m in re.finditer(pattern, region):
                raw_name = m.group(1).strip()
                firm_name, is_normalized = self._normalize(raw_name)

                # Determine role from the matched text context
                matched_context = m.group(0).lower()
                if "placement" in matched_context:
                    role = _ROLE_PLACEMENT_AGENT
                else:
                    role = _ROLE_SALES_AGENT

                key = (firm_name, role)
                if key not in seen:
                    seen.add(key)
                    records.append(ParticipantRecord(
                        accession_number=filing.accession_number,
                        firm_name=firm_name,
                        role=role,
                        is_normalized=is_normalized,
                        raw_text_snippet=_get_snippet(region, m),
                    ))

        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, raw_name: str) -> tuple[str, bool]:
        """
        Look up raw_name in the normalization map.

        Strips trailing legal suffixes before the lookup (case-insensitive).
        Returns (canonical_name, is_normalized).
        """
        lookup_key = _strip_legal_suffix(raw_name).lower()
        canonical = self.normalization_map.get(lookup_key)
        if canonical is not None:
            return canonical, True
        # Also try the raw name itself (without suffix stripping)
        canonical = self.normalization_map.get(raw_name.strip().lower())
        if canonical is not None:
            return canonical, True
        return raw_name, False
