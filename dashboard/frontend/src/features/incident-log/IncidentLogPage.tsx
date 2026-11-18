import { useEffect, useState } from "react";
import { ArrowUpRight, ClipboardList, Filter } from "lucide-react";
import { useReplay } from "../../app/ReplayContext";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { StatusBadge } from "../../components/shared/StatusBadge";
import { api } from "../../lib/api";
import { formatNumber, formatTimestamp } from "../../lib/utils";
import type { AlarmRecord } from "../../types/api";

export function IncidentLogPage() {
  const { cursor } = useReplay();
  const [alarms, setAlarms] = useState<AlarmRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!cursor) return;
    api.alarms(cursor).then(setAlarms).catch((err: Error) => setError(err.message));
  }, [cursor]);
  return <>
    <PageIntro eyebrow="ALARM HISTORY" title="Log insiden & anomali" description="Episode alarm yang telah terjadi hingga posisi waktu replay saat ini." actions={<span className="data-window-chip"><Filter size={14} />Sampai {formatTimestamp(cursor)}</span>} />
    <Panel title="Episode peringatan" subtitle={`${alarms.length} episode · alarm yang berdekatan digabung dalam jeda 30 menit`}>
      {error && <div className="inline-error">{error}</div>}
      {alarms.length === 0 ? <div className="empty-state"><div className="empty-icon"><ClipboardList size={22} /></div><strong>Belum ada episode alarm</strong><p>Log akan terisi saat replay mencapai status Kuning atau Merah.</p></div> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Waktu mulai</th><th>Durasi</th><th>Level tertinggi</th><th>Pemicu merah</th><th>TP3</th><th>Suhu oli</th><th>Arus motor</th><th></th></tr></thead><tbody>{alarms.slice().reverse().map((alarm) => <tr key={alarm.id}><td><strong>{formatTimestamp(alarm.started_at)}</strong><small>{alarm.red_started_at ? `Merah ${new Date(alarm.red_started_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })}` : "Tidak meningkat ke Merah"}</small></td><td>{alarm.duration_minutes} mnt</td><td><StatusBadge status={alarm.highest_status} /></td><td>{alarm.trigger ?? "—"}</td><td>{formatNumber(typeof alarm.sensors.TP3 === "number" ? alarm.sensors.TP3 : null, 2)} bar</td><td>{formatNumber(typeof alarm.sensors.Oil_temperature === "number" ? alarm.sensors.Oil_temperature : null, 1)} °C</td><td>{formatNumber(typeof alarm.sensors.Motor_current === "number" ? alarm.sensors.Motor_current : null, 2)} A</td><td><ArrowUpRight size={15} className="table-arrow" /></td></tr>)}</tbody></table></div>}
    </Panel>
    <div className="note-card"><ClipboardList size={18} /><div><strong>Log operasional berbasis episode</strong><p>Label kegagalan historis tidak ditampilkan sebagai fakta yang tersedia bagi operator. Baris log hanya memuat waktu alarm, pemicu, durasi, dan cuplikan sensor.</p></div></div>
  </>;
}
