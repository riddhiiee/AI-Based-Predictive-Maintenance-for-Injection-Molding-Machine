"""
Pydantic models for the FastAPI layer.

These mirror the shapes documented in services/*.py. Keeping them in one
place makes it easy to see the full "public contract" of the API, and to
extend it later without hunting through router files.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Subsystem = Literal["hopper", "heater", "screw", "injection", "hydraulic", "clamp", "mold", "cooling", "ejector"]
Severity = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------

class TopFeature(BaseModel):
    feature: str
    impact: float
    direction: str


class PredictionItem(BaseModel):
    subsystem: str
    subsystem_name: str
    predicted_state: str
    severity: str
    confidence: float
    top_features: list[TopFeature]
    recommended_action: str
    prediction_window: str


class PredictionsResponse(BaseModel):
    generated_at: str
    cycle_id: str
    mold: str
    material: str
    predictions: list[PredictionItem]


class MoldUploadPrediction(BaseModel):
    mold: str
    material: str
    cycle_id: str
    rows_used: int
    recognized_mold: bool
    predictions: list[PredictionItem]


class UploadPredictionsResponse(BaseModel):
    generated_at: str
    source: str
    molds: list[MoldUploadPrediction]


class UploadRequirementsResponse(BaseModel):
    required_columns: list[str]


# ---------------------------------------------------------------------------
# Subsystems overview (dashboard cards + schematic)
# ---------------------------------------------------------------------------

class MachineSummary(BaseModel):
    id: str
    model: str
    serial_no: str
    location: str
    status: str
    overall_health: int
    overall_status: str
    overall_summary: str
    mtbf_hours: float
    mtbf_delta_pct: float
    last_maintenance: str
    active_alert_count: int
    predicted_issue_count: int
    prediction_window_hours: int


class SubsystemParam(BaseModel):
    label: str
    value: float
    unit: str
    flag: bool
    direction: Optional[str] = None


class SubsystemItem(BaseModel):
    id: str
    name: str
    short_name: str
    icon: str
    status: str
    confidence: float
    diagnostic_text: str
    trend_direction: str
    params: list[SubsystemParam]
    sparkline: list[float]


class SubsystemsOverviewResponse(BaseModel):
    machine: MachineSummary
    subsystems: list[SubsystemItem]


# ---------------------------------------------------------------------------
# Maintenance needs (dashboard table)
# ---------------------------------------------------------------------------

class MaintenanceNeedItem(BaseModel):
    component: str
    subsystem: str
    issue: str
    severity: str
    prediction_window: str
    recommendation: str
    confidence: float


class MaintenanceNeedsResponse(BaseModel):
    items: list[MaintenanceNeedItem]


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

class AlertItem(BaseModel):
    id: str
    subsystem: str
    severity: str
    title: str
    detail: str
    timestamp: str
    acknowledged: bool


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------

class TrendSeries(BaseModel):
    labels: list[str]
    series: list[float]
    unit: Optional[str] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None


class TrendsResponse(BaseModel):
    health_trend_7d: TrendSeries
    parameter_trends: dict[str, TrendSeries]


# ---------------------------------------------------------------------------
# Assistant - suggested prompts
# ---------------------------------------------------------------------------

class SuggestedPromptsResponse(BaseModel):
    prompts: list[str]


# ---------------------------------------------------------------------------
# Explain
# ---------------------------------------------------------------------------

class ExplainResponse(BaseModel):
    subsystem: str
    subsystem_name: str
    predicted_state: str
    severity: str
    confidence: float
    top_features: list[TopFeature]
    recommended_action: str
    explanation_method: str


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    subsystem_hint: Optional[Subsystem] = None


class ManualChunk(BaseModel):
    document_id: str
    document_title: str
    chunk_id: str
    snippet: str
    page: Optional[int] = None
    relevance_score: Optional[float] = None


class AssistantChatResponse(BaseModel):
    message_id: str
    timestamp: str
    query: str
    subsystem: str
    predicted_state: str
    confidence: float
    severity: str
    top_features: list[TopFeature]
    explanation_summary: str
    maintenance_actions: list[str]
    source_documents: list[str]
    retrieved_manual_chunks: list[ManualChunk]


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------

class DocumentItem(BaseModel):
    id: str
    title: str
    type: str
    subsystem: str
    pages: Optional[int] = None
    status: str
    uploaded_at: str
    chunks_indexed: int
    error: Optional[str] = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentItem]


class RagUploadRequest(BaseModel):
    filename: str
    subsystem: Optional[str] = None
    doc_type: Optional[str] = None


class RagQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    subsystem_filter: Optional[str] = None


class RagQueryResponse(BaseModel):
    query: str
    subsystem_filter: Optional[str] = None
    retrieved_manual_chunks: list[ManualChunk]
    answer_summary: str
    source_documents: list[str]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class HistoryEvent(BaseModel):
    id: str
    timestamp: str
    subsystem: str
    event_type: str
    state: str
    confidence: Optional[float] = None
    note: str


class HistoryResponse(BaseModel):
    events: list[HistoryEvent]
    count: int


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    mock_mode: bool
