"""
Prediction/subsystem-overview service (formerly services/mock_prediction_service.py).

Real body: delegates to models/inference.py for everything ML-derived
(predictions, SHAP top features, subsystem health, alerts, maintenance
needs, health trend) and adds the small amount of static identity/config
data (machine id, model, location) and the one field genuinely sourced from
the mock history log (last_maintenance) that isn't something a classifier
produces.
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd

import config
from models import inference
from models.preprocessing import SUBSYSTEM_TARGET_MAP
from services import runtime_state

VALID_SUBSYSTEMS = set(SUBSYSTEM_TARGET_MAP.keys())



def get_live_machine_status() -> dict[str, Any]:
    return inference.live_machine_status()


def select_live_machine(mold_name: str) -> dict[str, Any]:
    return inference.set_live_machine(mold_name)

def get_all_predictions() -> dict[str, Any]:
    return inference.run_inference()


def get_prediction(subsystem: str) -> dict[str, Any] | None:
    if subsystem not in VALID_SUBSYSTEMS:
        return None
    return inference.run_inference(subsystem=subsystem)


def _last_maintenance_date() -> str:
    # Valid ISO timestamp keeps the dashboard date widget stable. This is UI
    # metadata only; it is not used as a model feature or prediction input.
    return "2026-08-20T09:00:00+00:00"


def get_subsystems_overview() -> dict[str, Any]:
    overview = inference.subsystems_overview()
    machine = {
        "id": config.DEFAULT_MACHINE_ID,
        "model": "IMM 240T",
        "serial_no": "IMM240T03-2210",
        "location": "Plant 01 / Line A",
        "status": "online",
        "overall_health": overview["overall_health"],
        "overall_status": overview["overall_status"],
        "overall_summary": overview["overall_summary"],
        "mtbf_hours": overview["mtbf_hours"],
        "mtbf_delta_pct": overview["mtbf_delta_pct"],
        "last_maintenance": _last_maintenance_date(),
        "active_alert_count": overview["active_alert_count"],
        "predicted_issue_count": overview["predicted_issue_count"],
        "prediction_window_hours": overview["prediction_window_hours"],
    }
    return {"machine": machine, "subsystems": overview["subsystems"]}


def get_maintenance_needs() -> dict[str, Any]:
    return {"items": inference.maintenance_needs()}


def get_trends(
    limit: int = 50
) -> dict[str, Any]:

    from services import live_history_service

    trend = (
        live_history_service
        .get_health_trend(
            limit=limit
        )
    )

    return {
        "health_trend_7d":
            trend,

        "parameter_trends":
            {},
    }


def get_alerts() -> dict[str, Any]:
    return {"alerts": inference.alerts()}


def get_predictions_from_upload(filename: str, file_bytes: bytes) -> dict[str, Any]:
    """Parse an uploaded CSV or Excel file of machine cycle data and run the real
    trained models against it (models/inference.py:run_inference_on_dataframe),
    instead of the simulated live-feed rotation. Raises ValueError on anything
    that should surface as a 400 to the caller (bad format, missing columns)."""
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            raise ValueError("Unsupported file type. Upload a .csv, .xlsx, or .xls file.")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not parse '{filename}': {exc}") from exc

    if df.empty:
        raise ValueError("The uploaded file has no data rows.")

    result = inference.run_inference_on_dataframe(df)

    # Keep the actual latest uploaded readings so the AI assistant can use
    # real sensor/process values together with predictions and manual RAG.
    context_df = df.copy()

    if "cycle_number" not in context_df.columns:
        context_df["cycle_number"] = context_df.groupby("mold_name").cumcount() + 1

    if "material_name" not in context_df.columns:
        context_df["material_name"] = "Uploaded material"

    latest_readings = []

    for mold_name, mold_df in context_df.groupby("mold_name", sort=False):
        mold_df = mold_df.sort_values("cycle_number")
        latest = mold_df.iloc[-1]

        reading = {
            "mold_name": str(mold_name),
            "material_name": str(latest.get("material_name", "Uploaded material")),
            "cycle_number": int(latest["cycle_number"]),
        }

        # Save actual model input parameters
        for col in inference.required_upload_columns():
            if col == "mold_name":
                continue

            if col in latest.index:
                value = latest[col]

                try:
                    if pd.isna(value):
                        reading[col] = None
                    elif hasattr(value, "item"):
                        reading[col] = value.item()
                    else:
                        reading[col] = value
                except Exception:
                    reading[col] = str(value)

        latest_readings.append(reading)

    runtime_state.set_uploaded(
        filename,
        result,
        readings=latest_readings,
    )

    return result


def get_upload_requirements() -> dict[str, Any]:
    """Column requirements for the predictions-page upload widget, so the UI can
    show the operator what their file needs before they try uploading it."""
    return {"required_columns": inference.required_upload_columns()}
