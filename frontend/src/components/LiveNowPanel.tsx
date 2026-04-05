"use client";
import { useEffect, useRef, useState } from "react";
import { getSignals } from "@/services/api";
import type { SignalRow } from "@/types/signals";
import SignalRow_ from "@/components/SignalRow";

type PanelState = "loading" | "empty" | "error" | "data";

interface LiveNowPanelProps {
  refreshTick: number;
  onSignalClick: (id: number) => void;
}

function SkeletonRow() {
  return (
    <div
      style={{
        height: "40px",
        borderRadius: "4px",
        backgroundColor: "var(--text-muted)",
        opacity: 0.2,
        marginBottom: "var(--space-sm)",
      }}
    />
  );
}

export default function LiveNowPanel({ refreshTick, onSignalClick }: LiveNowPanelProps) {
  const [panelState, setPanelState] = useState<PanelState>("loading");
  const [signals, setSignals] = useState<SignalRow[]>([]);
  const seenIdsRef = useRef<Set<number>>(new Set());
  const newIdsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    const controller = new AbortController();

    async function fetchData() {
      try {
        const result = await getSignals(controller.signal);
        const live = result.signals
          .filter((s) => s.status === "LIVE")
          .sort((a, b) => b.score - a.score);

        // Diff to find genuinely new ids
        const incoming = new Set(live.map((s) => s.id));
        const fresh: Set<number> = new Set();
        for (const id of incoming) {
          if (!seenIdsRef.current.has(id)) {
            fresh.add(id);
          }
        }
        seenIdsRef.current = incoming;
        newIdsRef.current = fresh;

        setSignals(live);
        setPanelState(live.length === 0 ? "empty" : "data");
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        setPanelState("error");
      }
    }

    fetchData();
    return () => controller.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshTick]);

  const count = panelState === "data" ? signals.length : 0;
  const isPulsing = panelState === "data" && count > 0;

  return (
    <section
      style={{
        backgroundColor: "var(--bg-card)",
        border: "1px solid var(--border-color)",
        borderRadius: "6px",
        padding: "var(--space-lg)",
        marginBottom: "var(--space-lg)",
        boxShadow: "0 2px 4px rgba(0,0,0,0.2)",
      }}
    >
      {/* Panel header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-sm)",
          marginBottom: "var(--space-sm)",
        }}
      >
        <div
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            backgroundColor: "var(--negative)",
            flexShrink: 0,
            animation: isPulsing ? "pulse-dot 1s ease-in-out infinite" : "none",
          }}
        />
        <span
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: panelState === "error" ? "var(--negative)" : "var(--text-primary)",
            textTransform: "uppercase",
          }}
        >
          LIVE NOW
        </span>
        {panelState === "loading" && (
          <span
            style={{
              display: "inline-block",
              width: 14,
              height: 14,
              border: "2px solid var(--text-muted)",
              borderTopColor: "var(--accent-cyan)",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
              marginLeft: 6,
            }}
          />
        )}
        {panelState === "error" && (
          <span style={{ fontSize: "14px", color: "var(--negative)" }}>(!) </span>
        )}
        {panelState !== "loading" && panelState !== "error" && (
          <span style={{ fontSize: "14px", color: "var(--text-secondary)" }}>
            ({count})
          </span>
        )}
      </div>

      {/* Divider */}
      <div
        style={{
          borderTop: "1px solid var(--border-color)",
          marginBottom: "var(--space-sm)",
        }}
      />

      {/* Content */}
      {panelState === "loading" && (
        <>
          <SkeletonRow />
          <SkeletonRow />
        </>
      )}
      {panelState === "empty" && (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", margin: 0 }}>
          No active setups
        </p>
      )}
      {panelState === "error" && (
        <p
          style={{
            color: "var(--negative)",
            fontSize: "12px",
            fontWeight: 600,
            margin: 0,
          }}
        >
          Failed to load — retrying
        </p>
      )}
      {panelState === "data" && signals.length === 0 && (
        <p style={{ color: "var(--text-muted)", fontSize: "14px", margin: 0 }}>
          No active setups
        </p>
      )}
      {panelState === "data" && signals.length > 0 && (
        <div>
          {signals.map((s) => (
            <SignalRow_
              key={s.id}
              signal={s}
              panelType="live"
              onClick={onSignalClick}
              isNew={newIdsRef.current.has(s.id)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
