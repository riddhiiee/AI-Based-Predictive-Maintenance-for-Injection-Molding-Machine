"""
SHAP-explanation entry point, matching the interface models/README.md
documented as the replacement for services/mock_explain_service.py.

The actual SHAP computation lives alongside prediction in models/inference.py
(`_top_shap_features`) since a prediction and its explanation are always
produced from the same feature row in one pass -- this module just re-shapes
that into the ExplainResponse contract.
"""
from __future__ import annotations

from typing import Any

from models import inference
from models.preprocessing import SUBSYSTEM_TARGET_MAP


def compute_shap_explanation(subsystem: str, machine_id: str | None = None) -> dict[str, Any] | None:
    if subsystem not in SUBSYSTEM_TARGET_MAP:
        return None
    prediction = inference.run_inference(machine_id=machine_id, subsystem=subsystem)
    if prediction is None:
        return None
    return {
        "subsystem": prediction["subsystem"],
        "subsystem_name": prediction["subsystem_name"],
        "predicted_state": prediction["predicted_state"],
        "severity": prediction["severity"],
        "confidence": prediction["confidence"],
        "top_features": prediction["top_features"],
        "recommended_action": prediction["recommended_action"],
        "explanation_method": "shap",
    }
