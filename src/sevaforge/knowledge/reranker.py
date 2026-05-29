"""
SevaForge Cross-Encoder Reranker — US-046

Second-stage relevance scoring that re-evaluates first-stage retrieval
results using a cross-encoder model for more accurate ranking.

Pipeline:
    First-stage results (BM25/Vector/Hybrid)
    → Cross-Encoder scoring (query, doc) pairs
    → Re-sorted results with calibrated scores
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────


@dataclass
class RerankerConfig:
    """Configuration for the cross-encoder reranker."""
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    max_candidates: int = 100      # Max docs to rerank per query
    top_k: int = 10                 # Final results to return
    min_score: float = 0.0          # Minimum score threshold
    batch_size: int = 32            # Scoring batch size
    normalize_scores: bool = True   # Normalize to [0, 1]
    use_builtin: bool = True        # Use built-in scorer (no external model)


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class RerankedResult:
    """A reranked search result with cross-encoder score."""
    doc_id: str
    original_rank: int
    original_score: float
    rerank_score: float = 0.0
    final_rank: int = 0
    rank_change: int = 0           # Positive = moved up, negative = moved down
    content_preview: str = ""
    title: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content_preview": self.content_preview,
            "source": self.source,
            "original_rank": self.original_rank,
            "original_score": round(self.original_score, 4),
            "rerank_score": round(self.rerank_score, 4),
            "final_rank": self.final_rank,
            "rank_change": self.rank_change,
        }


# ── Cross-Encoder Scorer ─────────────────────────────────────────────


class BuiltinScorer:
    """
    Built-in relevance scorer using lexical overlap features.

    When a real cross-encoder model is not available, this provides
    a reasonable approximation using:
    - Exact match ratio
    - Term overlap (Jaccard)
    - Bigram overlap
    - Query coverage
    - Title bonus
    """

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r'\b\w+\b', text.lower())

    @staticmethod
    def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
        return {(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)}

    def score(self, query: str, document: str, title: str = "") -> float:
        """
        Score a (query, document) pair.
        Returns a float in [0, 1].
        """
        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(document)
        t_tokens = self._tokenize(title) if title else []

        if not q_tokens or not d_tokens:
            return 0.0

        q_set = set(q_tokens)
        d_set = set(d_tokens)

        # 1. Term overlap (Jaccard similarity)
        intersection = q_set & d_set
        union = q_set | d_set
        jaccard = len(intersection) / len(union) if union else 0.0

        # 2. Query coverage — what fraction of query terms appear in doc
        coverage = len(intersection) / len(q_set) if q_set else 0.0

        # 3. Bigram overlap
        q_bigrams = self._bigrams(q_tokens)
        d_bigrams = self._bigrams(d_tokens)
        bigram_overlap = 0.0
        if q_bigrams:
            bigram_overlap = len(q_bigrams & d_bigrams) / len(q_bigrams)

        # 4. Title match bonus
        title_bonus = 0.0
        if t_tokens:
            t_set = set(t_tokens)
            title_bonus = len(q_set & t_set) / len(q_set) if q_set else 0.0

        # 5. Length penalty — very short or very long docs penalized
        doc_len = len(d_tokens)
        length_factor = 1.0
        if doc_len < 10:
            length_factor = doc_len / 10.0
        elif doc_len > 1000:
            length_factor = max(0.7, 1000.0 / doc_len)

        # Weighted combination
        score = (
            0.25 * jaccard
            + 0.30 * coverage
            + 0.20 * bigram_overlap
            + 0.15 * title_bonus
            + 0.10 * length_factor
        )

        return min(1.0, max(0.0, score))


# ── Cross-Encoder Reranker ───────────────────────────────────────────


class CrossEncoderReranker:
    """
    Two-stage reranking pipeline.

    Takes first-stage retrieval results and re-scores them using
    a cross-encoder model (or built-in fallback), producing a
    more accurate final ranking.

    Usage:
        reranker = CrossEncoderReranker()
        results = reranker.rerank(query, candidates)
    """

    def __init__(self, config: RerankerConfig | None = None):
        self.config = config or RerankerConfig()
        self._scorer = BuiltinScorer()
        self._custom_scorer: Callable[[str, str, str], float] | None = None
        self._stats = {
            "total_reranks": 0,
            "total_candidates_scored": 0,
            "avg_rank_change": 0.0,
        }

    def set_scorer(self, scorer_fn: Callable[[str, str, str], float]) -> None:
        """
        Plug in a custom scoring function.

        The function signature is: scorer(query, document_text, title) -> float
        This allows swapping in a real cross-encoder model when available.
        """
        self._custom_scorer = scorer_fn

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
    ) -> list[RerankedResult]:
        """
        Rerank a list of candidate documents.

        Args:
            query: The search query
            candidates: List of dicts with keys:
                - doc_id (str)
                - content (str)
                - title (str, optional)
                - source (str, optional)
                - score (float) — original retrieval score
                - rank (int) — original rank
                - metadata (dict, optional)
            top_k: Override number of results to return

        Returns:
            Reranked results sorted by cross-encoder score
        """
        top_k = top_k or self.config.top_k
        self._stats["total_reranks"] += 1

        # Limit candidates
        candidates = candidates[:self.config.max_candidates]
        self._stats["total_candidates_scored"] += len(candidates)

        # Score each candidate
        scored: list[RerankedResult] = []
        for candidate in candidates:
            doc_id = candidate.get("doc_id", "")
            content = candidate.get("content", "")
            title = candidate.get("title", "")
            source = candidate.get("source", "")
            original_score = candidate.get("score", 0.0)
            original_rank = candidate.get("rank", 0)

            # Use custom scorer if available, else built-in
            if self._custom_scorer:
                rerank_score = self._custom_scorer(query, content, title)
            else:
                rerank_score = self._scorer.score(query, content, title)

            scored.append(RerankedResult(
                doc_id=doc_id,
                original_rank=original_rank,
                original_score=original_score,
                rerank_score=rerank_score,
                content_preview=content[:200],
                title=title,
                source=source,
                metadata=candidate.get("metadata", {}),
            ))

        # Sort by rerank score
        scored.sort(key=lambda r: r.rerank_score, reverse=True)

        # Assign final ranks and compute rank change
        total_rank_change = 0
        results: list[RerankedResult] = []
        for i, result in enumerate(scored):
            result.final_rank = i + 1
            result.rank_change = result.original_rank - result.final_rank
            total_rank_change += abs(result.rank_change)

            if result.rerank_score >= self.config.min_score:
                results.append(result)

        # Normalize scores if configured
        if self.config.normalize_scores and results:
            max_score = max(r.rerank_score for r in results)
            if max_score > 0:
                for r in results:
                    r.rerank_score = r.rerank_score / max_score

        # Update stats
        if candidates:
            self._stats["avg_rank_change"] = total_rank_change / len(candidates)

        return results[:top_k]

    def rerank_with_diversity(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int | None = None,
        diversity_weight: float = 0.3,
    ) -> list[RerankedResult]:
        """
        Rerank with Maximal Marginal Relevance (MMR) for diversity.

        Balances relevance with diversity by penalizing candidates
        that are too similar to already-selected results.
        """
        top_k = top_k or self.config.top_k

        # First, score all candidates
        all_scored = self.rerank(query, candidates, top_k=len(candidates))
        if not all_scored:
            return []

        selected: list[RerankedResult] = []
        remaining = list(all_scored)

        while remaining and len(selected) < top_k:
            best_idx = 0
            best_mmr = -float('inf')

            for i, candidate in enumerate(remaining):
                relevance = candidate.rerank_score

                # Compute max similarity to already selected
                max_sim = 0.0
                if selected:
                    for sel in selected:
                        sim = self._text_similarity(
                            candidate.content_preview, sel.content_preview
                        )
                        max_sim = max(max_sim, sim)

                mmr = (1 - diversity_weight) * relevance - diversity_weight * max_sim
                if mmr > best_mmr:
                    best_mmr = mmr
                    best_idx = i

            selected.append(remaining.pop(best_idx))

        # Reassign final ranks
        for i, result in enumerate(selected):
            result.final_rank = i + 1
        return selected

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """Simple Jaccard similarity between two text snippets."""
        tokens_a = set(re.findall(r'\b\w+\b', a.lower()))
        tokens_b = set(re.findall(r'\b\w+\b', b.lower()))
        if not tokens_a or not tokens_b:
            return 0.0
        return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)

    def stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "model": self.config.model_name,
            "using_builtin_scorer": self._custom_scorer is None,
        }

    def reset(self) -> None:
        self._stats = {k: 0 if isinstance(v, (int, float)) else v for k, v in self._stats.items()}
