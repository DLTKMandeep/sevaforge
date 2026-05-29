"""
SevaForge AI Gateway — Semantic Cache
Two-tier cache: exact hash match (fast) + embedding similarity (fuzzy).
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sevaforge.config import get_settings
from sevaforge.models.schemas import CacheStats

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cached prompt→response pair."""

    key_hash: str
    prompt_text: str
    response: Any
    model: str
    embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    hit_count: int = 0
    last_hit: float = 0.0


class SemanticCache:
    """
    Two-tier caching for LLM responses.

    Tier 1 — Exact Match:
        SHA-256 hash of the full prompt text. O(1) lookup.

    Tier 2 — Semantic Similarity:
        Cosine similarity on prompt embeddings.
        If similarity >= threshold, return cached response.

    In-memory implementation for Week 1. Redis-backed in Week 2.

    Usage:
        cache = SemanticCache()
        hit = cache.lookup("What is Python?")
        if hit:
            return hit.response
        # ... call LLM ...
        cache.store("What is Python?", response, model="claude-3.5")
    """

    def __init__(
        self,
        enabled: bool | None = None,
        ttl_seconds: int | None = None,
        similarity_threshold: float | None = None,
    ):
        settings = get_settings()
        self._enabled = enabled if enabled is not None else settings.cache_enabled
        self._ttl = ttl_seconds or settings.cache_ttl_seconds
        self._threshold = similarity_threshold or settings.cache_similarity_threshold

        # In-memory stores
        self._exact_cache: dict[str, CacheEntry] = {}
        self._semantic_entries: list[CacheEntry] = []

        # Stats
        self._exact_hits = 0
        self._semantic_hits = 0
        self._misses = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _hash(self, text: str) -> str:
        """SHA-256 hash of normalized text."""
        normalized = " ".join(text.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if a cache entry has exceeded TTL."""
        return (time.time() - entry.created_at) > self._ttl

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def lookup(self, prompt_text: str, embedding: list[float] | None = None) -> CacheEntry | None:
        """
        Look up a prompt in the cache.

        1. Try exact hash match (Tier 1).
        2. If embedding provided, try semantic similarity (Tier 2).
        3. Return None on miss.
        """
        if not self._enabled:
            return None

        # Tier 1: Exact match
        key = self._hash(prompt_text)
        if key in self._exact_cache:
            entry = self._exact_cache[key]
            if not self._is_expired(entry):
                entry.hit_count += 1
                entry.last_hit = time.time()
                self._exact_hits += 1
                logger.debug("Cache exact hit: %s (hits=%d)", key[:12], entry.hit_count)
                return entry
            else:
                # Expired — remove
                del self._exact_cache[key]

        # Tier 2: Semantic similarity
        if embedding:
            best_entry: CacheEntry | None = None
            best_score = 0.0

            for entry in self._semantic_entries:
                if self._is_expired(entry):
                    continue
                if entry.embedding is None:
                    continue
                score = self._cosine_similarity(embedding, entry.embedding)
                if score >= self._threshold and score > best_score:
                    best_score = score
                    best_entry = entry

            if best_entry:
                best_entry.hit_count += 1
                best_entry.last_hit = time.time()
                self._semantic_hits += 1
                logger.debug(
                    "Cache semantic hit: similarity=%.3f, key=%s",
                    best_score,
                    best_entry.key_hash[:12],
                )
                return best_entry

        self._misses += 1
        return None

    def store(
        self,
        prompt_text: str,
        response: Any,
        model: str,
        embedding: list[float] | None = None,
    ) -> str:
        """
        Store a prompt→response pair in the cache.

        Returns the cache key hash.
        """
        if not self._enabled:
            return ""

        key = self._hash(prompt_text)
        entry = CacheEntry(
            key_hash=key,
            prompt_text=prompt_text,
            response=response,
            model=model,
            embedding=embedding,
        )

        # Store in exact cache
        self._exact_cache[key] = entry

        # Store in semantic index if embedding available
        if embedding:
            self._semantic_entries.append(entry)

        logger.debug("Cached response: key=%s, has_embedding=%s", key[:12], embedding is not None)
        return key

    def invalidate(self, prompt_text: str) -> bool:
        """Remove a specific entry from the cache."""
        key = self._hash(prompt_text)
        removed = key in self._exact_cache
        self._exact_cache.pop(key, None)
        self._semantic_entries = [e for e in self._semantic_entries if e.key_hash != key]
        return removed

    def clear(self) -> int:
        """Clear all cache entries. Returns count of entries removed."""
        count = len(self._exact_cache)
        self._exact_cache.clear()
        self._semantic_entries.clear()
        logger.info("Cache cleared: %d entries removed", count)
        return count

    def evict_expired(self) -> int:
        """Remove all expired entries. Returns count of entries evicted."""
        now = time.time()
        before = len(self._exact_cache)
        self._exact_cache = {
            k: v for k, v in self._exact_cache.items() if (now - v.created_at) <= self._ttl
        }
        self._semantic_entries = [
            e for e in self._semantic_entries if (now - e.created_at) <= self._ttl
        ]
        evicted = before - len(self._exact_cache)
        if evicted:
            logger.info("Evicted %d expired cache entries", evicted)
        return evicted

    def stats(self) -> CacheStats:
        """Return current cache statistics."""
        total = self._exact_hits + self._semantic_hits + self._misses
        return CacheStats(
            enabled=self._enabled,
            total_entries=len(self._exact_cache),
            exact_hits=self._exact_hits,
            semantic_hits=self._semantic_hits,
            misses=self._misses,
            hit_rate=(self._exact_hits + self._semantic_hits) / total if total > 0 else 0.0,
            estimated_savings_usd=0.0,
        )
