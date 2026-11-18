from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.schemas.models import FrameResponse, ReplayMetadata
from app.services.data_store import load_data
from app.services.replay_service import get_frame, replay_metadata

router = APIRouter(prefix="/replay", tags=["replay"])


@router.get("/metadata", response_model=ReplayMetadata)
def metadata() -> ReplayMetadata:
    try:
        return replay_metadata(load_data())
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/frame", response_model=FrameResponse)
def frame(timestamp: datetime) -> FrameResponse:
    try:
        return get_frame(load_data(), timestamp)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
