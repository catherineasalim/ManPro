import { useEffect, useState } from "react";
import { Activity, AlertTriangle, ShieldCheck } from "lucide-react";
import { useReplay } from "../../app/ReplayContext";
import { TelemetryChart } from "../../components/charts/TelemetryChart";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { StatusBadge } from "../../components/shared/StatusBadge";
import { api } from "../../lib/api";
import { formatNumber, localTimestamp } from "../../lib/utils";
import type { TelemetryPoint } from "../../types/api";

export function AnomalyPage() {
  const { current, cursor } = useReplay();
  const [points, setPoints] = useState<TelemetryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!cursor) return;
    const end = new Date(cursor), start = new Date(end.getTime() - 7 * 24 * 60 * 60_000);
    api.telemetry(localTimestamp(start), localTimestamp(end), ["TP3"], 1000).then((result) => setPoints(result.points)).catch((err: Error) => setError(err.message));
  }, [cursor]);
  const probability = current?.probability;
  const level = probability == null ? "Belum tersedia" : probability >= 0.75 ? "Ambang model terlampaui" : "Di bawah ambang";
  return <>
    <PageIntro eyebrow="ANOMALY DETECTION" title="Deteksi berbasis kondisi" description="Skor anomali terkalibrasi dan status dari evaluasi walk-forward per menit." />
    <section className="anomaly-highlight"><div className="anomaly-icon"><Activity size={21} /></div><div className="anomaly-copy"><span>SKOR TERKALIBRASI PADA FRAME</span><strong>{probability == null ? "—" : `${formatNumber(probability * 100, 1)}%`}</strong><small>{level}</small></div><div className="anomaly-current"><span>STATUS MODEL</span>{current && <StatusBadge status={current.status} large />}<small>Pemicu: {current?.trigger ?? "—"}</small></div></section>
    <div className="chart-grid two-columns"><Panel title="Skor anomali" subtitle="Skor terkalibrasi dan ambang keputusan model" className="chart-panel"><TelemetryChart data={points} signals={["p_terkalibrasi"]} cursor={cursor} percent unit="" /><div className="chart-legend"><span><i style={{ background: "#bf9bff" }} />Skor terkalibrasi</span><span><i style={{ background: "#f6b64b" }} />Ambang model</span><span className="threshold-note">Skala 0–100%</span></div>{error && <div className="inline-error">{error}</div>}</Panel><Panel title="Cara membaca" subtitle="Sistem status pada replay"><div className="status-explainer"><div><StatusBadge status="Hijau" /><p>Tidak ada alarm pada pola sensor yang dinilai.</p></div><div><StatusBadge status="Kuning" /><p>Isolation Forest mendeteksi penyimpangan yang perlu dipantau.</p></div><div><StatusBadge status="Merah" /><p>Alarm kritis aktif menurut aturan dan keluaran model.</p></div><div><StatusBadge status="Abu-abu" /><p>Data tidak cukup atau skor model tidak tersedia.</p></div></div></Panel></div>
    <div className="note-card warning-note"><AlertTriangle size={18} /><div><strong>Skor bukan jaminan probabilitas kegagalan</strong><p>Kalibrasi dibuat dari 16 kejadian berlabel. Gunakan skor sebagai sinyal model bersama status dan kondisi telemetri.</p></div><span><ShieldCheck size={15} />Validasi walk-forward</span></div>
  </>;
}
