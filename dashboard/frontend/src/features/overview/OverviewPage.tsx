import { useMemo } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Clock3, Gauge, Thermometer, Waves, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { StatusBadge } from "../../components/shared/StatusBadge";
import { formatNumber, formatTimestamp } from "../../lib/utils";
import { useReplay } from "../../app/ReplayContext";

const metrics = [
  { key: "TP3", label: "Tekanan discharge", unit: "bar", icon: Waves, color: "mint" },
  { key: "Oil_temperature", label: "Suhu oli", unit: "°C", icon: Thermometer, color: "coral" },
  { key: "Motor_current", label: "Arus motor", unit: "A", icon: Zap, color: "blue" },
  { key: "TP2", label: "Tekanan intake", unit: "bar", icon: Gauge, color: "amber" },
];

function getActuator(value: number | boolean | null | undefined) {
  if (value === null || value === undefined) return "Tidak tersedia";
  return Number(value) >= 0.5 ? "Aktif / berbeban" : "Tidak aktif / tanpa beban";
}

export function OverviewPage() {
  const { current, cursor, metadata } = useReplay();
  const model = metadata?.model_summary;
  const currentTime = formatTimestamp(current?.timestamp ?? cursor);
  const rulDays = current?.rul_hours == null ? null : current.rul_hours / 24;
  const alertText = useMemo(() => {
    if (!current) return "Menunggu frame replay";
    if (current.status === "Abu-abu") return "Data tidak cukup untuk menyimpulkan kondisi mesin.";
    if (current.status === "Merah") return "Pola kritis terdeteksi pada replay historis.";
    if (current.status === "Kuning") return "Pola sensor menyimpang; lanjutkan pemantauan.";
    return "Tidak ada alarm pada frame replay ini.";
  }, [current]);

  return <>
    <PageIntro eyebrow="CONDITION OVERVIEW" title="Status kompresor" description={`Kondisi mesin pada posisi replay · ${currentTime}`} actions={<span className="data-window-chip"><Clock3 size={14} /> Walk-forward · Apr—Agu 2020</span>} />
    <section className={`status-hero hero-${(current?.status ?? "Abu-abu").replace("-", "").toLowerCase()}`}>
      <div className="hero-main"><div className="hero-kicker"><span className="pulse-ring" /> STATUS OPERASI SAAT INI</div><div className="hero-status-row"><h3>{current?.status ?? "Memuat"}</h3>{current && <StatusBadge status={current.status} large />}</div><p>{alertText}</p><div className="hero-meta"><span><Clock3 size={14} />{currentTime}</span><span className="hero-divider" /><span>Pemicu: <strong>{current?.trigger || "Tidak ada"}</strong></span></div></div>
      <div className="hero-rul"><div className="hero-rul-icon"><Gauge size={20} /></div><span className="hero-kicker">RUL PERKIRAAN</span><strong>{current?.rul_hours == null ? "—" : `${formatNumber(current.rul_hours, 1)} jam`}</strong><span>{rulDays == null ? "belum tersedia" : `≈ ${formatNumber(rulDays, 2)} hari`}</span>{current?.rul_lower != null && current.rul_upper != null && <small>Rentang {formatNumber(current.rul_lower, 0)}–{formatNumber(current.rul_upper, 0)} jam</small>}</div>
    </section>
    <div className="metric-grid">{metrics.map(({ key, label, unit, icon: Icon, color }) => {
      const value = current?.sensors[key];
      const numeric = typeof value === "number" ? value : null;
      return <div className="metric-card" key={key}><div className={`metric-icon ${color}`}><Icon size={17} /></div><div className="metric-label">{label}</div><div className="metric-value">{formatNumber(numeric, 2)}<span>{unit}</span></div><div className="metric-foot"><span className="metric-live-dot" />Nilai pada {current ? new Date(current.timestamp).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" }) : "—"}</div></div>;
    })}</div>
    <div className="overview-lower">
      <Panel title="Aktuator kompresor" subtitle="Sinyal digital dari frame replay" action={<Link className="text-link" to="/telemetri">Lihat telemetri <ArrowRight size={14} /></Link>}>
        <div className="actuator-list"><div className="actuator-row"><span className="actuator-symbol">CMP</span><div><strong>COMP</strong><small>Indikator kompresor</small></div><span className={`actuator-state ${current?.sensors.COMP ? "on" : "off"}`}><i />{getActuator(current?.sensors.COMP as number | boolean | null)}</span></div><div className="actuator-row"><span className="actuator-symbol valve">DV</span><div><strong>DV_eletric</strong><small>Katup elektrik / status beban</small></div><span className={`actuator-state ${Number(current?.sensors.DV_eletric ?? 0) >= 0.5 ? "on" : "off"}`}><i />{getActuator(current?.sensors.DV_eletric as number | boolean | null)}</span></div></div>
      </Panel>
      <Panel title="Ringkasan model" subtitle="Validasi maju-waktu, bukan penilaian pada data latih" action={<Link className="text-link" to="/anomali">Detail model <ArrowRight size={14} /></Link>}>
        <div className="model-summary"><div className="summary-stat"><span>Kejadian hybrid terdeteksi</span><strong>{model?.hybrid_events_detected ?? "—"}</strong><span className="summary-hint"><ArrowUpRight size={13} /> Walk-forward</span></div><div className="summary-stat"><span>Kegagalan resmi terdeteksi</span><strong>{model?.hybrid_official_detected ?? "—"}</strong><span className="summary-hint muted">{model?.hybrid_false_alarm_episodes ?? "—"} alarm palsu · {model?.hybrid_false_alarms_per_week == null ? "—" : `${formatNumber(model.hybrid_false_alarms_per_week, 2)} per minggu`}</span></div><div className="summary-note"><span className="note-mark">i</span><p>Anomali: {model?.anomaly_model ?? "model"} terkalibrasi (ECE {model?.calibrated_ece == null ? "—" : formatNumber(model.calibrated_ece, 4)}). RUL belum membuktikan peringatan 24–72 jam sebelum gagal.</p></div></div>
      </Panel>
    </div>
    <div className="overview-footnote"><span><ArrowDownRight size={14} />Data replay dari keluaran walk-forward yang telah tersedia</span><span>Rentang tersedia: {metadata ? `${new Date(metadata.start).toLocaleDateString("id-ID")} – ${new Date(metadata.end).toLocaleDateString("id-ID")}` : "memuat"}</span></div>
  </>;
}
