"""
Flask UI server for the AI-Powered Predictive Maintenance System.

This process only serves templates, static assets, and page-level
frontend interactions. All machine/prediction/assistant/RAG data is
fetched client-side from the FastAPI backend (see api/main.py) via
static/js/api.js.

Run with:
    python3 app.py
(or: flask --app app run --port 5000)

The FastAPI backend must be running separately for the pages to load
live model/RAG data — see README.md for the two-process run instructions.
"""
from datetime import datetime

from flask import Flask, render_template

import config

app = Flask(__name__)


def base_context(active_page: str) -> dict:
    """Common template context shared by every page."""
    return {
        "active_page": active_page,
        "api_base_url": config.API_BASE_URL,
        "app_name": config.APP_NAME,
        "app_tagline": config.APP_TAGLINE,
        "machine_id": config.DEFAULT_MACHINE_ID,
        "now": datetime.now(),
    }


@app.route("/")
def index():
    return render_template("dashboard.html", **base_context("dashboard"))


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", **base_context("dashboard"))


@app.route("/predictions")
def predictions():
    return render_template("predictions.html", **base_context("predictions"))


@app.route("/assistant")
def assistant():
    return render_template("assistant.html", **base_context("assistant"))

@app.route("/history")
def history():
    return render_template(
        "history.html",
        **base_context("history")
    )




if __name__ == "__main__":
    app.run(host="127.0.0.1", port=config.FLASK_PORT, debug=True, use_reloader=False)
