"""
Real-time-style inference using the selected best model for each subsystem (Gradient Boosting, RNN, or LSTM).

Loads the artifacts written by models/train.py once (lazily, on first call)
and serves `run_inference()`, matching the interface models/README.md
documented as the replacement for services/mock_prediction_service.py.

There is no live PLC/sensor feed wired into this prototype, so "current"
readings are simulated by replaying real historical cycles from the held-out
test split (models/artifacts/live_feed/*.csv, written by train.py) through
the exact same feature pipeline (models/preprocessing.py) used at training
time -- the rolling/delta features, mold one-hot, scaling, anomaly-detector
scores, and subsystem-specific best-model predictions are all genuinely computed, not
hand-authored. Which mold/cycle is "current" rotates on a short timer so the
dashboard feels alive across repeated polls; see `_select_snapshot()`.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

import joblib
import numpy as np
import pandas as pd

import uuid

from models import preprocessing as prep
import warnings
warnings.filterwarnings(
    "ignore",
    message=(
        ".*sklearn.utils.parallel.delayed.*"
    ),
    category=UserWarning,
)
ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts")
BEST_MODEL_CONFIG = {
    "Hopper_State": {
        "type": "RNN",
        "file": "Hopper_State__RNN_fixed.keras",
    },
    "Barrel_Heater_State": {
        "type": "Gradient_Boosting",
        "file": "Barrel_Heater_State__Gradient_Boosting.pkl",
    },
    "Screw_State": {
        "type": "RNN",
        "file": "Screw_State__RNN_fixed.keras",
    },
    "Injection_Unit_State": {
        "type": "Gradient_Boosting",
        "file": "Injection_Unit_State__Gradient_Boosting.pkl",
    },
    "Hydraulic_System_State": {
        "type": "Gradient_Boosting",
        "file": "Hydraulic_System_State__Gradient_Boosting.pkl",
    },
    "Clamp_Unit_State": {
        "type": "LSTM",
        "file": "Clamp_Unit_State__LSTM_fixed.keras",
    },
    "Mold_State": {
        "type": "Gradient_Boosting",
        "file": "Mold_State__Gradient_Boosting.pkl",
    },
    "Cooling_System_State": {
        "type": "Gradient_Boosting",
        "file": "Cooling_System_State__Gradient_Boosting.pkl",
    },
    "Ejector_System_State": {
        "type": "Gradient_Boosting",
        "file": "Ejector_System_State__Gradient_Boosting.pkl",
    },
}
_lock = threading.Lock()
_registry: dict[str, Any] | None = None
_prediction_cache_lock = threading.Lock()
_inference_compute_lock = threading.Lock()

_prediction_cache = {
    "key": None,
    "result": None,
}

# Real-world replay configuration. One CSV row represents one completed molding cycle.
# The selected production profile controls both which mold data is replayed and how
# often the next row becomes available to the model.
LIVE_MACHINE_PROFILES = {
    "Smart Router Enclosure": {"material": "ABS (Flame Retardant, Medium Flow)", "cycle_seconds": 24.34, "tonnage": 180},
    "Blood Filtration Housing": {"material": "Polycarbonate (PC - Medical Grade)", "cycle_seconds": 31.35, "tonnage": 250},
    "Rectangular Food Container": {"material": "Polypropylene (PP - High Flow, MFI 45+)", "cycle_seconds": 4.48, "tonnage": 300},
    "Engine Mount Bracket": {"material": "PA66 + 30% GF (Polyamide 66, 30% Glass Fiber)", "cycle_seconds": 39.65, "tonnage": 400},
}
_live_selected_mold = "Smart Router Enclosure"

_live_started_at = time.time()

_live_state_lock = threading.Lock()

_live_session_id = uuid.uuid4().hex


def _load_registry() -> dict[str, Any]:
    with open(os.path.join(ARTIFACTS_DIR, "feature_config.json"), encoding="utf-8") as f:
        feature_config = json.load(f)

    scaler = joblib.load(os.path.join(ARTIFACTS_DIR, "scaler.joblib"))

    best_models = {}

    for target_col, cfg in BEST_MODEL_CONFIG.items():
        path = os.path.join(
            ARTIFACTS_DIR,
            "best_models",
            cfg["file"],
        )

        if cfg["type"] in {"RNN", "LSTM"}:
            import keras
            model = keras.models.load_model(
                path,
                compile=False
            )
        else:
            model = joblib.load(path)

        best_models[target_col] = {
            "type": cfg["type"],
            "model": model,
        }

    detectors = {}
    for col in prep.TARGET:
        algo = feature_config["detector_algorithm"][col]
        if algo == "Autoencoder":
            import keras
            model = keras.models.load_model(os.path.join(ARTIFACTS_DIR, "detectors", f"{col}.keras"))
            meta = joblib.load(os.path.join(ARTIFACTS_DIR, "detectors", f"{col}_meta.joblib"))
            detectors[col] = {"algorithm": algo, "model": {"model": model, "threshold": meta["threshold"]}}
        else:
            model = joblib.load(os.path.join(ARTIFACTS_DIR, "detectors", f"{col}.joblib"))
            detectors[col] = {"algorithm": algo, "model": model}

    with open(os.path.join(ARTIFACTS_DIR, "mold_slugs.json"), encoding="utf-8") as f:
        mold_slugs = json.load(f)
    live_feed = {
        mold: pd.read_csv(os.path.join(ARTIFACTS_DIR, "live_feed", f"{slug}.csv"))
        for mold, slug in mold_slugs.items()
    }

    return {
        "feature_config": feature_config,
        "scaler": scaler,
        "best_models": best_models,
        "detectors": detectors,
        "live_feed": live_feed,
        "explainers": {},  # lazily built per target, see _get_explainer()
    }


def _registry_state() -> dict[str, Any]:
    global _registry
    if _registry is None:
        with _lock:
            if _registry is None:
                _registry = _load_registry()
    return _registry


def is_trained() -> bool:
    """Whether models/train.py has been run and artifacts exist."""
    return os.path.exists(os.path.join(ARTIFACTS_DIR, "feature_config.json"))


# ---------------------------------------------------------------------------
# "Live" snapshot selection
# ---------------------------------------------------------------------------
def set_live_machine(mold_name: str) -> dict[str, Any]:
    """Select the production profile used by the simulated real-time feed."""
    global _live_selected_mold
    global _live_started_at
    global _live_session_id
    reg = _registry_state()
    if mold_name not in reg["live_feed"] or mold_name not in LIVE_MACHINE_PROFILES:
        raise ValueError(f"Unknown mold/machine profile: {mold_name}")
    with _live_state_lock:
        _live_selected_mold = mold_name
        _live_started_at = time.time()
        _live_session_id = uuid.uuid4().hex
    return live_machine_status()


def live_machine_status() -> dict[str, Any]:
    reg = _registry_state()
    mold, df, idx = _select_snapshot(reg)
    profile = LIVE_MACHINE_PROFILES[mold]
    elapsed = max(0.0, time.time() - _live_started_at)
    cycle_seconds = profile["cycle_seconds"]
    next_in = cycle_seconds - (elapsed % cycle_seconds)
    return {
        "selected_mold": mold,
        "material": profile["material"],
        "cycle_seconds": cycle_seconds,
        "machine_tonnage": profile["tonnage"],

        "csv_row_index": int(idx),
        "completed_cycles": int(elapsed // cycle_seconds),

        "cycle_id": f"CYC-{int(df.iloc[idx]['cycle_number'])}",
        "next_cycle_in_seconds": round(next_in, 1),

        "profiles": [
            {"mold": name, **meta}
            for name, meta in LIVE_MACHINE_PROFILES.items()
            if name in reg["live_feed"]
        ],
    }


def _max_required_sequence_length(reg: dict[str, Any]) -> int:
    """Largest fixed sequence length required by the loaded RNN/LSTM models."""
    lengths = []
    for info in reg["best_models"].values():
        if info["type"] not in {"RNN", "LSTM"}:
            continue
        shape = info["model"].input_shape
        if isinstance(shape, list):
            shape = shape[0]
        if len(shape) != 3 or shape[1] is None:
            raise ValueError(
                f"{info['type']} model must have a fixed 3D input shape "
                f"(batch, sequence_length, features); got {shape}."
            )
        lengths.append(int(shape[1]))
    return max(lengths, default=1)


def _select_snapshot(reg: dict[str, Any]) -> tuple[str, pd.DataFrame, int]:
    with _live_state_lock:
        mold = _live_selected_mold
        started_at = _live_started_at
    if mold not in reg["live_feed"]:
        mold = next(iter(reg["live_feed"]))

    df = reg["live_feed"][mold]
    cycle_seconds = LIVE_MACHINE_PROFILES.get(mold, {}).get("cycle_seconds", 24.34)

    # Do not start before enough cycles exist for both rolling features and
    # the longest RNN/LSTM sequence.
    max_seq = _max_required_sequence_length(reg)
    usable_start = max(prep.WINDOW - 1, max_seq - 1)
    usable_start = min(usable_start, max(0, len(df) - 1))

    usable_len = max(1, len(df) - usable_start)
    completed_cycles = int(max(0.0, time.time() - started_at) // cycle_seconds)
    cycle_idx = usable_start + (completed_cycles % usable_len)
    return mold, df, min(cycle_idx, len(df) - 1)


def _build_feature_row(
    reg: dict[str, Any],
    mold_df: pd.DataFrame,
    cycle_idx: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """Build both tabular and sequence-ready inputs using the same inference
    preprocessing pipeline.

    Returns:
      X_row     - latest processed cycle, used by Gradient Boosting
      X_history - processed recent cycles, used to create RNN/LSTM sequences
      context   - current mold/material/cycle metadata
      raw_row   - latest engineered row before scaling, for UI display
    """
    fc = reg["feature_config"]

    # We need enough rows for the longest neural sequence, plus extra preceding
    # rows so rolling/delta features at the beginning of that sequence are valid.
    max_seq = _max_required_sequence_length(reg)
    history_needed = max_seq + max(prep.WINDOW - 1, 0)
    lo = max(0, cycle_idx - history_needed + 1)
    window_slice = mold_df.iloc[lo:cycle_idx + 1].copy()

    engineered = prep.add_engineered_features(
        window_slice,
        fc["kept_numeric_cols"],
    )

    raw_row = engineered.iloc[[-1]].copy()
    context = {
        "mold_name": raw_row["mold_name"].iloc[0],
        "material_name": raw_row["material_name"].iloc[0],
        "cycle_number": int(raw_row["cycle_number"].iloc[0]),
        "true_states": {
            col: int(raw_row[col].iloc[0])
            for col in prep.TARGET
            if col in raw_row.columns
        },
    }

    processed = prep.add_mold_dummies(
        engineered.copy(),
        fc["mold_names"],
    )
    processed = processed.drop(
        columns=[c for c in prep.TARGET if c in processed.columns]
    )
    processed = processed.drop(
        columns=[c for c in prep.ID_CAT_COLS if c in processed.columns]
    )

    # Reuse the scaler fitted during training.
    processed[fc["numeric_cols"]] = reg["scaler"].transform(
        processed[fc["numeric_cols"]]
    )

    # Add one anomaly-score feature per subsystem.
    # Score the complete recent history in ONE detector call
    # instead of calling the detector once for every row.
    for target_col in prep.TARGET:

        feats = fc[
            "target_feature_map"
        ][target_col]

        detector = reg[
            "detectors"
        ][target_col]

        detector_input = processed[
            feats
        ].copy()

        scores = prep.score_with_detector(
            detector["algorithm"],
            detector["model"],
            detector_input,
        )

        score_arr = np.asarray(
            scores,
            dtype=float,
        ).reshape(-1)

        if score_arr.size != len(processed):

            raise ValueError(
                f"Detector for {target_col} returned "
                f"{score_arr.size} scores for "
                f"{len(processed)} cycles."
            )

        processed[
            f"{target_col}_anomaly_score"
        ] = score_arr

    # Keep exactly the training-time final feature order.
    X_history = processed[fc["feature_columns"]].copy()
    X_row = X_history.iloc[[-1]].copy()
    return X_row, X_history, context, raw_row


# ---------------------------------------------------------------------------
# SHAP explanations
# ---------------------------------------------------------------------------
def _get_tree_explainer(reg: dict[str, Any], target_col: str):
    """Lazy TreeExplainer for Gradient Boosting models."""
    key = f"tree::{target_col}"
    if key not in reg["explainers"]:
        import shap
        model = reg["best_models"][target_col]["model"]
        reg["explainers"][key] = shap.TreeExplainer(model)
    return reg["explainers"][key]


_NON_FEATURE_COLS = {"cycle_number", "cycle_number_delta"}


def _top_tree_shap_features(
    reg: dict[str, Any],
    target_col: str,
    X_row: pd.DataFrame,
    predicted_class: int,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """SHAP explanation for Gradient Boosting."""
    try:
        explainer = _get_tree_explainer(reg, target_col)
        raw = explainer.shap_values(X_row)

        if isinstance(raw, list):
            row_values = np.asarray(raw[predicted_class])[0]
        else:
            arr = np.asarray(raw)
            if arr.ndim == 3:
                row_values = arr[0, :, predicted_class]
            else:
                row_values = arr[0]

        pairs = [
            (col, float(row_values[i]))
            for i, col in enumerate(X_row.columns)
            if not col.startswith("mold_name_") and col not in _NON_FEATURE_COLS
        ]
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)
        top = pairs[:top_n]
        max_abs = max((abs(v) for _, v in top), default=1.0) or 1.0
        return [
            {
                "feature": prep.label_for_feature(col),
                "impact": round(abs(v) / max_abs, 4),
                "direction": "increasing" if v > 0 else ("decreasing" if v < 0 else "stable"),
            }
            for col, v in top
        ]
    except Exception:
        # Safe GB-only fallback to global feature importances.
        model = reg["best_models"][target_col]["model"]
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return []
        pairs = [
            (col, float(importances[i]), float(X_row.iloc[0, i]))
            for i, col in enumerate(X_row.columns)
            if not col.startswith("mold_name_") and col not in _NON_FEATURE_COLS
        ]
        pairs.sort(key=lambda p: p[1], reverse=True)
        top = pairs[:top_n]
        max_imp = max((imp for _, imp, _ in top), default=1.0) or 1.0
        return [
            {
                "feature": prep.label_for_feature(col),
                "impact": round(imp / max_imp, 4),
                "direction": "increasing" if val > 0 else ("decreasing" if val < 0 else "stable"),
            }
            for col, imp, val in top
        ]


def _make_sequence(
    reg: dict[str, Any],
    X_history: pd.DataFrame,
    target_col: str,
) -> np.ndarray:
    """Create the exact 3D tensor expected by a loaded RNN/LSTM model."""
    info = reg["best_models"][target_col]
    model = info["model"]
    shape = model.input_shape
    if isinstance(shape, list):
        shape = shape[0]

    if len(shape) != 3:
        raise ValueError(
            f"{target_col} {info['type']} expects input shape {shape}; "
            "this runtime supports sequence models shaped "
            "(batch, sequence_length, features)."
        )

    sequence_length = shape[1]
    expected_features = shape[2]
    if sequence_length is None or expected_features is None:
        raise ValueError(
            f"{target_col} has dynamic input shape {shape}. Save the model with a "
            "fixed sequence length and feature count, or store those values in metadata."
        )

    sequence_length = int(sequence_length)
    expected_features = int(expected_features)

    if len(X_history) < sequence_length:
        raise ValueError(
            f"{target_col} requires {sequence_length} cycles but only "
            f"{len(X_history)} processed cycles are available."
        )

    if X_history.shape[1] != expected_features:
        raise ValueError(
            f"{target_col} expects {expected_features} input features per cycle, "
            f"but the current inference pipeline produces {X_history.shape[1]}. "
            "The RNN/LSTM must use the exact same feature set/order used during training."
        )

    sequence = X_history.iloc[-sequence_length:].to_numpy(dtype=np.float32)
    return np.expand_dims(sequence, axis=0)


def _neural_background_sequences(
    X_history: pd.DataFrame,
    sequence_length: int,
    max_background: int = 8,
) -> np.ndarray:
    """Create a small recent background set for neural SHAP."""
    arrays = []
    latest_start = len(X_history) - sequence_length
    start_min = max(0, latest_start - max_background + 1)
    for start in range(start_min, latest_start + 1):
        stop = start + sequence_length
        if stop <= len(X_history):
            arrays.append(
                X_history.iloc[start:stop].to_numpy(dtype=np.float32)
            )
    if not arrays:
        arrays.append(
            X_history.iloc[-sequence_length:].to_numpy(dtype=np.float32)
        )
    return np.stack(arrays, axis=0)


def _top_neural_shap_features(
    reg: dict[str, Any],
    target_col: str,
    X_history: pd.DataFrame,
    X_sequence: np.ndarray,
    predicted_class: int,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """SHAP explanation for RNN/LSTM using GradientExplainer.

    SHAP is aggregated across the time dimension so the UI still receives a
    simple top-feature list. If the installed SHAP/TensorFlow combination does
    not support the loaded network, return an empty list rather than failing
    the prediction API.
    """
    try:
        import shap

        model = reg["best_models"][target_col]["model"]
        sequence_length = X_sequence.shape[1]
        background = _neural_background_sequences(
            X_history, sequence_length
        )
        explainer = shap.GradientExplainer(model, background)
        raw = explainer.shap_values(X_sequence)

        if isinstance(raw, list):
            values = np.asarray(raw[predicted_class])[0]
        else:
            arr = np.asarray(raw)
            if arr.ndim == 4:
                values = arr[0, :, :, predicted_class]
            elif arr.ndim == 3:
                values = arr[0]
            else:
                return []

        if values.ndim != 2:
            return []

        # Sum signed contribution across timesteps for each feature.
        feature_values = values.sum(axis=0)
        pairs = [
            (col, float(feature_values[i]))
            for i, col in enumerate(X_history.columns)
            if not col.startswith("mold_name_") and col not in _NON_FEATURE_COLS
        ]
        pairs.sort(key=lambda p: abs(p[1]), reverse=True)
        top = pairs[:top_n]
        max_abs = max((abs(v) for _, v in top), default=1.0) or 1.0
        return [
            {
                "feature": prep.label_for_feature(col),
                "impact": round(abs(v) / max_abs, 4),
                "direction": "increasing" if v > 0 else ("decreasing" if v < 0 else "stable"),
            }
            for col, v in top
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Recommended actions (templated from the real top feature + severity)
# ---------------------------------------------------------------------------
_ACTION_TEMPLATES = {
    "hopper": {"high": "Stop material feeding at a safe point and inspect the hopper/feed path and temperature sensing linked to {feature}.", "medium": "Inspect hopper material flow, drying/feed condition, and temperature sensing related to {feature}.", "low": "No action required. Continue routine monitoring of hopper and material feed conditions."},
    "heater": {"high": "Stop at the next safe cycle break and inspect the heater band and thermocouple linked to {feature} before resuming production.", "medium": "Inspect the heater band and thermocouple linked to {feature} within the next shift; check for loose contact or sensor drift.", "low": "No action required. Continue routine monitoring of barrel heater zones."},
    "screw": {"high": "Stop at the next safe cycle break and inspect the screw drive, plasticizing section, and suck-back operation linked to {feature}.", "medium": "Check screw drive, back pressure, decompression, and plasticizing behavior related to {feature}.", "low": "No action required. Continue routine monitoring of the screw/plasticizing unit."},
    "injection": {"high": "Stop at the next safe cycle break and inspect the injection unit pressure/speed control linked to {feature}.", "medium": "Inspect injection pressure, speed, V/P transition, and holding control related to {feature}.", "low": "No action required. Continue routine monitoring of the injection unit."},
    "hydraulic": {"high": "Stop at the next safe cycle break and inspect the hydraulic circuit for the fault linked to {feature}.", "medium": "Check hydraulic oil condition, filter condition, leakage, and valve response related to {feature}.", "low": "No action required. Continue routine monitoring of hydraulic pressure."},
    "clamp": {"high": "Stop at the next safe cycle break and inspect clamp force, tie-bar/platen alignment, and mold protection linked to {feature}.", "medium": "Inspect clamp force, platen alignment, lubrication, and mold-protection response related to {feature}.", "low": "No action required. Continue routine monitoring of clamp force and mold protection pressure."},
    "mold": {"high": "Stop at the next safe cycle break and inspect the mold/tooling condition, alignment, temperature, and part-quality signal linked to {feature}.", "medium": "Inspect mold temperature balance, alignment, vents, and tooling condition related to {feature}.", "low": "No action required. Continue routine monitoring of mold/tooling condition."},
    "cooling": {"high": "Stop at the next safe cycle break and inspect cooling flow, channels, hoses, and temperature control linked to {feature}.", "medium": "Check cooling-water flow, channel restriction, leaks, and mold temperature related to {feature}.", "low": "No action required. Continue routine monitoring of the cooling system."},
    "ejector": {"high": "Stop at the next safe cycle break and inspect ejector pins, plate movement, stroke, and drive linked to {feature}.", "medium": "Inspect ejector stroke/speed, pin movement, lubrication, and obstruction related to {feature}.", "low": "No action required. Continue routine monitoring of the ejector system."},
}


def _action_feature_label(top_features: list[dict[str, Any]]) -> str:
    """Prefer a concrete sensor reading over the generic anomaly-score feature when
    phrasing a recommended action -- "linked to back pressure" reads better than
    "linked to Hydraulic System anomaly score"."""
    concrete = next((f for f in top_features if not f["feature"].endswith("anomaly score")), None)
    feature = (concrete or (top_features[0] if top_features else None) or {}).get("feature", "the flagged parameter")
    return re.sub(r"\s*\([^)]*\)\s*$", "", feature)  # drop trailing "(5-cycle average)" etc.


def _recommended_action(subsystem: str, severity: str, top_features: list[dict[str, Any]]) -> str:
    templates = _ACTION_TEMPLATES.get(subsystem, _ACTION_TEMPLATES["heater"])
    template = templates.get(severity, templates["low"])
    return template.format(feature=_action_feature_label(top_features))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _normalize_class_scores(values: Any, target_col: str) -> np.ndarray:
    """Return a 3-class probability vector from model output.

    GB already returns probabilities. Neural models commonly return softmax
    probabilities, but if logits are returned we safely apply softmax.
    """
    scores = np.asarray(values, dtype=float).reshape(-1)
    if scores.size != 3:
        raise ValueError(
            f"{target_col} returned {scores.size} outputs; expected exactly 3 "
            "for classes 0=Healthy, 1=Warning, 2=Critical."
        )

    if np.any(~np.isfinite(scores)):
        raise ValueError(f"{target_col} returned non-finite class scores: {scores}")

    if np.any(scores < 0) or not np.isclose(scores.sum(), 1.0, atol=1e-3):
        shifted = scores - np.max(scores)
        exp_scores = np.exp(shifted)
        scores = exp_scores / exp_scores.sum()

    return scores

def _keras_predict(
    model,
    X: np.ndarray,
) -> np.ndarray:
    """
    Run a single-input Keras model while preserving its
    saved Functional input structure.
    """

    try:

        model_inputs = model.inputs

        if (
            isinstance(model_inputs, (list, tuple))
            and len(model_inputs) == 1
        ):

            input_name = (
                model_inputs[0]
                .name
                .split(":")[0]
            )

            output = model(
                {
                    input_name: X
                },
                training=False,
            )

        else:

            output = model(
                X,
                training=False,
            )

        if hasattr(output, "numpy"):
            output = output.numpy()

        return np.asarray(output)

    except Exception:

        # Compatibility fallback
        return np.asarray(
            model.predict(
                X,
                verbose=0,
            )
        )

def _predict_one(
    reg: dict[str, Any],
    X_row: pd.DataFrame,
    target_col: str,
    X_history: pd.DataFrame,
) -> dict[str, Any]:
    """Predict one subsystem using its selected best model."""
    model_info = reg["best_models"][target_col]
    model = model_info["model"]
    model_type = model_info["type"]

    X_sequence = None
    if model_type == "Gradient_Boosting":
        raw_scores = model.predict_proba(X_row)[0]
    elif model_type in {"RNN", "LSTM"}:

        X_sequence = _make_sequence(
            reg,
            X_history,
            target_col,
        )

        neural_output = _keras_predict(
            model,
            X_sequence,
        )

        raw_scores = neural_output[0]
    else:
        raise ValueError(
            f"Unsupported model type '{model_type}' for {target_col}"
        )

    proba = _normalize_class_scores(raw_scores, target_col)
    predicted_class = int(np.argmax(proba))
    confidence = float(proba[predicted_class])
    state, severity = prep.label_prediction(predicted_class, proba)

    if model_type == "Gradient_Boosting":
        top_features = _top_tree_shap_features(
            reg,
            target_col,
            X_row,
            predicted_class,
        )
    else:
        # Neural SHAP is intentionally skipped during normal
        # dashboard polling because GradientExplainer is expensive.
        #
        # A detailed neural explanation can be calculated separately
        # only when the user explicitly requests an explanation.
        top_features = []

    subsystem = prep.TARGET_TO_SUBSYSTEM.get(target_col)
    return {
        "target": target_col,
        "model_type": model_type,
        "predicted_class": predicted_class,
        "predicted_state": state,
        "severity": severity,
        "confidence": round(confidence, 4),
        "top_features": top_features,
        "recommended_action": _recommended_action(
            subsystem or "heater", severity, top_features
        ),
        "prediction_window": prep.WINDOW_FOR_SEVERITY[severity],
    }


def required_upload_columns(reg: dict[str, Any] | None = None) -> list[str]:
    """Raw columns an uploaded CSV/Excel file must contain to run real inference --
    the exact numeric sensor set the models were trained on (kept_numeric_cols,
    minus cycle_number which can be inferred from row order), plus mold_name."""
    reg = reg or _registry_state()
    numeric = [c for c in reg["feature_config"]["kept_numeric_cols"] if c != "cycle_number"]
    return ["mold_name"] + numeric


def run_inference_on_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Run the exact same trained-model feature pipeline (models/preprocessing.py:
    rolling mean/std + delta engineering -> mold one-hot -> scaling -> anomaly-detector
    scores -> subsystem-specific best model) against uploaded machine data (CSV/Excel), instead of
    the simulated live-feed replay used by run_inference(). Real inference either way --
    this only swaps where the input rows come from.

    Predicts on the LATEST cycle for each distinct mold in the upload (by
    `cycle_number` if present, otherwise by row order), so a file with multiple
    molds and/or many historical cycles per mold returns one set of subsystem
    predictions per mold, each informed by that mold's own recent trend (rolling
    features use up to the trailing `WINDOW` rows available for that mold).
    """
    reg = _registry_state()
    required = required_upload_columns(reg)
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Uploaded data is missing required column(s): {', '.join(missing)}")

    df = df.copy()
    if "cycle_number" not in df.columns:
        df["cycle_number"] = df.groupby("mold_name").cumcount() + 1
    if "material_name" not in df.columns:
        df["material_name"] = "Uploaded material"

    known_molds = set(reg["feature_config"]["mold_names"])
    mold_results = []
    for mold_name, mold_df in df.groupby("mold_name", sort=False):
        mold_df = mold_df.sort_values("cycle_number").reset_index(drop=True)
        cycle_idx = len(mold_df) - 1
        X_row, X_history, context, _raw_row = _build_feature_row(reg, mold_df, cycle_idx)

        predictions = []
        for ui_subsystem, mapping in prep.SUBSYSTEM_TARGET_MAP.items():
            result = _predict_one(reg, X_row, mapping["target"], X_history)
            predictions.append({
                "subsystem": ui_subsystem,
                "subsystem_name": mapping["name"],
                "predicted_state": result["predicted_state"],
                "severity": result["severity"],
                "confidence": result["confidence"],
                "top_features": result["top_features"],
                "recommended_action": result["recommended_action"],
                "prediction_window": result["prediction_window"],
            })

        mold_results.append({
            "mold": mold_name,
            "material": context["material_name"],
            "cycle_id": f"CYC-{context['cycle_number']}",
            "rows_used": len(mold_df),
            "recognized_mold": mold_name in known_molds,
            "predictions": predictions,
        })

    from datetime import datetime, timezone
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "uploaded",
        "molds": mold_results,
    }


def current_live_readings() -> dict[str, Any]:
    """Human-scale sensor/process values for the currently completed simulated cycle."""
    reg = _registry_state()
    mold, mold_df, cycle_idx = _select_snapshot(reg)
    _x, _history, context, raw_row = _build_feature_row(
        reg,
        mold_df,
        cycle_idx
    )
    values = {}
    for col in reg["feature_config"]["kept_numeric_cols"]:
        if col in raw_row.columns:
            try:
                values[col] = round(float(raw_row[col].iloc[0]), 4)
            except Exception:
                pass
    return {
        "mold_name": context["mold_name"],
        "material_name": context["material_name"],
        "cycle_number": context["cycle_number"],
        "readings": values,
    }

def _current_cycle_cache_key(
    mold: str,
    cycle_idx: int,
) -> str:

    with _live_state_lock:
        session_id = _live_session_id

    return (
        f"{session_id}::"
        f"{mold}::"
        f"{cycle_idx}"
    )

def run_inference(
    machine_id: str | None = None,
    subsystem: str | None = None,
) -> dict[str, Any]:

    reg = _registry_state()

    mold, mold_df, cycle_idx = (
        _select_snapshot(reg)
    )

    cache_key = (
        _current_cycle_cache_key(
            mold,
            cycle_idx,
        )
    )

    # ---------------------------------------------------------
    # Helper:
    # return either the full result or one subsystem
    # ---------------------------------------------------------

    def select_response(
        response: dict[str, Any],
    ):

        if subsystem is None:
            return response

        for item in response[
            "predictions"
        ]:

            if (
                item["subsystem"]
                == subsystem
            ):
                return item

        return None

    # ---------------------------------------------------------
    # FAST PATH
    #
    # Most requests should finish here.
    # If this exact live cycle was already calculated,
    # simply return the cached result.
    # ---------------------------------------------------------

    with _prediction_cache_lock:

        if (
            _prediction_cache.get("key")
            == cache_key
            and
            _prediction_cache.get("result")
            is not None
        ):

            cached_result = (
                _prediction_cache[
                    "result"
                ]
            )

            return select_response(
                cached_result
            )

    # ---------------------------------------------------------
    # COMPUTE LOCK
    #
    # Only ONE API request is allowed to calculate
    # a new machine cycle at a time.
    #
    # /subsystems
    # /alerts
    # /maintenance-needs
    # /predict/all
    #
    # may arrive together, but only one performs ML.
    # ---------------------------------------------------------

    with _inference_compute_lock:

        # -----------------------------------------------------
        # SECOND CACHE CHECK
        #
        # Another request may have calculated the cycle
        # while this request was waiting for the compute lock.
        # -----------------------------------------------------

        with _prediction_cache_lock:

            if (
                _prediction_cache.get(
                    "key"
                )
                == cache_key
                and
                _prediction_cache.get(
                    "result"
                )
                is not None
            ):

                cached_result = (
                    _prediction_cache[
                        "result"
                    ]
                )

                return select_response(
                    cached_result
                )

        # -----------------------------------------------------
        # Build features ONCE for this cycle
        # -----------------------------------------------------

        (
            X_row,
            X_history,
            context,
            _raw_row,
        ) = _build_feature_row(
            reg,
            mold_df,
            cycle_idx,
        )

        # -----------------------------------------------------
        # Run all 9 subsystem models ONCE
        # -----------------------------------------------------

        predictions = []

        for (
            ui_subsystem,
            mapping,
        ) in (
            prep
            .SUBSYSTEM_TARGET_MAP
            .items()
        ):

            result = _predict_one(
                reg,
                X_row,
                mapping["target"],
                X_history,
            )

            predictions.append(
                {
                    "subsystem":
                        ui_subsystem,

                    "subsystem_name":
                        mapping["name"],

                    "predicted_state":
                        result[
                            "predicted_state"
                        ],

                    "severity":
                        result[
                            "severity"
                        ],

                    "confidence":
                        result[
                            "confidence"
                        ],

                    "top_features":
                        result[
                            "top_features"
                        ],

                    "recommended_action":
                        result[
                            "recommended_action"
                        ],

                    "prediction_window":
                        result[
                            "prediction_window"
                        ],
                }
            )

        # -----------------------------------------------------
        # Build response
        # -----------------------------------------------------

        from datetime import (
            datetime,
            timezone,
        )

        response = {

            "generated_at":
                datetime.now(
                    timezone.utc
                ).isoformat(),

            "cycle_id":
                f"CYC-{context['cycle_number']}",

            "mold":
                context[
                    "mold_name"
                ],

            "material":
                context[
                    "material_name"
                ],

            "predictions":
                predictions,
        }

        # -----------------------------------------------------
        # Save this completed live cycle to History
        # -----------------------------------------------------

        with _live_state_lock:

            started_at = (
                _live_started_at
            )

            session_id = (
                _live_session_id
            )

        cycle_seconds = (
            LIVE_MACHINE_PROFILES[
                mold
            ][
                "cycle_seconds"
            ]
        )

        completed_cycle = int(
            max(
                0.0,
                time.time()
                - started_at,
            )
            // cycle_seconds
        )

        try:

            from services import (
                live_history_service,
            )

            live_history_service.save_cycle(

                session_id=
                    session_id,

                completed_cycle=
                    completed_cycle,

                generated_at=
                    response[
                        "generated_at"
                    ],

                cycle_id=
                    response[
                        "cycle_id"
                    ],

                mold=
                    response[
                        "mold"
                    ],

                material=
                    response[
                        "material"
                    ],

                predictions=
                    response[
                        "predictions"
                    ],
            )

        except Exception as exc:

            print(
                "[history] Could not save "
                f"live cycle: {exc}"
            )

        # -----------------------------------------------------
        # Store result in cache BEFORE releasing compute lock
        # -----------------------------------------------------

        with _prediction_cache_lock:

            _prediction_cache[
                "key"
            ] = cache_key

            _prediction_cache[
                "result"
            ] = response

        # -----------------------------------------------------
        # Return full or single subsystem response
        # -----------------------------------------------------

        return select_response(
            response
        )

_SEVERITY_HEALTH_PENALTY = {"low": 0, "medium": 14, "high": 32}
ASSUMED_CYCLE_SECONDS = 18.5  # total_cycle_time was correlation-pruned out of the feature set;
# this stands in only for converting a real fault-cycle-frequency count into an hours figure.


def _param_flag_and_direction(raw_row: pd.DataFrame, X_row: pd.DataFrame, col: str) -> tuple[bool, str | None]:
    delta_col = f"{col}_delta"
    delta = float(raw_row[delta_col].iloc[0]) if delta_col in raw_row.columns else 0.0
    direction = "up" if delta > 0 else ("down" if delta < 0 else None)
    z = float(X_row[col].iloc[0]) if col in X_row.columns else 0.0
    return abs(z) > 1.25, direction


def _sparkline_for(mold_df: pd.DataFrame, cycle_idx: int, col: str, n: int = 7) -> list[float]:
    """Return a compact recent-history series for a raw live-feed column.

    Dashboard rendering must never take the API down just because an optional
    display-only parameter was pruned from the trained dataset. If a requested
    column is unavailable, return an empty series instead of raising KeyError.
    """
    if not col or col not in mold_df.columns:
        return []
    lo = max(0, cycle_idx - n + 1)
    values = pd.to_numeric(mold_df.iloc[lo:cycle_idx + 1][col], errors="coerce").dropna()
    return [round(float(v), 3) for v in values.tolist()]


def _diagnostic_text(subsystem_name: str, predicted_state: str, top_features: list[dict[str, Any]]) -> str:
    if predicted_state == "Healthy":
        return f"{subsystem_name} readings are within normal range for the current cycle."
    if not top_features:
        return f"{subsystem_name} is trending {predicted_state.lower()}."
    top = top_features[0]
    return f"{top['feature']} is {top['direction']}, driving the {predicted_state.lower()} classification."


def _count_incidents(mask: pd.Series) -> int:
    """Count contiguous fault runs (incidents), not individual affected rows -- a
    fault that stays active for 20 consecutive cycles is one incident, not 20."""
    starts = mask & ~mask.shift(1, fill_value=False)
    return int(starts.sum())


def _mtbf_estimate(mold_df: pd.DataFrame) -> tuple[float, float]:
    """Mean-time-between-failure-incidents for the 9 monitored targets, converted to
    an approximate hours figure (see ASSUMED_CYCLE_SECONDS) since the raw cycle-time
    column was pruned out of the feature set during correlation pruning. An
    "incident" is a contiguous run of cycles where any tracked subsystem is
    non-healthy, not every individual affected row -- otherwise a single fault that
    persists for many cycles in a row inflates the failure count and collapses MTBF
    toward zero. Also returns the % change between the first and second half of the
    available history, as a lightweight "trending better/worse" signal."""
    target_cols = [m["target"] for m in prep.SUBSYSTEM_TARGET_MAP.values()]
    is_fault = (mold_df[target_cols] != 0).any(axis=1)

    def mtbf_hours(mask: pd.Series) -> float:
        n = len(mask)
        incidents = _count_incidents(mask)
        cycles_between = n / incidents if incidents else float(n)
        return cycles_between * ASSUMED_CYCLE_SECONDS / 3600

    half = len(is_fault) // 2
    overall = mtbf_hours(is_fault)
    first_half, second_half = mtbf_hours(is_fault.iloc[:half]), mtbf_hours(is_fault.iloc[half:])
    delta_pct = ((second_half - first_half) / first_half * 100) if first_half else 0.0
    delta_pct = max(-95.0, min(95.0, delta_pct))  # a two-way split of ~750 rows each can swing
    # wildly when incident counts are small in either half -- clamp to a readable range
    return round(overall, 1), round(delta_pct, 1)


def subsystems_overview() -> dict[str, Any]:
    """Real machine + subsystem health snapshot for the dashboard cards/schematic,
    matching the SubsystemsOverviewResponse shape minus static identity fields
    (id/model/serial_no/location/last_maintenance), which services/prediction_service.py
    fills in from config + the history log."""
    reg = _registry_state()
    mold, mold_df, cycle_idx = _select_snapshot(
        reg
    )

    # Reuse the already-cached ML result.
    live_prediction = run_inference()

    # Build only what the dashboard cards need
    # for raw values / flags / sparklines.
    fc = reg["feature_config"]

    max_seq = _max_required_sequence_length(reg)

    history_needed = (
        max_seq
        + max(prep.WINDOW - 1, 0)
    )

    lo = max(
        0,
        cycle_idx - history_needed + 1
    )

    window_slice = mold_df.iloc[
        lo:cycle_idx + 1
    ].copy()

    engineered = prep.add_engineered_features(
        window_slice,
        fc["kept_numeric_cols"],
    )

    raw_row = engineered.iloc[[-1]].copy()

    processed = prep.add_mold_dummies(
        engineered.copy(),
        fc["mold_names"],
    )

    processed = processed.drop(
        columns=[
            c for c in prep.TARGET
            if c in processed.columns
        ]
    )

    processed = processed.drop(
        columns=[
            c for c in prep.ID_CAT_COLS
            if c in processed.columns
        ]
    )

    processed[
        fc["numeric_cols"]
    ] = reg["scaler"].transform(
        processed[
            fc["numeric_cols"]
        ]
    )

    X_row = processed.iloc[[-1]].copy()

    prediction_map = {
        item["subsystem"]: item
        for item in live_prediction["predictions"]
    }
    subsystem_items = []
    severity_counts = {"low": 0, "medium": 0, "high": 0}
    total_penalty = 0
    windows_active = []

    for ui_subsystem, mapping in prep.SUBSYSTEM_TARGET_MAP.items():
        result = prediction_map[
            ui_subsystem
        ]
        severity_counts[result["severity"]] += 1
        total_penalty += _SEVERITY_HEALTH_PENALTY[result["severity"]]
        if result["severity"] != "low":
            windows_active.append(result["prediction_window"])

        params = []
        for col, label, unit in prep.SUBSYSTEM_PARAMS.get(ui_subsystem, []):
            if col not in raw_row.columns:
                continue
            flag, direction = _param_flag_and_direction(raw_row, X_row, col)
            # Only surface a param as "flagged" (red) when the subsystem itself is
            # actually non-healthy -- an individually unusual reading shouldn't read
            # as an alarm next to a green "Healthy" badge if the model isn't
            # concerned about it overall.
            flag = flag and result["predicted_state"] != "Healthy"
            params.append({
                "label": label,
                "value": round(float(raw_row[col].iloc[0]), 2),
                "unit": unit,
                "flag": bool(flag),
                "direction": direction,
            })

        spark_col = prep.SUBSYSTEM_SPARKLINE_COL.get(ui_subsystem)
        sparkline = _sparkline_for(mold_df, cycle_idx, spark_col) if spark_col else []
        trend_direction = "flat"
        if len(sparkline) >= 2:
            trend_direction = "up" if sparkline[-1] > sparkline[0] else ("down" if sparkline[-1] < sparkline[0] else "flat")

        subsystem_items.append({
            "id": ui_subsystem,
            "name": mapping["name"],
            "short_name": mapping["short_name"],
            "icon": mapping["icon"],
            "status": result["predicted_state"].lower(),
            "confidence": result["confidence"],
            "diagnostic_text": _diagnostic_text(mapping["name"], result["predicted_state"], result["top_features"]),
            "trend_direction": trend_direction,
            "params": params,
            "sparkline": sparkline,
        })

    overall_health = max(15, 100 - total_penalty)
    overall_status = "Good" if overall_health >= 80 else ("Fair" if overall_health >= 60 else "Needs Attention")
    if severity_counts["high"]:
        overall_summary = f"{severity_counts['high']} subsystem(s) need attention"
    elif severity_counts["medium"]:
        overall_summary = f"{severity_counts['medium']} subsystem(s) trending toward a warning"
    else:
        overall_summary = "Operating normally"

    mtbf_hours, mtbf_delta_pct = _mtbf_estimate(mold_df)

    return {
        "overall_health": overall_health,
        "overall_status": overall_status,
        "overall_summary": overall_summary,
        "mtbf_hours": mtbf_hours,
        "mtbf_delta_pct": mtbf_delta_pct,
        "active_alert_count": severity_counts["high"],
        "predicted_issue_count": severity_counts["medium"] + severity_counts["high"],
        "prediction_window_hours": 2 if "Within 2 hours" in windows_active else 24,
        "subsystems": subsystem_items,
    }


def alerts() -> list[dict[str, Any]]:

    live = run_inference()

    predictions = live[
        "predictions"
    ]

    from datetime import datetime, timezone

    now = datetime.now(
        timezone.utc
    ).isoformat()

    items = []

    for i, p in enumerate(
        predictions
    ):

        if p["severity"] == "low":
            continue

        top = (
            p["top_features"][0]
            if p["top_features"]
            else None
        )

        if top:

            detail = (
                f"{top['feature']} is "
                f"{top['direction']}, "
                f"{p['predicted_state'].lower()} "
                f"confidence "
                f"{p['confidence'] * 100:.0f}%."
            )

        else:

            detail = (
                f"{p['subsystem_name']} "
                f"predicted "
                f"{p['predicted_state']} "
                f"({p['confidence'] * 100:.0f}% "
                f"confidence)."
            )

        items.append({

            "id":
                f"ALT-{live['cycle_id']}-{i}",

            "subsystem":
                p["subsystem"],

            "severity":
                p["severity"],

            "title":
                f"{p['subsystem_name']}: "
                f"{p['predicted_state']}",

            "detail":
                detail,

            "timestamp":
                now,

            "acknowledged":
                False,
        })

    items.sort(
        key=lambda a: {
            "high": 0,
            "medium": 1,
            "low": 2,
        }[a["severity"]]
    )

    return items


def maintenance_needs() -> list[dict[str, Any]]:
    """'Predicted Maintenance Needs' table, derived from the same live predictions
    as the dashboard cards (replaces the old static mock_data/maintenance_needs.json)."""
    predictions = run_inference()["predictions"]
    items = []
    for p in predictions:
        if p["severity"] == "low":
            continue
        top = p["top_features"][0]["feature"] if p["top_features"] else p["subsystem_name"]
        items.append({
            "component": top,
            "subsystem": p["subsystem"],
            "issue": f"{p['predicted_state']} ({p['subsystem_name']})",
            "severity": p["severity"],
            "prediction_window": p["prediction_window"],
            "recommendation": p["recommended_action"],
            "confidence": p["confidence"],
        })
    items.sort(key=lambda i: {"high": 0, "medium": 1, "low": 2}[i["severity"]])
    return items


def health_trend(n_points: int = 7) -> dict[str, Any]:
    """Real historical health trend for the currently-selected mold, computed from
    the TRUE recorded subsystem states in the held-out test split (not re-run
    through the model -- this is ground truth, evenly sampled across that mold's
    available cycle history) rather than a static 7-day mock series."""
    reg = _registry_state()
    mold, mold_df, _cycle_idx = _select_snapshot(reg)
    target_cols = [m["target"] for m in prep.SUBSYSTEM_TARGET_MAP.values()]

    n = len(mold_df)
    n_points = min(n_points, n) or 1
    idxs = sorted({round(i * (n - 1) / max(1, n_points - 1)) for i in range(n_points)})

    labels, series = [], []
    for idx in idxs:
        row = mold_df.iloc[idx]
        penalty = sum(_SEVERITY_HEALTH_PENALTY[prep.SEVERITY_FOR_STATE[int(row[c])]] for c in target_cols)
        labels.append(f"Cycle {int(row['cycle_number'])}")
        series.append(max(15, 100 - penalty))
    return {"labels": labels, "series": series}


def current_context() -> dict[str, Any]:
    """Mold/material/cycle currently being "monitored" -- used by the dashboard's
    live status chip and by the assistant for subsystem-agnostic context."""
    reg = _registry_state()
    mold, mold_df, cycle_idx = _select_snapshot(reg)
    row = mold_df.iloc[cycle_idx]
    return {"mold": row["mold_name"], "material": row["material_name"], "cycle_number": int(row["cycle_number"])}
