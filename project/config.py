"""
Shared configuration for the Flask UI layer and the FastAPI service layer
(services/*.py is imported by both processes, so this file is too).
"""
import os

from dotenv import load_dotenv

load_dotenv()  # reads a .env file in the project root, if present (see .env.example)

FLASK_PORT = int(os.environ.get("FLASK_PORT", 5000))
FASTAPI_PORT = int(os.environ.get("FASTAPI_PORT", 8000))

# Injected into every template as `api_base_url`. Override via env var if the
# FastAPI backend runs on a different host/port (e.g. in Docker Compose).
API_BASE_URL = os.environ.get("API_BASE_URL", f"http://127.0.0.1:{FASTAPI_PORT}")

APP_NAME = "MoldGuard AI"
APP_TAGLINE = "Predictive Maintenance"
DEFAULT_MACHINE_ID = "IMM-240T-03"

# --- Groq LLM config, used by services/llm_client.py ---------------
# Set GROQ_API_KEY in your environment (never commit it):
#   export GROQ_API_KEY="gsk_..."
# If it's unset, the assistant and RAG answer-generation both fall back to
# the original extractive/templated behavior automatically -- nothing
# breaks, you just don't get LLM-composed answers.
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_BASE = os.environ.get("GROQ_API_BASE", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
LLM_ENABLED = bool(GROQ_API_KEY)
