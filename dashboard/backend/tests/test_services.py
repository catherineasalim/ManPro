from app.schemas.models import ROIRequest
from app.services.alarm_service import build_notifications
from app.services.data_store import DataBundle
from app.services.roi_service import calculate, calculate_roi


def test_roi_comparison_is_finite_and_ordered():
    result = calculate( {
        "kegagalan_per_unit_tahun": 6.8,
        "downtime_jam_per_kegagalan": 22.0,
        "biaya_downtime_per_jam": 0.5,
        "biaya_perbaikan_darurat": 3.0,
        "biaya_perbaikan_terencana": 1.0,
        "biaya_inspeksi": 0.1,
        "interval_penggantian_bulan": 6.0,
        "biaya_penggantian_preventif": 1.2,
        "kegagalan_lolos_preventif": 0.3,
        "biaya_sistem": 1.0,
    })
    assert result["reactive"] > 0
    assert result["preventive"] > 0
    assert result["predictive"] > 0
    assert result["roi_reactive"] == (result["reactive"] - result["predictive"]) * 100


def test_roi_request_returns_three_scenarios_and_sensitivity():
    result = calculate_roi(ROIRequest(scenario="Dasar"))
    assert result.selected.name == "Dasar"
    assert {scenario.name for scenario in result.scenarios} == {"Batas rendah", "Dasar", "Batas tinggi"}
    assert result.detection_basis["official_recall"] == 1.0
    assert result.sensitivity
    assert result.break_even
    system_cost_break_even = next(item for item in result.break_even if item["parameter"] == "biaya_sistem")
    assert system_cost_break_even["titik_impas"] > result.selected.costs["biaya_sistem"]


def test_notification_sent_only_when_status_steps_up():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "status_final": ["Hijau", "Kuning", "Kuning", "Merah", "Hijau", "Merah"],
            "pemicu_final": ["-", "IF", "IF", "XGB", "-", "IF"],
            "TP3": [8.0] * 6,
            "Oil_temperature": [70.0] * 6,
            "Motor_current": [3.0] * 6,
        },
        index=pd.date_range("2020-04-01", periods=6, freq="min", name="timestamp"),
    )
    messages = build_notifications(DataBundle(frame=frame, metadata={}), frame.index[-1])
    assert [(m.timestamp.minute, m.status) for m in messages if m.channel == "Email"] == [(1, "Kuning"), (3, "Merah"), (5, "Merah")]
    assert all(m.delivery == "Simulasi" for m in messages)


def test_api_smoke_against_project_parquet_artifacts():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["data_ready"] is True

    metadata = client.get("/api/replay/metadata")
    assert metadata.status_code == 200
    start = metadata.json()["start"]
    frame = client.get("/api/replay/frame", params={"timestamp": start})
    assert frame.status_code == 200
    assert frame.json()["status"] in {"Hijau", "Kuning", "Merah", "Abu-abu"}
    assert "TP3" in frame.json()["sensors"]

    telemetry = client.get("/api/telemetry", params={"start": start, "end": start, "signals": ["TP2", "TP3"]})
    assert telemetry.status_code == 200
    assert len(telemetry.json()["points"]) == 1
    assert "threshold" in telemetry.json()["points"][0]
    invalid_signal = client.get("/api/telemetry", params={"start": start, "end": start, "signals": ["NOT_A_SENSOR"]})
    assert invalid_signal.status_code == 422

    through = metadata.json()["end"]
    alarms = client.get("/api/alarms", params={"through": through, "limit": 5})
    notifications = client.get("/api/notifications", params={"through": through, "limit": 4})
    assert alarms.status_code == 200
    assert notifications.status_code == 200
    assert notifications.json()
    assert all(item["delivery"] == "Simulasi" for item in notifications.json())

    roi = client.post("/api/roi/calculate", json={"scenario": "Dasar", "costs": {"biaya_sistem": 1.25}})
    assert roi.status_code == 200
    assert roi.json()["selected"]["costs"]["biaya_sistem"] == 1.25
    invalid_roi = client.post("/api/roi/calculate", json={"scenario": "Dasar", "costs": {"biaya_sistem": -1}})
    assert invalid_roi.status_code == 422
