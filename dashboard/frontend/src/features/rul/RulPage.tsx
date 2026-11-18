import { useEffect, useState } from "react";
import { Clock3, Gauge, Info } from "lucide-react";
import { useReplay } from "../../app/ReplayContext";
import { TelemetryChart } from "../../components/charts/TelemetryChart";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { api } from "../../lib/api";
import { formatNumber, localTimestamp } from "../../lib/utils";
import type { TelemetryPoint } from "../../types/api";

const stageClass = (stage?: string | null) => stage?.toLowerCase() ?? "unavailable";

export function RulPage() {
  const { current, cursor } = useReplay();
  const [points, setPoints] = useState<TelemetryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!cursor) return;
    const end = new Date(cursor), start = new Date(end.getTime() - 24 * 60 * 60_000);
    api.telemetry(localTimestamp(start), localTimestamp(end), ["TP3"], 1000).then((result) => setPoints(result.points)).catch((err: Error) => setError(err.message));
  }, [cursor]);
  const value = current?.rul_hours;
  return <>
    <PageIntro eyebrow="REMAINING USEFUL LIFE" title="Perkiraan sisa waktu operasi" description="Perkiraan RUL model XGBoost, dengan tahap risiko dan interval yang tersedia pada validasi." />
    <div className="rul-main-grid"><section className={`rul-card stage-${stageClass(current?.rul_stage)}`}><div className="rul-card-top"><div className="rul-symbol"><Gauge size={21} /></div><span className="small-label">RUL FRAME SAAT INI</span></div><div className="rul-value">{value == null ? "—" : formatNumber(value, 1)}<span>{value == null ? "" : "jam"}</span></div><div className="rul-days">{value == null ? "Belum ada estimasi pada timestamp ini" : `Sekitar ${formatNumber(value / 24, 2)} hari`}</div><div className={`rul-stage-pill stage-pill-${stageClass(current?.rul_stage)}`}>{current?.rul_stage ?? "Tidak tersedia"}</div><div className="rul-interval"><span>Rentang perkiraan 80%</span><strong>{current?.rul_lower == null || current?.rul_upper == null ? "—" : `${formatNumber(current.rul_lower, 1)} – ${formatNumber(current.rul_upper, 1)} jam`}</strong></div></section>
      <Panel title="Tahap risiko" subtitle="Aturan tampilan keluaran model"><div className="stage-list"><div className={`stage-row ${current?.rul_stage === "Failure" ? "current" : ""}`}><i className="stage-bar red" /><div><strong>Failure</strong><small>Pola kegagalan sedang terdeteksi</small></div><span>0 jam</span></div><div className={`stage-row ${current?.rul_stage === "Critical" ? "current" : ""}`}><i className="stage-bar coral" /><div><strong>Critical</strong><small>Perlu inspeksi segera</small></div><span>≤ 6 jam</span></div><div className={`stage-row ${current?.rul_stage === "Warning" ? "current" : ""}`}><i className="stage-bar amber" /><div><strong>Warning</strong><small>Jadwalkan evaluasi kondisi</small></div><span>6–24 jam</span></div><div className={`stage-row ${current?.rul_stage === "Normal" ? "current" : ""}`}><i className="stage-bar mint" /><div><strong>Normal</strong><small>Di luar jendela peringatan RUL</small></div><span>&gt; 24 jam</span></div></div></Panel></div>
    <Panel title="Lintasan RUL" subtitle="Perkiraan mengikuti posisi replay · interval dapat berbeda menurut tahap"><TelemetryChart data={points} signals={["rul_hours"]} cursor={cursor} unit="jam" /><div className="chart-legend"><span><i style={{ background: "#3dd6b5" }} />RUL prediksi</span><span className="threshold-note">Batas model 72 jam</span></div>{error && <div className="inline-error">{error}</div>}</Panel>
    <div className="note-card warning-note"><Info size={18} /><div><strong>Perkiraan, bukan jadwal penggantian pasti</strong><p>Validasi menunjukkan MAE pra-kegagalan sekitar 33,9 jam dan belum membuktikan peringatan 24–72 jam sebelumnya. Gunakan tahap dan rentangnya untuk membantu evaluasi teknisi.</p></div><span><Clock3 size={15} />Maksimum 72 jam</span></div>
  </>;
}
