"use client";
import HealthBar from "./HealthBar";

export default function Header() {
  return (
    <header
      style={{
        height: "48px",
        backgroundColor: "var(--bg-card)",
        borderBottom: "1px solid var(--border-color)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 var(--space-lg)",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <span
        style={{
          fontSize: "16px",
          fontWeight: 700,
          letterSpacing: "0.05em",
        }}
      >
        <span style={{ color: "var(--text-primary)" }}>DILUTION SHORT </span>
        <span style={{ color: "var(--accent-cyan)" }}>FILTER</span>
      </span>
      <HealthBar />
    </header>
  );
}
