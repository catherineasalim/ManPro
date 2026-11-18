import { useEffect, useState } from "react";
import { Download, RefreshCw, SlidersHorizontal } from "lucide-react";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { TelemetryChart } from "../../components/charts/TelemetryChart";
import { api } from "../../lib/api";
import { asIso, formatNumber, localInputValue } from "../../lib/utils";
import { useReplay } from "../../app/ReplayContext";
import type { TelemetryPoint } from "../../types/api";

const defaultSignals = ["TP2", "TP3", "Oil_temperature", "Motor_current"];

export function TelemetryPage() {
  const { cursor } = useReplay();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [applied, setApplied] = useState<{ start: string; end: string } | null>(null);
  const [points, setPoints] = useState<TelemetryPoint[]>([]);
  const [total, setTotal] = useState(0);
  const [downsampled, setDownsampled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!cursor || applied) return;
    const end = new Date(cursor);
    const start = new Date(end.getTime() - 6 * 60 * 60_000);
    setFrom(localInputValue(start));
    setTo(localInputValue(end));
    setApplied({ start: asIso(localInputValue(start)), end: asIso(localInputValue(end)) });
  }, [cursor, applied]);

  useEffect(() => {
    if (!applied) return;
    let alive = true;
    setBusy(true); setError(null);
    api.telemetry(applied.start, applied.end, defaultSignals).then((response) => {
      if (!alive) return;
      setPoints(response.points); setTotal(response.total_points); setDownsampled(response.downsampled);
    }).catch((err: Error) => { if (alive) setError(err.message); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [applied]);

  const apply = () => {
    if (!from || !to) return;
    setApplied({ start: asIso(from), end: asIso(to) });
  };
  const rangeLabel = applied ? `${new Date(applied.start).toLocaleString("id-ID")} — ${new Date(applied.end).toLocaleString("id-ID")}` : "Pilih rentang waktu";
  const last = points.at(-1);
  return <>
    <PageIntro eyebrow="TELEMETRY EXPLORER" title="Data telemetri" description="Jelajahi tekanan, suhu, dan arus motor pada data historis kompresor." actions={<button className="button button-outline" onClick={() => applied && setApplied({ ...applied })}><RefreshCw size={14} />Muat ulang</button>} />
    <Panel title="Filter waktu" subtitle={rangeLabel} action={<span className="small-label"><SlidersHorizontal size={14} />FILTER AKTIF</span>}>
      <div className="filter-row"><label>Dari<input type="datetime-local" value={from} onChange={(event) => setFrom(event.target.value)} /></label><label>Sampai<input type="datetime-local" value={to} onChange={(event) => setTo(event.target.value)} /></label><button className="button button-primary" onClick={apply}>Terapkan rentang</button><span className="filter-count">{busy ? "Memuat…" : `${formatNumber(total, 0)} titik data${downsampled ? " · disampling" : ""}`}</span></div>
    </Panel>
    {error && <div className="inline-error">{error}</div>}
    <div className="chart-grid two-columns">
      <Panel title="Tekanan udara" subtitle="TP2 · intake  |  TP3 · discharge" className="chart-panel"><TelemetryChart data={points} signals={["TP2", "TP3"]} cursor={cursor} unit="bar" /><div className="chart-legend"><span><i style={{ background: "#f6b64b" }} />TP2</span><span><i style={{ background: "#3dd6b5" }} />TP3</span></div></Panel>
      <Panel title="Suhu & arus motor" subtitle="Oil temperature · Motor current" className="chart-panel"><TelemetryChart data={points} signals={["Oil_temperature", "Motor_current"]} cursor={cursor} /><div className="chart-legend"><span><i style={{ background: "#f17967" }} />Suhu oli · °C</span><span><i style={{ background: "#8d9bff" }} />Arus motor · A</span></div></Panel>
    </div>
    <Panel title="Pembacaan terakhir pada rentang" subtitle={last ? new Date(last.timestamp).toLocaleString("id-ID") : "Belum ada titik pada rentang ini"}>
      <div className="reading-row">{defaultSignals.map((signal) => <div className="reading-cell" key={signal}><span>{signal.replace("_", " ")}</span><strong>{formatNumber(typeof last?.values[signal] === "number" ? last.values[signal] as number : null, 2)}</strong></div>)}</div>
    </Panel>
    <div className="chart-note"><span className="note-mark">i</span><p>Tarik seleksi di bagian bawah grafik untuk zoom rentang. Garis amber menunjukkan posisi replay saat ini. Maksimal 1.200 titik dikirim untuk menjaga grafik tetap ringan.</p><span><Download size={14} /> Parquet historis</span></div>
  </>;
}
