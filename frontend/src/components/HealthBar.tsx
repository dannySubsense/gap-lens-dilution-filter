"use client";
import { useEffect, useRef, useState } from "react";
import { getHealth } from "@/services/api";
import type { HealthResponse } from "@/types/signals";

type DotState = "ok" | "degraded" | "error" | "unknown";

function getDotColor(state: DotState): string {
  switch (state) {
    case "ok":
      return "var(--positive)";
    case "degraded":
      return "var(--warning)";
    case "error":
      return "var(--negative)";
    case "unknown":
      return "var(--text-muted)";
  }
}

function getDotTitle(state: DotState): string {
  switch (state) {
    case "ok":
      return "System healthy";
    case "degraded":
      return "Poll delayed";
    case "error":
      return "Poll failed or stalled";
    case "unknown":
      return "Waiting for first poll";
  }
}

function computeDotState(health: HealthResponse): DotState {
  if (!health.last_success_at) return "unknown";
  const elapsed = (Date.now() - new Date(health.last_success_at).getTime()) / 1000;
  if (elapsed < 180) return "ok";
  if (elapsed < 600) return "degraded";
  return "error";
}

function formatElapsed(seconds: number): string {
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${Math.floor(seconds)}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

export default function HealthBar() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [dotState, setDotState] = useState<DotState>("unknown");
  const [elapsed, setElapsed] = useState<number | null>(null);
  const lastSuccessRef = useRef<string | null>(null);

  function updateElapsed() {
    if (!lastSuccessRef.current) {
      setElapsed(null);
      return;
    }
    const secs = (Date.now() - new Date(lastSuccessRef.current).getTime()) / 1000;
    setElapsed(secs);
  }

  useEffect(() => {
    const controller = new AbortController();

    const fetchHealth = async () => {
      try {
        const data = await getHealth(controller.signal);
        setHealth(data);
        lastSuccessRef.current = data.last_success_at;
        setDotState(computeDotState(data));
        updateElapsed();
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setDotState("error");
      }
    };

    fetchHealth();
    const healthInterval = setInterval(fetchHealth, 15_000);
    const tickInterval = setInterval(updateElapsed, 1_000);

    return () => {
      controller.abort();
      clearInterval(healthInterval);
      clearInterval(tickInterval);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const isPulsing = dotState === "degraded" || dotState === "error";
  const dotColor = getDotColor(dotState);
  const dotTitle = getDotTitle(dotState);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--space-sm)",
        fontSize: "12px",
        color: "var(--text-secondary)",
      }}
    >
      <span>
        {elapsed !== null ? `Last poll: ${formatElapsed(elapsed)}` : "Last poll: —"}
      </span>
      <div
        title={dotTitle}
        style={{
          width: "8px",
          height: "8px",
          borderRadius: "50%",
          backgroundColor: dotColor,
          animation: isPulsing ? "pulse-dot 1s ease-in-out infinite" : "none",
          flexShrink: 0,
        }}
      />
    </div>
  );
}
