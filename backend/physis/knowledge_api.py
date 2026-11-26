"""Read-only local literature API. Collection and destructive maintenance use the CLI."""
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request

from .knowledge_terms import concepts, norm


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/stats")
def stats(request: Request):
    return request.app.state.knowledge.stats()


@router.get("/documents")
def documents(request: Request, q: str = Query("", max_length=400), model: str | None = None,
              source: str | None = None, level: str | None = None):
    docs = request.app.state.knowledge.documents(model, source, level)
    if q.strip():
        labels = set(concepts(q))
        term = norm(q.strip())
        docs = [doc for doc in docs if labels.intersection(doc["concepts"]) or
                term in norm(" ".join((doc["id"], doc["title"], doc["book"], doc["author"], doc["publisher"])))]
    return {"items": docs}


@router.get("/documents/{doc_id}")
def document(doc_id: str, request: Request):
    store = request.app.state.knowledge
    item = store.document(doc_id)
    if not item:
        raise HTTPException(404, "자료를 찾을 수 없습니다.")
    return {**item, "related": store.related(doc_id)}


@router.get("/chunks/{chunk_id}")
def chunk(chunk_id: str, request: Request):
    item = request.app.state.knowledge.chunk(chunk_id)
    if not item:
        raise HTTPException(404, "인용 가능한 문단을 찾을 수 없습니다.")
    return item


@router.get("/search")
def search(request: Request, q: str = Query(min_length=1, max_length=2000),
           model: str | None = None, source: str | None = None, level: str | None = None,
           mode: Literal["lexical", "hybrid", "rrf"] = "hybrid", limit: int = Query(12, ge=1, le=50),
           embeddings: bool = False):
    items = request.app.state.knowledge.search(q, model, source, level, mode, limit, embeddings)
    return {"items": items, "mode": mode, "embeddings": False}

