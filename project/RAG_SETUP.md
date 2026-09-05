# RAG Setup

The project already contains a pre-built FAISS index at `rag/store/manuals.faiss` and chunk metadata at `rag/store/chunks.json`.

To rebuild the index after changing the built-in manuals:

```powershell
python -m rag.ingest
```

Start the backend:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Start the UI in a second terminal:

```powershell
python app.py
```

The browser UI is served at `http://127.0.0.1:5000` and talks to FastAPI at `http://127.0.0.1:8000`.
