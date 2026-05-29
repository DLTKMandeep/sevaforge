"""
SevaForge FastAPI Application Factory
Creates and configures the main application with middleware, routes, and lifecycle.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from sevaforge import __app_name__, __version__
from sevaforge.config import get_settings
from sevaforge.gateway import AIGateway, PromptEngine, SchemaGate, SemanticCache
from sevaforge.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)


# ── Application State ─────────────────────────────────────────────────
# Shared gateway instance, initialized at startup or on first access.

_gateway: AIGateway | None = None


def get_gateway() -> AIGateway:
    """Return the global AI Gateway instance (lazy-init for test compat)."""
    global _gateway
    if _gateway is None:
        _gateway = _create_gateway()
    return _gateway


def _create_gateway() -> AIGateway:
    """Build a fresh AI Gateway with all sub-components."""
    prompt_engine = PromptEngine()
    cache = SemanticCache()
    schema_gate = SchemaGate()
    gw = AIGateway(prompt_engine=prompt_engine, cache=cache, schema_gate=schema_gate)
    logger.info("AI Gateway initialized — prompt templates: %d", len(prompt_engine.list_templates()))
    return gw


# ── Lifecycle ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle manager."""
    global _gateway

    settings = get_settings()
    logger.info(
        "Starting %s v%s [env=%s]",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    _gateway = _create_gateway()
    app.state.start_time = time.time()
    app.state.gateway = _gateway

    yield  # ← App is running

    # Shutdown
    logger.info("Shutting down %s", settings.app_name)
    _gateway = None


# ── App Factory ───────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "SevaForge Enterprise AI Platform — "
            "Agentic orchestration with prompt assembly, semantic caching, "
            "and schema-validated LLM output."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Correlation ID Middleware ──────────────────────────────────────
    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next) -> Response:
        """Inject a correlation/trace ID into every request."""
        trace_id = request.headers.get("X-Trace-ID", f"sf-{uuid.uuid4().hex[:12]}")
        request.state.trace_id = trace_id

        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        logger.info(
            "%s %s → %d (%.1fms) [trace=%s]",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            trace_id,
        )
        return response

    # ── Global Error Handler ──────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = getattr(request.state, "trace_id", "unknown")
        logger.exception("Unhandled error [trace=%s]: %s", trace_id, exc)
        error = ErrorResponse(
            error=type(exc).__name__,
            detail=str(exc),
            trace_id=trace_id,
            status_code=500,
        )
        return JSONResponse(status_code=500, content=error.model_dump())

    # ── Register Routes ───────────────────────────────────────────────
    from sevaforge.api.v1.routes_health import router as health_router
    from sevaforge.api.v1.routes_agents import router as agents_router
    from sevaforge.api.v1.routes_gateway import router as gateway_router

    app.include_router(health_router, prefix=settings.api_prefix, tags=["Health"])
    app.include_router(agents_router, prefix=settings.api_prefix, tags=["Agents"])
    app.include_router(gateway_router, prefix=settings.api_prefix, tags=["Gateway"])

    # ── Root redirect to docs ─────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": f"Welcome to {settings.app_name} v{settings.app_version}", "docs": "/docs"}

    return app
