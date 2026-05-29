"""
SevaForge API — Knowledge Layer Endpoints (Layer 7)
Hybrid search, knowledge graph operations, and reranking.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sevaforge.knowledge.hybrid_search import Document, HybridSearchEngine, SearchMode
from sevaforge.knowledge.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relationship,
    RelationshipType,
)
from sevaforge.knowledge.reranker import CrossEncoderReranker

router = APIRouter()

# ── Shared instances ─────────────────────────────────────────────────

_search_engine: HybridSearchEngine | None = None
_knowledge_graph: KnowledgeGraph | None = None
_reranker: CrossEncoderReranker | None = None


def get_search_engine() -> HybridSearchEngine:
    global _search_engine
    if _search_engine is None:
        _search_engine = HybridSearchEngine()
    return _search_engine


def get_knowledge_graph() -> KnowledgeGraph:
    global _knowledge_graph
    if _knowledge_graph is None:
        _knowledge_graph = KnowledgeGraph()
    return _knowledge_graph


def get_reranker() -> CrossEncoderReranker:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoderReranker()
    return _reranker


# ── Request Models ───────────────────────────────────────────────────


class IndexDocumentRequest(BaseModel):
    title: str = ""
    content: str
    source: str = ""
    collection: str = "default"
    embedding: list[float] = []
    metadata: dict[str, Any] = {}


class SearchRequest(BaseModel):
    query: str
    mode: str = "hybrid"
    collection: str | None = None
    top_k: int = 10
    query_embedding: list[float] = []


class AddEntityRequest(BaseModel):
    name: str
    entity_type: str = "concept"
    description: str = ""
    properties: dict[str, Any] = {}
    aliases: list[str] = []


class AddRelationshipRequest(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str = "related_to"
    weight: float = 1.0
    properties: dict[str, Any] = {}


class RerankRequest(BaseModel):
    query: str
    candidates: list[dict[str, Any]]
    top_k: int = 10


class ExtractEntitiesRequest(BaseModel):
    text: str
    source_doc_id: str = ""


# ══════════════════════════════════════════════════════════════════════
# Hybrid Search Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/search/index")
async def index_document(req: IndexDocumentRequest) -> dict:
    """Index a document for search."""
    engine = get_search_engine()
    doc = Document(
        title=req.title,
        content=req.content,
        source=req.source,
        collection=req.collection,
        embedding=req.embedding,
        metadata=req.metadata,
    )
    doc_id = engine.index_document(doc)
    return {"indexed": True, "doc_id": doc_id, "collection": req.collection}


@router.post("/search/query")
async def search_documents(req: SearchRequest) -> dict:
    """Execute a search query."""
    engine = get_search_engine()
    results = engine.search(
        query=req.query,
        mode=SearchMode(req.mode),
        collection=req.collection,
        top_k=req.top_k,
        query_embedding=req.query_embedding or None,
    )
    return {
        "query": req.query,
        "mode": req.mode,
        "total_results": len(results),
        "results": [r.to_dict() for r in results],
    }


@router.get("/search/collections")
async def list_collections() -> dict:
    """List all search collections with document counts."""
    return get_search_engine().list_collections()


@router.delete("/search/documents/{doc_id}")
async def remove_document(doc_id: str) -> dict:
    engine = get_search_engine()
    if not engine.remove_document(doc_id):
        raise HTTPException(404, f"Document '{doc_id}' not found")
    return {"removed": True, "doc_id": doc_id}


@router.get("/search/stats")
async def search_stats() -> dict:
    return get_search_engine().stats()


# ══════════════════════════════════════════════════════════════════════
# Knowledge Graph Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/graph/entities")
async def add_entity(req: AddEntityRequest) -> dict:
    """Add an entity to the knowledge graph."""
    kg = get_knowledge_graph()
    entity = Entity(
        name=req.name,
        entity_type=EntityType(req.entity_type),
        description=req.description,
        properties=req.properties,
        aliases=req.aliases,
    )
    eid = kg.add_entity(entity)
    return {"entity_id": eid, "name": req.name, "type": req.entity_type}


@router.get("/graph/entities")
async def list_entities(entity_type: str | None = None, limit: int = 100) -> list[dict]:
    kg = get_knowledge_graph()
    etype = EntityType(entity_type) if entity_type else None
    entities = kg.list_entities(entity_type=etype, limit=limit)
    return [e.to_dict() for e in entities]


@router.get("/graph/entities/{entity_id}")
async def get_entity(entity_id: str) -> dict:
    kg = get_knowledge_graph()
    entity = kg.get_entity(entity_id)
    if not entity:
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return entity.to_dict()


@router.get("/graph/entities/search/{query}")
async def search_entities(query: str, limit: int = 20) -> list[dict]:
    kg = get_knowledge_graph()
    results = kg.search_entities(query, limit=limit)
    return [e.to_dict() for e in results]


@router.delete("/graph/entities/{entity_id}")
async def remove_entity(entity_id: str) -> dict:
    kg = get_knowledge_graph()
    if not kg.remove_entity(entity_id):
        raise HTTPException(404, f"Entity '{entity_id}' not found")
    return {"removed": True, "entity_id": entity_id}


@router.post("/graph/relationships")
async def add_relationship(req: AddRelationshipRequest) -> dict:
    """Add a relationship between two entities."""
    kg = get_knowledge_graph()
    rel = Relationship(
        source_id=req.source_id,
        target_id=req.target_id,
        relationship_type=RelationshipType(req.relationship_type),
        weight=req.weight,
        properties=req.properties,
    )
    try:
        rid = kg.add_relationship(rel)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"relationship_id": rid, "type": req.relationship_type}


@router.get("/graph/entities/{entity_id}/neighbors")
async def get_neighbors(entity_id: str, depth: int = 1) -> dict:
    """Get neighbors of an entity up to a certain depth."""
    kg = get_knowledge_graph()
    result = kg.get_neighbors(entity_id, depth=depth)
    return result.to_dict()


@router.get("/graph/path/{source_id}/{target_id}")
async def find_path(source_id: str, target_id: str) -> dict:
    """Find shortest path between two entities."""
    kg = get_knowledge_graph()
    path = kg.shortest_path(source_id, target_id)
    if path is None:
        raise HTTPException(404, "No path found between entities")
    return {
        "source": source_id,
        "target": target_id,
        "path": path,
        "length": len(path) - 1,
    }


@router.post("/graph/extract")
async def extract_entities_from_text(req: ExtractEntitiesRequest) -> dict:
    """Extract entities from text using rule-based extraction."""
    kg = get_knowledge_graph()
    entities = kg.extract_entities(req.text, source_doc_id=req.source_doc_id)
    return {
        "extracted": len(entities),
        "entities": [e.to_dict() for e in entities],
    }


@router.get("/graph/stats")
async def graph_stats() -> dict:
    return get_knowledge_graph().stats()


# ══════════════════════════════════════════════════════════════════════
# Reranker Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/rerank")
async def rerank_results(req: RerankRequest) -> dict:
    """Rerank search results using cross-encoder scoring."""
    reranker = get_reranker()
    results = reranker.rerank(req.query, req.candidates, top_k=req.top_k)
    return {
        "query": req.query,
        "total_reranked": len(results),
        "results": [r.to_dict() for r in results],
    }


@router.get("/rerank/stats")
async def reranker_stats() -> dict:
    return get_reranker().stats()
