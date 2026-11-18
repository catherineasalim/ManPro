from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas.models import TelemetryResponse
from app.services.data_store import load_data
from app.services.replay_service import get_telemetry

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("", response_model=TelemetryResponse)
def telemetry(
    start: datetime,
    end: datetime,
    signals: list[str] | None = Query(default=None),
    limit: int = Query(default=1200, ge=2, le=5000),
) -> TelemetryResponse:
    try:
        return get_telemetry(load_data(), start, end, signals, limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
