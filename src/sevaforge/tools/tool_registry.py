"""
SevaForge Semantic Tool Registry — US-048

Discovery engine for tools and capabilities. Supports registration,
semantic search (TF-IDF + cosine similarity), capability matching,
and intelligent tool suggestion.

Architecture:
    Register Tool → Compute Embedding → Index
    Query → Embed → Cosine Similarity → Rank → Top-K Results
    Task Description → Semantic Search + Capability Match → Suggestions
"""

from __future__ import annotations

import logging
import math
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class ToolCapability:
    """
    A single capability offered by a tool.

    Capabilities describe what a tool can do, including its expected
    input and output schemas for automated matching.
    """

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }


@dataclass
class ToolDefinition:
    """
    A registered tool with metadata, capabilities, and computed embedding.

    The embedding is derived from the tool's name, description, and
    capability descriptions to enable semantic discovery.
    """

    tool_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: list[ToolCapability] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    category: str = "general"
    author: str = ""
    is_active: bool = True
    registered_at: datetime = field(default_factory=datetime.utcnow)
    embedding: list[float] = field(default_factory=list)

    @property
    def capability_names(self) -> list[str]:
        """Return a flat list of capability names."""
        return [c.name for c in self.capabilities]

    def text_for_embedding(self) -> str:
        """
        Build the text representation used for embedding computation.

        Combines name, description, capabilities, tags, and category
        to produce a rich text suitable for TF-IDF vectorisation.
        """
        parts = [self.name, self.description]
        for cap in self.capabilities:
            parts.append(cap.name)
            parts.append(cap.description)
        parts.extend(self.tags)
        parts.append(self.category)
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "tags": self.tags,
            "category": self.category,
            "author": self.author,
            "is_active": self.is_active,
            "registered_at": self.registered_at.isoformat(),
        }


# ── Semantic Tool Registry ────────────────────────────────────────────


class ToolRegistry:
    """
    Semantic tool discovery engine.

    Maintains a registry of tools with TF-IDF-based embeddings for
    similarity search. Supports exact lookup, filtered listing,
    semantic search, capability matching, and intelligent suggestion.

    Usage:
        registry = ToolRegistry()
        registry.register_tool(ToolDefinition(name="code-review", ...))
        results = registry.search_tools("review my pull request", top_k=3)
        suggestions = registry.suggest_tools("I need to analyse code quality")
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._vocabulary: dict[str, int] = {}  # word → index
        self._doc_freq: Counter[str] = Counter()  # word → num docs containing it
        self._stats = {
            "tools_registered": 0,
            "searches": 0,
            "matches": 0,
            "suggestions": 0,
        }

    # ── Registration ─────────────────────────────────────────────────

    def register_tool(self, tool_def: ToolDefinition) -> ToolDefinition:
        """
        Register a tool and compute its embedding.

        If the tool_id already exists, it is updated in place.
        After registration the global vocabulary and IDF weights are
        rebuilt so that all embeddings remain consistent.

        Args:
            tool_def: The tool definition to register.

        Returns:
            The registered tool definition with embedding populated.
        """
        self._tools[tool_def.tool_id] = tool_def
        self._stats["tools_registered"] = len(self._tools)

        # Rebuild vocabulary and all embeddings (vocabulary may have grown)
        self._rebuild_vocabulary()
        self._recompute_all_embeddings()

        logger.info(
            "Registered tool '%s' (id=%s, category=%s, caps=%d)",
            tool_def.name,
            tool_def.tool_id,
            tool_def.category,
            len(tool_def.capabilities),
        )
        return tool_def

    def unregister_tool(self, tool_id: str) -> bool:
        """
        Remove a tool from the registry.

        Rebuilds vocabulary and embeddings after removal so that
        IDF weights remain accurate.

        Returns:
            True if the tool was found and removed, False otherwise.
        """
        if tool_id not in self._tools:
            logger.warning("Unregister failed: tool_id '%s' not found", tool_id)
            return False

        name = self._tools[tool_id].name
        del self._tools[tool_id]
        self._stats["tools_registered"] = len(self._tools)

        # Rebuild to keep IDF accurate
        self._rebuild_vocabulary()
        self._recompute_all_embeddings()

        logger.info("Unregistered tool '%s' (id=%s)", name, tool_id)
        return True

    # ── Lookup ───────────────────────────────────────────────────────

    def get_tool(self, tool_id: str) -> ToolDefinition | None:
        """Look up a tool by its unique identifier."""
        return self._tools.get(tool_id)

    def list_tools(
        self,
        category: str | None = None,
        tag: str | None = None,
        active_only: bool = True,
    ) -> list[ToolDefinition]:
        """
        Return tools matching the given filters.

        Args:
            category: If set, only return tools in this category.
            tag: If set, only return tools bearing this tag.
            active_only: When True (default), exclude inactive tools.

        Returns:
            A list of matching ToolDefinition objects.
        """
        results: list[ToolDefinition] = []
        for tool in self._tools.values():
            if active_only and not tool.is_active:
                continue
            if category and tool.category != category:
                continue
            if tag and tag not in tool.tags:
                continue
            results.append(tool)
        return results

    # ── Semantic Search ──────────────────────────────────────────────

    def search_tools(self, query: str, top_k: int = 5) -> list[tuple[ToolDefinition, float]]:
        """
        Semantic search over registered tools using TF-IDF cosine similarity.

        Computes a TF-IDF embedding for the query text and ranks all active
        tools by cosine similarity to their pre-computed embeddings.

        Args:
            query: Free-text search query.
            top_k: Maximum number of results to return.

        Returns:
            List of (ToolDefinition, similarity_score) tuples, highest first.
        """
        self._stats["searches"] += 1

        if not self._tools:
            return []

        query_embedding = self._compute_embedding(query)
        if not query_embedding or all(v == 0.0 for v in query_embedding):
            return []

        scored: list[tuple[ToolDefinition, float]] = []
        for tool in self._tools.values():
            if not tool.is_active:
                continue
            if not tool.embedding:
                continue
            sim = self._cosine_similarity(query_embedding, tool.embedding)
            if sim > 0.0:
                scored.append((tool, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ── Capability Matching ──────────────────────────────────────────

    def match_capabilities(
        self,
        required_capabilities: list[str],
    ) -> list[tuple[ToolDefinition, list[str]]]:
        """
        Find tools whose capabilities overlap with the requirements.

        Performs case-insensitive substring matching against capability
        names and descriptions for flexible matching.

        Args:
            required_capabilities: List of capability name/keyword strings.

        Returns:
            List of (ToolDefinition, matched_capability_names) sorted by
            number of matches descending.
        """
        self._stats["matches"] += 1

        if not required_capabilities:
            return []

        results: list[tuple[ToolDefinition, list[str]]] = []
        required_lower = [r.lower() for r in required_capabilities]

        for tool in self._tools.values():
            if not tool.is_active:
                continue

            matched: list[str] = []
            for cap in tool.capabilities:
                cap_text = f"{cap.name} {cap.description}".lower()
                for req in required_lower:
                    if req in cap_text:
                        matched.append(cap.name)
                        break  # Avoid duplicate matches for the same capability

            if matched:
                results.append((tool, matched))

        # Sort by number of matched capabilities (descending), then by name
        results.sort(key=lambda x: (-len(x[1]), x[0].name))
        return results

    # ── Intelligent Suggestion ───────────────────────────────────────

    def suggest_tools(
        self,
        task_description: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Suggest tools for a given task using semantic search and capability matching.

        Combines two signals:
        1. Semantic similarity (TF-IDF cosine) between task description and tool embeddings.
        2. Capability keyword matching against extracted task terms.

        Results are merged and ranked by a weighted composite score.

        Args:
            task_description: Natural language description of the task.
            top_k: Maximum number of suggestions.

        Returns:
            List of suggestion dicts with tool info, scores, and rationale.
        """
        self._stats["suggestions"] += 1

        if not self._tools or not task_description.strip():
            return []

        # Signal 1: Semantic search
        semantic_results = self.search_tools(task_description, top_k=top_k * 2)
        semantic_scores: dict[str, float] = {
            tool.tool_id: score for tool, score in semantic_results
        }

        # Signal 2: Capability matching using extracted keywords
        keywords = self._extract_keywords(task_description)
        cap_results = self.match_capabilities(keywords) if keywords else []
        cap_scores: dict[str, float] = {}
        if cap_results:
            max_caps = max(len(caps) for _, caps in cap_results)
            for tool, caps in cap_results:
                cap_scores[tool.tool_id] = len(caps) / max(max_caps, 1)

        # Merge scores (70% semantic, 30% capability match)
        all_tool_ids = set(semantic_scores.keys()) | set(cap_scores.keys())
        composite: list[tuple[str, float, float, float]] = []

        for tid in all_tool_ids:
            sem = semantic_scores.get(tid, 0.0)
            cap = cap_scores.get(tid, 0.0)
            combined = 0.7 * sem + 0.3 * cap
            composite.append((tid, combined, sem, cap))

        composite.sort(key=lambda x: x[1], reverse=True)

        # Build suggestion dicts
        suggestions: list[dict[str, Any]] = []
        for tid, combined, sem, cap in composite[:top_k]:
            tool = self._tools[tid]
            matched_caps = []
            for t, caps in cap_results:
                if t.tool_id == tid:
                    matched_caps = caps
                    break

            suggestions.append({
                "tool_id": tool.tool_id,
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
                "capabilities": tool.capability_names,
                "matched_capabilities": matched_caps,
                "semantic_score": round(sem, 4),
                "capability_score": round(cap, 4),
                "composite_score": round(combined, 4),
                "tags": tool.tags,
            })

        return suggestions

    # ── TF-IDF Embedding Engine ──────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text into lowercase word tokens."""
        return re.findall(r"\b\w+\b", text.lower())

    def _rebuild_vocabulary(self) -> None:
        """
        Rebuild the global vocabulary and document frequency counts
        from all currently registered tools.
        """
        self._vocabulary.clear()
        self._doc_freq.clear()

        word_set: set[str] = set()
        doc_word_sets: list[set[str]] = []

        for tool in self._tools.values():
            tokens = self._tokenize(tool.text_for_embedding())
            token_set = set(tokens)
            word_set.update(token_set)
            doc_word_sets.append(token_set)

        # Assign indices to vocabulary words (sorted for determinism)
        for idx, word in enumerate(sorted(word_set)):
            self._vocabulary[word] = idx

        # Count document frequency for each word
        for token_set in doc_word_sets:
            for word in token_set:
                self._doc_freq[word] += 1

    def _recompute_all_embeddings(self) -> None:
        """Recompute embeddings for every registered tool."""
        for tool in self._tools.values():
            tool.embedding = self._compute_embedding(tool.text_for_embedding())

    def _compute_embedding(self, text: str) -> list[float]:
        """
        Compute a TF-IDF weighted bag-of-words embedding for the given text.

        Each dimension corresponds to a word in the global vocabulary.
        The weight is TF (term frequency in this text) multiplied by
        IDF (inverse document frequency across all registered tools).

        Uses stdlib only — no external dependencies.
        """
        if not self._vocabulary:
            return []

        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * len(self._vocabulary)

        tf = Counter(tokens)
        n_docs = max(len(self._tools), 1)
        vec_size = len(self._vocabulary)
        embedding = [0.0] * vec_size

        for word, count in tf.items():
            if word not in self._vocabulary:
                continue
            idx = self._vocabulary[word]
            # Term frequency: raw count normalised by document length
            term_freq = count / len(tokens)
            # Inverse document frequency with smoothing
            df = self._doc_freq.get(word, 0)
            idf = math.log((n_docs + 1) / (df + 1)) + 1.0
            embedding[idx] = term_freq * idf

        return embedding

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns 0.0 for mismatched lengths, zero-magnitude vectors, or
        empty inputs.
        """
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """
        Extract meaningful keywords from a task description.

        Filters out common stop words to keep only content-bearing terms
        suitable for capability matching.
        """
        stop_words = {
            "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
            "they", "them", "the", "a", "an", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
            "into", "through", "during", "before", "after", "above", "below",
            "between", "out", "off", "over", "under", "again", "further",
            "then", "once", "here", "there", "when", "where", "why", "how",
            "all", "each", "every", "both", "few", "more", "most", "other",
            "some", "such", "no", "nor", "not", "only", "own", "same", "so",
            "than", "too", "very", "just", "don", "now", "and", "but", "or",
            "if", "that", "this", "what", "which", "who", "whom", "these",
            "those", "am", "about", "up", "need", "want", "like",
        }
        tokens = re.findall(r"\b\w+\b", text.lower())
        return [t for t in tokens if t not in stop_words and len(t) > 1]

    # ── Stats & Reset ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return registry-level statistics."""
        categories: dict[str, int] = defaultdict(int)
        for tool in self._tools.values():
            categories[tool.category] += 1

        return {
            **self._stats,
            "vocabulary_size": len(self._vocabulary),
            "categories": dict(categories),
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._tools.clear()
        self._vocabulary.clear()
        self._doc_freq.clear()
        self._stats = {k: 0 for k in self._stats}
