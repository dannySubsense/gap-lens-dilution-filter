"use client";
import { useState, useRef } from "react";
import type { SignalRow } from "@/types/signals";
import { recordPosition, closeSignal } from "@/services/api";

interface PositionFormProps {
  signal: SignalRow;
  currentPrice: number | null;
  onUpdate: () => void;
  onClose?: () => void;
}

function formatClosedAt(closed_at: string): string {
  try {
    const d = new Date(closed_at);
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const min = String(d.getUTCMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${min} UTC`;
  } catch {
    return closed_at;
  }
}

const LABEL_STYLE: React.CSSProperties = {
  display: "inline-block",
  width: 120,
  flexShrink: 0,
  fontSize: 11,
  color: "var(--text-secondary)",
  fontFamily: "system-ui",
};

const VALUE_STYLE: React.CSSProperties = {
  fontSize: 14,
  fontFamily: "Consolas, monospace",
  color: "var(--text-primary)",
};

const ROW_STYLE: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  marginBottom: 6,
};

const INPUT_STYLE: React.CSSProperties = {
  width: 120,
  fontFamily: "Consolas, monospace",
  fontSize: 13,
  backgroundColor: "var(--bg-input)",
  border: "1px solid var(--border-input)",
  borderRadius: 4,
  color: "var(--text-primary)",
  padding: "4px 8px",
  outline: "none",
};

const PRIMARY_BTN_STYLE: React.CSSProperties = {
  backgroundColor: "var(--accent-cyan)",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  padding: "6px 14px",
  fontSize: 13,
  cursor: "pointer",
  fontFamily: "system-ui",
};

const SECONDARY_BTN_STYLE: React.CSSProperties = {
  backgroundColor: "transparent",
  color: "var(--text-secondary)",
  border: "1px solid var(--border-color)",
  borderRadius: 4,
  padding: "6px 14px",
  fontSize: 13,
  cursor: "pointer",
  fontFamily: "system-ui",
};

const ERROR_STYLE: React.CSSProperties = {
  fontSize: 12,
  color: "var(--negative)",
  fontFamily: "system-ui",
  marginTop: 4,
};

const SEPARATOR_STYLE: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  color: "var(--text-muted)",
  fontSize: 12,
  fontFamily: "system-ui",
  margin: "8px 0",
};

export default function PositionForm({ signal, currentPrice, onUpdate, onClose }: PositionFormProps) {
  const [entryInput, setEntryInput] = useState("");
  const [entryError, setEntryError] = useState<string | null>(null);
  const [entrySubmitting, setEntrySubmitting] = useState(false);

  const [coverInput, setCoverInput] = useState("");
  const [coverError, setCoverError] = useState<string | null>(null);
  const [coverSubmitting, setCoverSubmitting] = useState(false);

  const [closeWithoutSubmitting, setCloseWithoutSubmitting] = useState(false);

  const entryRef = useRef<HTMLInputElement>(null);
  const coverRef = useRef<HTMLInputElement>(null);

  // Determine state
  const isClosed = signal.cover_price != null;
  const hasEntry = signal.entry_price != null;

  // State C: closed, read-only
  if (isClosed && hasEntry) {
    const entry = signal.entry_price as number;
    const cover = signal.cover_price as number;
    const pnlPct = signal.pnl_pct;
    let pnlDisplay: React.ReactNode = "\u2014";
    if (pnlPct != null) {
      const sign = pnlPct >= 0 ? "+" : "";
      const color = pnlPct >= 0 ? "var(--positive)" : "var(--negative)";
      pnlDisplay = (
        <span style={{ ...VALUE_STYLE, color }}>
          {sign}{pnlPct.toFixed(1)}%
        </span>
      );
    }

    return (
      <div>
        <div style={ROW_STYLE}>
          <span style={LABEL_STYLE}>Entry price</span>
          <span style={VALUE_STYLE}>${entry.toFixed(2)}</span>
        </div>
        <div style={ROW_STYLE}>
          <span style={LABEL_STYLE}>Cover price</span>
          <span style={VALUE_STYLE}>${cover.toFixed(2)}</span>
        </div>
        <div style={ROW_STYLE}>
          <span style={LABEL_STYLE}>P&amp;L</span>
          {pnlDisplay}
        </div>
        {signal.closed_at != null && (
          <div style={ROW_STYLE}>
            <span style={LABEL_STYLE}>Closed</span>
            <span style={VALUE_STYLE}>{formatClosedAt(signal.closed_at)}</span>
          </div>
        )}
        <div style={ROW_STYLE}>
          <span style={LABEL_STYLE}>Reason</span>
          <span style={VALUE_STYLE}>{signal.close_reason ?? "\u2014"}</span>
        </div>
      </div>
    );
  }

  // State B: has entry, awaiting cover
  if (hasEntry) {
    const entry = signal.entry_price as number;

    // Compute live P&L: use cover input if valid, else current price
    let livePnl: React.ReactNode = null;
    const coverVal = parseFloat(coverInput);
    const referencePrice = !isNaN(coverVal) && coverVal > 0 ? coverVal : currentPrice;
    if (referencePrice != null && referencePrice > 0) {
      const pnlPct = ((entry - referencePrice) / entry) * 100;
      const sign = pnlPct >= 0 ? "+" : "";
      const color = pnlPct >= 0 ? "var(--positive)" : "var(--negative)";
      livePnl = (
        <span style={{ color, fontFamily: "Consolas, monospace", fontSize: 14 }}>
          {sign}{pnlPct.toFixed(1)}% (open)
        </span>
      );
    } else {
      livePnl = (
        <span style={{ color: "var(--text-muted)", fontFamily: "Consolas, monospace", fontSize: 14 }}>
          — (open)
        </span>
      );
    }

    async function handleCoverSubmit() {
      const val = parseFloat(coverInput);
      if (isNaN(val) || val < 0.01) {
        setCoverError("Cover price must be at least $0.01");
        return;
      }
      setCoverError(null);
      setCoverSubmitting(true);
      try {
        await recordPosition(signal.id, { cover_price: val });
        onUpdate();
      } catch {
        setCoverError("Failed to record cover price. Please try again.");
      } finally {
        setCoverSubmitting(false);
      }
    }

    function handleCoverKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
      if (e.key === "Enter") {
        handleCoverSubmit();
      }
    }

    return (
      <div>
        <div style={ROW_STYLE}>
          <span style={LABEL_STYLE}>Entry price</span>
          <span style={VALUE_STYLE}>${entry.toFixed(4)}</span>
        </div>
        <div style={{ ...ROW_STYLE, marginBottom: 10 }}>
          <span style={LABEL_STYLE}>Current P&amp;L</span>
          {livePnl}
        </div>
        <div style={{ marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <label
              style={{ ...LABEL_STYLE, fontSize: 11 }}
              htmlFor="cover-price-input"
            >
              Cover price
            </label>
            <input
              id="cover-price-input"
              ref={coverRef}
              type="number"
              step="0.0001"
              min="0"
              style={INPUT_STYLE}
              value={coverInput}
              placeholder="0.0000"
              onChange={(e) => {
                setCoverInput(e.target.value);
                if (coverError) setCoverError(null);
              }}
              onKeyDown={handleCoverKeyDown}
              disabled={coverSubmitting}
            />
          </div>
          {coverError && <p style={ERROR_STYLE}>{coverError}</p>}
        </div>
        <button
          style={PRIMARY_BTN_STYLE}
          onClick={handleCoverSubmit}
          disabled={coverSubmitting}
        >
          {coverSubmitting ? "Saving..." : "Close Position"}
        </button>
      </div>
    );
  }

  // State A: no entry
  async function handleEntrySubmit() {
    const val = parseFloat(entryInput);
    if (isNaN(val) || val <= 0) {
      setEntryError("Entry price must be greater than $0.00");
      return;
    }
    setEntryError(null);
    setEntrySubmitting(true);
    try {
      await recordPosition(signal.id, { entry_price: val });
      onUpdate();
    } catch {
      setEntryError("Failed to record entry price. Please try again.");
    } finally {
      setEntrySubmitting(false);
    }
  }

  async function handleCloseWithoutPosition() {
    setCloseWithoutSubmitting(true);
    try {
      await closeSignal(signal.id);
      onClose?.();
    } catch {
      // no-op: modal stays open if close fails; user can retry
    } finally {
      setCloseWithoutSubmitting(false);
    }
  }

  function handleEntryKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      handleEntrySubmit();
    }
  }

  return (
    <div>
      <p
        style={{
          fontSize: 13,
          color: "var(--text-muted)",
          fontFamily: "system-ui",
          margin: "0 0 12px 0",
        }}
      >
        No position recorded.
      </p>
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <label
            style={{ ...LABEL_STYLE, fontSize: 11 }}
            htmlFor="entry-price-input"
          >
            Entry price
          </label>
          <input
            id="entry-price-input"
            ref={entryRef}
            type="number"
            step="0.0001"
            min="0"
            style={INPUT_STYLE}
            value={entryInput}
            placeholder="0.0000"
            onChange={(e) => {
              setEntryInput(e.target.value);
              if (entryError) setEntryError(null);
            }}
            onKeyDown={handleEntryKeyDown}
            disabled={entrySubmitting}
          />
        </div>
        {entryError && <p style={ERROR_STYLE}>{entryError}</p>}
      </div>
      <button
        style={{ ...PRIMARY_BTN_STYLE, marginBottom: 4 }}
        onClick={handleEntrySubmit}
        disabled={entrySubmitting}
      >
        {entrySubmitting ? "Saving..." : "Record Entry"}
      </button>

      <div style={SEPARATOR_STYLE}>
        <span style={{ flex: 1, borderTop: "1px solid var(--border-color)" }} />
        <span>or</span>
        <span style={{ flex: 1, borderTop: "1px solid var(--border-color)" }} />
      </div>

      <button
        style={SECONDARY_BTN_STYLE}
        onClick={handleCloseWithoutPosition}
        disabled={closeWithoutSubmitting}
      >
        {closeWithoutSubmitting ? "Closing..." : "Close Without Position"}
      </button>
    </div>
  );
}
