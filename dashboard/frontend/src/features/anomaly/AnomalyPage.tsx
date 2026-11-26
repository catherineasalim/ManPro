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
  const { current, cursor, metadata } = useReplay();
  const [points, setPoints] = useState<TelemetryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!cursor) return;
    const end = new Date(cursor), start = new Date(end.getTime() - 7 * 24 * 60 * 60_000);
    api.telemetry(localTimestamp(start), localTimestamp(end), ["TP3"], 1000).then((result) => setPoints(result.points)).catch((err: Error) => setError(err.message));
  }, [cursor]);
  const probability = current?.probability;
  const model = metadata?.model_summary;
  const threshold = current?.threshold;
  const level = probability == null ? "Belum tersedia" : threshold == null ? "Ambang tidak tersedia" : probability >= threshold ? "Ambang model terlampaui" : "Di bawah ambang";
  return <>
    <PageIntro eyebrow="ANOMALY DETECTION" title="Deteksi berbasis kondisi" description="Skor anomali terkalibrasi dan status dari evaluasi walk-forward per menit." />
    <section className="anomaly-highlight"><div className="anomaly-icon"><Activity size={21} /></div><div className="anomaly-copy"><span>SKOR ENSEMBLE PADA FRAME</span><strong>{probability == null ? "—" : `${formatNumber(probability * 100, 1)}%`}</strong><small>{level} · Ambang {threshold == null ? "—" : `${formatNumber(threshold * 100, 0)}%`}</small></div><div className="anomaly-current"><span>STATUS HYBRID</span>{current && <StatusBadge status={current.status} large />}<small>Pemicu: {current?.trigger ?? "—"}</small></div></section>
    <div className="chart-grid two-columns anomaly-grid"><Panel title="Skor anomali" subtitle="Skor ensemble terkalibrasi dan ambang pada waktu replay" className="chart-panel"><TelemetryChart data={points} signals={["p_terkalibrasi"]} cursor={cursor} percent unit="" /><div className="chart-legend"><span><i style={{ background: "#bf9bff" }} />Skor ensemble terkalibrasi</span><span><i style={{ background: "#f6b64f" }} />Ambang bulan berjalan</span><span className="threshold-note">Skala 0–100%</span></div>{error && <div className="inline-error">{error}</div>}</Panel><Panel title="Cara membaca" subtitle="Skor model dan status hybrid pada replay"><div className="status-explainer"><div><StatusBadge status="Hijau" /><p>Tidak ada alarm pada pola sensor yang dinilai.</p></div><div><StatusBadge status="Kuning" /><p>Isolation Forest atau aturan hybrid menandai pola yang perlu dipantau.</p></div><div><StatusBadge status="Merah" /><p>Status kritis dari sistem hybrid; tidak ditentukan oleh skor ensemble saja.</p></div><div><StatusBadge status="Abu-abu" /><p>Data tidak cukup atau model supervised belum aktif.</p></div></div></Panel></div>
    <div className="chart-grid two-columns anomaly-grid"><Panel title="Ringkasan model" subtitle="Artefak final yang dievaluasi dengan walk-forward"><div className="status-explainer"><div><strong>Model {model?.anomaly_model ?? "ensemble"}</strong><p>{model?.anomaly_calibration ?? "Kalibrasi isotonic"}. Ambang final metadata: {model?.anomaly_threshold == null ? "—" : `${formatNumber(model.anomaly_threshold * 100, 0)}%`}.</p></div><div><strong>Anggota ensemble</strong><p>{model?.anomaly_members.map((member) => member === "rf" ? "Random Forest" : member === "xgb_dangkal" ? "XGBoost dangkal" : member === "xgb_sedang" ? "XGBoost sedang" : member).join(" + ") || "Random Forest + dua XGBoost"}</p></div><div><strong>{model?.anomaly_features.length ?? 9} fitur proses</strong><p>{model?.anomaly_features.join(", ") || "Daftar fitur metadata model final."}</p></div><div><strong>ECE {model?.calibrated_ece == null ? "—" : formatNumber(model.calibrated_ece, 4)}</strong><p>Ini metrik kalibrasi ensemble, bukan metrik status hybrid.</p></div></div></Panel><Panel title="Ambang per bulan" subtitle="Nilai ambang dari keluaran walk-forward"><div className="status-explainer">{model?.monthly_thresholds.map((item) => <div key={item.month}><strong>{item.month}</strong><p>{item.supervised_active ? `Ambang ${item.threshold == null ? "—" : `${formatNumber(item.threshold * 100, 0)}%`}` : "Model supervised belum aktif (cold start)."}</p></div>)}</div></Panel></div>
    <div className="note-card warning-note"><AlertTriangle size={18} /><div><strong>Skor bukan jaminan probabilitas kegagalan</strong><p>ECE dihitung dari data walk-forward. Status akhir menggabungkan skor supervised dengan Isolation Forest dan aturan hybrid.</p></div><span><ShieldCheck size={15} />Validasi walk-forward</span></div>
  </>;
}
