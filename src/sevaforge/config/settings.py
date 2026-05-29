"""
SevaForge Platform Settings
Loaded from environment variables and .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — every setting overridable via env var."""

    # ── App ────────────────────────────────────────────────────────────
    app_name: str = "SevaForge"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ── API Server ─────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Auth (JWT) ─────────────────────────────────────────────────────
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # ── LLM Providers ──────────────────────────────────────────────────
    anthropic_api_key: str = ""
    google_api_key: str = ""
    default_model: str = "claude-sonnet-4-20250514"
    fallback_model: str = "gemini-2.0-flash"
    max_tokens: int = 4096
    temperature: float = 0.3

    # ── AI Gateway ─────────────────────────────────────────────────────
    prompt_template_dir: str = "templates/prompts"
    cache_enabled: bool = True
    cache_ttl_seconds: int = 86400  # 24 hours
    cache_similarity_threshold: float = 0.95
    schema_gate_max_retries: int = 3

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./sevaforge.db"
    db_pool_min: int = 2
    db_pool_max: int = 20

    # ── Redis ─────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    redis_session_ttl: int = 3600
    redis_rate_limit_max: int = 100
    redis_rate_limit_refill: float = 10.0

    # ── Knowledge Layer ───────────────────────────────────────────────
    search_rrf_k: int = 60
    search_default_top_k: int = 10
    search_vector_weight: float = 0.5
    search_bm25_weight: float = 0.5
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    reranker_top_k: int = 10

    # ── Orchestration ─────────────────────────────────────────────────
    context_max_sessions: int = 10000
    context_max_history: int = 200
    a2a_max_history: int = 10000

    # ── Observability ──────────────────────────────────────────────────
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"

    model_config = {
        "env_prefix": "SEVAFORGE_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance — cached after first call."""
    return Settings()
