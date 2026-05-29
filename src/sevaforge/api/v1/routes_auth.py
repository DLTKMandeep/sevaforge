"""
SevaForge API — Auth Layer Endpoints (Layer 2)
JWT token management, rate limiting, and circuit breaker status.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from sevaforge.auth import JWTHandler, RateLimiter, CircuitBreaker
from sevaforge.auth.jwt_handler import TokenError, TokenExpiredError, TokenRevokedError

router = APIRouter()

# ── Shared instances (lazy-initialized) ──────────────────────────────

_jwt: JWTHandler | None = None
_limiter: RateLimiter | None = None
_breaker: CircuitBreaker | None = None


def get_jwt() -> JWTHandler:
    global _jwt
    if _jwt is None:
        _jwt = JWTHandler()
    return _jwt


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter


def get_breaker() -> CircuitBreaker:
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker(name="api-gateway")
    return _breaker


# ══════════════════════════════════════════════════════════════════════
# JWT Token Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.post("/token")
async def create_token(request: Request) -> dict:
    """Create a JWT token for the given user, tenant, and roles."""
    body = await request.json()
    user_id = body.get("user_id")
    tenant_id = body.get("tenant_id")
    roles = body.get("roles", [])

    if not user_id or not tenant_id:
        raise HTTPException(400, "Both 'user_id' and 'tenant_id' are required")

    jwt = get_jwt()
    token = jwt.create_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles,
        extra_claims=body.get("extra_claims"),
        expire_minutes=body.get("expire_minutes"),
    )
    # Decode to get expiry info
    payload = jwt.validate_token(token)
    return {
        "token": token,
        "user_id": payload.user_id,
        "tenant_id": payload.tenant_id,
        "roles": payload.roles,
        "expires_at": payload.exp,
        "issued_at": payload.iat,
        "jti": payload.jti,
    }


@router.post("/verify")
async def verify_token(request: Request) -> dict:
    """Verify a JWT token and return the decoded payload."""
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(400, "'token' is required")

    jwt = get_jwt()
    try:
        payload = jwt.validate_token(token)
    except TokenExpiredError:
        raise HTTPException(401, "Token has expired")
    except TokenRevokedError:
        raise HTTPException(401, "Token has been revoked")
    except TokenError as exc:
        raise HTTPException(401, str(exc))

    return {
        "valid": True,
        "user_id": payload.user_id,
        "tenant_id": payload.tenant_id,
        "roles": payload.roles,
        "expires_at": payload.exp,
        "remaining_seconds": payload.remaining_seconds,
        "jti": payload.jti,
    }


@router.post("/refresh")
async def refresh_token(request: Request) -> dict:
    """Refresh a JWT token, issuing a new one with a fresh expiry."""
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(400, "'token' is required")

    jwt = get_jwt()
    try:
        new_token = jwt.refresh_token(token)
    except TokenExpiredError:
        raise HTTPException(401, "Token has expired — cannot refresh")
    except TokenRevokedError:
        raise HTTPException(401, "Token has been revoked — cannot refresh")
    except TokenError as exc:
        raise HTTPException(401, str(exc))

    payload = jwt.validate_token(new_token)
    return {
        "token": new_token,
        "user_id": payload.user_id,
        "tenant_id": payload.tenant_id,
        "expires_at": payload.exp,
        "jti": payload.jti,
    }


@router.post("/revoke")
async def revoke_token(request: Request) -> dict:
    """Revoke a token by its JTI so it can no longer be validated."""
    body = await request.json()
    token = body.get("token")
    if not token:
        raise HTTPException(400, "'token' is required")

    jwt = get_jwt()
    try:
        payload = jwt.validate_token(token)
    except TokenError as exc:
        raise HTTPException(400, f"Cannot revoke invalid token: {exc}")

    jwt.revoke_token(payload.jti)
    return {"revoked": True, "jti": payload.jti}


# ══════════════════════════════════════════════════════════════════════
# Rate Limiter Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/rate-limit/{key}")
async def check_rate_limit(key: str) -> dict:
    """Check rate limit status for a given key without consuming tokens."""
    limiter = get_limiter()
    remaining = limiter.remaining(key)
    allowed = limiter.check(key)
    stats = limiter.stats()
    return {
        "key": key,
        "allowed": allowed,
        "remaining_tokens": remaining,
        "max_tokens": stats["max_tokens"],
        "refill_rate": stats["refill_rate"],
    }


@router.post("/rate-limit/{key}/consume")
async def consume_rate_limit(key: str, request: Request) -> dict:
    """Consume one or more rate limit tokens for a key."""
    body = await request.json()
    tokens = body.get("tokens", 1)

    limiter = get_limiter()
    result = limiter.consume(key, tokens=tokens)
    return {
        "key": key,
        "allowed": result.allowed,
        "remaining": result.remaining,
        "reset_at": result.reset_at,
        "retry_after": result.retry_after,
    }


# ══════════════════════════════════════════════════════════════════════
# Circuit Breaker Endpoints
# ══════════════════════════════════════════════════════════════════════


@router.get("/circuit-breaker/stats")
async def circuit_breaker_stats() -> dict:
    """Return circuit breaker state and statistics."""
    return get_breaker().stats()
