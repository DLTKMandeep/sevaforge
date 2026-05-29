"""
SevaForge Auth Layer — FastAPI Middleware & Dependencies

Provides request-level authentication and role-based authorisation:
  - ``AuthMiddleware``  — ASGI middleware that extracts Bearer tokens
  - ``require_auth``    — FastAPI dependency returning a ``TokenPayload``
  - ``require_role``    — Dependency factory enforcing role membership
  - ``get_current_user``— Lightweight dependency for current user info
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from sevaforge.auth.jwt_handler import (
    JWTHandler,
    TokenError,
    TokenExpiredError,
    TokenInvalidError,
    TokenPayload,
    TokenRevokedError,
)

logger = logging.getLogger(__name__)


# ── Module-level JWT handler (lazy-initialised) ─────────────────────

_jwt_handler: JWTHandler | None = None


def get_jwt_handler() -> JWTHandler:
    """Return the module-level JWT handler, creating it on first call."""
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler()
    return _jwt_handler


def set_jwt_handler(handler: JWTHandler) -> None:
    """Override the module-level JWT handler (useful in tests)."""
    global _jwt_handler
    _jwt_handler = handler


# ── Bearer token scheme ─────────────────────────────────────────────

_bearer_scheme = HTTPBearer(auto_error=False)


# ── ASGI Middleware ──────────────────────────────────────────────────


class AuthMiddleware(BaseHTTPMiddleware):
    """
    HTTP middleware that extracts and validates Bearer tokens.

    On success, ``request.state.token_payload`` is set to the decoded
    :class:`TokenPayload`.  On failure the request proceeds without
    authentication — downstream dependencies (``require_auth``, etc.)
    enforce access control.

    Exempt paths (health checks, docs) skip validation entirely.
    """

    EXEMPT_PATHS: set[str] = {
        "/",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
    EXEMPT_PREFIXES: tuple[str, ...] = (
        "/api/v1/health",
    )

    def __init__(self, app: Any, jwt_handler: JWTHandler | None = None):
        super().__init__(app)
        self._jwt = jwt_handler or get_jwt_handler()

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        """Extract Bearer token, validate, and stash payload on request state."""
        # Skip auth for exempt paths
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PREFIXES):
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization", "")
        request.state.token_payload = None

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = self._jwt.validate_token(token)
                request.state.token_payload = payload
                logger.debug(
                    "Auth OK: user=%s tenant=%s path=%s",
                    payload.user_id, payload.tenant_id, path,
                )
            except TokenExpiredError:
                logger.debug("Expired token on path=%s", path)
                return JSONResponse(
                    status_code=401,
                    content={"error": "Token expired", "detail": "Please refresh your token"},
                )
            except TokenRevokedError:
                logger.debug("Revoked token on path=%s", path)
                return JSONResponse(
                    status_code=401,
                    content={"error": "Token revoked", "detail": "This token has been revoked"},
                )
            except TokenInvalidError as exc:
                logger.debug("Invalid token on path=%s: %s", path, exc)
                return JSONResponse(
                    status_code=401,
                    content={"error": "Invalid token", "detail": str(exc)},
                )

        return await call_next(request)


# ── FastAPI Dependencies ─────────────────────────────────────────────


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> TokenPayload:
    """
    FastAPI dependency that requires a valid JWT.

    Returns the decoded :class:`TokenPayload` or raises HTTP 401.

    Usage::

        @router.get("/protected")
        async def protected(user: TokenPayload = Depends(require_auth)):
            return {"user_id": user.user_id}
    """
    # First check if middleware already validated
    payload: TokenPayload | None = getattr(request.state, "token_payload", None)
    if payload is not None:
        return payload

    # Fall back to manual extraction (when middleware is not installed)
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required — provide a Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    handler = get_jwt_handler()
    try:
        return handler.validate_token(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenRevokedError:
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenError as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(*required_roles: str) -> Callable:
    """
    FastAPI dependency factory that enforces role-based access.

    The user must hold **at least one** of the specified roles.

    Usage::

        @router.delete("/admin/purge")
        async def purge(user: TokenPayload = Depends(require_role("admin", "superadmin"))):
            ...
    """

    async def _role_checker(
        payload: TokenPayload = Depends(require_auth),
    ) -> TokenPayload:
        user_roles = set(payload.roles)
        allowed = set(required_roles)
        if not user_roles & allowed:
            logger.warning(
                "Insufficient permissions: user=%s has=%s needs_one_of=%s",
                payload.user_id, payload.roles, list(required_roles),
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Insufficient permissions — requires one of: "
                    f"{', '.join(required_roles)}"
                ),
            )
        return payload

    return _role_checker


async def get_current_user(
    payload: TokenPayload = Depends(require_auth),
) -> dict[str, Any]:
    """
    FastAPI dependency that returns a user-info dict.

    Convenience wrapper over ``require_auth`` for endpoints that only
    need the user identity without the full ``TokenPayload``.

    Usage::

        @router.get("/me")
        async def me(user: dict = Depends(get_current_user)):
            return user
    """
    return {
        "user_id": payload.user_id,
        "tenant_id": payload.tenant_id,
        "roles": payload.roles,
        "token_jti": payload.jti,
        "token_expires_at": payload.exp,
    }
