"""
SHAP explanation service (formerly services/mock_explain_service.py).

Real body: delegates to models/shap_service.py, which reuses the same
prediction + SHAP computation as services/prediction_service.py so a
subsystem's "current prediction" and its "explanation" are always
consistent with each other (both come from the same live-simulated cycle).
"""
from __future__ import annotations

from typing import Any

from models.preprocessing import SUBSYSTEM_TARGET_MAP
from models.shap_service import compute_shap_explanation

VALID_SUBSYSTEMS = set(SUBSYSTEM_TARGET_MAP.keys())


def explain_subsystem(subsystem: str) -> dict[str, Any] | None:
    if subsystem not in VALID_SUBSYSTEMS:
        return None
    return compute_shap_explanation(subsystem)
