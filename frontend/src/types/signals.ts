export interface SignalRow {
  id: number;
  accession_number: string;
  ticker: string;
  setup_type: string;
  score: number;
  rank: "A" | "B" | "C" | "D";
  alert_type: "NEW_SETUP" | "SETUP_UPDATE" | "TIME_EXCEEDED";
  status: "LIVE" | "WATCHLIST" | "CLOSED" | "TIME_EXCEEDED";
  alerted_at: string;
  price_at_alert: number | null;
  entry_price: number | null;
  cover_price: number | null;
  pnl_pct: number | null;
  closed_at: string | null;
  close_reason: "MANUAL" | "TIME_EXCEEDED" | null;
  price_move_pct: number | null;
  elapsed_seconds: number | null;
}

export interface ClassificationDetail {
  setup_type: string;
  confidence: number;
  dilution_severity: number;
  immediate_pressure: boolean;
  price_discount: number | null;
  short_attractiveness: number;
  key_excerpt: string;
  reasoning: string;
  classifier_version: string;
  scored_at: string;
}

export interface SignalDetailResponse {
  signal: SignalRow;
  ticker: string;
  entity_name: string | null;
  classification: ClassificationDetail;
  filing_url: string;
  form_type: string;
  filed_at: string;
  current_price: number | null;
}

export interface SignalListResponse {
  signals: SignalRow[];
  count: number;
}

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  last_poll_at: string | null;
  last_success_at: string | null;
  poll_interval_seconds: number;
  fmp_configured: boolean;
  askedgar_configured: boolean;
  db_path: string;
}

export interface PositionRequest {
  entry_price?: number;
  cover_price?: number;
}

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string };
