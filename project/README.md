# MoldGuard AI — 9-Subsystem Predictive Maintenance

A local two-process application for predictive maintenance of plastic injection molding machines. The dashboard replays one CSV cycle at the material-specific production interval, runs the trained 9-subsystem Gradient Boosting models, displays the result on a detailed injection molding machine schematic, and uses the built-in RAG manuals in the AI Assistant.

## Monitored subsystems

1. Hopper
2. Barrel Heater
3. Screw / Plasticizing
4. Injection Unit
5. Hydraulic System
6. Clamp Unit
7. Mold / Tooling
8. Cooling System
9. Ejector System

## First-time setup

```powershell
cd project
python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and place your own Groq key in `GROQ_API_KEY`.

## Run — Terminal 1 (FastAPI backend)

```powershell
cd project
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Verify the backend before starting the UI:

```text
http://127.0.0.1:8000/health
```

It should return a JSON object with `"status":"ok"`.

## Run — Terminal 2 (Flask UI)

```powershell
cd project
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

The frontend prefers `127.0.0.1:8000` and automatically falls back to `localhost:8000` on a connection-level failure. This avoids the Windows IPv4/IPv6 `localhost` issue that can make a healthy Uvicorn server appear unreachable.

## Live CSV simulation

Select one of the four production profiles from the Dashboard. One row is fed to the model only after the selected molding cycle completes:

- ABS / Smart Router Enclosure — 24.34 s
- Polycarbonate / Blood Filtration Housing — 31.35 s
- Polypropylene / Rectangular Food Container — 4.48 s
- PA66 + 30% GF / Engine Mount Bracket — 39.65 s

Every completed row is processed by the same feature engineering, anomaly detection, Gradient Boosting and SHAP pipeline used by the prediction API.

## RAG Assistant

The maintenance manuals are pre-indexed in `rag/store/manuals.faiss`; operators do not need to upload the manuals. The assistant combines retrieved manual evidence with the current machine/model context.
