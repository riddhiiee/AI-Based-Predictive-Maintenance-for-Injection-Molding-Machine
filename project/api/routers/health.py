from fastapi import APIRouter

from api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Simple liveness check. Extend later with DB / model registry checks."""
    return HealthResponse(status="ok", service="predictive-maintenance-api", mock_mode=False)
