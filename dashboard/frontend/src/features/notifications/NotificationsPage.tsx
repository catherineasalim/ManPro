import { useEffect, useState } from "react";
import { BellRing, Mail, MessageCircle, Radio } from "lucide-react";
import { useReplay } from "../../app/ReplayContext";
import { PageIntro } from "../../components/shared/PageIntro";
import { Panel } from "../../components/shared/Panel";
import { StatusBadge } from "../../components/shared/StatusBadge";
import { api } from "../../lib/api";
import { formatTimestamp } from "../../lib/utils";
import type { NotificationRecord } from "../../types/api";

export function NotificationsPage() {
  const { cursor } = useReplay();
  const [messages, setMessages] = useState<NotificationRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!cursor) return;
    api.notifications(cursor).then(setMessages).catch((err: Error) => setError(err.message));
  }, [cursor]);
  return <>
    <PageIntro eyebrow="SIMULATED NOTIFICATIONS" title="Pusat notifikasi" description="Pratinjau pesan ketika status replay masuk episode Merah. Status Kuning tidak dikirim; lihat Log insiden." actions={<span className="simulation-chip"><Radio size={14} /> SIMULASI SAJA</span>} />
    <div className="notice-strip"><BellRing size={17} /><span>Pesan email dan WhatsApp di bawah ini hanya simulasi berdasarkan replay historis. Tidak ada pesan yang dikirim ke layanan eksternal.</span></div>
    <Panel title="Riwayat notifikasi" subtitle={`${messages.length / 2} notifikasi Merah · dua kanal simulasi`}>
      {error && <div className="inline-error">{error}</div>}
      {messages.length === 0 ? <div className="empty-state"><div className="empty-icon"><BellRing size={22} /></div><strong>Belum ada notifikasi</strong><p>Putar replay sampai status masuk episode Merah.</p></div> : <div className="notification-list">{messages.slice().reverse().map((item) => <article className="notification-item" key={item.id}><div className={`notification-channel ${item.channel === "Email" ? "email" : "whatsapp"}`}>{item.channel === "Email" ? <Mail size={17} /> : <MessageCircle size={17} />}</div><div className="notification-content"><div className="notification-title"><strong>{item.title}</strong><StatusBadge status={item.status} /></div><p>{item.message}</p><div className="notification-meta"><span>{item.channel}</span><span>·</span><span>{formatTimestamp(item.timestamp)}</span><span className="simulated-tag">Simulasi</span></div></div></article>)}</div>}
    </Panel>
  </>;
}
