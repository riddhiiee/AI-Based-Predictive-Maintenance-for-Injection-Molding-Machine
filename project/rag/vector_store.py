from __future__ import annotations
import json, threading
from pathlib import Path
from typing import Any
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

ROOT=Path(__file__).resolve().parents[1]
STORE=ROOT/"rag"/"store"
STORE.mkdir(parents=True,exist_ok=True)
INDEX_PATH=STORE/"manuals.faiss"
META_PATH=STORE/"chunks.json"
MODEL_NAME="sentence-transformers/all-MiniLM-L6-v2"
_lock=threading.Lock(); _model=None; _index=None; _chunks=[]

def _encoder():
    global _model
    if _model is None: _model=SentenceTransformer(MODEL_NAME)
    return _model

def rebuild(chunks:list[dict[str,Any]]):
    global _index,_chunks
    texts=[c["text"] for c in chunks]
    if not texts: return
    vec=_encoder().encode(texts,normalize_embeddings=True,show_progress_bar=False).astype("float32")
    idx=faiss.IndexFlatIP(vec.shape[1]); idx.add(vec)
    faiss.write_index(idx,str(INDEX_PATH)); META_PATH.write_text(json.dumps(chunks,ensure_ascii=False),encoding="utf-8")
    _index,_chunks=idx,chunks

def _load():
    global _index,_chunks
    if _index is not None:return
    with _lock:
        if INDEX_PATH.exists() and META_PATH.exists():
            _index=faiss.read_index(str(INDEX_PATH)); _chunks=json.loads(META_PATH.read_text(encoding="utf-8"))
        else:
            from rag.ingest import build_default_index
            build_default_index()

def all_chunks(): _load(); return _chunks

def search(query:str,top_k:int=5,subsystem_filter:str|None=None):
    _load()
    if not query.strip() or not _chunks:return []
    q=_encoder().encode([query],normalize_embeddings=True,show_progress_bar=False).astype("float32")
    scores,ids=_index.search(q,min(max(top_k*5,20),len(_chunks)))
    out=[]
    for score,i in zip(scores[0],ids[0]):
        if i<0:continue
        c=dict(_chunks[i])
        if subsystem_filter and c.get("subsystem") not in (subsystem_filter,"general"):continue
        c["relevance_score"]=round(float(score),4); out.append(c)
        if len(out)>=top_k:break
    return out
