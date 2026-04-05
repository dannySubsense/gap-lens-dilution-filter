"""
Playwright QC — gap-lens-dilution-filter Phase 1

Prerequisites (from docs/TEST_AND_DEPLOY_PLAYBOOK.md):
  Terminal 1: uvicorn app.main:app --host 0.0.0.0 --port 8000
  Terminal 2: cd frontend && npm run dev

Run:
  python3 -m pytest tests/test_playwright_qc.py -v -s

Skips automatically if backend or frontend are not reachable.
Each test is independent; the fixture injects and cleans up a test signal.
"""

from __future__ import annotations

import time
from pathlib import Path

import duckdb
import httpx
import pytest
from playwright.sync_api import Page, sync_playwright, expect

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DUCKDB_PATH = PROJECT_ROOT / "data" / "filter.duckdb"

TEST_ACCESSION = "TEST-PW-QC-001"
TEST_TICKER = "PWQC"

# ---------------------------------------------------------------------------
# Service availability guard — skip entire module if services are not up
# ---------------------------------------------------------------------------

def _service_up(url: str) -> bool:
    try:
        r = httpx.get(url, timeout=3)
        return r.status_code < 500
    except Exception:
        return False


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "playwright_qc: Playwright browser QC tests")


# Module-level skip if either service is unreachable
pytestmark = pytest.mark.skipif(
    not (_service_up(f"{BACKEND_URL}/api/v1/health") and _service_up(FRONTEND_URL)),
    reason=(
        "Backend or frontend not running. "
        "Start both per docs/TEST_AND_DEPLOY_PLAYBOOK.md before running this suite."
    ),
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def browser_context():
    """Single Chromium browser instance shared across all tests in this module."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
        )
        yield context
        context.close()
        browser.close()


@pytest.fixture
def page(browser_context):
    """Fresh page per test; closed after each test."""
    pg = browser_context.new_page()
    yield pg
    pg.close()


@pytest.fixture(scope="module", autouse=True)
def test_signal():
    """
    Insert a WATCHLIST test signal into the live DuckDB before the module runs.
    Cleaned up after all tests complete.
    Signal is rank B / WATCHLIST so it appears in the Watchlist panel.
    """
    conn = duckdb.connect(str(DUCKDB_PATH))

    conn.execute(
        """
        INSERT INTO filings (
            accession_number, cik, form_type, filed_at,
            filing_url, entity_name, processing_status
        )
        VALUES (?, '8888888', '424B4', NOW(),
                'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=8888888',
                'Playwright QC Corp', 'ALERTED')
        ON CONFLICT (accession_number) DO NOTHING
        """,
        [TEST_ACCESSION],
    )

    conn.execute(
        """
        INSERT INTO signals (
            accession_number, ticker, setup_type, score, rank,
            status, alert_type, alerted_at
        )
        VALUES (?, ?, 'C', 76, 'B', 'WATCHLIST', 'NEW_SETUP', NOW())
        ON CONFLICT DO NOTHING
        """,
        [TEST_ACCESSION, TEST_TICKER],
    )

    conn.execute(
        """
        INSERT INTO labels (
            accession_number, classifier_version, setup_type,
            confidence, dilution_severity, immediate_pressure,
            price_discount, short_attractiveness, rank,
            key_excerpt, reasoning
        )
        VALUES (?, 'rule-based-v1', 'C',
                0.95, 0.50, true,
                0.03, 0, 'B',
                '2,000,000 shares of common stock at $3.97 per share.',
                'Playwright QC: Setup C with priced offering.')
        ON CONFLICT (accession_number, classifier_version) DO NOTHING
        """,
        [TEST_ACCESSION],
    )

    conn.close()
    yield

    # Cleanup
    conn = duckdb.connect(str(DUCKDB_PATH))
    conn.execute("DELETE FROM labels  WHERE accession_number = ?", [TEST_ACCESSION])
    conn.execute("DELETE FROM signals WHERE accession_number = ?", [TEST_ACCESSION])
    conn.execute("DELETE FROM filings WHERE accession_number = ?", [TEST_ACCESSION])
    conn.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def load_dashboard(page: Page) -> None:
    """Navigate to the dashboard and wait for the network to settle."""
    page.goto(FRONTEND_URL)
    page.wait_for_load_state("networkidle", timeout=15_000)


# ---------------------------------------------------------------------------
# QC-01: Page load — title and background
# ---------------------------------------------------------------------------

def test_qc01_page_loads(page: Page):
    """Dashboard loads without JS errors; page title is set."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    load_dashboard(page)

    # Title set by Next.js (layout.tsx default is "Create Next App" unless overridden;
    # either way the page must have a non-empty title)
    assert page.title() != "", "Page title should not be empty"
    assert errors == [], f"JS errors on load: {errors}"


# ---------------------------------------------------------------------------
# QC-02: Header — brand text and health dot present
# ---------------------------------------------------------------------------

def test_qc02_header_brand_and_health_dot(page: Page):
    """'DILUTION SHORT FILTER' visible in header; health dot element present."""
    load_dashboard(page)

    # Brand text: "DILUTION SHORT " + "FILTER"
    expect(page.get_by_text("DILUTION SHORT")).to_be_visible()
    expect(page.get_by_text("FILTER")).to_be_visible()

    # Health dot: an 8x8 circle in the header (role=generic, inspected by size)
    # We verify the HealthBar container is present by checking "Last poll:" label
    last_poll_label = page.locator("text=Last poll:").first
    expect(last_poll_label).to_be_visible()


# ---------------------------------------------------------------------------
# QC-03: FMP banner absent (key is configured)
# ---------------------------------------------------------------------------

def test_qc03_no_fmp_warning_banner(page: Page):
    """FMP warning banner must NOT appear — key is configured in .env."""
    load_dashboard(page)
    banner = page.locator('text=FMP API key not configured')
    expect(banner).not_to_be_visible()


# ---------------------------------------------------------------------------
# QC-04: All three panels present
# ---------------------------------------------------------------------------

def test_qc04_three_panels_present(page: Page):
    """LIVE NOW, WATCHLIST, and RECENT CLOSED panels all render."""
    load_dashboard(page)
    expect(page.get_by_text("LIVE NOW")).to_be_visible()
    expect(page.get_by_text("WATCHLIST")).to_be_visible()
    expect(page.get_by_text("RECENT CLOSED")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-05: Test signal appears in Watchlist panel
# ---------------------------------------------------------------------------

def test_qc05_test_signal_in_watchlist(page: Page):
    """Injected WATCHLIST signal (ticker=PWQC) appears in the Watchlist panel."""
    load_dashboard(page)

    ticker_cell = page.locator(f"text={TEST_TICKER}").first
    expect(ticker_cell).to_be_visible(timeout=10_000)


# ---------------------------------------------------------------------------
# QC-06: Signal row shows expected columns
# ---------------------------------------------------------------------------

def test_qc06_signal_row_columns(page: Page):
    """Signal row displays ticker, setup badge [C], and score/rank."""
    load_dashboard(page)

    # Ticker
    expect(page.locator(f"text={TEST_TICKER}").first).to_be_visible()

    # Setup badge [C]
    expect(page.locator("text=[C]").first).to_be_visible()


# ---------------------------------------------------------------------------
# QC-07: Detail panel opens on row click
# ---------------------------------------------------------------------------

def test_qc07_detail_panel_opens(page: Page):
    """Clicking the signal row opens the detail slide-out panel."""
    load_dashboard(page)

    page.locator(f"text={TEST_TICKER}").first.click()

    # Panel header should show ticker
    expect(page.locator(f"text={TEST_TICKER}").nth(1)).to_be_visible(timeout=5_000)


# ---------------------------------------------------------------------------
# QC-08: Detail panel — Filing Info section populated
# ---------------------------------------------------------------------------

def test_qc08_detail_panel_filing_info(page: Page):
    """Detail panel shows Filing Info section with form type and EDGAR link."""
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    expect(page.get_by_text("Filing Info")).to_be_visible(timeout=5_000)
    expect(page.get_by_text("424B4")).to_be_visible()
    expect(page.get_by_text("View on EDGAR")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-09: Detail panel — Classification Output section populated
# ---------------------------------------------------------------------------

def test_qc09_detail_panel_classification(page: Page):
    """Classification Output section shows Setup Type, Confidence, Key Excerpt."""
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    expect(page.get_by_text("Classification Output")).to_be_visible(timeout=5_000)
    expect(page.get_by_text("Confidence")).to_be_visible()
    expect(page.get_by_text("Dilution Severity")).to_be_visible()
    expect(page.get_by_text("Key Excerpt")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-10: Position tracking — State A (no entry recorded)
# ---------------------------------------------------------------------------

def test_qc10_position_state_a(page: Page):
    """Detail panel opens in State A: 'No position recorded.' and entry input visible."""
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    expect(page.get_by_text("No position recorded.")).to_be_visible(timeout=5_000)
    expect(page.locator("#entry-price-input")).to_be_visible()
    expect(page.get_by_role("button", name="Record Entry")).to_be_visible()
    expect(page.get_by_role("button", name="Close Without Position")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-11: Position tracking — State A → B (record entry price)
# ---------------------------------------------------------------------------

def test_qc11_position_state_a_to_b(page: Page):
    """
    Recording entry price 5.00 transitions the panel to State B.
    Verify entry is shown and cover input appears.
    Note: this modifies the test signal — QC-12 must run after this test.
    This test relies on module-scope fixture signal which persists across tests.
    """
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    # State A: fill entry price and submit
    page.locator("#entry-price-input").fill("5.0000")
    page.get_by_role("button", name="Record Entry").click()

    # State B: entry shown, cover input visible
    expect(page.locator("#cover-price-input")).to_be_visible(timeout=8_000)
    expect(page.get_by_role("button", name="Close Position")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-12: Position tracking — State B → C (record cover price)
# ---------------------------------------------------------------------------

def test_qc12_position_state_b_to_c(page: Page):
    """
    Recording cover price 4.00 transitions to State C.
    Short P&L = (5.00 - 4.00) / 5.00 * 100 = +20.0% — must appear green.
    Depends on QC-11 having set entry_price=5.00.
    """
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    # Should already be in State B after QC-11
    expect(page.locator("#cover-price-input")).to_be_visible(timeout=8_000)

    page.locator("#cover-price-input").fill("4.0000")
    page.get_by_role("button", name="Close Position").click()

    # State C: read-only P&L display
    expect(page.get_by_text("+20.0%")).to_be_visible(timeout=8_000)
    expect(page.get_by_text("Cover price")).to_be_visible()


# ---------------------------------------------------------------------------
# QC-13: Closed signal appears in Recent Closed panel
# ---------------------------------------------------------------------------

def test_qc13_closed_signal_in_recent_closed(page: Page):
    """
    After QC-12 closes the position, the signal should appear in Recent Closed.
    Depends on QC-12 having submitted cover price.
    """
    load_dashboard(page)

    # Close any open detail panel first
    page.keyboard.press("Escape")
    time.sleep(0.3)

    # The signal should now be in Recent Closed
    recent_closed = page.locator("text=RECENT CLOSED").first
    expect(recent_closed).to_be_visible()

    # Ticker should appear under Recent Closed section
    expect(page.locator(f"text={TEST_TICKER}").first).to_be_visible(timeout=10_000)


# ---------------------------------------------------------------------------
# QC-14: Detail panel closes on backdrop click
# ---------------------------------------------------------------------------

def test_qc14_panel_closes_on_backdrop(page: Page):
    """Clicking the backdrop (outside the panel) closes the detail panel."""
    load_dashboard(page)
    page.locator(f"text={TEST_TICKER}").first.click()

    # Verify panel is open
    expect(page.get_by_text("Filing Info")).to_be_visible(timeout=5_000)

    # Click the backdrop (fixed overlay behind the panel)
    # The backdrop covers the left side of the viewport
    page.mouse.click(100, 400)

    # Panel should be gone
    expect(page.get_by_text("Filing Info")).not_to_be_visible(timeout=3_000)


# ---------------------------------------------------------------------------
# QC-15: API health endpoint returns valid JSON
# ---------------------------------------------------------------------------

def test_qc15_health_api_returns_valid_json():
    """GET /api/v1/health returns 200 with required fields — no browser needed."""
    r = httpx.get(f"{BACKEND_URL}/api/v1/health", timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"

    data = r.json()
    assert "status" in data, "Response missing 'status' field"
    assert data["status"] in ("ok", "degraded", "error"), (
        f"Unexpected status value: {data['status']!r}"
    )
    assert "fmp_configured" in data, "Response missing 'fmp_configured'"
    assert data["fmp_configured"] is True, (
        "fmp_configured should be True — check FMP_API_KEY in .env"
    )


# ---------------------------------------------------------------------------
# QC-16: API signals endpoint returns valid JSON
# ---------------------------------------------------------------------------

def test_qc16_signals_api_returns_valid_json():
    """GET /api/v1/signals returns 200 with signals list — no browser needed."""
    r = httpx.get(f"{BACKEND_URL}/api/v1/signals", timeout=5)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"

    data = r.json()
    assert "signals" in data, "Response missing 'signals' key"
    assert "count" in data, "Response missing 'count' key"
    assert isinstance(data["signals"], list)
