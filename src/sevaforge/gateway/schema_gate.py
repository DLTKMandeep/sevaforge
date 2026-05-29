"""
SevaForge AI Gateway — Schema Gate
Validates LLM output against Pydantic schemas with retry logic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from sevaforge.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class SchemaValidationError(Exception):
    """Raised when LLM output fails schema validation after all retries."""

    def __init__(self, message: str, raw_output: str, errors: list[dict]):
        super().__init__(message)
        self.raw_output = raw_output
        self.errors = errors


class SchemaGate:
    """
    Validates and coerces LLM output into typed Pydantic models.

    Features:
      - JSON extraction from markdown code blocks
      - Pydantic validation with detailed error messages
      - Retry loop with error-augmented re-prompting
      - Fallback to partial parsing on final attempt

    Usage:
        gate = SchemaGate()
        result = gate.validate(raw_llm_output, CodeReviewOutput)
        # result is a validated CodeReviewOutput instance

        # With retry callback (calls LLM again with error context)
        result = gate.validate_with_retry(
            raw_output, CodeReviewOutput, retry_fn=call_llm_again
        )
    """

    def __init__(self, max_retries: int | None = None):
        settings = get_settings()
        self._max_retries = max_retries or settings.schema_gate_max_retries

    def extract_json(self, text: str) -> str:
        """
        Extract JSON from LLM output, handling common formats:
          - Raw JSON string
          - JSON inside ```json ... ``` code blocks
          - JSON inside ``` ... ``` code blocks
          - JSON embedded in prose (first { to last })
        """
        text = text.strip()

        # Try raw JSON first
        if text.startswith("{") or text.startswith("["):
            return text

        # Try ```json ... ``` blocks
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Fallback: extract first JSON object
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]

        # Last resort: return as-is
        return text

    def validate(self, raw_output: str, schema: type[T]) -> T:
        """
        Validate raw LLM output against a Pydantic schema.

        Args:
            raw_output: The raw string output from the LLM.
            schema: A Pydantic BaseModel class to validate against.

        Returns:
            A validated instance of the schema.

        Raises:
            SchemaValidationError: If validation fails.
        """
        json_str = self.extract_json(raw_output)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(
                message=f"Invalid JSON: {e}",
                raw_output=raw_output,
                errors=[{"type": "json_parse_error", "msg": str(e)}],
            )

        try:
            return schema.model_validate(data)
        except ValidationError as e:
            raise SchemaValidationError(
                message=f"Schema validation failed: {e.error_count()} errors",
                raw_output=raw_output,
                errors=e.errors(),
            )

    def build_retry_prompt(self, original_prompt: str, raw_output: str, errors: list[dict]) -> str:
        """
        Build a retry prompt that includes the validation errors,
        so the LLM can correct its output.
        """
        error_summary = "\n".join(
            f"  - {e.get('loc', '?')}: {e.get('msg', 'unknown error')}" for e in errors[:5]
        )

        return (
            f"{original_prompt}\n\n"
            f"--- VALIDATION ERROR ---\n"
            f"Your previous response had the following errors:\n"
            f"{error_summary}\n\n"
            f"Your previous (invalid) output was:\n"
            f"```\n{raw_output[:500]}\n```\n\n"
            f"Please fix these errors and respond with valid JSON only."
        )

    async def validate_with_retry(
        self,
        raw_output: str,
        schema: type[T],
        retry_fn: Any | None = None,
        original_prompt: str = "",
    ) -> T:
        """
        Validate with automatic retry loop.

        Args:
            raw_output: Initial LLM output to validate.
            schema: Pydantic model class.
            retry_fn: Async callable(prompt: str) -> str to re-call the LLM.
            original_prompt: The original prompt for building retry context.

        Returns:
            Validated schema instance.

        Raises:
            SchemaValidationError: After all retries exhausted.
        """
        current_output = raw_output
        last_errors: list[dict] = []

        for attempt in range(self._max_retries + 1):
            try:
                result = self.validate(current_output, schema)
                if attempt > 0:
                    logger.info("Schema validation succeeded on retry %d", attempt)
                return result

            except SchemaValidationError as e:
                last_errors = e.errors
                logger.warning(
                    "Schema validation failed (attempt %d/%d): %s",
                    attempt + 1,
                    self._max_retries + 1,
                    e,
                )

                # If we have retries left and a retry function
                if attempt < self._max_retries and retry_fn and original_prompt:
                    retry_prompt = self.build_retry_prompt(original_prompt, current_output, e.errors)
                    try:
                        current_output = await retry_fn(retry_prompt)
                    except Exception as retry_err:
                        logger.error("Retry call failed: %s", retry_err)
                        break

        # All retries exhausted
        raise SchemaValidationError(
            message=f"Schema validation failed after {self._max_retries + 1} attempts",
            raw_output=current_output,
            errors=last_errors,
        )

    def validate_partial(self, raw_output: str, schema: type[T]) -> tuple[T | None, list[dict]]:
        """
        Attempt validation, returning (result, errors).
        On failure, try to construct a partial result with defaults.
        """
        try:
            result = self.validate(raw_output, schema)
            return result, []
        except SchemaValidationError as e:
            # Try to parse what we can with defaults
            try:
                json_str = self.extract_json(raw_output)
                data = json.loads(json_str)
                # Let Pydantic fill defaults for missing fields
                result = schema.model_validate(data)
                return result, e.errors
            except Exception:
                return None, e.errors
