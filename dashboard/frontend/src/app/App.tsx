import { lazy, Suspense, useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Activity, AlertTriangle, BellRing, ChartNoAxesCombined, ChevronDown, Gauge, LayoutDashboard, Menu, Play, Pause, Radio, Server, ShieldAlert, Siren, Wrench, X } from "lucide-react";
import { api } from "../lib/api";
import { formatTimestamp, localInputValue, localTimestamp } from "../lib/utils";
import { useReplay } from "./ReplayContext";

const OverviewPage = lazy(() => import("../features/overview/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const TelemetryPage = lazy(() => import("../features/telemetry/TelemetryPage").then((module) => ({ default: module.TelemetryPage })));
const AnomalyPage = lazy(() => import("../features/anomaly/AnomalyPage").then((module) => ({ default: module.AnomalyPage })));
const RulPage = lazy(() => import("../features/rul/RulPage").then((module) => ({ default: module.RulPage })));
const NotificationsPage = lazy(() => import("../features/notifications/NotificationsPage").then((module) => ({ default: module.NotificationsPage })));
const IncidentLogPage = lazy(() => import("../features/incident-log/IncidentLogPage").then((module) => ({ default: module.IncidentLogPage })));
const RoiPage = lazy(() => import("../features/roi/RoiPage").then((module) => ({ default: module.RoiPage })));

const navigation = [
  { to: "/", label: "Ringkasan mesin", icon: LayoutDashboard, end: true },
  { to: "/telemetri", label: "Telemetri", icon: Activity },
  { to: "/anomali", label: "Deteksi anomali", icon: ShieldAlert },
  { to: "/rul", label: "Remaining useful life", icon: Gauge },
  { to: "/notifikasi", label: "Notifikasi", icon: BellRing },
  { to: "/insiden", label: "Log insiden", icon: Siren },
  { to: "/roi", label: "Biaya & ROI", icon: ChartNoAxesCombined },
];
const titles: Record<string, string> = {
  "/": "Ringkasan mesin", "/telemetri": "Visualisasi telemetri", "/anomali": "Deteksi anomali",
  "/rul": "Remaining useful life", "/notifikasi": "Pusat notifikasi", "/insiden": "Log insiden & anomali", "/roi": "Simulasi biaya & ROI",
};

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  return <>
    <button className={`sidebar-scrim ${open ? "is-open" : ""}`} onClick={onClose} aria-label="Close menu" />
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-mark"><Activity size={20} strokeWidth={2.6} /></div><div><strong>METRO<span>PT</span></strong><small>CONDITION MONITOR</small></div><button className="icon-button mobile-close" onClick={onClose} aria-label="Close menu"><X size={18} /></button></div>
      <div className="workspace-label">WORKSPACE <span className="live-dot" /></div>
      <div className="asset-card"><div className="asset-icon"><Wrench size={16} /></div><div><strong>Air compressor</strong><small>Metro do Porto · APU</small></div><ChevronDown size={15} /></div>
      <div className="nav-section-label">MONITORING</div>
      <nav className="nav-list">
        {navigation.map(({ to, label, icon: Icon, end }) => <NavLink key={to} to={to} end={end} onClick={onClose} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}><Icon size={17} strokeWidth={1.8} /><span>{label}</span></NavLink>)}
      </nav>
      <div className="sidebar-bottom"><div className="source-indicator"><span className="source-icon"><Server size={15} /></span><div><strong>Mode replay lokal</strong><small>Data historis 2020</small></div><span className="status-dot green" /></div><div className="user-row"><div className="avatar">MP</div><div><strong>ManPro Kelompok 20</strong><small>Dashboard demo</small></div><ChevronDown size={14} /></div></div>
    </aside>
  </>;
}

function ReplayControls() {
  const { metadata, cursor, playing, speed, setCursor, setPlaying, setSpeed, current } = useReplay();
  const [showPicker, setShowPicker] = useState(false);
  const dateValue = cursor ? localInputValue(new Date(cursor)) : "";
  const setDate = (value: string) => { if (value) setCursor(`${value}:00`); };
  const jump = (amount: number) => {
    if (!cursor || !metadata) return;
    const next = new Date(new Date(cursor).getTime() + amount * 60_000);
    const start = new Date(metadata.start), end = new Date(metadata.end);
    setCursor(localTimestamp(new Date(Math.min(Math.max(next.getTime(), start.getTime()), end.getTime()))));
  };
  return <div className="replay-control-wrap">
    <div className="replay-control"><span className="replay-label"><Radio size={14} /> HISTORICAL REPLAY</span><span className="replay-separator" /><button className="play-button" onClick={() => setPlaying(!playing)} aria-label={playing ? "Pause replay" : "Play replay"}>{playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" />}</button><button className="step-button" onClick={() => jump(-1)} aria-label="Back one minute">−1m</button><button className="step-button" onClick={() => jump(1)} aria-label="Forward one minute">+1m</button><span className="replay-time">{formatTimestamp(current?.timestamp ?? cursor, { year: "numeric" })}</span><button className="calendar-button" onClick={() => setShowPicker(!showPicker)} aria-label="Choose replay time"><ChevronDown size={14} /></button><select className="speed-select" aria-label="Replay speed" value={speed} onChange={(event) => setSpeed(Number(event.target.value))}><option value={1}>1×</option><option value={10}>10×</option><option value={60}>60×</option><option value={200}>200×</option><option value={300}>300×</option><option value={500}>500×</option><option value={1000}>1000×</option></select><span className="replay-range">{metadata ? `${new Date(metadata.start).toLocaleDateString("id-ID", { month: "short", year: "numeric" })} — ${new Date(metadata.end).toLocaleDateString("id-ID", { month: "short", year: "numeric" })}` : "Memuat data"}</span></div>
    {showPicker && <div className="replay-popover"><label>Waktu replay<input type="datetime-local" value={dateValue} min={metadata ? localInputValue(new Date(metadata.start)) : undefined} max={metadata ? localInputValue(new Date(metadata.end)) : undefined} onChange={(event) => setDate(event.target.value)} /></label><button className="button button-small" onClick={() => setShowPicker(false)}>Apply</button></div>}
  </div>;
}

function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const location = useLocation();
  const { current, error } = useReplay();
  useEffect(() => { api.health().then((health) => setApiReady(health.data_ready)).catch(() => setApiReady(false)); }, []);
  return <div className="app-shell"><Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} /><main className="main-area"><header className="topbar"><div className="topbar-title"><button className="icon-button menu-toggle" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu size={19} /></button><span className="eyebrow">MAINTENANCE WORKSPACE <span>/</span></span><h1>{titles[location.pathname] ?? "Dashboard"}</h1></div><div className="topbar-actions"><div className={`connection-pill ${apiReady ? "connected" : "disconnected"}`}><span className="status-dot" />{apiReady ? "API terhubung" : "API offline"}</div><button className="topbar-icon" title="Historical replay, no real-time sensor data"><AlertTriangle size={17} /></button><div className="topbar-date">{current ? new Date(current.timestamp).toLocaleDateString("id-ID", { weekday: "short", day: "2-digit", month: "long", year: "numeric" }) : "Data belum dimuat"}</div></div></header><div className="replay-bar"><ReplayControls /><div className="simulation-note"><span className="status-dot amber" />Simulasi · data historis</div></div>{(error || apiReady === false) && <div className="error-banner"><AlertTriangle size={17} /><span>{error ?? "API belum siap. Jalankan backend FastAPI sesuai README dashboard."}</span></div>}<div className="page-content"><Suspense fallback={<div className="loading-state"><span className="loader-dot" />Memuat halaman…</div>}><Routes><Route path="/" element={<OverviewPage />} /><Route path="/telemetri" element={<TelemetryPage />} /><Route path="/anomali" element={<AnomalyPage />} /><Route path="/rul" element={<RulPage />} /><Route path="/notifikasi" element={<NotificationsPage />} /><Route path="/insiden" element={<IncidentLogPage />} /><Route path="/roi" element={<RoiPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></Suspense></div><footer className="app-footer"><span>MetroPT-3 · Predictive maintenance</span><span>Walk-forward replay · Apr—Aug 2020</span></footer></main></div>;
}

export default function App() { return <AppShell />; }
