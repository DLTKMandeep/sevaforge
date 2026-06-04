"""
SevaForge Text / Code Embedding MCP Server

Provides embedding operations: embed single text, embed batches,
embed code with language-aware prefixes, and compute similarity
between two inputs using cosine distance.

Tools:
  - embed_text:       Generate a vector embedding for a single text input
  - embed_batch:      Generate embeddings for multiple texts in one call
  - embed_code:       Generate an embedding for code with language prefix
  - get_similarity:   Compute cosine similarity between two text inputs
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from typing import Any

from sevaforge.mcp.base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter

logger = logging.getLogger(__name__)

# Embedding dimension for mock vectors
_EMBED_DIM = 384


def _mock_embedding(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Generate a deterministic mock embedding vector seeded from input text."""
    seed = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    raw = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [round(x / norm, 6) for x in raw]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return round(dot / (norm_a * norm_b), 6)


class EmbeddingMCPServer(BaseMCPServer):
    """
    Text / Code Embedding MCP server.

    Generates 384-dimensional vector embeddings for text and code.
    In mock mode, vectors are deterministic (seeded from input
    content) so similarity comparisons are consistent.
    """

    def __init__(self):
        super().__init__(
            server_id="embedding",
            name="Text / Code Embedding MCP Server",
            description="Vectorise text and code, compute cosine similarity between inputs",
            version="1.0.0",
        )

    def _register_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="embed_text",
                description="Generate a vector embedding for a single text input",
                category="embedding",
                tags=["embedding", "vector", "text"],
                parameters=[
                    MCPToolParameter(name="text", type="string", required=True,
                                     description="Text to embed"),
                    MCPToolParameter(name="model", type="string", default="all-MiniLM-L6-v2",
                                     description="Embedding model to use",
                                     enum=["all-MiniLM-L6-v2", "text-embedding-3-small",
                                           "text-embedding-3-large"]),
                    MCPToolParameter(name="normalize", type="boolean", default=True,
                                     description="L2-normalise the output vector"),
                ],
                handler=self._embed_text,
            ),
            MCPTool(
                name="embed_batch",
                description="Generate vector embeddings for multiple texts in one call",
                category="embedding",
                tags=["embedding", "vector", "batch"],
                parameters=[
                    MCPToolParameter(name="texts", type="array", required=True,
                                     description="List of text strings to embed"),
                    MCPToolParameter(name="model", type="string", default="all-MiniLM-L6-v2",
                                     enum=["all-MiniLM-L6-v2", "text-embedding-3-small",
                                           "text-embedding-3-large"]),
                ],
                handler=self._embed_batch,
            ),
            MCPTool(
                name="embed_code",
                description="Generate a vector embedding for code with a language-aware prefix",
                category="embedding",
                tags=["embedding", "vector", "code"],
                parameters=[
                    MCPToolParameter(name="code", type="string", required=True,
                                     description="Code snippet to embed"),
                    MCPToolParameter(name="language", type="string", required=True,
                                     description="Programming language of the snippet",
                                     enum=["python", "javascript", "typescript",
                                           "java", "go", "rust", "sql"]),
                    MCPToolParameter(name="model", type="string", default="all-MiniLM-L6-v2"),
                    MCPToolParameter(name="include_docstrings", type="boolean", default=True,
                                     description="Include docstrings in the embedding input"),
                ],
                handler=self._embed_code,
            ),
            MCPTool(
                name="get_similarity",
                description="Compute cosine similarity between two text inputs",
                category="similarity",
                tags=["similarity", "cosine", "compare"],
                parameters=[
                    MCPToolParameter(name="text_a", type="string", required=True,
                                     description="First text input"),
                    MCPToolParameter(name="text_b", type="string", required=True,
                                     description="Second text input"),
                    MCPToolParameter(name="model", type="string", default="all-MiniLM-L6-v2"),
                ],
                handler=self._get_similarity,
            ),
        ]

    # ── Tool Handlers ────────────────────────────────────────────────

    async def _embed_text(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        text = params["text"]
        model = params.get("model", "all-MiniLM-L6-v2")
        do_normalize = params.get("normalize", True)

        vector = _mock_embedding(text)
        token_count = len(text.split())

        return {
            "model": model,
            "input_length": len(text),
            "token_count": token_count,
            "dimension": _EMBED_DIM,
            "normalized": do_normalize,
            "embedding": vector,
            "usage": {"prompt_tokens": token_count, "total_tokens": token_count},
        }

    async def _embed_batch(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        texts = params["texts"]
        model = params.get("model", "all-MiniLM-L6-v2")

        embeddings: list[dict[str, Any]] = []
        total_tokens = 0
        for idx, text in enumerate(texts):
            vector = _mock_embedding(text)
            tokens = len(text.split())
            total_tokens += tokens
            embeddings.append({
                "index": idx,
                "input_length": len(text),
                "token_count": tokens,
                "embedding": vector,
            })

        return {
            "model": model,
            "count": len(embeddings),
            "dimension": _EMBED_DIM,
            "embeddings": embeddings,
            "usage": {"prompt_tokens": total_tokens, "total_tokens": total_tokens},
        }

    async def _embed_code(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        code = params["code"]
        language = params["language"]
        model = params.get("model", "all-MiniLM-L6-v2")
        include_docstrings = params.get("include_docstrings", True)

        # Prefix code with language tag for language-aware embedding
        prefix = f"[{language}]"
        if not include_docstrings:
            # Strip common docstring markers (mock behaviour)
            code_input = "\n".join(
                line for line in code.splitlines()
                if not line.strip().startswith(('"""', "'''", "#", "//", "/*"))
            )
        else:
            code_input = code

        prefixed = f"{prefix} {code_input}"
        vector = _mock_embedding(prefixed)
        token_count = len(code.split())

        return {
            "model": model,
            "language": language,
            "prefix_applied": prefix,
            "include_docstrings": include_docstrings,
            "input_length": len(code),
            "token_count": token_count,
            "dimension": _EMBED_DIM,
            "embedding": vector,
            "usage": {"prompt_tokens": token_count, "total_tokens": token_count},
        }

    async def _get_similarity(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        text_a = params["text_a"]
        text_b = params["text_b"]
        model = params.get("model", "all-MiniLM-L6-v2")

        vec_a = _mock_embedding(text_a)
        vec_b = _mock_embedding(text_b)
        similarity = _cosine_similarity(vec_a, vec_b)

        # Classify similarity level
        if similarity >= 0.85:
            level = "very_similar"
        elif similarity >= 0.65:
            level = "similar"
        elif similarity >= 0.40:
            level = "somewhat_related"
        else:
            level = "dissimilar"

        return {
            "model": model,
            "text_a_length": len(text_a),
            "text_b_length": len(text_b),
            "cosine_similarity": similarity,
            "similarity_level": level,
            "dimension": _EMBED_DIM,
        }
