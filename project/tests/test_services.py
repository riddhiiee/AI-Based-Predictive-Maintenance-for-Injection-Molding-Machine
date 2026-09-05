"""
Lightweight sanity checks for the services layer.

Predictions/explanations/assistant answers now come from the real trained
Gradient Boosting models (models/inference.py) and the real RAG pipeline
(rag/rag_service.py), so these checks assert shapes, ranges, and internal
consistency rather than fixed mock values -- the actual "current" prediction
depends on which mold/cycle the live-feed simulator lands on when the test
runs (see models/inference.py's rotation).

Run with:
    python3 tests/test_services.py

(from the project root)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import (  # noqa: E402
    prediction_service as pred,
    explain_service as explain,
    assistant_service as assistant,
    knowledge_base_service as rag,
    mock_history_service as history,
)

VALID_STATES = {"Healthy", "Warning", "Degrading", "Critical"}
VALID_SEVERITIES = {"low", "medium", "high"}

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  OK   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}")


def main():
    print("subsystems overview")
    overview = pred.get_subsystems_overview()
    check("has machine block", "machine" in overview)
    check("has 4 subsystems", len(overview["subsystems"]) == 4)
    check("overall_health in 0-100", 0 <= overview["machine"]["overall_health"] <= 100)
    check("every subsystem has a valid status", all(s["status"] in {"healthy", "warning", "degrading", "critical"} for s in overview["subsystems"]))
    check("every subsystem has real params", all(len(s["params"]) > 0 for s in overview["subsystems"]))

    print("predictions")
    all_preds = pred.get_all_predictions()
    check("4 predictions", len(all_preds["predictions"]) == 4)
    check("every prediction has a valid state", all(p["predicted_state"] in VALID_STATES for p in all_preds["predictions"]))
    check("every prediction has 0-1 confidence", all(0 <= p["confidence"] <= 1 for p in all_preds["predictions"]))
    check("every prediction has top_features", all(len(p["top_features"]) > 0 for p in all_preds["predictions"]))
    clamp = pred.get_prediction("clamp")
    check("clamp prediction found", clamp is not None)
    check("clamp prediction has a valid severity", clamp["severity"] in VALID_SEVERITIES)
    check("unknown subsystem returns None", pred.get_prediction("nonexistent") is None)

    print("maintenance needs + trends + alerts")
    check("trends has health_trend_7d", "health_trend_7d" in pred.get_trends())
    check("health trend has matching labels/series lengths", (lambda t: len(t["labels"]) == len(t["series"]))(pred.get_trends()["health_trend_7d"]))
    alerts = pred.get_alerts()["alerts"]
    check("alerts (if any) all have valid severity", all(a["severity"] in VALID_SEVERITIES for a in alerts))
    needs = pred.get_maintenance_needs()["items"]
    check("maintenance needs (if any) all have valid severity", all(i["severity"] in VALID_SEVERITIES for i in needs))

    print("explain service")
    exp = explain.explain_subsystem("heater")
    check("heater explanation found", exp is not None)
    check("explanation has top_features", len(exp["top_features"]) > 0)
    check("explanation method is shap", exp["explanation_method"] == "shap")
    check("bad subsystem returns None", explain.explain_subsystem("bogus") is None)

    print("assistant service")
    resp = assistant.ask_assistant("Why is the Clamp system flagged?", subsystem_hint="clamp")
    check("assistant honors subsystem_hint", resp["subsystem"] == "clamp")
    check("assistant response has maintenance_actions", len(resp["maintenance_actions"]) > 0)
    check("assistant response has a valid state", resp["predicted_state"] in VALID_STATES)
    fallback = assistant.ask_assistant("asdkfjasldkfj nonsense query")
    check("assistant fallback still returns a subsystem", fallback["subsystem"] in pred.VALID_SUBSYSTEMS)
    check("assistant fallback has explanation_summary", "explanation_summary" in fallback)
    prompts = assistant.get_suggested_prompts()
    check("suggested prompts exist", len(prompts) > 0)

    print("rag service")
    docs = rag.list_documents()
    check("documents exist", len(docs["documents"]) > 0)
    check("seed documents are indexed with real chunk counts", any(d["status"] == "indexed" and d["chunks_indexed"] > 0 for d in docs["documents"]))
    count_before = len(docs["documents"])
    new_doc = rag.upload_document("test_manual.pdf", "clamp", "SOP")
    check("upload adds a document", new_doc["status"] == "queued")
    docs_after = rag.list_documents()
    check("document count increased", len(docs_after["documents"]) == count_before + 1)
    query_result = rag.query_knowledge_base("clamp force decline tie-bar")
    check("query returns chunks list", "retrieved_manual_chunks" in query_result)
    check("query on a real topic returns at least one real chunk", len(query_result["retrieved_manual_chunks"]) > 0)
    check("retrieved chunk is not the old placeholder text", "Once indexed" not in (query_result["retrieved_manual_chunks"] or [{"snippet": ""}])[0]["snippet"])

    print("history service")
    hist = history.get_history()
    check("history events exist", hist["count"] > 0)
    hist_filtered = history.get_history(subsystem="heater")
    check("history filter by subsystem works", all(e["subsystem"] == "heater" for e in hist_filtered["events"]))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
