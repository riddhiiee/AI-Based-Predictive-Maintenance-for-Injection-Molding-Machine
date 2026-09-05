"""
FastAPI backend for the AI-Powered Predictive Maintenance System.

Run with:
    uvicorn api.main:app --reload --port 8000

All endpoints currently return mock/simulated data (see services/mock_*.py).
Swap those service modules for real implementations to go live; the
routers, schemas, and response shapes are designed to stay stable.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import assistant, explain, health, predict,history

app = FastAPI(
    title="Predictive Maintenance API",
    description=(
        "Machine health, predictions, explanations, "
        "the AI assistant, and the manual/RAG knowledge base. "
        "The assistant uses the trained ML pipeline plus a pre-indexed manual RAG knowledge base."
    ),
    version="0.1.0",
)

# The Flask app serves the UI on a different port and calls this API
# directly from browser JS (see static/js/api.js). Restrict origins to
# local dev servers; add your deployed frontend origin(s) here later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(predict.router)
app.include_router(explain.router)
app.include_router(assistant.router)
app.include_router(history.router)

@app.get("/")
def root():
    return {
        "service": "predictive-maintenance-api",
        "status": "ok",
        "docs": "/docs",
    }
