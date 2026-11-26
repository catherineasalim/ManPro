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

  const eventCount = messages.filter((item) => item.channel === "Email").length;

  return <>
    <PageIntro eyebrow="RED ALERTS" title="Pusat notifikasi" description="Kejadian Merah saat replay; Kuning tidak ditampilkan." actions={<span className="simulation-chip"><Radio size={14} /> EMAIL MAILTRAP</span>} />
    <div className="notice-strip"><BellRing size={17} /><span>Email dikirim melalui Mailtrap saat replay melewati kejadian Merah. WhatsApp Bot masih simulasi. Isi MAILTRAP_API_KEY di dashboard/backend/.env untuk mengaktifkan pengiriman.</span></div>
    <Panel title="Riwayat notifikasi Merah" subtitle={`${eventCount} kejadian Merah · Email Mailtrap dan WhatsApp simulasi`}>
      {error && <div className="inline-error">{error}</div>}
      {messages.length === 0 ? <div className="empty-state"><div className="empty-icon"><BellRing size={22} /></div><strong>Belum ada kejadian Merah</strong><p>Putar replay sampai status mencapai Merah.</p></div> : <div className="notification-list">{messages.slice().reverse().map((item) => {
        const deliveryClass = item.delivery === "Terkirim" ? "sent" : item.delivery === "Gagal" ? "failed" : item.delivery === "Simulasi" ? "simulated" : "pending";
        return <article className="notification-item" key={item.id}><div className={`notification-channel ${item.channel === "Email" ? "email" : "whatsapp"}`}>{item.channel === "Email" ? <Mail size={17} /> : <MessageCircle size={17} />}</div><div className="notification-content"><div className="notification-title"><strong>{item.title}</strong><StatusBadge status={item.status} /></div><p>{item.message}</p><div className="notification-meta"><span>{item.channel}</span><span>·</span><span>{formatTimestamp(item.timestamp)}</span><span className={`delivery-tag ${deliveryClass}`}>{item.delivery}</span></div>{item.delivery_error && <p className="delivery-error">Detail: {item.delivery_error}</p>}</div></article>;
      })}</div>}
    </Panel>
  </>;
}
