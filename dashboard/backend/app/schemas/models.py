from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    data_ready: bool
    detail: str | None = None


class MonthlyThreshold(BaseModel):
    month: str
    threshold: float | None = None
    supervised_active: bool


class ModelSummary(BaseModel):
    anomaly_model: str | None = None
    anomaly_members: list[str] = Field(default_factory=list)
    anomaly_calibration: str | None = None
    anomaly_threshold: float | None = None
    anomaly_features: list[str] = Field(default_factory=list)
    hybrid_events_detected: str | None = None
    hybrid_official_detected: str | None = None
    hybrid_false_alarm_episodes: int | None = None
    hybrid_false_alarms_per_week: float | None = None
    calibrated_ece: float | None = None
    rul_model: str | None = None
    rul_mae_pre_failure_hours: float | None = None
    rul_critical_recall: float | None = None
    targets_passed: int | None = None
    targets_total: int | None = None
    monthly_thresholds: list[MonthlyThreshold] = Field(default_factory=list)


class ReplayMetadata(BaseModel):
    start: datetime
    end: datetime
    rows: int
    interval: str = "1 menit"
    signals: list[str]
    statuses: list[str]
    model_summary: ModelSummary | None = None


class FrameResponse(BaseModel):
    timestamp: datetime
    status: str
    trigger: str | None = None
    probability: float | None = None
    threshold: float | None = None
    rul_hours: float | None = None
    rul_lower: float | None = None
    rul_upper: float | None = None
    rul_stage: str | None = None
    model_active: bool | None = None
    sensors: dict[str, float | bool | None]


class TelemetryPoint(BaseModel):
    timestamp: datetime
    values: dict[str, float | bool | None]
    status: str
    probability: float | None = None
    threshold: float | None = None
    rul_hours: float | None = None
    rul_lower: float | None = None
    rul_upper: float | None = None
    rul_stage: str | None = None


class TelemetryResponse(BaseModel):
    points: list[TelemetryPoint]
    total_points: int
    downsampled: bool


class AlarmRecord(BaseModel):
    id: str
    started_at: datetime
    ended_at: datetime
    duration_minutes: int
    highest_status: str
    red_started_at: datetime | None = None
    trigger: str | None = None
    sensors: dict[str, float | bool | None]


class NotificationRecord(BaseModel):
    id: str
    timestamp: datetime
    status: str
    channel: str
    title: str
    message: str
    delivery: str = "Belum dikirim"
    delivery_error: str | None = None


class NotificationDispatchRequest(BaseModel):
    since: datetime
    through: datetime


class ROIRequest(BaseModel):
    scenario: str = Field(default="Dasar", pattern="^(Batas rendah|Dasar|Batas tinggi)$")
    costs: dict[str, float] | None = None


class ROIScenario(BaseModel):
    name: str
    costs: dict[str, float]
    annual_costs: dict[str, float]
    savings_vs_reactive: float
    savings_vs_preventive: float
    roi_vs_reactive_percent: float
    roi_vs_preventive_percent: float


class ROIResponse(BaseModel):
    detection_basis: dict[str, float]
    rupiah_per_ub: int = 50_000_000
    selected: ROIScenario
    scenarios: list[ROIScenario]
    sensitivity: list[dict[str, Any]]
    break_even: list[dict[str, Any]]
    per_failure_costs: dict[str, float | None]
