import type { AlarmRecord, Frame, NotificationRecord, ReplayMetadata, ROIRequest, ROIResponse, TelemetryResponse } from "../types/api";

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("API tidak dapat dijangkau. Pastikan FastAPI sedang berjalan.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null;
    throw new Error(body?.detail ?? `API gagal (${response.status}).`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string; data_ready: boolean; detail?: string }>('/health'),
  metadata: () => request<ReplayMetadata>('/replay/metadata'),
  frame: (timestamp: string) => request<Frame>(`/replay/frame?timestamp=${encodeURIComponent(timestamp)}`),
  telemetry: (start: string, end: string, signals: string[], limit = 1200) => {
    const query = new URLSearchParams({ start, end, limit: String(limit) });
    signals.forEach((signal) => query.append("signals", signal));
    return request<TelemetryResponse>(`/telemetry?${query.toString()}`);
  },
  alarms: (through: string, limit = 1000) => request<AlarmRecord[]>(`/alarms?through=${encodeURIComponent(through)}&limit=${limit}`),
  notifications: (through: string) => request<NotificationRecord[]>(`/notifications?through=${encodeURIComponent(through)}`),
  roi: (body: ROIRequest) => request<ROIResponse>("/roi/calculate", { method: "POST", body: JSON.stringify(body) }),
};
