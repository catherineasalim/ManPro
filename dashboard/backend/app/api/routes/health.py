from fastapi import APIRouter

from app.schemas.models import HealthResponse
from app.services.data_store import DataUnavailableError, load_data

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    try:
        data = load_data()
        return HealthResponse(status="ok", data_ready=not data.frame.empty)
    except DataUnavailableError as exc:
        return HealthResponse(status="degraded", data_ready=False, detail=str(exc))
