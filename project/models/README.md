# models/ — trained ML pipeline

This is no longer a placeholder — real models are trained and running here.

```
models/
  preprocessing.py   shared feature engineering (used by BOTH train.py and inference.py,
                      so a served prediction is built the exact same way the model was trained)
  train.py            trains everything below and writes artifacts/ — rerun anytime the
                      dataset or pipeline changes: `python -m models.train`
  inference.py        loads artifacts/, simulates a "live" cycle from the held-out test
                      split, and serves predictions/SHAP/subsystem-overview/alerts/etc.
  shap_service.py     thin ExplainResponse wrapper around inference.py's SHAP computation
  artifacts/          (gitignored) trained models, scaler, detectors, live-feed samples —
                      regenerate with `python -m models.train`
```

## What's trained

Faithful to `final_model.ipynb`'s own pipeline and conclusion: correlation
pruning → rolling/delta feature engineering → mold one-hot → StandardScaler
→ a per-subsystem anomaly-detector score (best of Isolation Forest / ECOD /
COPOD / LOF / Autoencoder, picked by validation PR-AUC) → a
**GradientBoostingClassifier per subsystem target**, which the notebook's
own final comparison found to be the best of the 9 models it tried
(F1-macro 0.708, beating CatBoost/RandomForest/XGBoost/LightGBM/RNN/LSTM).

All **9** subsystem targets are trained and saved (`Hopper_State`,
`Barrel_Heater_State`, `Screw_State`, `Injection_Unit_State`,
`Hydraulic_System_State`, `Clamp_Unit_State`, `Mold_State`,
`Cooling_System_State`, `Ejector_System_State`) — the current 4-card UI
(heater/hydraulic/screw/clamp) surfaces one representative target per card
via `preprocessing.SUBSYSTEM_TARGET_MAP`; the other 5 are trained and
available via `models.inference` for future UI expansion.

Per-target test-set metrics are in `artifacts/metrics_summary.json` after
training.

## No live sensor feed

There's no PLC/OPC-UA connection in this prototype, so "current" readings
are simulated by replaying real historical cycles from the held-out test
split (`artifacts/live_feed/*.csv`) through the full feature pipeline —
every prediction is a genuine model output on real data, just not a live
plant connection. Which mold/cycle is "current" rotates on a timer
(`models/inference.py`: `MOLD_ROTATE_SECONDS` / `CYCLE_ROTATE_SECONDS`) so
the dashboard feels alive across repeated polls.

## Where this plugs in

`services/prediction_service.py` and `services/explain_service.py` call
straight into this package — see those files for the thin composition
layer (adding static machine identity + the one field genuinely sourced
from the mock history log).
