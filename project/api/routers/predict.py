from fastapi import APIRouter, File, HTTPException, UploadFile

from api.schemas import (
    AlertsResponse,
    MaintenanceNeedsResponse,
    PredictionItem,
    PredictionsResponse,
    SubsystemsOverviewResponse,
    TrendsResponse,
    UploadPredictionsResponse,
    UploadRequirementsResponse,
)
from services import prediction_service

router = APIRouter(tags=["predictions"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB


@router.get("/live-machine")
def live_machine_status():
    """Selected simulated production profile and its real cycle interval."""
    return prediction_service.get_live_machine_status()


@router.post("/live-machine/select")
def select_live_machine(payload: dict):
    mold_name = str(payload.get("mold_name", "")).strip()
    if not mold_name:
        raise HTTPException(status_code=400, detail="mold_name is required")
    try:
        return prediction_service.select_live_machine(mold_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/predict/all", response_model=PredictionsResponse)
def predict_all():
    """Current predictions for all nine subsystems, from the trained Gradient
    Boosting models (see models/inference.py)."""
    return prediction_service.get_all_predictions()


@router.get("/predict/upload-requirements", response_model=UploadRequirementsResponse)
def predict_upload_requirements():
    """Required columns for the CSV/Excel upload widget on the Predictions page."""
    return prediction_service.get_upload_requirements()


@router.post("/predict/upload", response_model=UploadPredictionsResponse)
async def predict_upload(file: UploadFile = File(...)):
    """
    Run the real trained models against uploaded machine cycle data (CSV or
    Excel), instead of the simulated live-feed replay used by /predict/all.

    Returns one set of subsystem predictions per distinct mold found in the
    file, each based on that mold's latest uploaded cycle (with rolling
    features computed from whatever trailing cycles are present for it).
    """
    if not file.filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Upload a .csv, .xlsx, or .xls file.")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 20MB upload limit.")

    try:
        return prediction_service.get_predictions_from_upload(file.filename, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/predict/current-upload")
def current_upload():
    """Return the latest uploaded machine dataset prediction/context."""
    from services import runtime_state

    uploaded = runtime_state.get_uploaded()

    if uploaded is None:
        return {
            "has_upload": False,
            "filename": None,
            "result": None,
            "readings": [],
        }

    return {
        "has_upload": True,
        "filename": uploaded.get("filename"),
        "result": uploaded.get("result"),
        "readings": uploaded.get("readings", []),
    }


@router.post("/predict/clear-upload")
def clear_upload():
    """Return the application to simulated/live inference mode."""
    from services import runtime_state

    runtime_state.clear_uploaded()

    return {"cleared": True}

@router.get("/predict/{subsystem}", response_model=PredictionItem)
def predict_one(subsystem: str):
    """Current prediction for a single subsystem: hopper | heater | screw | injection | hydraulic | clamp | mold | cooling | ejector."""
    result = prediction_service.get_prediction(subsystem)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown subsystem '{subsystem}'")
    return result


@router.get("/subsystems", response_model=SubsystemsOverviewResponse)
def subsystems_overview():
    """Machine + subsystem health snapshot used by the dashboard cards."""
    return prediction_service.get_subsystems_overview()


@router.get("/maintenance-needs", response_model=MaintenanceNeedsResponse)
def maintenance_needs():
    """'Predicted Maintenance Needs' table shown on the dashboard."""
    return prediction_service.get_maintenance_needs()


@router.get(
    "/trends",
    response_model=TrendsResponse
)
def trends(
    limit: int = 50
):
    return (
        prediction_service
        .get_trends(
            limit=limit
        )
    )


@router.get("/alerts", response_model=AlertsResponse)
def alerts():
    """Active alerts feed."""
    return prediction_service.get_alerts()
