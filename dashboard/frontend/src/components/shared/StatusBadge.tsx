import type { Status } from "../../types/api";

const labels: Record<Status, string> = { Hijau: "AMAN", Kuning: "PERHATIAN", Merah: "KRITIS", "Abu-abu": "DATA KOSONG" };
export function StatusBadge({ status, large = false }: { status: Status; large?: boolean }) {
  return <span className={`status-badge status-${status.replace("-", "").toLowerCase()} ${large ? "status-large" : ""}`}><span className="status-dot" />{labels[status] ?? status}</span>;
}
