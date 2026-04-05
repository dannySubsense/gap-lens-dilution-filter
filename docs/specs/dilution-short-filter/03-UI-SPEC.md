# UI Specification: Dilution Short Filter Dashboard

- **Project**: gap-lens-dilution-filter
- **Phase**: Phase 1 (Rule-Based Pipeline)
- **Status**: APPROVED FOR IMPLEMENTATION
- **Date**: 2026-04-04
- **Author**: @ui-spec-writer
- **Based On**: 01-REQUIREMENTS.md, 02-ARCHITECTURE.md, gap-lens-dilution phase2 design system

---

## 1. Design System (Inherited — No Modifications)

All tokens are inherited from gap-lens-dilution phase2. They are repeated here as the authoritative reference for this project; do not derive them from the parent project at build time.

### 1.1 Color Palette

| CSS Token | Hex | Usage |
|-----------|-----|-------|
| `--bg-primary` | #1a1a1a | Page background |
| `--bg-card` | #2d2d2d | Panel and card backgrounds |
| `--bg-card-hover` | #333333 | Row hover state |
| `--bg-input` | #252525 | Input field background |
| `--text-primary` | #ffffff | Ticker symbols, values, headings |
| `--text-secondary` | #a0a0a0 | Labels, column headers, metadata |
| `--text-muted` | #666666 | Placeholder text, disabled fields |
| `--border-color` | #444444 | Card borders, section dividers |
| `--border-input` | #555555 | Input field borders |
| `--accent-cyan` | #00bcd4 | App title accent, EDGAR links |
| `--accent-cyan-hover` | #00acc1 | Cyan hover state |
| `--positive` | #4caf50 | Price moves favorable to short, profitable P&L |
| `--negative` | #f44336 | Price moves against short, loss P&L, error states |
| `--warning` | #ff9800 | Warning status, poll health degraded |
| `--rank-a` | #f44336 | Rank A badge (red) |
| `--rank-b` | #ff9800 | Rank B badge (orange) |
| `--rank-c` | #ffc107 | Rank C badge (yellow) |
| `--rank-d` | #9e9e9e | Rank D badge (gray) |
| `--rank-e` | #ce93d8 | Rank E badge (purple) |

Note: `--rank-a` through `--rank-e` are the setup type badges. Rank A/B/C/D score-rank badges use the same color mapping by convention (score rank A = red, B = orange, C = yellow, D = gray).

### 1.2 Typography

| Element | Font Family | Size | Weight | Color |
|---------|-------------|------|--------|-------|
| App title | System UI / Segoe UI | 16px | 700 | `--text-primary` / `--accent-cyan` |
| Section header | System UI | 14px | 600 | `--text-primary` |
| Column label | System UI | 11px | 400 | `--text-secondary` |
| Data value | Consolas / Monospace | 14px | 400 | `--text-primary` |
| Ticker symbol | Consolas / Monospace | 14px | 700 | `--text-primary` |
| Badge text | System UI | 11px | 700 | `--text-primary` |
| Status label | System UI | 12px | 400 | `--text-secondary` |
| Elapsed time | System UI | 11px | 400 | `--text-secondary` |
| Blockquote / excerpt | Consolas / Monospace | 12px | 400 | `--text-secondary` |
| Error / warning | System UI | 12px | 600 | `--negative` or `--warning` |

### 1.3 Spacing System

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | 4px | Badge padding, tight row gaps |
| `--space-sm` | 8px | Row padding, cell gaps |
| `--space-md` | 12px | Section interior padding |
| `--space-lg` | 16px | Card padding, panel headers |
| `--space-xl` | 24px | Between major panels |
| `--space-xxl` | 32px | Page-level vertical padding |

### 1.4 Shape and Elevation

| Element | Border Radius | Shadow |
|---------|---------------|--------|
| Panel card | 6px | `0 2px 4px rgba(0,0,0,0.2)` |
| Badge / pill | 4px | none |
| Input field | 4px | none |
| Button | 4px | none |
| Modal overlay | 8px | `0 4px 8px rgba(0,0,0,0.3)` |

### 1.5 Setup Type Badge Color Map

| Setup Type | Badge Color Token | Badge Color Hex |
|------------|-------------------|-----------------|
| A | `--rank-a` | #f44336 (red) |
| B | `--rank-b` | #ff9800 (orange) |
| C | `--rank-c` | #ffc107 (yellow) |
| D | `--rank-d` | #9e9e9e (gray) |
| E | `--rank-e` | #ce93d8 (purple) |

Badge renders as: `[A]` with 4px horizontal padding, 2px vertical padding, 4px border radius, and badge background color at 20% opacity with full-opacity border and text.

---

## 2. Screen Inventory

| Screen | Purpose | Entry Point | Component |
|--------|---------|-------------|-----------|
| Main Dashboard | Auto-refreshing feed of all active and closed setups | App load (root `/`) | `page.tsx` |
| Setup Detail Panel | Full classification output and position tracking for one signal | Click any signal row | `SetupDetailModal.tsx` |

There is no multi-page navigation. Both views exist within the single-page Next.js app. The Setup Detail Panel overlays the Main Dashboard.

---

## 3. Main Dashboard Layout

### 3.1 Viewport

| Property | Value |
|----------|-------|
| Optimal width | 960px |
| Minimum width | 800px |
| Layout type | Fixed-width centered, vertical scroll |
| Page background | `--bg-primary` (#1a1a1a) |

### 3.2 Full Layout Structure

```
┌──────────────────────────────────────────────────────────────────┐
│  HEADER BAR  (height: 48px, bg: --bg-card, border-bottom: 1px)   │
│  [App Title]                    [Last poll: 14s ago]  [● green]  │
├──────────────────────────────────────────────────────────────────┤
│  MAIN CONTENT  (padding: 24px horizontal)                        │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  LIVE NOW PANEL  (bg: --bg-card, border: --border-color)   │  │
│  │  Section header: "● LIVE NOW  (2)"                         │  │
│  │  ──────────────────────────────────────────────────────    │  │
│  │  [SignalRow] TICKER  [A]  Score:94  -12%  2h ago           │  │
│  │  [SignalRow] TICKER  [C]  Score:87   -8%  4h ago           │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  WATCHLIST PANEL  (bg: --bg-card, border: --border-color)  │  │
│  │  Section header: "● WATCHLIST  (5)"                        │  │
│  │  ──────────────────────────────────────────────────────    │  │
│  │  [SignalRow] TICKER  [B]  Score:72  Awaiting pricing  2d   │  │
│  │  [SignalRow] TICKER  [D]  Score:68  ATM active         6h  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  RECENT CLOSED PANEL                                       │  │
│  │  Section header: "● RECENT CLOSED  (3)"                    │  │
│  │  ──────────────────────────────────────────────────────    │  │
│  │  [SignalRow] TICKER  [A]  +18%  $5.20 → $4.26  MANUAL     │  │
│  │  [SignalRow] TICKER  [B]  No position  TIME_EXCEEDED       │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 3.3 Header Bar

```
┌──────────────────────────────────────────────────────────────────┐
│  DILUTION SHORT FILTER          Last poll: 14s ago   [●]         │
└──────────────────────────────────────────────────────────────────┘
```

| Element | Spec |
|---------|------|
| Container height | 48px |
| Container background | `--bg-card` (#2d2d2d) |
| Border bottom | 1px solid `--border-color` |
| Left content | App title: "DILUTION SHORT" in `--text-primary`, "FILTER" in `--accent-cyan`. 16px bold. |
| Right content | Status cluster (see Section 6) |
| Padding | 16px horizontal |
| No ticker input | Ticker search is out of scope; header has no input field |

### 3.4 Panel Structure (Shared by All Three Sections)

Each of the three sections (Live Now, Watchlist, Recent Closed) is a card with:

| Property | Value |
|----------|-------|
| Background | `--bg-card` |
| Border | 1px solid `--border-color` |
| Border radius | 6px |
| Padding | 16px |
| Vertical margin | 16px between panels |

**Panel header row:**

```
[status dot]  [SECTION LABEL]  [(count)]
```

| Element | Spec |
|---------|------|
| Status dot (Live Now) | 8px circle, `--negative` (#f44336), pulsing animation when count > 0 |
| Status dot (Watchlist) | 8px circle, `--warning` (#ff9800), static |
| Status dot (Recent Closed) | 8px circle, `--positive` (#4caf50), static |
| Section label | 14px semibold, `--text-primary`, uppercase |
| Count | 14px, `--text-secondary`, parenthesized |
| Divider below header | 1px solid `--border-color`, full width, 8px margin below |

---

## 4. Signal Row Layout

`SignalRow` is a single shared component rendered differently depending on which panel it appears in. The panel type is passed as a prop to control which fields are shown.

### 4.1 Live Now Row

```
┌──────────────────────────────────────────────────────────────────┐
│  TICKER   [A]   Score: 94   -12.4%   2h ago                      │
└──────────────────────────────────────────────────────────────────┘
```

| Column | Data Source | Format | Color |
|--------|-------------|--------|-------|
| Ticker | `signal.ticker` | Uppercase, monospace 14px bold | `--text-primary` |
| Setup type badge | `signal.setup_type` | `[A]` pill | Badge color per type (see 1.5) |
| Score | `signal.score` | `Score: 94`, monospace 14px | `--text-primary` |
| Price move | `signal.price_move_pct` | `+X.X%` or `-X.X%`, monospace 14px | Negative pct = `--positive` (favorable short); positive pct = `--negative` (moving against) |
| Elapsed time | `signal.elapsed_seconds` | `2h ago`, `14m ago`, `just now` | `--text-secondary` 11px |

Column widths (proportional, flex layout):
- Ticker: 80px fixed
- Badge: 36px fixed
- Score: 90px fixed
- Price move: 80px fixed
- Elapsed: remaining space, right-aligned

### 4.2 Watchlist Row

```
┌──────────────────────────────────────────────────────────────────┐
│  TICKER   [B]   Score: 72   Awaiting pricing    2d ago           │
└──────────────────────────────────────────────────────────────────┘
```

| Column | Data Source | Format | Color |
|--------|-------------|--------|-------|
| Ticker | `signal.ticker` | Uppercase, monospace 14px bold | `--text-primary` |
| Setup type badge | `signal.setup_type` | `[B]` pill | Badge color per type |
| Score | `signal.score` | `Score: 72` | `--text-primary` |
| Status label | `signal.status` + derived from context | Human-readable (see mapping below) | `--text-secondary` |
| Elapsed time | `signal.elapsed_seconds` | `2d ago` | `--text-secondary` 11px |

**Status label mapping** (derived from `signal.status` + `signal.alert_type`):

| Condition | Label |
|-----------|-------|
| `setup_type == "D"` | "ATM active" |
| `alert_type == "SETUP_UPDATE"` | "Updated" |
| `alert_type == "NEW_SETUP"` and score < 70 | "Awaiting pricing" |
| `alert_type == "NEW_SETUP"` and score >= 70 | "Monitoring" |

### 4.3 Recent Closed Row

```
┌──────────────────────────────────────────────────────────────────┐
│  TICKER   [A]   +18.3%   $5.20 → $4.26   MANUAL                 │
└──────────────────────────────────────────────────────────────────┘
```

| Column | Data Source | Format | Color |
|--------|-------------|--------|-------|
| Ticker | `signal.ticker` | Uppercase, monospace 14px bold | `--text-primary` |
| Setup type badge | `signal.setup_type` | `[A]` pill | Badge color per type |
| P&L | `signal.pnl_pct` | `+18.3%` or `–4.1%` or `—` | `--positive` if profitable, `--negative` if loss, `--text-muted` if null |
| Entry / cover | `signal.entry_price`, `signal.cover_price` | `$5.20 → $4.26` or `No position` | Monospace 12px, `--text-secondary`; "No position" in `--text-muted` |
| Close reason | `signal.close_reason` | `MANUAL` or `TIME_EXCEEDED` | `--text-muted` 11px |

### 4.4 Row Shared Behaviors

| State | Visual |
|-------|--------|
| Default | Background `--bg-card`, no border highlight |
| Hover | Background `--bg-card-hover` (#333333), cursor: pointer |
| Active (click pressed) | Background `#3a3a3a`, no other change |
| New arrival (Live Now only) | Row background pulses from `#1a3a3a` (teal-dark) to `--bg-card` over 3 seconds, once on mount |

Clicking any row opens the Setup Detail Panel for that signal. The entire row is the click target.

---

## 5. Setup Detail Panel

Opens as a slide-in panel from the right edge. It overlays the main dashboard behind a semi-transparent backdrop.

### 5.1 Panel Container

| Property | Value |
|----------|-------|
| Width | 480px |
| Position | Fixed, right: 0, top: 0, bottom: 0 |
| Background | `--bg-card` (#2d2d2d) |
| Border left | 1px solid `--border-color` |
| Shadow | `0 0 24px rgba(0,0,0,0.5)` |
| Backdrop | `rgba(0,0,0,0.4)` full-page overlay behind panel |
| Overflow | Vertical scroll internally |
| Z-index | Above main content |

Close triggers: click the X button in the panel header, or click the backdrop.

### 5.2 Panel Layout Structure

```
┌────────────────────────────────────────────┐
│  PANEL HEADER                              │
│  [TICKER]  [A badge]  Company name    [X]  │
├────────────────────────────────────────────┤
│  FILING INFO                               │
│  Form: 424B2   Filed: 2026-04-04           │
│  EDGAR: [link]                             │
├────────────────────────────────────────────┤
│  CLASSIFICATION OUTPUT                     │
│  Setup Type        [A]                     │
│  Confidence        100%                    │
│  Dilution Severity 32.4% of float          │
│  Immediate Pressure Yes                    │
│  Price Discount    -14.2%                  │
│  Score             94  [A rank badge]      │
│                                            │
│  Key Excerpt                               │
│  ┌──────────────────────────────────────┐  │
│  │ "...the Company intends to offer..."  │  │
│  └──────────────────────────────────────┘  │
│  Reasoning:                                │
│  [one-sentence text]                       │
├────────────────────────────────────────────┤
│  MARKET DATA SNAPSHOT                      │
│  Price at alert    $4.82                   │
│  Current price     $4.23   (-12.4%)        │
│  Float             18.5M shares            │
│  Market cap        $89.2M                  │
│  ADV               $1.4M                   │
├────────────────────────────────────────────┤
│  POSITION TRACKING                         │
│  [state-dependent — see Section 5.4]       │
└────────────────────────────────────────────┘
```

#### Panel Header

| Element | Data Source | Format |
|---------|-------------|--------|
| Ticker symbol | `signal.ticker` | Uppercase, monospace 14px bold, `--text-primary` |
| Setup type badge | `signal.setup_type` | Badge pill per Section 1.5 |
| Company name | `SignalDetailResponse.entity_name` | 14px, `--text-secondary`, rendered after the badge |
| Close button | — | [X] icon, right-aligned |

Company name is populated from the `entity_name` field in `SignalDetailResponse`. If `entity_name` is null (e.g., for filings processed before this field was added), display only the ticker symbol in the header. Do not fall back to a placeholder like "Unknown" — simply omit the name.

### 5.3 Panel Sections

#### Filing Info Section

| Field | Data Source | Format |
|-------|-------------|--------|
| Form type | `filing.form_type` | E.g. "424B2", label in `--text-secondary`, value in monospace |
| Filed date | `filing.filed_at` | `YYYY-MM-DD HH:MM UTC` |
| EDGAR link | `filing.filing_url` | Text "View on EDGAR", color `--accent-cyan`, opens new tab |

#### Classification Output Section

| Field | Data Source | Format |
|-------|-------------|--------|
| Setup Type | `classification.setup_type` | Badge (same pill style as row) |
| Confidence | `classification.confidence` | Percentage: `100%` or `73%` |
| Dilution Severity | `classification.dilution_severity` | `X.X% of float` |
| Immediate Pressure | `classification.immediate_pressure` | `Yes` in `--warning` / `No` in `--text-secondary` |
| Price Discount | `classification.price_discount` | `-X.X%` or `N/A` |
| Score + Rank | `signal.score`, `signal.rank` | Numeric score followed by rank badge; e.g. `94  [A]` |
| Key Excerpt | `classification.key_excerpt` | Blockquote: left border 3px `--accent-cyan`, italic, monospace 12px, `--text-secondary`, max 500 chars |
| Reasoning | `classification.reasoning` | Plain text, 12px, `--text-secondary` |

Each field renders as a label-value pair:
- Label: 11px, `--text-secondary`, left column ~140px
- Value: 14px monospace, `--text-primary`, right column

#### Market Data Snapshot Section

| Field | Data Source | Format |
|-------|-------------|--------|
| Price at alert | `signal.price_at_alert` | `$X.XX` monospace |
| Current price | Computed: `price_at_alert * (1 + price_move_pct/100)` | `$X.XX  (+X.X%)` — move colored per direction |
| Float | Market data snapshot | `X.XM shares` |
| Market cap | Market data snapshot | `$X.XM` or `$X.XB` |
| ADV | Market data snapshot | `$X.XM` |

Note: "Current price" is the backend-computed value returned via `signal.price_move_pct`; the frontend reconstructs the display price. Architecture note: the `GET /api/v1/signals/{id}` response returns the price_move_pct field on `SignalRow`. If the backend adds a `current_price` field to `SignalDetailResponse` that is preferred; otherwise the frontend derives it.

### 5.4 Position Tracking Section

The section renders one of three states based on `signal.entry_price` and `signal.cover_price`.

#### State A: No Entry Recorded

```
┌────────────────────────────────────────┐
│  POSITION TRACKING                     │
│                                        │
│  No position recorded.                 │
│                                        │
│  Entry price  $[ _________ ]           │
│               [  Record Entry  ]       │
│                                        │
│  ─── or ───                            │
│                                        │
│  [  Close Without Position  ]          │
└────────────────────────────────────────┘
```

| Element | Spec |
|---------|------|
| Entry price input | 120px wide, monospace, `--bg-input`, `--border-input` border, placeholder `0.0000` |
| Record Entry button | Primary: background `--accent-cyan`, text white, 4px radius |
| Close Without Position button | Secondary: background transparent, border `--border-color`, text `--text-secondary` |

Submission behavior: Enter key in the input field triggers Record Entry. Field must be a number > 0; if not, show inline error below the field: "Entry price must be greater than $0.00" in `--negative`.

#### State B: Entry Recorded, Not Yet Covered

```
┌────────────────────────────────────────┐
│  POSITION TRACKING                     │
│                                        │
│  Entry price   $5.20                   │
│  Current P&L   -8.4% (open)            │
│                                        │
│  Cover price  $[ _________ ]           │
│               [  Close Position  ]     │
└────────────────────────────────────────┘
```

| Element | Spec |
|---------|------|
| Entry price display | Monospace, `--text-primary` |
| Current P&L (open) | `–X.X% (open)` — color per direction. Computed from `(cover_input or current_price) vs entry_price`. Updates as user types cover price. |
| Cover price input | Same style as entry price input |
| Close Position button | Primary: `--accent-cyan` background |

Submission behavior: Enter key or button triggers Close Position. Validates cover price > $0.01; if not: "Cover price must be at least $0.01". On success: signal moves to CLOSED status, panel updates to State C without reload.

#### State C: Position Closed

```
┌────────────────────────────────────────┐
│  POSITION TRACKING                     │
│                                        │
│  Entry price   $5.20                   │
│  Cover price   $4.26                   │
│  P&L           +18.3%                  │
│  Closed        2026-04-04 14:22 UTC    │
│  Reason        MANUAL                  │
└────────────────────────────────────────┘
```

This state is read-only. No inputs or buttons appear.

---

## 6. Status Indicator (HealthBar)

Located in the right portion of the header bar.

### 6.1 Layout

```
Last poll: 14s ago   [●]
```

The elapsed counter ("14s ago") updates every second via a client-side interval. It does not re-poll the API; it computes elapsed time from the `last_success_at` timestamp received in the last health response.

### 6.2 Status Dot States

| State | Condition | Dot Color | Tooltip |
|-------|-----------|-----------|---------|
| Healthy | `last_success_at` < 3 minutes ago | `--positive` (#4caf50) | "System healthy" |
| Warning | `last_success_at` 3–10 minutes ago | `--warning` (#ff9800) | "Poll delayed" |
| Error | `last_success_at` > 10 minutes ago, or last poll returned an error | `--negative` (#f44336) | "Poll failed or stalled" |
| Unknown | `last_success_at` is null (no poll yet since app start) | `--text-muted` (#666666) | "Waiting for first poll" |

The dot is an 8px circle. In Warning and Error states it pulses with a CSS animation (opacity 1.0 to 0.4 at 1s intervals).

### 6.3 Health API Integration

The `HealthBar` component polls `GET /api/v1/health` every 15 seconds (independent of the 30-second signal refresh). It uses the `last_success_at` field from `HealthResponse` to drive the elapsed counter and status dot. If the `/health` call itself fails, the dot immediately transitions to Error state.

---

## 7. Auto-Refresh Behavior

### 7.1 Polling Mechanism

- The frontend polls `GET /api/v1/signals` and `GET /api/v1/signals/closed` every 30 seconds.
- Interval is client-side only (configurable via env var `NEXT_PUBLIC_REFRESH_INTERVAL_MS`, default `30000`).
- On each poll response, the data store (React state or SWR cache) is updated in-place.

### 7.2 No-Flash Update

To prevent visible re-render flash or layout jump:
- New data replaces old data in state after the fetch resolves; the UI does not blank out during the fetch.
- The three panels are each independently keyed; a change in one panel does not cause the others to re-render unnecessarily.
- Row order is stable: rows are sorted by score descending within each panel before rendering; a score change that does not change row order causes no visible movement.

### 7.3 New Row Animation (Live Now Panel Only)

When a new row appears in the Live Now panel (a row with an `id` that was not in the previous render):
1. The row renders immediately in the sorted position.
2. Its background is set to `#1a3a3a` (muted teal dark).
3. A CSS transition eases the background back to `--bg-card` over 3 seconds.
4. Animation fires once per new row id; it does not repeat on subsequent refreshes.

### 7.4 In-Place Update (SETUP_UPDATE)

When a row already visible in Live Now or Watchlist receives a SETUP_UPDATE (same `id`, changed `score` or `alert_type`):
- The score and badge values update without animation.
- If the score change alters sort order, the row moves to its new position; no animation on the reorder.

---

## 8. State Matrix

Each panel and the detail panel have four possible states. The component renders exactly one state at a time.

### 8.1 Live Now Panel

| State | Trigger | Visual |
|-------|---------|--------|
| Loading | Initial page load before first API response | Section header shows "LIVE NOW" + spinner (16px spinner replacing count), rows are 2 skeleton rows (gray bars of row height) |
| Empty | API responded, `signals` where status=LIVE is empty | Section header shows "LIVE NOW (0)"; body shows centered text "No active setups" in `--text-muted`, 14px |
| Error | API request failed (network error or non-2xx) | Section header shows "LIVE NOW (!)" in `--negative`; body shows "Failed to load — retrying" in `--negative` 12px; auto-retries on next 30s cycle |
| Data | API returned >= 1 LIVE signal | Section header shows "LIVE NOW (N)"; rows rendered in score-descending order |

### 8.2 Watchlist Panel

| State | Trigger | Visual |
|-------|---------|--------|
| Loading | Initial page load before first API response | Same skeleton pattern as Live Now |
| Empty | No signals with status=WATCHLIST | Centered text "No setups on watchlist" in `--text-muted` |
| Error | API request failed | Same error treatment as Live Now: "Failed to load — retrying" in `--negative` |
| Data | >= 1 WATCHLIST signal | Rows rendered score-descending |

### 8.3 Recent Closed Panel

| State | Trigger | Visual |
|-------|---------|--------|
| Loading | Initial page load before first API response | Skeleton rows |
| Empty | No closed signals in last-50 results | Centered text "No closed setups yet" in `--text-muted` |
| Error | API request failed | Same error treatment |
| Data | >= 1 closed signal | Rows rendered by `closed_at` descending (most recently closed at top); max 50 rows |

### 8.4 Setup Detail Panel

| State | Trigger | Visual |
|-------|---------|--------|
| Loading | Row clicked, `GET /api/v1/signals/{id}` pending | Panel slides in, shows spinner in center area |
| Error | `GET /api/v1/signals/{id}` failed | Panel shows: "Failed to load setup details." in `--negative` + [Retry] button |
| Data | API returned detail response | Full panel content as described in Section 5 |

### 8.5 API Configuration Warning

When `HealthResponse.fmp_configured == false`:
- A warning banner appears between the header bar and the Live Now panel.
- Banner background: `#3d2400` (dark orange), border `--warning`, text: "FMP API key not configured — enrichment disabled. Check your .env file." in `--warning`.
- The banner is persistent until the condition clears (on next health poll).

---

## 9. User Flows

### Flow 1: Trader Reviews Active Setups (US-07)

1. User opens app at `/`.
2. User sees: Header bar with title and status indicator. Three panels in loading state (skeleton rows).
3. System: Fetches `/api/v1/signals` and `/api/v1/signals/closed` on mount.
4. User sees: Live Now, Watchlist, Recent Closed panels populate with rows (or empty states if no data).
5. Auto-refresh: Every 30 seconds, all panels silently refresh. New Live Now rows pulse once.
6. End state: User has a continuous view of all active and recent setups. No action required to stay current.

**Error path:** If API is unreachable, all three panels show error state with "Failed to load — retrying". The status dot turns red. Retry occurs automatically on next 30s cycle.

### Flow 2: Trader Inspects a Setup (US-08)

1. User sees a ticker row in Live Now or Watchlist.
2. User hovers the row: background changes to `--bg-card-hover`.
3. User clicks the row.
4. System: `GET /api/v1/signals/{id}` fires. Panel slides in from right. Backdrop appears.
5. User sees: Panel in loading state (spinner) briefly, then full detail.
6. User reads classification output, market data snapshot, filing excerpt.
7. User closes panel: clicks X button or clicks backdrop.
8. End state: Panel slides out, main dashboard resumes normal state.

**Error path:** If `/signals/{id}` fails, panel shows error state with Retry button. User can retry or close the panel.

### Flow 3: Trader Records a Short Entry (US-09)

1. User opens Setup Detail for a LIVE or WATCHLIST setup.
2. Position Tracking section shows State A (no entry).
3. User types entry price into the input field (e.g. `5.20`).
4. User presses Enter or clicks [Record Entry].
5. System: `POST /api/v1/signals/{id}/position` with `{ entry_price: 5.20 }`.
6. User sees: Position section transitions to State B. Entry price displayed. Current P&L visible as open estimate.
7. End state: Entry price persisted. User can continue monitoring.

**Validation error path:** User enters `0` or non-numeric text. Inline error appears below input: "Entry price must be greater than $0.00". Form does not submit.

### Flow 4: Trader Closes a Position (US-09, US-10)

1. User opens Setup Detail for a setup with entry recorded (State B).
2. User types cover price (e.g. `4.26`).
3. As user types, Current P&L estimate updates in real time.
4. User presses Enter or clicks [Close Position].
5. System: `POST /api/v1/signals/{id}/position` with `{ cover_price: 4.26 }`. Backend computes P&L, transitions status to CLOSED.
6. User sees: Position section transitions to State C (read-only summary). Panel can be closed.
7. On next 30s refresh (or immediately on response): signal moves from Live Now or Watchlist to Recent Closed.
8. End state: P&L recorded. Setup visible in Recent Closed.

**Validation error path:** Cover price <= $0.01 → inline error "Cover price must be at least $0.01".

### Flow 5: Trader Closes Without Recording Position (US-10)

1. User opens Setup Detail, State A (no entry).
2. User clicks [Close Without Position].
3. System: `POST /api/v1/signals/{id}/close`.
4. User sees: Panel closes. On next refresh, setup appears in Recent Closed with "No position" and close_reason "MANUAL".
5. End state: Setup archived. P&L fields are null.

### Flow 6: System Generates a New Rank A Alert (US-05, US-07)

1. Backend pipeline scores a filing as Rank A during a poll cycle.
2. Frontend polls `/api/v1/signals` 30s later (or sooner if timing aligns).
3. New signal id appears in LIVE signals list.
4. Live Now panel inserts new row in score-descending position with pulse animation.
5. Live Now count increments.
6. End state: Trader sees new alert without any action required.

### Flow 7: Setup Expires by Hold Time (US-10)

1. Backend lifecycle checker transitions a LIVE or WATCHLIST setup to `TIME_EXCEEDED`.
2. Next frontend refresh fetches updated signals; LIVE/WATCHLIST no longer contains that id.
3. Closed signals fetch returns it in Recent Closed with `close_reason = TIME_EXCEEDED`.
4. End state: Setup disappears from active panels, appears in Recent Closed.

---

## 10. Interaction Specification Table

| Element | Hover | Click | Submit / Enter | Other |
|---------|-------|-------|----------------|-------|
| Signal row (any panel) | Background → `--bg-card-hover`, cursor pointer | Open Setup Detail Panel | — | New Live Now row pulses on mount |
| Setup Detail backdrop | — | Close Setup Detail Panel | — | — |
| Setup Detail [X] button | Lighten icon color | Close Setup Detail Panel | — | — |
| EDGAR link in panel | Underline, color → `--accent-cyan-hover` | Open filing URL in new tab | — | — |
| Entry price input | — | Focus, show cursor | POST position with entry_price | Validate > 0 before submit |
| [Record Entry] button | Lighten background | POST position with entry_price | — | Disabled while request in flight |
| Cover price input | — | Focus, show cursor | POST position with cover_price | Real-time P&L preview as user types; validate > 0.01 |
| [Close Position] button | Lighten background | POST position with cover_price | — | Disabled while request in flight |
| [Close Without Position] button | Border → `--border-input` | POST close | — | Disabled while request in flight |
| [Retry] button (error states) | Lighten background | Re-fetch the failed request | — | — |
| Status dot | Show tooltip | — | — | Tooltip: status description text |

---

## 11. Component Hierarchy

Maps to `02-ARCHITECTURE.md` frontend component list.

```
page.tsx  (route: /)
├── Header.tsx
│   └── HealthBar.tsx
│       └── [status dot + elapsed text]
├── [API config warning banner — conditional]
├── LiveNowPanel.tsx
│   ├── [panel header with count]
│   ├── [LoadingState | EmptyState | ErrorState]
│   └── SignalRow.tsx (×N, variant="live")
├── WatchlistPanel.tsx
│   ├── [panel header with count]
│   ├── [LoadingState | EmptyState | ErrorState]
│   └── SignalRow.tsx (×N, variant="watchlist")
├── RecentClosedPanel.tsx
│   ├── [panel header with count]
│   ├── [LoadingState | EmptyState | ErrorState]
│   └── SignalRow.tsx (×N, variant="closed")
└── SetupDetailModal.tsx  (conditional — mounted when a row is clicked)
    ├── [modal backdrop]
    ├── [panel header: ticker + badge + company name + close button]
    ├── [filing info section]
    ├── [classification output section]
    ├── [market data snapshot section]
    └── PositionForm.tsx
        ├── [State A: entry price input + Record Entry + Close Without Position]
        ├── [State B: entry display + cover price input + Close Position]
        └── [State C: read-only P&L summary]
```

### Component Descriptions

| Component | File | Purpose |
|-----------|------|---------|
| `Header` | `Header.tsx` | App title bar. Removed ticker input vs phase2 parent. Contains `HealthBar`. |
| `HealthBar` | `HealthBar.tsx` | Polls `/api/v1/health` every 15s. Renders elapsed counter and status dot. |
| `LiveNowPanel` | `LiveNowPanel.tsx` | Renders Rank A (LIVE) signals. Manages loading/empty/error states. Passes variant="live" to rows. |
| `WatchlistPanel` | `WatchlistPanel.tsx` | Renders Rank B (WATCHLIST) signals. Same structure as LiveNowPanel. |
| `RecentClosedPanel` | `RecentClosedPanel.tsx` | Renders closed signals (last 50 by closed_at desc). |
| `SignalRow` | `SignalRow.tsx` | Shared row component. Accepts `signal: SignalRow` and `variant: "live" | "watchlist" | "closed"`. Renders columns per variant. Handles hover and click. |
| `SetupDetailModal` | `SetupDetailModal.tsx` | Slide-in panel. Fetches `/api/v1/signals/{id}` on open. Manages loading/error/data states. Contains `PositionForm`. |
| `PositionForm` | `PositionForm.tsx` | Handles entry/cover price inputs and submission. Posts to `/api/v1/signals/{id}/position` and `/api/v1/signals/{id}/close`. Manages its own form state and inline validation. |

---

## 12. State Visibility Map

Maps which data from the API appears in which components.

| Data Field | Appears In | Updated By |
|------------|-----------|------------|
| `signal.ticker` | SignalRow (all variants), SetupDetailModal header | `GET /signals` (30s refresh), `GET /signals/{id}` |
| `SignalDetailResponse.entity_name` | SetupDetailModal header (company name, when non-null) | `GET /signals/{id}` |
| `signal.setup_type` | SignalRow badge, SetupDetailModal badge | Same |
| `signal.score` | SignalRow (live, watchlist variants) | Same |
| `signal.rank` | SetupDetailModal classification section | Same |
| `signal.price_move_pct` | SignalRow (live variant), SetupDetailModal market data | Same |
| `signal.elapsed_seconds` | SignalRow (live, watchlist variants) | Recomputed from `alerted_at` on each render; not re-fetched |
| `signal.status` | Controls which panel a row appears in | `GET /signals`, `POST position`, `POST close` |
| `signal.alert_type` | Watchlist status label | Same |
| `signal.entry_price` | PositionForm state indicator, SetupDetailModal (State B/C) | `POST /signals/{id}/position` |
| `signal.cover_price` | PositionForm (State C) | Same |
| `signal.pnl_pct` | SignalRow (closed variant), PositionForm (State C) | Same |
| `signal.close_reason` | SignalRow (closed variant), PositionForm (State C) | Same |
| `signal.price_at_alert` | SetupDetailModal market data | `GET /signals/{id}` |
| `classification.*` | SetupDetailModal classification section only | `GET /signals/{id}` |
| `filing.filing_url`, `filing.form_type`, `filing.filed_at` | SetupDetailModal filing info section | `GET /signals/{id}` |
| `health.last_success_at` | HealthBar elapsed counter + status dot | `GET /health` (15s refresh) |
| `health.fmp_configured` | API config warning banner | `GET /health` (15s refresh) |

---

## 13. Out-of-Scope Confirmations

The following are explicitly not defined in this UI spec:

- Ticker search / lookup input (feature belongs to gap-lens-dilution, not this project)
- JMT415 dilution alert feed (gap-lens-dilution feature)
- News / headlines section
- Mobile layout
- User authentication / login screen
- Export or download buttons
- Historical charts or price graphs
- Sector / industry filter controls
- Multi-signal comparison views
