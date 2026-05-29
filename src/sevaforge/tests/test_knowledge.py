"""
Tests for Knowledge Layer (Layer 7): Hybrid Search, Knowledge Graph, Reranker.
"""

import pytest

from sevaforge.knowledge.hybrid_search import (
    BM25Index,
    Document,
    HybridSearchEngine,
    SearchMode,
)
from sevaforge.knowledge.knowledge_graph import (
    Entity,
    EntityType,
    KnowledgeGraph,
    Relationship,
    RelationshipType,
)
from sevaforge.knowledge.reranker import CrossEncoderReranker, RerankerConfig


# ══════════════════════════════════════════════════════════════════════
# BM25 Index Tests
# ══════════════════════════════════════════════════════════════════════


class TestBM25Index:
    def test_basic_search(self):
        idx = BM25Index()
        idx.add_document("d1", "Python is a programming language")
        idx.add_document("d2", "Java is also a programming language")
        idx.add_document("d3", "Cooking recipes for beginners")
        results = idx.search("Python programming")
        assert len(results) > 0
        assert results[0][0] == "d1"  # Python doc should rank first

    def test_empty_search(self):
        idx = BM25Index()
        results = idx.search("anything")
        assert len(results) == 0

    def test_remove_document(self):
        idx = BM25Index()
        idx.add_document("d1", "test document")
        idx.remove_document("d1")
        assert len(idx.search("test")) == 0


# ══════════════════════════════════════════════════════════════════════
# Hybrid Search Engine Tests
# ══════════════════════════════════════════════════════════════════════


class TestHybridSearch:
    def _seed_engine(self) -> HybridSearchEngine:
        engine = HybridSearchEngine()
        engine.index_document(Document(
            doc_id="tf-1", title="Terraform Basics",
            content="Terraform is an infrastructure as code tool by HashiCorp for provisioning cloud resources",
            collection="terraform", embedding=[1.0, 0.0, 0.0],
        ))
        engine.index_document(Document(
            doc_id="tf-2", title="Terraform Modules",
            content="Terraform modules encapsulate groups of resources for reuse across configurations",
            collection="terraform", embedding=[0.9, 0.1, 0.0],
        ))
        engine.index_document(Document(
            doc_id="k8s-1", title="Kubernetes Deployment",
            content="Kubernetes orchestrates containerized applications across clusters of machines",
            collection="kubernetes", embedding=[0.0, 1.0, 0.0],
        ))
        return engine

    def test_bm25_search(self):
        engine = self._seed_engine()
        results = engine.search("Terraform infrastructure", mode=SearchMode.BM25)
        assert len(results) > 0
        assert results[0].doc_id == "tf-1"

    def test_vector_search(self):
        engine = self._seed_engine()
        results = engine.search(
            "similar to terraform",
            mode=SearchMode.VECTOR,
            query_embedding=[0.95, 0.05, 0.0],
        )
        assert len(results) > 0
        assert results[0].doc_id == "tf-1"

    def test_hybrid_search(self):
        engine = self._seed_engine()
        results = engine.search(
            "Terraform cloud resources",
            mode=SearchMode.HYBRID,
            query_embedding=[0.9, 0.0, 0.0],
        )
        assert len(results) > 0
        # Terraform docs should rank higher than Kubernetes
        terraform_ids = {r.doc_id for r in results if r.doc_id.startswith("tf-")}
        assert len(terraform_ids) > 0

    def test_keyword_search(self):
        engine = self._seed_engine()
        results = engine.search("Kubernetes", mode=SearchMode.KEYWORD)
        assert len(results) == 1
        assert results[0].doc_id == "k8s-1"

    def test_collection_filter(self):
        engine = self._seed_engine()
        results = engine.search("resources", mode=SearchMode.BM25, collection="terraform")
        for r in results:
            assert r.document.collection == "terraform"

    def test_list_collections(self):
        engine = self._seed_engine()
        collections = engine.list_collections()
        assert "terraform" in collections
        assert collections["terraform"] == 2
        assert collections["kubernetes"] == 1

    def test_remove_document(self):
        engine = self._seed_engine()
        assert engine.remove_document("tf-1") is True
        assert engine.remove_document("nonexistent") is False
        assert engine.get_document("tf-1") is None

    def test_highlights(self):
        engine = self._seed_engine()
        results = engine.search("Terraform", mode=SearchMode.BM25)
        assert len(results) > 0
        # Should have highlights
        assert any(r.highlights for r in results)

    def test_stats(self):
        engine = self._seed_engine()
        engine.search("test", mode=SearchMode.BM25)
        stats = engine.stats()
        assert stats["total_documents"] == 3
        assert stats["bm25_searches"] == 1


# ══════════════════════════════════════════════════════════════════════
# Knowledge Graph Tests
# ══════════════════════════════════════════════════════════════════════


class TestKnowledgeGraph:
    def _seed_graph(self) -> KnowledgeGraph:
        kg = KnowledgeGraph()
        e1 = Entity(entity_id="e1", name="PromptEngine", entity_type=EntityType.SERVICE)
        e2 = Entity(entity_id="e2", name="SemanticCache", entity_type=EntityType.SERVICE)
        e3 = Entity(entity_id="e3", name="AIGateway", entity_type=EntityType.SERVICE)
        e4 = Entity(entity_id="e4", name="PostgreSQL", entity_type=EntityType.DATABASE)
        kg.add_entity(e1)
        kg.add_entity(e2)
        kg.add_entity(e3)
        kg.add_entity(e4)
        kg.add_relationship(Relationship(
            source_id="e3", target_id="e1",
            relationship_type=RelationshipType.DEPENDS_ON,
        ))
        kg.add_relationship(Relationship(
            source_id="e3", target_id="e2",
            relationship_type=RelationshipType.DEPENDS_ON,
        ))
        kg.add_relationship(Relationship(
            source_id="e2", target_id="e4",
            relationship_type=RelationshipType.DEPENDS_ON,
        ))
        return kg

    def test_add_entity(self):
        kg = KnowledgeGraph()
        eid = kg.add_entity(Entity(name="TestService", entity_type=EntityType.SERVICE))
        assert kg.get_entity(eid) is not None

    def test_find_entity_by_name(self):
        kg = self._seed_graph()
        entity = kg.find_entity("PromptEngine")
        assert entity is not None
        assert entity.entity_id == "e1"

    def test_find_entity_case_insensitive(self):
        kg = self._seed_graph()
        entity = kg.find_entity("promptengine")
        assert entity is not None

    def test_remove_entity_cascades(self):
        kg = self._seed_graph()
        assert kg.remove_entity("e2") is True
        # Relationships involving e2 should be gone
        rels = kg.get_relationships("e3")
        assert all(r.target_id != "e2" for r in rels)

    def test_add_relationship(self):
        kg = self._seed_graph()
        rels = kg.get_relationships("e3", direction="out")
        assert len(rels) == 2  # AIGateway depends on PromptEngine and SemanticCache

    def test_relationship_invalid_entity(self):
        kg = KnowledgeGraph()
        kg.add_entity(Entity(entity_id="e1", name="A"))
        with pytest.raises(ValueError, match="not found"):
            kg.add_relationship(Relationship(source_id="e1", target_id="nonexistent"))

    def test_neighbors_bfs(self):
        kg = self._seed_graph()
        result = kg.get_neighbors("e3", depth=1)
        assert len(result.entities) == 3  # e3 + e1 + e2
        result_deep = kg.get_neighbors("e3", depth=2)
        assert len(result_deep.entities) == 4  # includes e4

    def test_shortest_path(self):
        kg = self._seed_graph()
        path = kg.shortest_path("e3", "e4")
        assert path is not None
        assert path[0] == "e3"
        assert path[-1] == "e4"
        assert len(path) == 3  # e3 → e2 → e4

    def test_shortest_path_no_route(self):
        kg = KnowledgeGraph()
        kg.add_entity(Entity(entity_id="a", name="A"))
        kg.add_entity(Entity(entity_id="b", name="B"))
        assert kg.shortest_path("a", "b") is None

    def test_search_entities(self):
        kg = self._seed_graph()
        results = kg.search_entities("Cache")
        assert len(results) == 1
        assert results[0].name == "SemanticCache"

    def test_list_entities_by_type(self):
        kg = self._seed_graph()
        services = kg.list_entities(entity_type=EntityType.SERVICE)
        assert len(services) == 3
        databases = kg.list_entities(entity_type=EntityType.DATABASE)
        assert len(databases) == 1

    def test_entity_extraction(self):
        kg = KnowledgeGraph()
        text = "The PromptEngine and SemanticCache are used by PostgreSQL and Redis for AIGateway"
        entities = kg.extract_entities(text)
        names = {e.name for e in entities}
        assert "PromptEngine" in names
        assert "SemanticCache" in names
        assert "PostgreSQL" in names
        assert "Redis" in names

    def test_stats(self):
        kg = self._seed_graph()
        stats = kg.stats()
        assert stats["total_entities"] == 4
        assert stats["total_relationships"] == 3


# ══════════════════════════════════════════════════════════════════════
# Reranker Tests
# ══════════════════════════════════════════════════════════════════════


class TestReranker:
    def _candidates(self) -> list[dict]:
        return [
            {"doc_id": "d1", "content": "Python is a programming language used for web development", "title": "Python Overview", "score": 0.8, "rank": 1},
            {"doc_id": "d2", "content": "Cooking recipes for Italian pasta dishes", "title": "Pasta Recipes", "score": 0.7, "rank": 2},
            {"doc_id": "d3", "content": "Python web frameworks like Django and Flask", "title": "Python Web Frameworks", "score": 0.6, "rank": 3},
        ]

    def test_basic_rerank(self):
        reranker = CrossEncoderReranker()
        results = reranker.rerank("Python web development", self._candidates())
        assert len(results) > 0
        # Python-related docs should score higher than cooking
        python_docs = [r for r in results if "Python" in r.title]
        cooking_docs = [r for r in results if "Pasta" in r.title]
        if python_docs and cooking_docs:
            assert python_docs[0].rerank_score >= cooking_docs[0].rerank_score

    def test_rerank_assigns_ranks(self):
        reranker = CrossEncoderReranker()
        results = reranker.rerank("Python programming", self._candidates())
        ranks = [r.final_rank for r in results]
        assert ranks == sorted(ranks)

    def test_rerank_top_k(self):
        reranker = CrossEncoderReranker()
        results = reranker.rerank("test", self._candidates(), top_k=2)
        assert len(results) <= 2

    def test_rerank_empty_candidates(self):
        reranker = CrossEncoderReranker()
        results = reranker.rerank("test", [])
        assert len(results) == 0

    def test_rerank_with_diversity(self):
        reranker = CrossEncoderReranker()
        results = reranker.rerank_with_diversity(
            "Python web development",
            self._candidates(),
            diversity_weight=0.3,
        )
        assert len(results) > 0

    def test_custom_scorer(self):
        reranker = CrossEncoderReranker()
        # Custom scorer that always returns 0.5
        reranker.set_scorer(lambda q, d, t: 0.5)
        results = reranker.rerank("test", self._candidates())
        for r in results:
            assert abs(r.rerank_score - 1.0) < 0.01  # Normalized from 0.5/0.5

    def test_stats(self):
        reranker = CrossEncoderReranker()
        reranker.rerank("test", self._candidates())
        stats = reranker.stats()
        assert stats["total_reranks"] == 1
        assert stats["total_candidates_scored"] == 3
