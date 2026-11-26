import { useEffect, useMemo, useState } from "react";
import { ClipboardList, Filter, RotateCcw } from "lucide-react";
import { useReplay } from "../../app/ReplayContext";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { StatusBadge } from "../../components/shared/StatusBadge";
import { api } from "../../lib/api";
import { formatNumber, formatTimestamp } from "../../lib/utils";
import type { AlarmRecord } from "../../types/api";

type LevelFilter = "Semua" | "Kuning" | "Merah";

export function IncidentLogPage() {
  const { cursor } = useReplay();
  const [alarms, setAlarms] = useState<AlarmRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<LevelFilter>("Semua");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    if (!cursor) return;
    api.alarms(cursor, 1000).then(setAlarms).catch((err: Error) => setError(err.message));
  }, [cursor]);

  const invalidRange = Boolean(from && to && new Date(from).getTime() > new Date(to).getTime());
  const filteredAlarms = useMemo(() => {
    if (invalidRange) return [];
    const startAt = from ? new Date(from).getTime() : null;
    // datetime-local has minute precision; include the entire selected end minute.
    const endAt = to ? new Date(to).getTime() + 60_000 - 1 : null;
    return alarms
      .filter((alarm) => level === "Semua" || alarm.highest_status === level)
      .filter((alarm) => {
        const startedAt = new Date(alarm.started_at).getTime();
        return (startAt === null || startedAt >= startAt) && (endAt === null || startedAt <= endAt);
      })
      .slice()
      .reverse();
  }, [alarms, from, invalidRange, level, to]);

  const resetFilters = () => {
    setLevel("Semua");
    setFrom("");
    setTo("");
  };

  return <>
    <PageIntro eyebrow="ALARM HISTORY" title="Log insiden & anomali" description="Episode alarm yang telah terjadi hingga posisi waktu replay saat ini." actions={<span className="data-window-chip"><Filter size={14} />Sampai {formatTimestamp(cursor)}</span>} />
    <Panel title="Episode peringatan" subtitle={`${filteredAlarms.length} dari ${alarms.length} episode · alarm berdekatan digabung dalam jeda 30 menit`}>
      <div className="filter-row incident-filters">
        <label>Level tertinggi<select value={level} onChange={(event) => setLevel(event.target.value as LevelFilter)}><option value="Semua">Semua level</option><option value="Kuning">Kuning</option><option value="Merah">Merah</option></select></label>
        <label>Start<input type="datetime-local" value={from} onChange={(event) => setFrom(event.target.value)} /></label>
        <label>End<input type="datetime-local" value={to} onChange={(event) => setTo(event.target.value)} /></label>
        <button className="button button-outline incident-reset" onClick={resetFilters}><RotateCcw size={13} />Reset filters</button>
        <span className="filter-count">{filteredAlarms.length} insiden cocok</span>
      </div>
      {error && <div className="inline-error">{error}</div>}
      {invalidRange && <div className="inline-error">Waktu awal harus sebelum atau sama dengan waktu akhir.</div>}
      {alarms.length === 0 ? <div className="empty-state"><div className="empty-icon"><ClipboardList size={22} /></div><strong>Belum ada episode alarm</strong><p>Log akan terisi saat replay mencapai status Kuning atau Merah.</p></div> : invalidRange ? null : filteredAlarms.length === 0 ? <div className="empty-state"><div className="empty-icon"><ClipboardList size={22} /></div><strong>Tidak ada insiden yang cocok</strong><p>Ubah level atau rentang waktu filter untuk melihat insiden lain.</p></div> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Waktu mulai</th><th>Durasi</th><th>Level tertinggi</th><th>Pemicu merah</th><th>TP3</th><th>Suhu oli</th><th>Arus motor</th></tr></thead><tbody>{filteredAlarms.map((alarm) => <tr key={alarm.id}><td><strong>{formatTimestamp(alarm.started_at)}</strong><small>{alarm.red_started_at ? `Merah ${new Date(alarm.red_started_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}` : "Tidak meningkat ke Merah"}</small></td><td>{alarm.duration_minutes} mnt</td><td><StatusBadge status={alarm.highest_status} /></td><td>{alarm.trigger ?? "—"}</td><td>{formatNumber(typeof alarm.sensors.TP3 === "number" ? alarm.sensors.TP3 : null, 2)} bar</td><td>{formatNumber(typeof alarm.sensors.Oil_temperature === "number" ? alarm.sensors.Oil_temperature : null, 1)} °C</td><td>{formatNumber(typeof alarm.sensors.Motor_current === "number" ? alarm.sensors.Motor_current : null, 2)} A</td></tr>)}</tbody></table></div>}
    </Panel>
    <div className="note-card"><ClipboardList size={18} /><div><strong>Log operasional berbasis episode</strong><p>Label kegagalan historis tidak ditampilkan sebagai fakta yang tersedia bagi operator. Baris log hanya memuat waktu alarm, pemicu, durasi, dan cuplikan sensor.</p></div></div>
  </>;
}
