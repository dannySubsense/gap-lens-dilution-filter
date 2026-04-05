"use client";
import { useEffect, useState } from "react";
import Header from "@/components/Header";
import LiveNowPanel from "@/components/LiveNowPanel";
import WatchlistPanel from "@/components/WatchlistPanel";
import RecentClosedPanel from "@/components/RecentClosedPanel";
import SetupDetailModal from "@/components/SetupDetailModal";
import { getHealth } from "@/services/api";

export default function DashboardPage() {
  const [fmpWarning, setFmpWarning] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);
  const [selectedSignalId, setSelectedSignalId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    async function checkHealth() {
      try {
        const health = await getHealth(controller.signal);
        setFmpWarning(!health.fmp_configured);
      } catch {
        // Health check failure is surfaced by HealthBar; no page-level action needed
      }
    }

    checkHealth();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const intervalMs = Number(process.env.NEXT_PUBLIC_REFRESH_INTERVAL_MS ?? 30_000);
    const id = setInterval(() => setRefreshTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, []);

  function handleSignalClick(id: number) {
    setSelectedSignalId(id);
  }

  return (
    <div className="dsf-page">
      <Header />
      <main
        style={{
          maxWidth: "960px",
          margin: "0 auto",
          padding: "var(--space-xxl) var(--space-xl)",
        }}
      >
        {fmpWarning && (
          <div
            role="alert"
            style={{
              backgroundColor: "#3d2400",
              border: "1px solid var(--warning)",
              borderRadius: "6px",
              padding: "var(--space-md) var(--space-lg)",
              marginBottom: "var(--space-lg)",
              fontSize: "12px",
              fontWeight: 600,
              color: "var(--warning)",
            }}
          >
            FMP API key not configured — enrichment disabled. Check your .env file.
          </div>
        )}
        <LiveNowPanel refreshTick={refreshTick} onSignalClick={handleSignalClick} />
        <WatchlistPanel refreshTick={refreshTick} onSignalClick={handleSignalClick} />
        <RecentClosedPanel refreshTick={refreshTick} onSignalClick={handleSignalClick} />
      </main>
      <SetupDetailModal
        signalId={selectedSignalId}
        onClose={() => setSelectedSignalId(null)}
      />
    </div>
  );
}
