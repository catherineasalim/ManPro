from __future__ import annotations

import pandas as pd

from app.core.config import SENSOR_FIELDS
from app.schemas.models import AlarmRecord, NotificationRecord
from app.services.data_store import DataBundle, json_value

# Aturan notifikasi (LAPORAN_ANALISIS.md bagian 9.2): hanya status Merah yang dikirim ke teknisi.
# Kuning cukup tampil di dashboard dan log insiden karena alarm palsunya sekitar 3 per minggu.
# Satu notifikasi per episode Merah. Jeda penggabungan 30 menit sama dengan MERGE_MIN di
# anomaly_detection/common/hybrid.py, jadi alarm Merah yang naik-turun tidak mengirim pesan berulang.
NOTIFY_STATUS = "Merah"
NOTIFY_MERGE_MINUTES = 30

_cached_frame: pd.DataFrame | None = None
_cached_alarms: list[AlarmRecord] = []
_cached_notifications: list[NotificationRecord] = []


def _prepare_cache(bundle: DataBundle) -> None:
    global _cached_frame, _cached_alarms, _cached_notifications
    if _cached_frame is bundle.frame:
        return
    _cached_frame = bundle.frame
    _cached_alarms = []
    _cached_notifications = []
    frame = bundle.frame
    statuses = frame["status_final"].fillna("Abu-abu").astype(str)
    red_times = statuses.index[statuses.eq(NOTIFY_STATUS)].to_series()
    gaps = red_times.diff()
    episode_starts = red_times.loc[gaps.isna() | gaps.gt(pd.Timedelta(minutes=NOTIFY_MERGE_MINUTES))]
    for stamp in episode_starts.index:
        status = NOTIFY_STATUS
        row = frame.loc[stamp]
        trigger = row.get("pemicu_final")
        sensor_values = ", ".join(
            f"{name}: {float(row[name]):.2f}"
            for name in ("TP3", "Oil_temperature", "Motor_current")
            if name in row.index and pd.notna(row[name])
        )
        title = f"Status kompresor naik ke {status}"
        body = f"{stamp:%d %b %Y %H:%M} WIB · Pemicu: {trigger or '-'} · {sensor_values}"
        for channel in ("Email", "WhatsApp Bot"):
            _cached_notifications.append(
                NotificationRecord(
                    id=f"{stamp.strftime('%Y%m%d%H%M')}-{channel.lower().replace(' ', '-')}",
                    timestamp=stamp.to_pydatetime(), status=status, channel=channel,
                    title=title, message=body,
                )
            )

    alert_rows = frame.loc[statuses.isin(["Kuning", "Merah"])]
    if not alert_rows.empty:
        gaps = alert_rows.index.to_series().diff().gt(pd.Timedelta(minutes=30)).fillna(True)
        groups = gaps.cumsum().to_numpy()
        for _, episode in alert_rows.groupby(groups, sort=False):
            start, end = episode.index[0], episode.index[-1]
            red_rows = episode.loc[episode["status_final"] == "Merah"]
            red_start = red_rows.index[0] if not red_rows.empty else None
            first = episode.iloc[0]
            _cached_alarms.append(AlarmRecord(
                id=start.strftime("%Y%m%d%H%M"),
                started_at=start.to_pydatetime(),
                ended_at=end.to_pydatetime(),
                duration_minutes=max(1, int((end - start).total_seconds() // 60) + 1),
                highest_status="Merah" if red_start is not None else "Kuning",
                red_started_at=red_start.to_pydatetime() if red_start is not None else None,
                trigger=first.get("pemicu_final") if pd.notna(first.get("pemicu_final")) else None,
                sensors={name: json_value(first.get(name)) for name in SENSOR_FIELDS if name in first.index},
            ))


def build_alarms(bundle: DataBundle, through: str | pd.Timestamp) -> list[AlarmRecord]:
    _prepare_cache(bundle)
    end = pd.Timestamp(through).floor("min")
    visible: list[AlarmRecord] = []
    for alarm in _cached_alarms:
        start = pd.Timestamp(alarm.started_at)
        if start > end:
            continue
        visible_end = min(pd.Timestamp(alarm.ended_at), end)
        current_statuses = bundle.frame.loc[start:visible_end, "status_final"]
        highest = "Merah" if (current_statuses == "Merah").any() else "Kuning"
        red_start = current_statuses[current_statuses == "Merah"].index.min()
        visible.append(alarm.model_copy(update={
            "ended_at": visible_end.to_pydatetime(),
            "duration_minutes": max(1, int((visible_end - start).total_seconds() // 60) + 1),
            "highest_status": highest,
            "red_started_at": red_start.to_pydatetime() if pd.notna(red_start) else None,
        }))
    return visible


def _finish_alarm(active: dict, ended_at: pd.Timestamp) -> AlarmRecord:
    started = active["started_at"]
    return AlarmRecord(
        id=started.strftime("%Y%m%d%H%M"),
        started_at=started.to_pydatetime(),
        ended_at=ended_at.to_pydatetime(),
        duration_minutes=max(1, int((ended_at - started).total_seconds() // 60) + 1),
        highest_status=active["highest_status"],
        red_started_at=active["red_started_at"].to_pydatetime() if active["red_started_at"] is not None else None,
        trigger=active["trigger"] if pd.notna(active["trigger"]) else None,
        sensors=active["sensors"],
    )


def build_notifications(bundle: DataBundle, through: str | pd.Timestamp) -> list[NotificationRecord]:
    _prepare_cache(bundle)
    end = pd.Timestamp(through).floor("min")
    return [message for message in _cached_notifications if pd.Timestamp(message.timestamp) <= end]
