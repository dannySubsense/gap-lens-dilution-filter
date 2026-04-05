"""
Slice 1: Project Scaffold — Acceptance Tests

Done-when criteria verified:
- All required backend files exist
- All required frontend scaffold files exist
- Infrastructure files exist
- DilutionService imports cleanly
- ExternalAPIError imports cleanly
- .env contains required keys
- Source repo (gap-lens-dilution) is unmodified
- git was initialized in project root
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path("/home/d-tuned/projects/gap-lens-dilution-filter")
SOURCE_REPO = Path("/home/d-tuned/projects/gap-lens-dilution")


# ---------------------------------------------------------------------------
# AC-S1-01: Required backend files exist
# ---------------------------------------------------------------------------

BACKEND_FILES = [
    "app/__init__.py",
    "app/core/__init__.py",
    "app/core/config.py",
    "app/models/__init__.py",
    "app/models/responses.py",
    "app/services/__init__.py",
    "app/services/dilution.py",
    "app/utils/__init__.py",
    "app/utils/errors.py",
    "app/utils/formatting.py",
    "app/utils/validation.py",
    "requirements.txt",
]


@pytest.mark.parametrize("rel_path", BACKEND_FILES)
def test_backend_file_exists(rel_path):
    """Each required backend file must be present at its target path."""
    assert (PROJECT_ROOT / rel_path).exists(), (
        f"Missing backend file: {PROJECT_ROOT / rel_path}"
    )


# ---------------------------------------------------------------------------
# AC-S1-02: Required frontend scaffold files exist
# ---------------------------------------------------------------------------

FRONTEND_FILES = [
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/src/app/globals.css",
]


@pytest.mark.parametrize("rel_path", FRONTEND_FILES)
def test_frontend_scaffold_file_exists(rel_path):
    """Each required frontend scaffold file must be present at its target path."""
    assert (PROJECT_ROOT / rel_path).exists(), (
        f"Missing frontend scaffold file: {PROJECT_ROOT / rel_path}"
    )


# ---------------------------------------------------------------------------
# AC-S1-03: Infrastructure files exist
# ---------------------------------------------------------------------------

INFRA_FILES = [
    ".gitignore",
    ".env",
    "data/.gitkeep",
]


@pytest.mark.parametrize("rel_path", INFRA_FILES)
def test_infrastructure_file_exists(rel_path):
    """Each required infrastructure file must be present at its target path."""
    assert (PROJECT_ROOT / rel_path).exists(), (
        f"Missing infrastructure file: {PROJECT_ROOT / rel_path}"
    )


# ---------------------------------------------------------------------------
# AC-S1-04: DilutionService imports cleanly
# ---------------------------------------------------------------------------

def test_dilution_service_imports_cleanly():
    """DilutionService must be importable and resolve to a non-None class object."""
    # Ensure project root is on sys.path for the import
    root_str = str(PROJECT_ROOT)
    path_inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        path_inserted = True

    try:
        from app.services.dilution import DilutionService  # noqa: PLC0415
        assert DilutionService is not None
    finally:
        if path_inserted:
            sys.path.remove(root_str)


# ---------------------------------------------------------------------------
# AC-S1-05: ExternalAPIError imports cleanly
# ---------------------------------------------------------------------------

def test_external_api_error_imports_cleanly():
    """ExternalAPIError must be importable from app.utils.errors."""
    root_str = str(PROJECT_ROOT)
    path_inserted = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        path_inserted = True

    try:
        from app.utils.errors import ExternalAPIError  # noqa: PLC0415
        assert ExternalAPIError is not None
    finally:
        if path_inserted:
            sys.path.remove(root_str)


# ---------------------------------------------------------------------------
# AC-S1-06: .env contains required keys
# ---------------------------------------------------------------------------

REQUIRED_ENV_KEYS = [
    "FMP_API_KEY",
    "ASKEDGAR_API_KEY",
    "CLASSIFIER_NAME",
    "EDGAR_POLL_INTERVAL",
    "DUCKDB_PATH",
    "SCORE_NORMALIZATION_CEILING",
    "ADV_MIN_THRESHOLD",
]


@pytest.mark.parametrize("key", REQUIRED_ENV_KEYS)
def test_env_file_contains_required_key(key):
    """Each required environment variable key must appear in .env (value may be empty)."""
    env_path = PROJECT_ROOT / ".env"
    content = env_path.read_text()
    # Match lines of the form KEY= or KEY=value (ignoring comment lines)
    key_lines = [
        line for line in content.splitlines()
        if line.startswith(key + "=") or line.startswith(key + " =")
    ]
    assert key_lines, f"Required key '{key}' not found in .env"


# ---------------------------------------------------------------------------
# AC-S1-07: Source repo (gap-lens-dilution) is unmodified
# ---------------------------------------------------------------------------

def test_source_repo_is_unmodified():
    """The original gap-lens-dilution repository must have no staged or unstaged changes.

    Untracked files (??) are acceptable and are not treated as modifications.
    """
    result = subprocess.run(
        ["git", "-C", str(SOURCE_REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"git status failed in {SOURCE_REPO}: {result.stderr}"
    )

    disallowed_prefixes = ("M", "A", "D", " M", " D", " A")
    modified_lines = [
        line for line in result.stdout.splitlines()
        if any(line.startswith(prefix) for prefix in disallowed_prefixes)
    ]
    assert not modified_lines, (
        f"Source repo has modifications:\n" + "\n".join(modified_lines)
    )


# ---------------------------------------------------------------------------
# AC-S1-08: git was initialized in project root
# ---------------------------------------------------------------------------

def test_git_initialized_in_project_root():
    """A .git/ directory must exist at the project root."""
    assert (PROJECT_ROOT / ".git").is_dir(), (
        f"No .git directory found at {PROJECT_ROOT}"
    )
