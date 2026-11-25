from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.core.config import SENSOR_FIELDS
from app.schemas.models import FrameResponse, ModelSummary, MonthlyThreshold, ReplayMetadata, TelemetryPoint, TelemetryResponse
from app.services.data_store import DataBundle, frame_payload, json_value, rul_stage


def _timestamp(value: datetime | str) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert(None)
    return stamp.floor("min")


def replay_metadata(bundle: DataBundle) -> ReplayMetadata:
    predictions = bundle.frame[bundle.frame["p_terkalibrasi"].notna()]
    if predictions.empty:
        raise ValueError("Tidak ada timestamp dengan prediksi walk-forward.")
    start, end = predictions.index.min(), predictions.index.max()
    available = bundle.frame.loc[start:end]
    metadata = bundle.metadata
    anomaly = metadata.get("anomali", {})
    rul = metadata.get("rul", {})
    walk_forward = metadata.get("walk_forward", {})
    anomaly_rows = walk_forward.get("anomali", [])
    hybrid_row = next((row for row in anomaly_rows if row.get("metode") == "Hybrid final Merah"), {})
    calibrated_row = next((row for row in anomaly_rows if row.get("metode") == "Model final terkalibrasi (ambang teroptimasi)"), {})
    target_rows = walk_forward.get("target", [])
    threshold_rows = []
    thresholds = available.get("ambang_anomali")
    if thresholds is not None:
        for month, month_frame in available.groupby(available.index.to_period("M"), sort=True):
            month_thresholds = pd.to_numeric(month_frame.get("ambang_anomali"), errors="coerce").dropna()
            active = bool(month_frame.get("model_aktif", pd.Series(False, index=month_frame.index)).fillna(False).any())
            threshold_rows.append(MonthlyThreshold(
                month=month.strftime("%Y-%m"),
                threshold=float(month_thresholds.iloc[0]) if not month_thresholds.empty else None,
                supervised_active=active,
            ))

    def fraction(value):
        return str(value) if value else None

    summary = ModelSummary(
        anomaly_model=anomaly.get("model"),
        anomaly_members=anomaly.get("members", []),
        anomaly_calibration=anomaly.get("kalibrasi"),
        anomaly_threshold=anomaly.get("ambang_terkalibrasi"),
        anomaly_features=anomaly.get("fitur", []),
        hybrid_events_detected=fraction(hybrid_row.get("kejadian")),
        hybrid_official_detected=fraction(hybrid_row.get("resmi")),
        hybrid_false_alarm_episodes=hybrid_row.get("alarm_palsu"),
        hybrid_false_alarms_per_week=hybrid_row.get("palsu_per_minggu"),
        calibrated_ece=calibrated_row.get("ece"),
        rul_model=rul.get("model"),
        rul_mae_pre_failure_hours=walk_forward.get("rul", {}).get("mae_pra_failure"),
        rul_critical_recall=walk_forward.get("rul", {}).get("recall_critical"),
        targets_passed=sum(row.get("status") == "LULUS" for row in target_rows),
        targets_total=len(target_rows),
        monthly_thresholds=threshold_rows,
    )
    return ReplayMetadata(
        start=start.to_pydatetime(),
        end=end.to_pydatetime(),
        rows=len(available),
        signals=[name for name in SENSOR_FIELDS if name in available.columns],
        statuses=["Hijau", "Kuning", "Merah", "Abu-abu"],
        model_summary=summary,
    )


def get_frame(bundle: DataBundle, timestamp: datetime | str) -> FrameResponse:
    stamp = _timestamp(timestamp)
    if stamp not in bundle.frame.index:
        raise KeyError(f"Tidak ada data pada {stamp.isoformat()}.")
    return FrameResponse(**frame_payload(stamp, bundle.frame.loc[stamp]))


def get_telemetry(
    bundle: DataBundle,
    start: datetime | str,
    end: datetime | str,
    signals: list[str] | None,
    limit: int,
) -> TelemetryResponse:
    start_at, end_at = _timestamp(start), _timestamp(end)
    if end_at < start_at:
        raise ValueError("Waktu akhir harus setelah waktu mulai.")
    allowed = [name for name in SENSOR_FIELDS if name != "data_ok" and name in bundle.frame.columns]
    selected = signals or ["TP2", "TP3", "Oil_temperature", "Motor_current"]
    unknown = sorted(set(selected) - set(allowed))
    if unknown:
        raise ValueError(f"Sinyal tidak dikenal: {', '.join(unknown)}")
    sliced = bundle.frame.loc[start_at:end_at]
    total = len(sliced)
    downsampled = total > limit
    if downsampled:
        positions = [round(i * (total - 1) / (limit - 1)) for i in range(limit)] if limit > 1 else [total - 1]
        sliced = sliced.iloc[positions]

    points = [
        TelemetryPoint(
            timestamp=idx.to_pydatetime(),
            values={name: json_value(row.get(name)) for name in selected},
            status=str(row.get("status_final") or "Abu-abu"),
            probability=json_value(row.get("p_terkalibrasi")),
            threshold=json_value(row.get("ambang_anomali")),
            rul_hours=json_value(row.get("rul_pred")),
            rul_lower=json_value(row.get("rul_bawah")),
            rul_upper=json_value(row.get("rul_atas")),
            rul_stage=rul_stage(row),
        )
        for idx, row in sliced.iterrows()
    ]
    return TelemetryResponse(points=points, total_points=total, downsampled=downsampled)
