import { useEffect, useMemo, useState } from "react";
import { Calculator, RotateCcw, SlidersHorizontal } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { api } from "../../lib/api";
import { formatNumber } from "../../lib/utils";
import type { ROIRequest, ROIResponse, ROICosts } from "../../types/api";

const fields: { key: keyof ROICosts; label: string; step: number; suffix: string }[] = [
  { key: "kegagalan_per_unit_tahun", label: "Kegagalan per unit per tahun", step: 0.1, suffix: "kejadian" },
  { key: "downtime_jam_per_kegagalan", label: "Downtime per kegagalan", step: 0.5, suffix: "jam" },
  { key: "biaya_downtime_per_jam", label: "Biaya downtime per jam", step: 0.05, suffix: "UB/jam" },
  { key: "biaya_perbaikan_darurat", label: "Perbaikan darurat", step: 0.1, suffix: "UB" },
  { key: "biaya_perbaikan_terencana", label: "Perbaikan terencana", step: 0.1, suffix: "UB" },
  { key: "biaya_inspeksi", label: "Inspeksi per alarm palsu", step: 0.01, suffix: "UB" },
  { key: "interval_penggantian_bulan", label: "Interval preventif", step: 1, suffix: "bulan" },
  { key: "biaya_penggantian_preventif", label: "Penggantian preventif", step: 0.1, suffix: "UB" },
  { key: "kegagalan_lolos_preventif", label: "Kegagalan lolos preventif", step: 0.05, suffix: "rasio" },
  { key: "biaya_sistem", label: "Biaya sistem prediktif", step: 0.1, suffix: "UB/tahun" },
];
const chartColors: Record<string, string> = { Reaktif: "#ef7666", Preventif: "#f5b84f", Prediktif: "#41d5b3" };

export function RoiPage() {
  const [scenario, setScenario] = useState<ROIRequest["scenario"]>("Dasar");
  const [data, setData] = useState<ROIResponse | null>(null);
  const [costs, setCosts] = useState<Partial<ROICosts>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true); setError(null);
    api.roi({ scenario, costs }).then((result) => { if (alive) setData(result); }).catch((err: Error) => { if (alive) setError(err.message); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [scenario, costs]);

  const selected = data?.selected;
  const chartData = useMemo(() => selected ? Object.entries(selected.annual_costs).map(([name, value]) => ({ name, biaya: value })) : [], [selected]);
  const updateCost = (key: keyof ROICosts, raw: string) => {
    if (raw === "") { setCosts((previous) => { const next = { ...previous }; delete next[key]; return next; }); return; }
    setCosts((previous) => ({ ...previous, [key]: Number(raw) }));
  };

  return <>
    <PageIntro eyebrow="MAINTENANCE ECONOMICS" title="Simulasi biaya & ROI" description="Ubah asumsi biaya untuk membandingkan biaya tahunan tiga strategi pemeliharaan." actions={<button className="button button-outline" onClick={() => setCosts({})}><RotateCcw size={14} />Reset biaya</button>} />
    <div className="roi-top-grid"><Panel title="Asumsi biaya" subtitle="Satuan biaya dalam unit biaya (UB)" action={<span className="small-label"><SlidersHorizontal size={14} />DAPAT DIUBAH</span>}>
      <div className="scenario-tabs">{(["Batas rendah", "Dasar", "Batas tinggi"] as const).map((item) => <button key={item} className={scenario === item ? "selected" : ""} onClick={() => { setScenario(item); setCosts({}); }}>{item}</button>)}</div>
      <div className="roi-form-grid">{fields.map(({ key, label, step, suffix }) => <label className="roi-field" key={key}><span>{label}</span><div><input type="number" min="0" step={step} value={costs[key] ?? selected?.costs[key] ?? ""} placeholder={selected ? String(selected.costs[key]) : ""} onChange={(event) => updateCost(key, event.target.value)} /><small>{suffix}</small></div></label>)}</div>
      <div className="detection-basis"><span className="basis-info"><Calculator size={15} />Metrik deteksi tetap dari walk-forward</span><span>Recall resmi <strong>{data ? formatNumber(data.detection_basis.official_recall * 100, 0) : "—"}%</strong></span><span>FP Merah <strong>{data ? formatNumber(data.detection_basis.false_red_alarms_per_week, 2) : "—"}</strong> / minggu</span></div>
    </Panel><Panel title="Biaya operasional per tahun" subtitle={`Skenario ${scenario} · ${busy ? "menghitung…" : "estimasi biaya"}`} className="roi-chart-panel"><div className="roi-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 8, right: 14, bottom: 4, left: -12 }}><CartesianGrid stroke="#26332f" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="name" tick={{ fill: "#91a198", fontSize: 11 }} axisLine={{ stroke: "#34413c" }} tickLine={false} /><YAxis tick={{ fill: "#73857d", fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: "#18211f", border: "1px solid #2b3a35", borderRadius: 12, fontSize: 12 }} formatter={(value) => [`${formatNumber(Number(value), 2)} UB`, "Biaya tahunan"]} /><Bar dataKey="biaya" radius={[6, 6, 0, 0]}>{chartData.map((item) => <Cell key={item.name} fill={chartColors[item.name]} />)}</Bar></BarChart></ResponsiveContainer></div><div className="roi-highlights"><div><span>ROI vs reaktif</span><strong className={(selected?.roi_vs_reactive_percent ?? 0) >= 0 ? "positive" : "negative"}>{selected ? `${formatNumber(selected.roi_vs_reactive_percent, 1)}%` : "—"}</strong></div><div><span>ROI vs preventif</span><strong className={(selected?.roi_vs_preventive_percent ?? 0) >= 0 ? "positive" : "negative"}>{selected ? `${formatNumber(selected.roi_vs_preventive_percent, 1)}%` : "—"}</strong></div></div></Panel></div>
    {error && <div className="inline-error">{error}</div>}
    <div className="roi-bottom-grid"><Panel title="Analisis sensitivitas" subtitle="Perubahan ROI bila parameter bergeser ±30%"><div className="sensitivity-list">{data?.sensitivity.slice(0, 7).map((item) => <div className="sensitivity-row" key={item.parameter}><span>{item.parameter.replaceAll("_", " ")}</span><div className="sensitivity-track"><i style={{ width: `${Math.min(100, item.rentang / Math.max(data.sensitivity[0]?.rentang ?? 1, 1) * 100)}%` }} /></div><strong>{formatNumber(item.rentang, 1)} pt</strong></div>)}</div></Panel><Panel title="Titik impas" subtitle="Kondisi ketika ROI terhadap reaktif mencapai 0%"><div className="break-even-list">{data?.break_even.map((item) => <div className="break-even-row" key={item.parameter}><span>{item.parameter.replaceAll("_", " ")}</span><strong>{item.titik_impas == null ? "Tidak tercapai dalam rentang uji" : formatNumber(item.titik_impas, 3)}</strong></div>)}</div></Panel></div>
    <div className="note-card"><Calculator size={18} /><div><strong>Simulasi berbasis asumsi, bukan harga operasional aktual</strong><p>Frekuensi kegagalan, downtime, dan metrik deteksi mengikuti validasi historis. Ganti asumsi dengan data biaya operasional sebelum memakai angka ini untuk keputusan investasi.</p></div><span>1 UB = 1 biaya perbaikan terencana</span></div>
  </>;
}
