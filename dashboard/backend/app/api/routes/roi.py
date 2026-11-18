from fastapi import APIRouter, HTTPException

from app.schemas.models import ROIRequest, ROIResponse
from app.services.roi_service import calculate_roi

router = APIRouter(prefix="/roi", tags=["roi"])


@router.post("/calculate", response_model=ROIResponse)
def calculate(request: ROIRequest) -> ROIResponse:
    try:
        return calculate_roi(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
