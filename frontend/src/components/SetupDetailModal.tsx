"use client";
import { useEffect, useState, useCallback } from "react";
import type { SignalDetailResponse } from "@/types/signals";
import { getSignalDetail } from "@/services/api";
import PositionForm from "@/components/PositionForm";

interface SetupDetailModalProps {
  signalId: number | null;
  onClose: () => void;
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

function formatFiledAt(filed_at: string): string {
  try {
    const d = new Date(filed_at);
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const hh = String(d.getUTCHours()).padStart(2, "0");
    const min = String(d.getUTCMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${min} UTC`;
  } catch {
    return filed_at;
  }
}

function formatClosedAt(closed_at: string): string {
  return formatFiledAt(closed_at);
}

type LoadState =
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "data"; detail: SignalDetailResponse };

export default function SetupDetailModal({ signalId, onClose }: SetupDetailModalProps) {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const fetchDetail = useCallback(() => {
    if (signalId === null) return;
    setState({ kind: "loading" });
    const controller = new AbortController();
    getSignalDetail(signalId, controller.signal)
      .then((detail) => setState({ kind: "data", detail }))
      .catch((err) => {
        if ((err as Error).name !== "AbortError") {
          setState({ kind: "error" });
        }
      });
    return () => controller.abort();
  }, [signalId]);

  useEffect(() => {
    const cleanup = fetchDetail();
    return cleanup;
  }, [fetchDetail]);

  if (signalId === null) return null;

  function handlePanelClick(e: React.MouseEvent) {
    e.stopPropagation();
  }

  function handlePositionUpdate() {
    fetchDetail();
  }

  const sectionHeaderStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--text-secondary)",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    marginBottom: 8,
    marginTop: 0,
  };

  const sectionStyle: React.CSSProperties = {
    padding: "12px 16px",
    borderBottom: "1px solid var(--border-color)",
  };

  const labelStyle: React.CSSProperties = {
    display: "inline-block",
    width: 140,
    flexShrink: 0,
    fontSize: 11,
    color: "var(--text-secondary)",
    fontFamily: "system-ui",
    verticalAlign: "top",
  };

  const valueStyle: React.CSSProperties = {
    fontSize: 14,
    fontFamily: "Consolas, monospace",
    color: "var(--text-primary)",
  };

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "flex-start",
    marginBottom: 6,
  };

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          backgroundColor: "rgba(0,0,0,0.4)",
          zIndex: 40,
        }}
      />

      {/* Panel */}
      <div
        onClick={handlePanelClick}
        style={{
          position: "fixed",
          right: 0,
          top: 0,
          bottom: 0,
          width: 480,
          backgroundColor: "var(--bg-card)",
          borderLeft: "1px solid var(--border-color)",
          boxShadow: "0 0 24px rgba(0,0,0,0.5)",
          zIndex: 50,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {state.kind === "loading" && (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--text-secondary)",
              fontSize: 14,
            }}
          >
            Loading...
          </div>
        )}

        {state.kind === "error" && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 12,
            }}
          >
            <span style={{ color: "var(--negative)", fontSize: 14 }}>
              Failed to load setup details.
            </span>
            <button
              onClick={fetchDetail}
              style={{
                backgroundColor: "var(--accent-cyan)",
                color: "#fff",
                border: "none",
                borderRadius: 4,
                padding: "6px 16px",
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Retry
            </button>
          </div>
        )}

        {state.kind === "data" && (() => {
          const { detail } = state;
          const { signal, classification } = detail;

          // Current price computation
          let currentPriceDisplay: React.ReactNode = "N/A";
          if (signal.price_at_alert != null && signal.price_move_pct != null) {
            const currentPrice = signal.price_at_alert * (1 + signal.price_move_pct / 100);
            const pct = signal.price_move_pct;
            const sign = pct >= 0 ? "+" : "";
            const moveColor = pct < 0 ? "var(--positive)" : "var(--negative)";
            currentPriceDisplay = (
              <span style={valueStyle}>
                ${currentPrice.toFixed(2)}&nbsp;&nbsp;
                <span style={{ color: moveColor }}>
                  ({sign}{pct.toFixed(1)}%)
                </span>
              </span>
            );
          }

          return (
            <>
              {/* Panel Header */}
              <div
                style={{
                  padding: 16,
                  borderBottom: "1px solid var(--border-color)",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  flexShrink: 0,
                }}
              >
                <span
                  style={{
                    fontFamily: "Consolas, monospace",
                    fontSize: 14,
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    flexShrink: 0,
                  }}
                >
                  {signal.ticker.toUpperCase()}
                </span>
                <SetupBadge type={signal.setup_type} />
                {detail.entity_name != null && (
                  <span
                    style={{
                      fontSize: 14,
                      color: "var(--text-secondary)",
                      flex: 1,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {detail.entity_name}
                  </span>
                )}
                {detail.entity_name == null && <span style={{ flex: 1 }} />}
                <button
                  onClick={onClose}
                  style={{
                    width: 24,
                    height: 24,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    color: "var(--text-secondary)",
                    fontSize: 16,
                    flexShrink: 0,
                    padding: 0,
                  }}
                  aria-label="Close"
                >
                  ×
                </button>
              </div>

              {/* Filing Info Section */}
              <div style={sectionStyle}>
                <p style={sectionHeaderStyle}>Filing Info</p>
                <div style={rowStyle}>
                  <span style={labelStyle}>Form type</span>
                  <span style={valueStyle}>{detail.form_type}</span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Filed date</span>
                  <span style={valueStyle}>{formatFiledAt(detail.filed_at)}</span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>EDGAR</span>
                  <a
                    href={detail.filing_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: "var(--accent-cyan)",
                      fontSize: 14,
                      fontFamily: "system-ui",
                      textDecoration: "none",
                    }}
                  >
                    View on EDGAR
                  </a>
                </div>
              </div>

              {/* Classification Output Section */}
              <div style={sectionStyle}>
                <p style={sectionHeaderStyle}>Classification Output</p>
                <div style={rowStyle}>
                  <span style={labelStyle}>Setup Type</span>
                  <SetupBadge type={classification.setup_type} />
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Confidence</span>
                  <span style={valueStyle}>
                    {Math.round(classification.confidence * 100)}%
                  </span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Dilution Severity</span>
                  <span style={valueStyle}>
                    {(classification.dilution_severity * 100).toFixed(1)}% of float
                  </span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Immediate Pressure</span>
                  <span
                    style={{
                      ...valueStyle,
                      color: classification.immediate_pressure
                        ? "var(--warning)"
                        : "var(--text-secondary)",
                    }}
                  >
                    {classification.immediate_pressure ? "Yes" : "No"}
                  </span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Price Discount</span>
                  <span style={valueStyle}>
                    {classification.price_discount !== null
                      ? `${(classification.price_discount * 100).toFixed(1)}%`
                      : "N/A"}
                  </span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Score + Rank</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={valueStyle}>{signal.score}</span>
                    <SetupBadge type={signal.rank} />
                  </span>
                </div>
                <div style={{ marginTop: 8 }}>
                  <span style={{ ...labelStyle, display: "block", marginBottom: 4 }}>
                    Key Excerpt
                  </span>
                  <blockquote
                    style={{
                      borderLeft: "3px solid var(--accent-cyan)",
                      fontStyle: "italic",
                      fontFamily: "Consolas, monospace",
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      padding: "8px 12px",
                      margin: "8px 0",
                    }}
                  >
                    {classification.key_excerpt}
                  </blockquote>
                </div>
                <div style={{ marginTop: 8 }}>
                  <span style={{ ...labelStyle, display: "block", marginBottom: 4 }}>
                    Reasoning
                  </span>
                  <p
                    style={{
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      fontFamily: "system-ui",
                      margin: 0,
                    }}
                  >
                    {classification.reasoning}
                  </p>
                </div>
              </div>

              {/* Market Data Snapshot Section */}
              <div style={sectionStyle}>
                <p style={sectionHeaderStyle}>Market Data Snapshot</p>
                <div style={rowStyle}>
                  <span style={labelStyle}>Price at alert</span>
                  <span style={valueStyle}>
                    {signal.price_at_alert != null
                      ? `$${signal.price_at_alert.toFixed(2)}`
                      : "N/A"}
                  </span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Current price</span>
                  {currentPriceDisplay}
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Float</span>
                  <span style={{ ...valueStyle, color: "var(--text-muted)" }}>N/A</span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>Market cap</span>
                  <span style={{ ...valueStyle, color: "var(--text-muted)" }}>N/A</span>
                </div>
                <div style={rowStyle}>
                  <span style={labelStyle}>ADV</span>
                  <span style={{ ...valueStyle, color: "var(--text-muted)" }}>N/A</span>
                </div>
              </div>

              {/* Position Tracking Section */}
              <div style={{ padding: "12px 16px" }}>
                <p style={sectionHeaderStyle}>Position Tracking</p>
                <PositionForm
                  signal={signal}
                  onClose={onClose}
                  currentPrice={
                    signal.price_at_alert != null && signal.price_move_pct != null
                      ? signal.price_at_alert * (1 + signal.price_move_pct / 100)
                      : null
                  }
                  onUpdate={handlePositionUpdate}
                />
              </div>
            </>
          );
        })()}
      </div>
    </>
  );
}

export { formatFiledAt as formatClosedAtDate };
