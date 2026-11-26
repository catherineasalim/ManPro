from datetime import datetime

from fastapi import APIRouter, Query

from app.schemas.models import AlarmRecord, NotificationDispatchRequest, NotificationRecord
from app.services.alarm_service import (
    build_alarms,
    build_notifications,
    dispatch_notifications,
)
from app.services.data_store import load_data

router = APIRouter(tags=["alarms"])


@router.get("/alarms", response_model=list[AlarmRecord])
def alarms(through: datetime, limit: int = Query(default=200, ge=1, le=1000)) -> list[AlarmRecord]:
    return build_alarms(load_data(), through)[-limit:]


@router.get("/notifications", response_model=list[NotificationRecord])
def notifications(through: datetime, limit: int = Query(default=200, ge=1, le=1000)) -> list[NotificationRecord]:
    return build_notifications(load_data(), through)[-limit:]


@router.post("/notifications/dispatch", response_model=list[NotificationRecord])
def dispatch_notification_events(request: NotificationDispatchRequest) -> list[NotificationRecord]:
    return dispatch_notifications(load_data(), request)
