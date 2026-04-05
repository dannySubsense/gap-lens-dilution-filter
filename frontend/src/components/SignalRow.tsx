"use client";
import type { SignalRow as SignalRowData } from "@/types/signals";

interface SignalRowProps {
  signal: SignalRowData;
  panelType: "live" | "watchlist" | "closed";
  onClick: (id: number) => void;
  isNew?: boolean;
}

const BADGE_COLORS: Record<string, string> = {
  A: "#f44336",
  B: "#ff9800",
  C: "#ffc107",
  D: "#9e9e9e",
  E: "#ce93d8",
};

function SetupBadge({ type }: { type: string }) {
  const color = BADGE_COLORS[type] ?? "#9e9e9e";
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 4px",
        borderRadius: 4,
        border: `1px solid ${color}`,
        backgroundColor: `${color}33`,
        color,
        fontSize: 11,
        fontWeight: 700,
        fontFamily: "system-ui",
        flexShrink: 0,
        width: "36px",
        textAlign: "center",
        boxSizing: "border-box",
      }}
    >
      [{type}]
    </span>
  );
}

function formatElapsed(elapsed: number | null): string {
  if (elapsed === null) return "—";
  if (elapsed < 60) return "just now";
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ago`;
  if (elapsed < 86400) return `${Math.floor(elapsed / 3600)}h ago`;
  return `${Math.floor(elapsed / 86400)}d ago`;
}

function watchlistLabel(signal: SignalRowData): string {
  if (signal.setup_type === "D") return "ATM active";
  if (signal.alert_type === "SETUP_UPDATE") return "Updated";
  if (signal.score < 70) return "Awaiting pricing";
  return "Monitoring";
}

function priceMoveColor(pct: number | null): string {
  if (pct === null) return "var(--text-muted)";
  return pct < 0 ? "var(--positive)" : "var(--negative)";
}

function formatPricePct(pct: number | null): string {
  if (pct === null) return "--";
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function formatPnl(pnl: number | null): { text: string; color: string } {
  if (pnl === null) return { text: "\u2014", color: "var(--text-muted)" };
  const sign = pnl >= 0 ? "+" : "";
  const color = pnl >= 0 ? "var(--positive)" : "var(--negative)";
  return { text: `${sign}${pnl.toFixed(1)}%`, color };
}

function formatEntryCover(entry: number | null, cover: number | null): { text: string; color: string } {
  if (entry === null || cover === null) {
    return { text: "No position", color: "var(--text-muted)" };
  }
  return { text: `$${entry.toFixed(2)} \u2192 $${cover.toFixed(2)}`, color: "var(--text-secondary)" };
}

const ROW_BASE_STYLE: React.CSSProperties = {
  padding: "var(--space-sm) var(--space-md)",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: "var(--space-sm)",
  backgroundColor: "var(--bg-card)",
  borderRadius: "2px",
};

export default function SignalRow({ signal, panelType, onClick, isNew }: SignalRowProps) {
  const className = panelType === "live" && isNew ? "signal-row-new" : undefined;

  function handleClick() {
    onClick(signal.id);
  }

  function handleMouseEnter(e: React.MouseEvent<HTMLDivElement>) {
    (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--bg-card-hover)";
  }

  function handleMouseLeave(e: React.MouseEvent<HTMLDivElement>) {
    if (!(panelType === "live" && isNew)) {
      (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--bg-card)";
    }
  }

  if (panelType === "live") {
    return (
      <div
        className={className}
        style={ROW_BASE_STYLE}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Ticker: 80px */}
        <span
          style={{
            width: "80px",
            flexShrink: 0,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            fontWeight: 700,
            color: "var(--text-primary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {signal.ticker.toUpperCase()}
        </span>

        {/* Badge: 36px */}
        <SetupBadge type={signal.setup_type} />

        {/* Score: 90px */}
        <span
          style={{
            width: "90px",
            flexShrink: 0,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            color: "var(--text-primary)",
          }}
        >
          Score: {signal.score}
        </span>

        {/* Price move: 80px */}
        <span
          style={{
            width: "80px",
            flexShrink: 0,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            color: priceMoveColor(signal.price_move_pct),
          }}
        >
          {formatPricePct(signal.price_move_pct)}
        </span>

        {/* Elapsed: flex-1, right-aligned */}
        <span
          style={{
            flex: 1,
            textAlign: "right",
            fontSize: 11,
            color: "var(--text-secondary)",
            fontFamily: "system-ui",
          }}
        >
          {formatElapsed(signal.elapsed_seconds)}
        </span>
      </div>
    );
  }

  if (panelType === "watchlist") {
    return (
      <div
        style={ROW_BASE_STYLE}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
      >
        {/* Ticker: 80px */}
        <span
          style={{
            width: "80px",
            flexShrink: 0,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            fontWeight: 700,
            color: "var(--text-primary)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {signal.ticker.toUpperCase()}
        </span>

        {/* Badge: 36px */}
        <SetupBadge type={signal.setup_type} />

        {/* Score: 90px */}
        <span
          style={{
            width: "90px",
            flexShrink: 0,
            fontFamily: "Consolas, monospace",
            fontSize: 14,
            color: "var(--text-primary)",
          }}
        >
          Score: {signal.score}
        </span>

        {/* Status label: flex-1 */}
        <span
          style={{
            flex: 1,
            fontSize: 12,
            color: "var(--text-secondary)",
            fontFamily: "system-ui",
          }}
        >
          {watchlistLabel(signal)}
        </span>

        {/* Elapsed: 120px, right-aligned */}
        <span
          style={{
            width: "120px",
            flexShrink: 0,
            textAlign: "right",
            fontSize: 11,
            color: "var(--text-secondary)",
            fontFamily: "system-ui",
          }}
        >
          {formatElapsed(signal.elapsed_seconds)}
        </span>
      </div>
    );
  }

  // panelType === "closed"
  const pnl = formatPnl(signal.pnl_pct);
  const entryCover = formatEntryCover(signal.entry_price, signal.cover_price);

  return (
    <div
      style={ROW_BASE_STYLE}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Ticker: 80px */}
      <span
        style={{
          width: "80px",
          flexShrink: 0,
          fontFamily: "Consolas, monospace",
          fontSize: 14,
          fontWeight: 700,
          color: "var(--text-primary)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {signal.ticker.toUpperCase()}
      </span>

      {/* Badge: 36px */}
      <SetupBadge type={signal.setup_type} />

      {/* P&L: 80px */}
      <span
        style={{
          width: "80px",
          flexShrink: 0,
          fontFamily: "Consolas, monospace",
          fontSize: 14,
          color: pnl.color,
        }}
      >
        {pnl.text}
      </span>

      {/* Entry→Cover: flex-1 */}
      <span
        style={{
          flex: 1,
          fontFamily: "Consolas, monospace",
          fontSize: 12,
          color: entryCover.color,
        }}
      >
        {entryCover.text}
      </span>

      {/* Close reason: 80px, right-aligned */}
      <span
        style={{
          width: "80px",
          flexShrink: 0,
          textAlign: "right",
          fontSize: 11,
          color: "var(--text-muted)",
          fontFamily: "system-ui",
        }}
      >
        {signal.close_reason ?? "—"}
      </span>
    </div>
  );
}
