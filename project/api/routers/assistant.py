from fastapi import APIRouter

from api.schemas import AssistantChatRequest, AssistantChatResponse, SuggestedPromptsResponse
from services import assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/suggested-prompts", response_model=SuggestedPromptsResponse)
def suggested_prompts():
    """Prompt chips shown in the assistant UI (dashboard rail + full chat page)."""
    return {"prompts": assistant_service.get_suggested_prompts()}


@router.post("/chat", response_model=AssistantChatResponse)
def chat(payload: AssistantChatRequest):
    """
    Ask the AI assistant a question about machine health.

    Combines a real model prediction (models/inference.py), its SHAP
    explanation, and real RAG retrieval over the manual knowledge base
    (rag/rag_service.py) into one grounded answer. See
    services/assistant_service.py for the orchestration.
    """
    return assistant_service.ask_assistant(payload.message, payload.subsystem_hint)
