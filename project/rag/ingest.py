from __future__ import annotations
import json,re
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from rag.vector_store import rebuild
ROOT=Path(__file__).resolve().parents[1]; MANUALS=ROOT/"knowledge_base"/"manuals"

def _chunk(text,target=180,overlap=35):
    words=text.split(); out=[]; step=max(1,target-overlap)
    for i in range(0,len(words),step):
        part=" ".join(words[i:i+target]).strip()
        if len(part.split())>=30: out.append(part)
        if i+target>=len(words): break
    return out

def _pdf_chunks(path):
    reader=PdfReader(str(path)); rows=[]
    for page_no,page in enumerate(reader.pages,1):
        text=re.sub(r"\s+"," ",(page.extract_text() or "")).strip()
        for n,part in enumerate(_chunk(text),1):
            rows.append({"chunk_id":f"{path.stem}-p{page_no}-c{n}","document_id":path.stem,"document_title":path.stem.replace("_"," ").title(),"source":str(path.relative_to(ROOT)),"page":page_no,"subsystem":"general","text":part})
    return rows

def _url_chunks(item):
    try:
        r=requests.get(item["url"],timeout=15,headers={"User-Agent":"Mozilla/5.0"}); r.raise_for_status()
        soup=BeautifulSoup(r.text,"html.parser");
        for x in soup(["script","style","nav","footer"]): x.decompose()
        text=re.sub(r"\s+"," ",soup.get_text(" ",strip=True))
        return [{"chunk_id":f"{item['id']}-c{n}","document_id":item["id"],"document_title":item["title"],"source":item["url"],"page":None,"subsystem":"general","text":part} for n,part in enumerate(_chunk(text),1)]
    except Exception as e:
        print(f"Skipping URL source {item['url']}: {e}"); return []

def build_default_index():
    chunks=[]
    for p in sorted(MANUALS.glob("*.pdf")): chunks.extend(_pdf_chunks(p))
    cfg=json.loads((ROOT/"knowledge_base"/"sources.json").read_text(encoding="utf-8"))
    for item in cfg.get("url_sources",[]): chunks.extend(_url_chunks(item))
    rebuild(chunks); print(f"Indexed {len(chunks)} manual chunks")
    return len(chunks)
if __name__=="__main__": build_default_index()
