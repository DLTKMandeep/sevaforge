"""
SevaForge Hybrid Search — US-044

Combines vector similarity search (dense) with BM25 keyword search (sparse)
using Reciprocal Rank Fusion (RRF) for robust retrieval.

Pipeline:
    Query → [Vector Search] + [BM25 Search] → RRF Fusion → Top-K Results

Reference: Cormack, Clarke & Butt (2009) — Reciprocal Rank Fusion
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class SearchMode(str, Enum):
    HYBRID = "hybrid"           # Vector + BM25 + RRF
    VECTOR = "vector"           # Dense embedding similarity only
    BM25 = "bm25"               # Sparse keyword only
    KEYWORD = "keyword"         # Simple substring match


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class Document:
    """A document in the search index."""
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    title: str = ""
    source: str = ""
    collection: str = "default"
    embedding: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content[:200] + ("..." if len(self.content) > 200 else ""),
            "source": self.source,
            "collection": self.collection,
            "has_embedding": len(self.embedding) > 0,
            "metadata": self.metadata,
        }


@dataclass
class SearchResult:
    """A single result from the search engine."""
    doc_id: str
    document: Document
    score: float = 0.0
    rank: int = 0
    mode: str = "hybrid"           # Which retriever produced this
    bm25_score: float = 0.0
    vector_score: float = 0.0
    rrf_score: float = 0.0
    highlights: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.document.title,
            "content_preview": self.document.content[:200],
            "source": self.document.source,
            "score": round(self.score, 4),
            "rank": self.rank,
            "mode": self.mode,
            "bm25_score": round(self.bm25_score, 4),
            "vector_score": round(self.vector_score, 4),
            "rrf_score": round(self.rrf_score, 4),
            "highlights": self.highlights,
        }


# ── BM25 Implementation ─────────────────────────────────────────────


class BM25Index:
    """
    Okapi BM25 ranking function.

    Parameters:
        k1: Term frequency saturation (default 1.5)
        b: Document length normalization (default 0.75)
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._docs: dict[str, list[str]] = {}      # doc_id → tokens
        self._doc_lengths: dict[str, int] = {}
        self._avg_dl: float = 0.0
        self._df: Counter = Counter()                # Document frequency
        self._n_docs: int = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer with lowercasing."""
        return re.findall(r'\b\w+\b', text.lower())

    def add_document(self, doc_id: str, text: str) -> None:
        """Index a document."""
        tokens = self._tokenize(text)
        self._docs[doc_id] = tokens
        self._doc_lengths[doc_id] = len(tokens)
        self._n_docs += 1

        # Update document frequencies
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self._df[token] += 1

        # Update average document length
        self._avg_dl = sum(self._doc_lengths.values()) / max(self._n_docs, 1)

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the index."""
        if doc_id not in self._docs:
            return
        tokens = self._docs[doc_id]
        unique_tokens = set(tokens)
        for token in unique_tokens:
            self._df[token] -= 1
            if self._df[token] <= 0:
                del self._df[token]
        del self._docs[doc_id]
        del self._doc_lengths[doc_id]
        self._n_docs -= 1
        self._avg_dl = sum(self._doc_lengths.values()) / max(self._n_docs, 1)

    def search(self, query: str, top_k: int = 10) -> list[tuple[str, float]]:
        """
        Score all documents against query using BM25.
        Returns list of (doc_id, score) sorted by score descending.
        """
        query_tokens = self._tokenize(query)
        scores: dict[str, float] = {}

        for doc_id, doc_tokens in self._docs.items():
            score = 0.0
            dl = self._doc_lengths[doc_id]
            tf_counter = Counter(doc_tokens)

            for qt in query_tokens:
                if qt not in self._df:
                    continue

                tf = tf_counter.get(qt, 0)
                df = self._df[qt]
                # IDF with smoothing
                idf = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1.0)
                # BM25 TF component
                tf_norm = (tf * (self.k1 + 1)) / (
                    tf + self.k1 * (1 - self.b + self.b * dl / max(self._avg_dl, 1))
                )
                score += idf * tf_norm

            if score > 0:
                scores[doc_id] = score

        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]


# ── Hybrid Search Engine ─────────────────────────────────────────────


class HybridSearchEngine:
    """
    Hybrid retrieval engine combining vector similarity and BM25.

    Uses Reciprocal Rank Fusion (RRF) to merge ranked lists:
        RRF(d) = sum(1 / (k + rank_i(d))) for each retriever i

    where k is a constant (default 60) that controls how much
    weight is given to items that appear high in individual lists.
    """

    def __init__(
        self,
        rrf_k: int = 60,
        default_top_k: int = 10,
        vector_weight: float = 0.5,
        bm25_weight: float = 0.5,
    ):
        self._documents: dict[str, Document] = {}
        self._collections: dict[str, set[str]] = defaultdict(set)
        self._bm25 = BM25Index()
        self._rrf_k = rrf_k
        self._default_top_k = default_top_k
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight
        self._stats = {
            "total_searches": 0,
            "vector_searches": 0,
            "bm25_searches": 0,
            "hybrid_searches": 0,
        }

    # ── Document Management ───────────────────────────────────────────

    def index_document(self, doc: Document) -> str:
        """Add a document to the search index."""
        self._documents[doc.doc_id] = doc
        self._collections[doc.collection].add(doc.doc_id)

        # Index in BM25
        text = f"{doc.title} {doc.content}"
        self._bm25.add_document(doc.doc_id, text)

        logger.debug("Indexed document '%s' in collection '%s'", doc.doc_id, doc.collection)
        return doc.doc_id

    def index_documents(self, docs: list[Document]) -> int:
        """Bulk index multiple documents."""
        for doc in docs:
            self.index_document(doc)
        return len(docs)

    def remove_document(self, doc_id: str) -> bool:
        """Remove a document from all indexes."""
        if doc_id not in self._documents:
            return False
        doc = self._documents[doc_id]
        self._collections[doc.collection].discard(doc_id)
        self._bm25.remove_document(doc_id)
        del self._documents[doc_id]
        return True

    def get_document(self, doc_id: str) -> Document | None:
        return self._documents.get(doc_id)

    def list_collections(self) -> dict[str, int]:
        """Return collection names with document counts."""
        return {name: len(ids) for name, ids in self._collections.items()}

    # ── Search ────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.HYBRID,
        collection: str | None = None,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """
        Execute a search query.

        Args:
            query: The search text
            mode: Retrieval strategy (hybrid, vector, bm25, keyword)
            collection: Limit to a specific collection
            top_k: Number of results to return
            query_embedding: Pre-computed query embedding (for vector/hybrid)
            filters: Metadata filters (key-value pairs that must match)
        """
        top_k = top_k or self._default_top_k
        self._stats["total_searches"] += 1

        # Get candidate doc IDs (collection filter)
        candidate_ids = self._get_candidates(collection)

        if mode == SearchMode.BM25:
            return self._bm25_search(query, candidate_ids, top_k)
        elif mode == SearchMode.VECTOR:
            return self._vector_search(query_embedding or [], candidate_ids, top_k)
        elif mode == SearchMode.KEYWORD:
            return self._keyword_search(query, candidate_ids, top_k)
        else:
            return self._hybrid_search(query, query_embedding, candidate_ids, top_k)

    def _get_candidates(self, collection: str | None) -> set[str] | None:
        """Return doc IDs for a collection, or None for all."""
        if collection:
            return self._collections.get(collection, set())
        return None

    def _bm25_search(
        self,
        query: str,
        candidates: set[str] | None,
        top_k: int,
    ) -> list[SearchResult]:
        """BM25 sparse retrieval."""
        self._stats["bm25_searches"] += 1
        raw_results = self._bm25.search(query, top_k=top_k * 2)

        results = []
        for rank, (doc_id, score) in enumerate(raw_results):
            if candidates and doc_id not in candidates:
                continue
            doc = self._documents.get(doc_id)
            if not doc:
                continue
            results.append(SearchResult(
                doc_id=doc_id,
                document=doc,
                score=score,
                rank=rank + 1,
                mode="bm25",
                bm25_score=score,
                highlights=self._extract_highlights(query, doc.content),
            ))
            if len(results) >= top_k:
                break

        return results

    def _vector_search(
        self,
        query_embedding: list[float],
        candidates: set[str] | None,
        top_k: int,
    ) -> list[SearchResult]:
        """Dense vector similarity search."""
        self._stats["vector_searches"] += 1
        if not query_embedding:
            return []

        scored: list[tuple[str, float]] = []
        target_ids = candidates or set(self._documents.keys())

        for doc_id in target_ids:
            doc = self._documents.get(doc_id)
            if not doc or not doc.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, doc.embedding)
            scored.append((doc_id, sim))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for rank, (doc_id, score) in enumerate(scored[:top_k]):
            doc = self._documents[doc_id]
            results.append(SearchResult(
                doc_id=doc_id,
                document=doc,
                score=score,
                rank=rank + 1,
                mode="vector",
                vector_score=score,
            ))

        return results

    def _keyword_search(
        self,
        query: str,
        candidates: set[str] | None,
        top_k: int,
    ) -> list[SearchResult]:
        """Simple substring keyword matching."""
        query_lower = query.lower()
        target_ids = candidates or set(self._documents.keys())
        results = []

        for doc_id in target_ids:
            doc = self._documents.get(doc_id)
            if not doc:
                continue
            content_lower = doc.content.lower()
            if query_lower in content_lower:
                # Score by match frequency
                count = content_lower.count(query_lower)
                results.append(SearchResult(
                    doc_id=doc_id,
                    document=doc,
                    score=float(count),
                    mode="keyword",
                    highlights=self._extract_highlights(query, doc.content),
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        for rank, result in enumerate(results[:top_k]):
            result.rank = rank + 1
        return results[:top_k]

    def _hybrid_search(
        self,
        query: str,
        query_embedding: list[float] | None,
        candidates: set[str] | None,
        top_k: int,
    ) -> list[SearchResult]:
        """
        Hybrid search with Reciprocal Rank Fusion.

        Merges BM25 and vector ranked lists using:
        RRF(d) = w_bm25/(k + rank_bm25(d)) + w_vec/(k + rank_vec(d))
        """
        self._stats["hybrid_searches"] += 1

        # Get ranked lists from each retriever
        bm25_results = self._bm25_search(query, candidates, top_k * 2)
        vector_results = self._vector_search(
            query_embedding or [], candidates, top_k * 2
        )

        # Build rank maps
        bm25_ranks: dict[str, int] = {
            r.doc_id: r.rank for r in bm25_results
        }
        vector_ranks: dict[str, int] = {
            r.doc_id: r.rank for r in vector_results
        }
        bm25_scores: dict[str, float] = {
            r.doc_id: r.bm25_score for r in bm25_results
        }
        vector_scores: dict[str, float] = {
            r.doc_id: r.vector_score for r in vector_results
        }

        # Compute RRF scores
        all_doc_ids = set(bm25_ranks.keys()) | set(vector_ranks.keys())
        rrf_scores: dict[str, float] = {}

        for doc_id in all_doc_ids:
            score = 0.0
            if doc_id in bm25_ranks:
                score += self._bm25_weight / (self._rrf_k + bm25_ranks[doc_id])
            if doc_id in vector_ranks:
                score += self._vector_weight / (self._rrf_k + vector_ranks[doc_id])
            rrf_scores[doc_id] = score

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

        results = []
        for rank, doc_id in enumerate(sorted_ids[:top_k]):
            doc = self._documents[doc_id]
            results.append(SearchResult(
                doc_id=doc_id,
                document=doc,
                score=rrf_scores[doc_id],
                rank=rank + 1,
                mode="hybrid",
                bm25_score=bm25_scores.get(doc_id, 0.0),
                vector_score=vector_scores.get(doc_id, 0.0),
                rrf_score=rrf_scores[doc_id],
                highlights=self._extract_highlights(query, doc.content),
            ))

        return results

    # ── Utilities ─────────────────────────────────────────────────────

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _extract_highlights(query: str, content: str, context_chars: int = 80) -> list[str]:
        """Extract text snippets around query term matches."""
        highlights = []
        query_lower = query.lower()
        content_lower = content.lower()
        terms = query_lower.split()

        for term in terms:
            idx = content_lower.find(term)
            if idx >= 0:
                start = max(0, idx - context_chars)
                end = min(len(content), idx + len(term) + context_chars)
                snippet = content[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                highlights.append(snippet)

        return highlights[:3]  # Max 3 highlights

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "total_documents": len(self._documents),
            "collections": self.list_collections(),
        }

    def reset(self) -> None:
        """Clear all indexes (for testing)."""
        self._documents.clear()
        self._collections.clear()
        self._bm25 = BM25Index()
        self._stats = {k: 0 for k in self._stats}
