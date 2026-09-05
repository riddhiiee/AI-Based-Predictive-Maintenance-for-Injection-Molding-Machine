from fastapi import APIRouter, HTTPException

from api.schemas import ExplainResponse
from services import explain_service

router = APIRouter(tags=["explain"])


@router.get("/explain/{subsystem}", response_model=ExplainResponse)
def explain(subsystem: str):
    """SHAP explanation for a subsystem's current prediction (see models/shap_service.py)."""
    result = explain_service.explain_subsystem(subsystem)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown subsystem '{subsystem}'")
    return result
