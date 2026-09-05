"""
Shared feature-engineering logic for the MoldGuard subsystem-health models.

This module is imported by BOTH `models/train.py` (fits everything once,
offline) and `models/inference.py` (re-applies the exact same steps to a
handful of "live" rows at request time). Keeping the logic in one place is
what guarantees a served prediction was produced the same way the model was
trained -- there is no duplicated feature math anywhere else in the project.

Faithfully mirrors final_model.ipynb: correlation pruning -> rolling
mean/std + delta engineering -> mold one-hot -> StandardScaler -> per-target
anomaly-detector score -> GradientBoostingClassifier.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# The 9 subsystem targets the notebook trains one classifier per (ordinal
# 3-level state: 0 = healthy, 1 = warning, 2 = fault).
# ---------------------------------------------------------------------------
TARGET = [
    "Hopper_State", "Barrel_Heater_State", "Screw_State", "Injection_Unit_State",
    "Hydraulic_System_State", "Clamp_Unit_State", "Mold_State",
    "Cooling_System_State", "Ejector_System_State",
]

# All 9 trained targets are surfaced consistently across the dashboard,
# machine schematic, predictions page, explain endpoint, and AI assistant.
SUBSYSTEM_TARGET_MAP = {
    "hopper": {"target": "Hopper_State", "name": "Hopper / Material Feed", "short_name": "Hopper", "icon": "box"},
    "heater": {"target": "Barrel_Heater_State", "name": "Barrel Heater", "short_name": "Heater", "icon": "flame"},
    "screw": {"target": "Screw_State", "name": "Screw / Plasticizing", "short_name": "Screw", "icon": "rotate-cw"},
    "injection": {"target": "Injection_Unit_State", "name": "Injection Unit", "short_name": "Injection", "icon": "activity"},
    "hydraulic": {"target": "Hydraulic_System_State", "name": "Hydraulic System", "short_name": "Hydraulic", "icon": "droplet"},
    "clamp": {"target": "Clamp_Unit_State", "name": "Clamp Unit", "short_name": "Clamp", "icon": "clamp"},
    "mold": {"target": "Mold_State", "name": "Mold / Tooling", "short_name": "Mold", "icon": "box"},
    "cooling": {"target": "Cooling_System_State", "name": "Cooling System", "short_name": "Cooling", "icon": "thermometer"},
    "ejector": {"target": "Ejector_System_State", "name": "Ejector System", "short_name": "Ejector", "icon": "arrow-right"},
}

# Real raw sensor columns to surface as "live parameters" per UI subsystem card
# (all confirmed present in models/artifacts/feature_config.json's kept_numeric_cols
# after correlation pruning -- see models/train.py).
SUBSYSTEM_PARAMS = {
    "hopper": [("hopper_temp", "Hopper Temperature", "°C")],
    "heater": [("H1", "Heater Zone 1", "°C"), ("H2", "Heater Zone 2", "°C"), ("H3", "Heater Zone 3", "°C"), ("nozzle_temp", "Nozzle Temperature", "°C")],
    "screw": [("screw_rpm", "Screw RPM", "rpm"), ("back_pressure", "Back Pressure", "bar"), ("decompression_speed", "Decompression Speed", "mm/s"), ("cushion_size", "Cushion Size", "mm")],
    "injection": [("actual_inj_pressure", "Injection Pressure", "bar"), ("inj_speed1", "Injection Speed", "mm/s"), ("vp_transition", "V/P Transition", "mm"), ("holding_pressure_stage2", "Holding Pressure", "bar")],
    "hydraulic": [("actual_inj_pressure", "Injection Pressure", "bar"), ("holding_pressure_stage2", "Holding Pressure", "bar"), ("back_pressure", "Back Pressure", "bar")],
    "clamp": [("clamp_force", "Clamp Force", "kN"), ("mold_protection_pressure", "Mold Protection Pressure", "bar"), ("mold_close_speed", "Mold Close Speed", "mm/s")],
    "mold": [("mold_core_temp", "Mold Core Temperature", "°C"), ("mold_cavity_temp", "Mold Cavity Temperature", "°C"), ("part_weight", "Part Weight", "g")],
    "cooling": [("mold_cavity_temp", "Mold Cavity Temperature", "°C"), ("mold_core_temp", "Mold Core Temperature", "°C"), ("cooling_time", "Cooling Time", "s")],
    "ejector": [("ejection_stroke", "Ejection Stroke", "mm"), ("ejection_speed", "Ejection Speed", "mm/s")],
}

# Primary sensor column used for each subsystem's dashboard-card sparkline.
SUBSYSTEM_SPARKLINE_COL = {
    "hopper": "hopper_temp",
    "heater": "H1",
    # The trained/live-feed dataset does not retain screw_rpm after feature pruning.
    # Back pressure is a real Screw_State driver and is present in every live-feed row.
    "screw": "back_pressure",
    "injection": "actual_inj_pressure",
    "hydraulic": "back_pressure",
    "clamp": "clamp_force",
    "mold": "mold_cavity_temp",
    # cooling_time is not retained in the model feed; mold cavity temperature is
    # the actual Cooling_System_State driver used by the trained pipeline.
    "cooling": "mold_cavity_temp",
    "ejector": "ejection_stroke",
}
TARGET_TO_SUBSYSTEM = {v["target"]: k for k, v in SUBSYSTEM_TARGET_MAP.items()}

WINDOW = 5  # trailing-cycle window for rolling mean/std features

TEMP_PRESSURE = [
    "hopper_temp", "H1", "mold_cavity_temp", "inj_speed1", "holding_pressure_stage2",
    "back_pressure", "decompression_speed", "mold_protection_pressure", "ejection_stroke",
    "part_weight",
]

# Which raw sensor column(s) drive each target (see final_model.ipynb, cell 17).
TARGET_BASE_COLS = {
    "Hopper_State": ["hopper_temp"],
    "Barrel_Heater_State": ["H1"],
    "Screw_State": ["back_pressure", "decompression_speed", "decompression_distance", "cushion_size"],
    "Injection_Unit_State": ["actual_inj_pressure", "cushion_size", "inj_speed1", "vp_transition", "holding_pressure_stage2"],
    "Hydraulic_System_State": ["clamp_force", "actual_inj_pressure", "holding_pressure_stage2"],
    "Clamp_Unit_State": ["mold_protection_pressure", "clamp_force"],
    "Mold_State": ["mold_cavity_temp", "part_weight"],
    "Cooling_System_State": ["mold_cavity_temp"],
    "Ejector_System_State": ["ejection_stroke"],
}

ID_CAT_COLS = ["mold_name", "material_name"]

# Human-readable labels for every raw sensor column, used to translate SHAP's
# internal (possibly engineered) column names into UI-facing feature names.
FEATURE_LABELS = {
    "machine_tonnage": "Machine tonnage",
    "cycle_number": "Cycle number",
    "hopper_temp": "Hopper temperature",
    "nozzle_temp": "Nozzle temperature",
    "H1": "Heater zone 1 temperature",
    "H2": "Heater zone 2 temperature",
    "H3": "Heater zone 3 temperature",
    "mold_core_temp": "Mold core temperature",
    "mold_cavity_temp": "Mold cavity temperature",
    "inj_speed1": "Injection speed (stage 1)",
    "inj_speed2": "Injection speed (stage 2)",
    "inj_speed3": "Injection speed (stage 3)",
    "actual_inj_pressure": "Actual injection pressure",
    "vp_transition": "V/P transition point",
    "inj_time_actual": "Actual injection time",
    "holding_pressure_stage1": "Holding pressure (stage 1)",
    "holding_pressure_stage2": "Holding pressure (stage 2)",
    "holding_pressure_stage3": "Holding pressure (stage 3)",
    "screw_rpm": "Screw RPM",
    "back_pressure": "Back pressure",
    "decompression_speed": "Decompression speed",
    "decompression_distance": "Decompression distance",
    "cushion_size": "Cushion size",
    "clamp_force": "Clamp force",
    "mold_close_speed": "Mold close speed",
    "mold_protection_pressure": "Mold protection pressure",
    "ejection_stroke": "Ejection stroke",
    "ejection_speed": "Ejection speed",
    "cooling_time": "Cooling time",
    "mold_open_reset_time": "Mold open/reset time",
    "part_weight": "Part weight",
    "shot_weight": "Shot weight",
    "screw_diameter": "Screw diameter",
    "total_cycle_time": "Total cycle time",
}


def label_for_feature(col: str) -> str:
    """Translate an (possibly engineered) feature column name into a UI label."""
    if col.startswith("mold_name_"):
        return f"Mold: {col[len('mold_name_'):]}"
    if col.endswith("_anomaly_score"):
        base = col[: -len("_anomaly_score")]
        subsystem = TARGET_TO_SUBSYSTEM.get(base)
        return f"{SUBSYSTEM_TARGET_MAP[subsystem]['name']} anomaly score" if subsystem else base.replace("_", " ")
    if col.endswith("_roll_mean"):
        base = col[: -len("_roll_mean")]
        return f"{FEATURE_LABELS.get(base, base)} (5-cycle average)"
    if col.endswith("_roll_std"):
        base = col[: -len("_roll_std")]
        return f"{FEATURE_LABELS.get(base, base)} (5-cycle volatility)"
    if col.endswith("_delta"):
        base = col[: -len("_delta")]
        return f"{FEATURE_LABELS.get(base, base)} (cycle-over-cycle change)"
    return FEATURE_LABELS.get(col, col.replace("_", " "))


def expand_features(base_cols: list[str], temp_pressure: list[str], kept_numeric_cols: list[str]) -> list[str]:
    """Raw column + its engineered roll_mean/roll_std (if in temp_pressure) and delta (if kept)."""
    feats = []
    for c in base_cols:
        feats.append(c)
        if c in temp_pressure:
            feats += [f"{c}_roll_mean", f"{c}_roll_std"]
        if c in kept_numeric_cols:
            feats.append(f"{c}_delta")
    seen = set()
    return [f for f in feats if not (f in seen or seen.add(f))]


def build_target_feature_map(kept_numeric_cols: list[str]) -> dict[str, list[str]]:
    return {col: expand_features(cols, TEMP_PRESSURE, kept_numeric_cols) for col, cols in TARGET_BASE_COLS.items()}


def add_engineered_features(data: pd.DataFrame, kept_numeric_cols: list[str], window: int = WINDOW) -> pd.DataFrame:
    """Rolling mean/std (over TEMP_PRESSURE cols) + cycle-over-cycle delta (over kept_numeric_cols),
    grouped per mold and ordered by cycle_number -- identical to final_model.ipynb cell 8."""
    data = data.sort_values(["mold_name", "cycle_number"]).reset_index(drop=True)
    grp = data.groupby("mold_name")

    roll_mean = grp[TEMP_PRESSURE].rolling(window, min_periods=1).mean().droplevel(0)
    roll_mean.columns = [f"{c}_roll_mean" for c in TEMP_PRESSURE]

    roll_std = grp[TEMP_PRESSURE].rolling(window, min_periods=1).std().droplevel(0)
    roll_std.columns = [f"{c}_roll_std" for c in TEMP_PRESSURE]

    delta = grp[kept_numeric_cols].diff()
    delta.columns = [f"{c}_delta" for c in kept_numeric_cols]

    eng = pd.concat([roll_mean, roll_std, delta], axis=1).sort_index().fillna(0.0)
    return pd.concat([data, eng], axis=1)


def add_mold_dummies(data: pd.DataFrame, mold_names: list[str]) -> pd.DataFrame:
    """One-hot encode mold_name using a FIXED column set (`mold_names`, saved at train
    time) so a slice containing only one mold still produces every mold_name_* column."""
    enc = pd.DataFrame(0, index=data.index, columns=[f"mold_name_{m}" for m in mold_names])
    for m in mold_names:
        enc.loc[data["mold_name"] == m, f"mold_name_{m}"] = 1
    return pd.concat([enc, data], axis=1)


def score_with_detector(
    algorithm: str,
    model,
    X_split: pd.DataFrame,
) -> np.ndarray:
    """
    Apply an already-fitted anomaly detector.

    Returns one anomaly score per row where:
        higher score = more anomalous

    The detector may have been fitted with pandas feature names.
    Therefore, preserve/reconstruct those feature names during inference
    instead of passing an unnamed NumPy array.
    """

    # ---------------------------------------------------------
    # Make sure input is a DataFrame
    # ---------------------------------------------------------

    if not isinstance(X_split, pd.DataFrame):
        X_split = pd.DataFrame(X_split)

    X_detector = X_split.copy()

    # ---------------------------------------------------------
    # Restore the exact feature names remembered by sklearn
    # ---------------------------------------------------------

    fitted_feature_names = getattr(
        model,
        "feature_names_in_",
        None,
    )

    if fitted_feature_names is not None:

        fitted_feature_names = list(
            fitted_feature_names
        )

        # If the same columns exist, put them in the exact
        # training-time order.
        if set(fitted_feature_names).issubset(
            X_detector.columns
        ):
            X_detector = X_detector[
                fitted_feature_names
            ].copy()

        # If the incoming DataFrame has the correct number
        # of columns but different/missing labels, restore
        # the training-time labels.
        elif len(fitted_feature_names) == X_detector.shape[1]:

            X_detector = X_detector.copy()

            X_detector.columns = (
                fitted_feature_names
            )

    # ---------------------------------------------------------
    # Isolation Forest
    # ---------------------------------------------------------

    if algorithm == "Isolation Forest":

        scores = -model.decision_function(
            X_detector
        )

        return np.asarray(
            scores,
            dtype=float,
        )

    # ---------------------------------------------------------
    # ECOD / COPOD
    # ---------------------------------------------------------

    if algorithm in ("ECOD", "COPOD"):

        scores = model.decision_function(
            X_detector
        )

        return np.asarray(
            scores,
            dtype=float,
        )

    # ---------------------------------------------------------
    # Local Outlier Factor
    # ---------------------------------------------------------

    if algorithm == "LOF":

        with warnings.catch_warnings():

            warnings.filterwarnings(
                "ignore",
                message=(
                    "X does not have valid feature names, "
                    "but LocalOutlierFactor was fitted "
                    "with feature names"
                ),
                category=UserWarning,
            )

            scores = -model.decision_function(
                X_detector
            )

        return np.asarray(
            scores,
            dtype=float,
        )

    # ---------------------------------------------------------
    # Autoencoder
    # ---------------------------------------------------------

    if algorithm == "Autoencoder":

        values = X_detector.to_numpy(
            dtype=np.float32
        )

        recon = model["model"].predict(
            values,
            verbose=0,
        )

        recon = np.asarray(
            recon,
            dtype=np.float32,
        )

        return np.mean(
            np.square(values - recon),
            axis=1,
        )

    # ---------------------------------------------------------
    # Unknown detector
    # ---------------------------------------------------------

    raise ValueError(
        f"Unsupported anomaly detector algorithm: {algorithm}"
    )


STATE_NAMES = {0: "Healthy", 1: "Warning", 2: "Critical"}
SEVERITY_FOR_STATE = {0: "low", 1: "medium", 2: "high"}
WINDOW_FOR_SEVERITY = {"low": "Not applicable", "medium": "Within 24 hours", "high": "Within 2 hours"}


def label_prediction(
    predicted_class: int,
    proba: np.ndarray,
) -> tuple[str, str]:
    """
    Convert model class output into the final MoldGuard health state.

    Final system:
        0 = Healthy
        1 = Warning
        2 = Critical
    """

    predicted_class = int(
        predicted_class
    )

    if predicted_class not in STATE_NAMES:
        raise ValueError(
            f"Invalid predicted class: {predicted_class}. "
            "Expected 0, 1, or 2."
        )

    state = STATE_NAMES[
        predicted_class
    ]

    severity = SEVERITY_FOR_STATE[
        predicted_class
    ]

    return state, severity
