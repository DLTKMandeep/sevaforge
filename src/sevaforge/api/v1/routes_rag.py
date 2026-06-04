"""
SevaForge API v1 — RAG Pipeline Service Routes

Multi-tenant RAG pipeline endpoints for document ingestion,
semantic search, and pipeline management.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.rag import (
    RAGPipeline,
    RAGConfig,
    Document,
    DocumentLoader,
    RAGEvaluator,
    EvalCase,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_pipelines: dict[str, RAGPipeline] = {}


def _get_pipeline(tenant_id: str = "default") -> RAGPipeline:
    if tenant_id not in _pipelines:
        config = RAGConfig(collection_name=f"tenant_{tenant_id}")
        _pipelines[tenant_id] = RAGPipeline(config)
        logger.info("RAG pipeline created for tenant '%s'", tenant_id)
    return _pipelines[tenant_id]


class IngestTextRequest(BaseModel):
    content: str = Field(..., min_length=1)
    source: str = Field("api")
    doc_type: str = Field("text")
    metadata: dict[str, Any] = Field(default_factory=dict)
    collection: str = Field("default")
    tenant_id: str = Field("default")


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    collection: str = Field("default")
    min_score: float = Field(0.0, ge=0.0, le=1.0)
    tenant_id: str = Field("default")
    filters: dict[str, Any] = Field(default_factory=dict)


@router.post("/rag/ingest")
async def ingest_text(body: IngestTextRequest) -> dict[str, Any]:
    start = time.time()
    pipeline = _get_pipeline(body.tenant_id)
    try:
        loader = DocumentLoader()
        doc = loader.load_text(content=body.content, metadata=body.metadata, source=body.source)
        doc.doc_type = body.doc_type
        original_collection = pipeline.config.collection_name
        if body.collection != "default":
            pipeline.config.collection_name = body.collection
        result = pipeline.ingest_document(doc)
        pipeline.config.collection_name = original_collection
        elapsed_ms = (time.time() - start) * 1000
        return {"status": "ok", "document_id": result.document_id, "chunks_created": result.chunks_created, "time_ms": round(elapsed_ms, 2)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


@router.post("/rag/query")
async def query_rag(body: QueryRequest) -> dict[str, Any]:
    start = time.time()
    pipeline = _get_pipeline(body.tenant_id)
    try:
        original_collection = pipeline.config.collection_name
        if body.collection != "default":
            pipeline.config.collection_name = body.collection
        result = pipeline.query(question=body.query, top_k=body.top_k, filters=body.filters if body.filters else None)
        pipeline.config.collection_name = original_collection
        filtered_chunks = []
        for chunk, score in zip(result.chunks, result.scores):
            if score >= body.min_score:
                filtered_chunks.append({"id": chunk.id, "content": chunk.content, "score": round(score, 4)})
        elapsed_ms = (time.time() - start) * 1000
        return {"query": body.query, "chunks": filtered_chunks, "total_results": len(filtered_chunks), "time_ms": round(elapsed_ms, 2)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Query failed: {exc}")


@router.get("/rag/collections")
async def list_collections(tenant_id: str = "default") -> dict[str, Any]:
    pipeline = _get_pipeline(tenant_id)
    collections = pipeline.vector_store.list_collections()
    return {"tenant_id": tenant_id, "total_collections": len(collections), "collections": collections}


@router.get("/rag/stats")
async def rag_stats() -> dict[str, Any]:
    tenant_stats = []
    for tenant_id, pipeline in _pipelines.items():
        stats = pipeline.get_stats()
        tenant_stats.append({"tenant_id": tenant_id, "config": stats["config"]})
    return {"total_tenants": len(_pipelines), "tenants": tenant_stats}
