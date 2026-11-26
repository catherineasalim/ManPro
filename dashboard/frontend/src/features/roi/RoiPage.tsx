import { useEffect, useMemo, useState } from "react";
import { Calculator, ChevronDown, ChevronUp, RotateCcw, SlidersHorizontal } from "lucide-react";
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
const scenarioLabels: Record<ROIRequest["scenario"], string> = {
  "Batas rendah": "Low",
  Dasar: "Base",
  "Batas tinggi": "High",
};
function rupiahFromUb(amount: number, rate: number) {
  const value = amount * rate;
  return value >= 1_000_000_000 ? `Rp ${formatNumber(value / 1_000_000_000, 2)} miliar` : `Rp ${formatNumber(value / 1_000_000, 1)} juta`;
}
const chartColors: Record<string, string> = { Reaktif: "#ef7666", Preventif: "#f5b84f", Prediktif: "#41d5b3" };
const parameterLabels: Record<string, string> = {
  kegagalan_per_unit_tahun: "Kegagalan per unit per tahun",
  downtime_jam_per_kegagalan: "Downtime per kegagalan",
  biaya_downtime_per_jam: "Biaya downtime per jam",
  biaya_perbaikan_darurat: "Perbaikan darurat",
  biaya_perbaikan_terencana: "Perbaikan terencana",
  biaya_inspeksi: "Inspeksi per alarm palsu",
  interval_penggantian_bulan: "Interval penggantian preventif",
  biaya_penggantian_preventif: "Biaya penggantian preventif",
  kegagalan_lolos_preventif: "Kegagalan lolos preventif",
  biaya_sistem: "Biaya sistem prediktif per tahun",
};

export function RoiPage() {
  const [scenario, setScenario] = useState<ROIRequest["scenario"]>("Dasar");
  const [data, setData] = useState<ROIResponse | null>(null);
  const [costs, setCosts] = useState<Partial<ROICosts>>({});
  const [assumptionsExpanded, setAssumptionsExpanded] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setBusy(true); setError(null);
    api.roi({ scenario, costs }).then((result) => { if (alive) setData(result); }).catch((err: Error) => { if (alive) setError(err.message); }).finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [scenario, costs]);

  const selected = data?.selected;
  const chartData = useMemo(() => selected ? Object.entries(selected.annual_costs).map(([name, value]) => ({ name, biaya: value, rupiah: rupiahFromUb(value, data?.rupiah_per_ub ?? 50_000_000) })) : [], [selected, data?.rupiah_per_ub]);
  const updateCost = (key: keyof ROICosts, raw: string) => {
    if (raw === "") { setCosts((previous) => { const next = { ...previous }; delete next[key]; return next; }); return; }
    setCosts((previous) => ({ ...previous, [key]: Number(raw) }));
  };

  return <>
    <PageIntro eyebrow="MAINTENANCE ECONOMICS" title="Simulasi biaya & ROI" description="Ubah asumsi biaya untuk membandingkan biaya tahunan tiga strategi pemeliharaan." actions={<button className="button button-outline" onClick={() => setCosts({})}><RotateCcw size={14} />Reset costs</button>} />
    <div className={`roi-top-grid ${assumptionsExpanded ? "" : "assumptions-collapsed"}`}><Panel title="Asumsi biaya" subtitle="Satuan biaya dalam unit biaya (UB)" action={<div className="roi-panel-actions"><span className="small-label"><SlidersHorizontal size={14} />DAPAT DIUBAH</span><button className="button button-outline roi-collapse-toggle" aria-expanded={assumptionsExpanded} aria-controls="roi-assumptions-content" onClick={() => setAssumptionsExpanded((expanded) => !expanded)}>{assumptionsExpanded ? <><ChevronUp size={14} />Minimize</> : <><ChevronDown size={14} />Expand</>}</button></div>}>
      <div id="roi-assumptions-content" hidden={!assumptionsExpanded}>
      <div className="roi-unit-callout"><span>Nilai konversi ilustratif</span><strong>1 UB = Rp {formatNumber((data?.rupiah_per_ub ?? 50_000_000) / 1_000_000, 0)} juta</strong><small>Asumsi nilai biaya dari laporan proyek</small></div>
      <div className="scenario-tabs">{(["Batas rendah", "Dasar", "Batas tinggi"] as const).map((item) => <button key={item} className={scenario === item ? "selected" : ""} onClick={() => { setScenario(item); setCosts({}); }}>{scenarioLabels[item]}</button>)}</div>
      <div className="roi-form-grid">{fields.map(({ key, label, step, suffix }) => <label className="roi-field" key={key}><span>{label}</span><div><input type="number" min="0" step={step} value={costs[key] ?? selected?.costs[key] ?? ""} placeholder={selected ? String(selected.costs[key]) : ""} onChange={(event) => updateCost(key, event.target.value)} /><small>{suffix}</small></div></label>)}</div>
      <div className="detection-basis"><span className="basis-info"><Calculator size={15} />Metrik deteksi dari status hybrid pada laporan walk-forward</span><span>Recall resmi <strong>{data ? formatNumber(data.detection_basis.official_recall * 100, 0) : "—"}%</strong></span><span>FP Merah <strong>{data ? formatNumber(data.detection_basis.false_red_alarms_per_week, 2) : "—"}</strong> / minggu</span></div>
      </div>{!assumptionsExpanded && <div className="roi-collapsed-summary">Asumsi disembunyikan · Skenario {scenario}</div>}</Panel><Panel title="Biaya operasional per tahun" subtitle={`Skenario ${scenario} · ${busy ? "menghitung…" : "estimasi biaya"}`} className="roi-chart-panel"><div className="roi-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chartData} margin={{ top: 8, right: 14, bottom: 4, left: -12 }}><CartesianGrid stroke="#26332f" strokeDasharray="3 5" vertical={false} /><XAxis dataKey="name" tick={{ fill: "#e8efeb", fontSize: 12, fontWeight: 600 }} axisLine={{ stroke: "#53635a" }} tickLine={false} /><YAxis tick={{ fill: "#d0dbd4", fontSize: 11 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: "#18211f", border: "1px solid #2b3a35", borderRadius: 12, color: "#eef3f0", fontSize: 13 }} itemStyle={{ color: "#e8efeb" }} labelStyle={{ color: "#c5d2ca", marginBottom: 5 }} formatter={(value) => [`${formatNumber(Number(value), 2)} UB · ${rupiahFromUb(Number(value), data?.rupiah_per_ub ?? 50_000_000)}`, "Biaya tahunan"]} /><Bar dataKey="biaya" radius={[6, 6, 0, 0]}>{chartData.map((item) => <Cell key={item.name} fill={chartColors[item.name]} />)}</Bar></BarChart></ResponsiveContainer></div><p className="roi-currency-note">Penghematan tahunan: {selected ? rupiahFromUb(selected.savings_vs_reactive, data?.rupiah_per_ub ?? 50_000_000) : "—"} vs reaktif | {selected ? rupiahFromUb(selected.savings_vs_preventive, data?.rupiah_per_ub ?? 50_000_000) : "—"} vs preventif</p><div className="roi-highlights"><div><span>ROI vs reaktif</span><strong className={(selected?.roi_vs_reactive_percent ?? 0) >= 0 ? "positive" : "negative"}>{selected ? `${formatNumber(selected.roi_vs_reactive_percent, 1)}%` : "—"}</strong></div><div><span>ROI vs preventif</span><strong className={(selected?.roi_vs_preventive_percent ?? 0) >= 0 ? "positive" : "negative"}>{selected ? `${formatNumber(selected.roi_vs_preventive_percent, 1)}%` : "—"}</strong></div></div></Panel></div>
    {error && <div className="inline-error">{error}</div>}
    <div className="roi-bottom-grid"><Panel title="Analisis sensitivitas" subtitle="Rentang ROI dari asumsi -30% hingga +30%"><div className="sensitivity-list">{data?.sensitivity.slice(0, 7).map((item) => <div className="sensitivity-row" key={item.parameter}><span>{parameterLabels[item.parameter] ?? item.parameter}</span><div className="sensitivity-track"><i style={{ width: `${Math.min(100, item.rentang / Math.max(data.sensitivity[0]?.rentang ?? 1, 1) * 100)}%` }} /></div><strong>{formatNumber(item.rentang, 1)} pt</strong></div>)}</div><p className="sensitivity-explanation">Angka pt adalah selisih ROI antara hasil kedua batas tersebut.</p></Panel><Panel title="Titik impas" subtitle="Kondisi ketika ROI terhadap reaktif mencapai 0%"><div className="break-even-list">{data?.break_even.map((item) => <div className="break-even-row" key={item.parameter}><span>{parameterLabels[item.parameter] ?? item.parameter}</span><div className="break-even-value">{item.titik_impas == null ? <strong>Tidak tercapai dalam rentang uji</strong> : item.parameter === "kegagalan_per_unit_tahun" ? <strong>{formatNumber(item.titik_impas, 3)} kejadian/unit/tahun</strong> : <><strong>{formatNumber(item.titik_impas, 3)} UB{item.parameter === "biaya_sistem" ? "/tahun" : ""}</strong><small>≈ {rupiahFromUb(item.titik_impas, data?.rupiah_per_ub ?? 50_000_000)}{item.parameter === "biaya_sistem" ? "/tahun" : ""}</small></>}</div></div>)}</div></Panel></div>
    <div className="note-card"><Calculator size={18} /><div><strong>Simulasi berbasis asumsi, bukan harga operasional aktual</strong><p>Dasar perhitungan alarm mengikuti laporan. Angka rupiah dihitung dari UB sebagai ilustrasi; ubah asumsi biaya operasional sebelum memakai angka ini untuk keputusan investasi.</p></div><span>1 UB = {rupiahFromUb(1, data?.rupiah_per_ub ?? 50_000_000)}</span></div>
  </>;
}
