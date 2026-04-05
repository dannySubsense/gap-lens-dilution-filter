import type {
  SignalListResponse,
  SignalDetailResponse,
  HealthResponse,
  PositionRequest,
  SignalRow,
} from "@/types/signals";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options?: RequestInit & { signal?: AbortSignal }
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function getSignals(signal?: AbortSignal): Promise<SignalListResponse> {
  return request<SignalListResponse>("/api/v1/signals", { signal });
}

export async function getClosedSignals(signal?: AbortSignal): Promise<SignalListResponse> {
  return request<SignalListResponse>("/api/v1/signals/closed", { signal });
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>("/api/v1/health", { signal });
}

export async function getSignalDetail(
  id: number,
  signal?: AbortSignal
): Promise<SignalDetailResponse> {
  return request<SignalDetailResponse>(`/api/v1/signals/${id}`, { signal });
}

export async function recordPosition(
  id: number,
  body: PositionRequest,
  signal?: AbortSignal
): Promise<SignalRow> {
  return request<SignalRow>(`/api/v1/signals/${id}/position`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export async function closeSignal(
  id: number,
  signal?: AbortSignal
): Promise<SignalDetailResponse> {
  return request<SignalDetailResponse>(`/api/v1/signals/${id}/close`, {
    method: "POST",
    signal,
  });
}
