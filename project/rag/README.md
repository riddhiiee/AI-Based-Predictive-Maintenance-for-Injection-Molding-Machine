# rag/ — real RAG pipeline

This is no longer a placeholder — real retrieval is running here.

```
rag/
  content.py         authored source text for the 5 knowledge-base manuals (no real
                      manual PDFs exist anywhere in this project — see note below)
  chunking.py         splits each document into chunks along its section boundaries
  vector_store.py      in-memory TF-IDF index + cosine-similarity search
  rag_service.py       public functions: ingest_document, run_semantic_search,
                      generate_grounded_answer
```

## Design decisions worth knowing

- **No real manual PDFs exist.** `mock_data/manuals.json` only ever had
  document titles/metadata. `rag/content.py` was authored (matching the
  actual failure modes the trained models key on — see
  `models/preprocessing.py: TARGET_BASE_COLS`) so retrieval has real,
  topical text to chunk and search instead of the old placeholder
  "once indexed, a real passage will be retrieved here" stand-in.
- **TF-IDF, not neural embeddings.** No LLM/embedding API key is configured
  anywhere in this project, so `vector_store.py` uses scikit-learn's
  `TfidfVectorizer` + cosine similarity — real lexical/semantic-ish
  retrieval, fully offline, no cost.
- **Extractive answers, not an LLM call.** `generate_grounded_answer()`
  composes its answer from the actual retrieved passage text (with
  citations) rather than paraphrasing through an LLM. It's still
  genuinely "retrieval-augmented" — the text is real, not canned — it just
  doesn't run a generative model over it. Swap in a real LLM call there if
  an API key becomes available later; the function signature doesn't need
  to change.

## Where this plugs in

- `services/knowledge_base_service.py` — document listing/upload (backed by
  an in-memory list, same limitation as before) + delegates search/answer
  generation here.
- `services/assistant_service.py` — the AI Assistant's chat orchestration
  calls `run_semantic_search` + `generate_grounded_answer` alongside a real
  model prediction (`models/inference.py`) to produce one grounded answer.
