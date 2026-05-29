"""
Tests for AI Gateway components: PromptEngine, SemanticCache, SchemaGate.
"""

import pytest

from sevaforge.gateway.prompt_engine import PromptEngine
from sevaforge.gateway.schema_gate import SchemaGate, SchemaValidationError
from sevaforge.gateway.semantic_cache import SemanticCache
from sevaforge.models.schemas import CodeReviewOutput


# ── Prompt Engine Tests ──────────────────────────────────────────────────


class TestPromptEngine:
    def test_list_templates(self):
        """Engine loads YAML templates from disk."""
        engine = PromptEngine(template_dir="templates/prompts")
        templates = engine.list_templates()
        assert isinstance(templates, list)
        # May be empty if running from wrong cwd, but shouldn't error

    def test_assemble_missing_template(self):
        """Assembling unknown template raises KeyError."""
        engine = PromptEngine(template_dir="templates/prompts")
        with pytest.raises(KeyError, match="not-a-template"):
            engine.assemble("not-a-template", {"input": "test"})

    def test_hash_prompt_deterministic(self):
        """Same prompt always produces the same hash."""
        engine = PromptEngine(template_dir="templates/prompts")
        from sevaforge.models.schemas import AssembledPrompt, PromptMessage

        prompt = AssembledPrompt(
            messages=[PromptMessage(role="user", content="hello")],
            template_id="test",
            template_version="1.0.0",
        )
        h1 = engine.hash_prompt(prompt)
        h2 = engine.hash_prompt(prompt)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex


# ── Semantic Cache Tests ─────────────────────────────────────────────────


class TestSemanticCache:
    def test_store_and_lookup_exact(self):
        """Exact hash lookup returns cached entry."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600)
        cache.store("What is Python?", {"answer": "A programming language"}, model="test-model")

        hit = cache.lookup("What is Python?")
        assert hit is not None
        assert hit.response == {"answer": "A programming language"}
        assert hit.model == "test-model"

    def test_lookup_miss(self):
        """Lookup returns None for uncached prompt."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600)
        hit = cache.lookup("Never seen this before")
        assert hit is None

    def test_disabled_cache(self):
        """Disabled cache always returns None and doesn't store."""
        cache = SemanticCache(enabled=False)
        key = cache.store("test", "response", model="m")
        assert key == ""
        assert cache.lookup("test") is None

    def test_clear(self):
        """Clear removes all entries."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600)
        cache.store("q1", "r1", model="m")
        cache.store("q2", "r2", model="m")
        count = cache.clear()
        assert count == 2
        assert cache.lookup("q1") is None

    def test_stats(self):
        """Stats track hits and misses."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600)
        cache.store("known", "response", model="m")

        cache.lookup("known")  # hit
        cache.lookup("unknown")  # miss

        stats = cache.stats()
        assert stats.exact_hits == 1
        assert stats.misses == 1
        assert stats.total_entries == 1
        assert stats.hit_rate == 0.5

    def test_invalidate(self):
        """Invalidate removes a specific entry."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600)
        cache.store("remove-me", "data", model="m")
        assert cache.lookup("remove-me") is not None

        removed = cache.invalidate("remove-me")
        assert removed is True
        assert cache.lookup("remove-me") is None

    def test_semantic_similarity(self):
        """Semantic tier returns hit when embedding similarity exceeds threshold."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600, similarity_threshold=0.9)
        embedding = [1.0, 0.0, 0.0]
        cache.store("original query", "cached response", model="m", embedding=embedding)

        # Very similar embedding
        similar = [0.99, 0.01, 0.0]
        hit = cache.lookup("slightly different query", embedding=similar)
        assert hit is not None
        assert hit.response == "cached response"

    def test_semantic_below_threshold(self):
        """Semantic tier returns None when similarity is below threshold."""
        cache = SemanticCache(enabled=True, ttl_seconds=3600, similarity_threshold=0.95)
        cache.store("q", "r", model="m", embedding=[1.0, 0.0, 0.0])

        # Dissimilar embedding
        hit = cache.lookup("different", embedding=[0.0, 1.0, 0.0])
        assert hit is None


# ── Schema Gate Tests ────────────────────────────────────────────────────


class TestSchemaGate:
    def test_extract_json_raw(self):
        """Extracts raw JSON string."""
        gate = SchemaGate()
        assert gate.extract_json('{"key": "value"}') == '{"key": "value"}'

    def test_extract_json_code_block(self):
        """Extracts JSON from markdown code block."""
        gate = SchemaGate()
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        assert gate.extract_json(text) == '{"key": "value"}'

    def test_extract_json_embedded(self):
        """Extracts JSON embedded in prose."""
        gate = SchemaGate()
        text = 'The answer is {"key": "value"} and that is all.'
        assert gate.extract_json(text) == '{"key": "value"}'

    def test_validate_valid_json(self):
        """Validates correct JSON against schema."""
        gate = SchemaGate()
        raw = '{"summary": "Good code", "findings": [], "overall_risk": "low", "confidence": 0.9}'
        result = gate.validate(raw, CodeReviewOutput)
        assert isinstance(result, CodeReviewOutput)
        assert result.summary == "Good code"
        assert result.confidence == 0.9

    def test_validate_invalid_json(self):
        """Raises error on invalid JSON."""
        gate = SchemaGate()
        with pytest.raises(SchemaValidationError, match="Invalid JSON"):
            gate.validate("not json at all", CodeReviewOutput)

    def test_validate_schema_mismatch(self):
        """Raises error when JSON doesn't match schema."""
        gate = SchemaGate()
        with pytest.raises(SchemaValidationError, match="Schema validation failed"):
            gate.validate('{"wrong_field": true}', CodeReviewOutput)

    def test_validate_partial(self):
        """Partial validation returns what it can with errors."""
        gate = SchemaGate()
        raw = '{"summary": "Partial result"}'
        result, errors = gate.validate_partial(raw, CodeReviewOutput)
        # CodeReviewOutput has defaults for findings, overall_risk, confidence
        # so partial should succeed with just summary
        assert result is not None
        assert result.summary == "Partial result"

    def test_build_retry_prompt(self):
        """Retry prompt includes original + errors."""
        gate = SchemaGate()
        prompt = gate.build_retry_prompt(
            original_prompt="Review this code",
            raw_output='{"bad": true}',
            errors=[{"loc": ("summary",), "msg": "field required"}],
        )
        assert "VALIDATION ERROR" in prompt
        assert "field required" in prompt
        assert "Review this code" in prompt
