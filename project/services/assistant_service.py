from __future__ import annotations
import json,uuid
from datetime import datetime,timezone
from models import inference
from rag import rag_service
from services import runtime_state
SUGGESTED_PROMPTS=["What does the manual recommend for the current warning?","Why is this subsystem at risk?","What should maintenance inspect first?","Compare the current readings with manual guidance."]
def get_suggested_prompts():return SUGGESTED_PROMPTS
def _context():
    uploaded = runtime_state.get_uploaded()

    if uploaded:
        payload = {
            "data_source": "user-uploaded CSV/Excel",
            "filename": uploaded.get("filename"),
            "latest_actual_readings": uploaded.get("readings", []),
            "model_results": uploaded.get("result"),
        }

        return json.dumps(
            payload,
            default=str,
            indent=2,
        )[:8000]

    live = inference.run_inference()
    live_readings = inference.current_live_readings()

    return json.dumps(
        {
            "data_source": "simulated real-time CSV cycle feed",
            "latest_actual_readings": live_readings,
            "model_results": live,
        },
        default=str,
        indent=2,
    )[:8000]
def _current_prediction_candidates():
    uploaded = runtime_state.get_uploaded()
    candidates = []
    if uploaded:
        result = uploaded.get("result") or {}
        for mold in result.get("molds") or []:
            for prediction in mold.get("predictions", []):
                candidates.append({**prediction, "mold": mold.get("mold"), "material": mold.get("material")})
    else:
        live = inference.run_inference()
        for prediction in live.get("predictions", []):
            candidates.append({**prediction, "mold": live.get("mold"), "material": live.get("material")})
    return candidates


def _primary_prediction():
    candidates = _current_prediction_candidates()
    if not candidates:
        return None
    severity_rank = {"high": 3, "medium": 2, "low": 1}
    return max(candidates, key=lambda p: (severity_rank.get(p.get("severity"), 0), p.get("confidence", 0)))

def ask_assistant(message: str, subsystem_hint: str | None = None):
    ctx = _context()

    primary = _prediction_for_question(
        message,
        subsystem_hint,
    )

    search_hint = subsystem_hint

    if not search_hint and primary:
        search_hint = primary.get("subsystem")

    chunks = rag_service.run_semantic_search(
        message,
        search_hint,
        3,
    )

    text = rag_service.answer(
        message,
        chunks,
        ctx,
    )

    if primary:
        subsystem = primary.get("subsystem", "general")
        predicted_state = primary.get("predicted_state", "Unknown")
        confidence = primary.get("confidence", 0.0)
        severity = primary.get("severity", "info")
        top_features = primary.get("top_features", [])
    else:
        subsystem = subsystem_hint or "manual guidance"
        predicted_state = "RAG"
        confidence = 0.0
        severity = "info"
        top_features = []

    return {
        "message_id": f"msg-{uuid.uuid4().hex[:10]}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": message,
        "subsystem": subsystem,
        "predicted_state": predicted_state,
        "confidence": confidence,
        "severity": severity,
        "top_features": top_features,
        "explanation_summary": text,
        "maintenance_actions": [],
        "source_documents": list(
            dict.fromkeys(c["document_id"] for c in chunks)
        ),
        "retrieved_manual_chunks": [
            {
                "document_id": c["document_id"],
                "document_title": c["document_title"],
                "chunk_id": c["chunk_id"],
                "snippet": c["text"],
                "page": c.get("page"),
                "relevance_score": c["relevance_score"],
            }
            for c in chunks
        ],
    }
def _prediction_for_question(message: str, subsystem_hint: str | None = None):
    """
    Select the prediction relevant to the user's question.

    If the user mentions a specific subsystem, return that subsystem.
    Otherwise return the highest-risk subsystem.
    """
    predictions = _current_prediction_candidates()
    if not predictions:
        return None

    text = f"{message} {subsystem_hint or ''}".lower()

    aliases = {
        "hydraulic": [
            "hydraulic",
            "hydraulic system",
        ],

        "screw": [
            "screw",
            "plasticizing",
            "plasticising",
            "screw / plasticizing",
        ],

        "heater": [
            "heater",
            "barrel heater",
            "heater band",
        ],

        "clamp": [
            "clamp",
            "clamping",
            "clamp unit",
        ],

        "injection": [
            "injection unit",
            "injection system",
        ],

        "cooling": [
            "cooling",
            "cooling system",
        ],

        "ejector": [
            "ejector",
            "ejection",
            "ejector system",
        ],

        "mold": [
            "mold",
            "mould",
        ],

        "hopper": [
            "hopper",
        ],
    }

    # Check whether the user explicitly asked
    # about a particular subsystem.
    requested = None

    for canonical, words in aliases.items():
        if any(word in text for word in words):
            requested = canonical
            break

    if requested:
        for prediction in predictions:
            subsystem = str(
                prediction.get("subsystem", "")
            ).lower()

            if requested in subsystem:
                return prediction

            if requested == "screw" and (
                "plastic" in subsystem or "screw" in subsystem
            ):
                return prediction

            if requested == "heater" and "heater" in subsystem:
                return prediction

            if requested == "clamp" and "clamp" in subsystem:
                return prediction

            if requested == "ejector" and (
                "eject" in subsystem
            ):
                return prediction

    # No specific subsystem requested:
    # return overall highest-risk component.
    return _primary_prediction()