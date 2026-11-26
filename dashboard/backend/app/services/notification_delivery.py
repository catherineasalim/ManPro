from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.core.config import (
    MAILTRAP_API_KEY,
    MAILTRAP_RECIPIENT_EMAIL,
    MAILTRAP_SENDER_EMAIL,
    MAILTRAP_SENDER_NAME,
    NOTIFICATION_DELIVERY_DB,
)
from app.schemas.models import NotificationRecord


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(NOTIFICATION_DELIVERY_DB, timeout=10)
    connection.execute(
        """CREATE TABLE IF NOT EXISTS notification_deliveries (
            notification_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error TEXT
        )"""
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(notification_deliveries)")}
    if "error" not in columns:
        connection.execute("ALTER TABLE notification_deliveries ADD COLUMN error TEXT")
    return connection


def notification_delivery_status(notification_id: str) -> str:
    with _connect() as connection:
        row = connection.execute(
            "SELECT status FROM notification_deliveries WHERE notification_id = ?",
            (notification_id,),
        ).fetchone()
    if row:
        return str(row[0])
    return "Belum dikonfigurasi" if not MAILTRAP_API_KEY else "Belum dikirim"


def notification_delivery_details(notification_id: str) -> tuple[str, str | None]:
    with _connect() as connection:
        row = connection.execute(
            "SELECT status, error FROM notification_deliveries WHERE notification_id = ?",
            (notification_id,),
        ).fetchone()
    if row:
        return str(row[0]), str(row[1]) if row[1] else None
    status = "Belum dikonfigurasi" if not MAILTRAP_API_KEY else "Belum dikirim"
    return status, None


def _claim_notification(notification_id: str) -> tuple[bool, str]:
    with _connect() as connection:
        cursor = connection.execute(
            """INSERT OR IGNORE INTO notification_deliveries
               (notification_id, status, updated_at) VALUES (?, ?, ?)""",
            (notification_id, "Mengirim", datetime.now(UTC).isoformat()),
        )
        row = connection.execute(
            "SELECT status FROM notification_deliveries WHERE notification_id = ?",
            (notification_id,),
        ).fetchone()
    return cursor.rowcount == 1, str(row[0])


def _set_status(notification_id: str, status: str, error: str | None = None) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE notification_deliveries SET status = ?, error = ?, updated_at = ? WHERE notification_id = ?",
            (status, error, datetime.now(UTC).isoformat(), notification_id),
        )


def dispatch_email(notification: NotificationRecord) -> str:
    if not MAILTRAP_API_KEY:
        return "Belum dikonfigurasi"
    if not MAILTRAP_SENDER_EMAIL or not MAILTRAP_RECIPIENT_EMAIL:
        return "Belum dikonfigurasi"

    claimed, existing_status = _claim_notification(notification.id)
    if not claimed:
        return existing_status

    try:
        import mailtrap as mt

        mail = mt.Mail(
            sender=mt.Address(email=MAILTRAP_SENDER_EMAIL, name=MAILTRAP_SENDER_NAME),
            to=[mt.Address(email=MAILTRAP_RECIPIENT_EMAIL)],
            subject=notification.title,
            text=notification.message,
            category="Alarm Merah MetroPT-3",
        )
        client = mt.MailtrapClient(token=MAILTRAP_API_KEY)
        client.send(mail)
    except Exception as exc:
        error = str(exc).strip() or type(exc).__name__
        if MAILTRAP_API_KEY:
            error = error.replace(MAILTRAP_API_KEY, "[API key disensor]")
        _set_status(notification.id, "Gagal", error[:500])
        return "Gagal"

    _set_status(notification.id, "Terkirim")
    return "Terkirim"
