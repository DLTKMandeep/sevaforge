"""
SevaForge Auth Layer — FastAPI Middleware & Dependencies

Provides request-level authentication and role-based authorisation.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from sevaforge.auth.jwt_handler import (
    JWTHandler, TokenError, TokenExpiredError, TokenInvalidError, TokenPayload, TokenRevokedError,
)

logger = logging.getLogger(__name__)

_jwt_handler: JWTHandler | None = None

def get_jwt_handler() -> JWTHandler:
    global _jwt_handler
    if _jwt_handler is None:
        _jwt_handler = JWTHandler()
    return _jwt_handler

def set_jwt_handler(handler: JWTHandler) -> None:
    global _jwt_handler
    _jwt_handler = handler

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    EXEMPT_PATHS: set[str] = {"/", "/docs", "/redoc", "/openapi.json"}
    EXEMPT_PREFIXES: tuple[str, ...] = ("/api/v1/health",)

    def __init__(self, app: Any, jwt_handler: JWTHandler | None = None):
        super().__init__(app)
        self._jwt = jwt_handler or get_jwt_handler()

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        path = request.url.path
        if path in self.EXEMPT_PATHS or path.startswith(self.EXEMPT_PREFIXES):
            return await call_next(request)
        auth_header = request.headers.get("Authorization", "")
        request.state.token_payload = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = self._jwt.validate_token(token)
                request.state.token_payload = payload
            except TokenExpiredError:
                return JSONResponse(status_code=401, content={"error": "Token expired"})
            except TokenRevokedError:
                return JSONResponse(status_code=401, content={"error": "Token revoked"})
            except TokenInvalidError as exc:
                return JSONResponse(status_code=401, content={"error": "Invalid token", "detail": str(exc)})
        return await call_next(request)


async def require_auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme)) -> TokenPayload:
    payload: TokenPayload | None = getattr(request.state, "token_payload", None)
    if payload is not None:
        return payload
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Bearer"})
    handler = get_jwt_handler()
    try:
        return handler.validate_token(credentials.credentials)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"})
    except TokenRevokedError:
        raise HTTPException(status_code=401, detail="Token has been revoked", headers={"WWW-Authenticate": "Bearer"})
    except TokenInvalidError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}", headers={"WWW-Authenticate": "Bearer"})
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc), headers={"WWW-Authenticate": "Bearer"})


def require_role(*required_roles: str) -> Callable:
    async def _role_checker(payload: TokenPayload = Depends(require_auth)) -> TokenPayload:
        user_roles = set(payload.roles)
        allowed = set(required_roles)
        if not user_roles & allowed:
            raise HTTPException(status_code=403, detail=f"Insufficient permissions — requires one of: {', '.join(required_roles)}")
        return payload
    return _role_checker


async def get_current_user(payload: TokenPayload = Depends(require_auth)) -> dict[str, Any]:
    return {"user_id": payload.user_id, "tenant_id": payload.tenant_id, "roles": payload.roles, "token_jti": payload.jti, "token_expires_at": payload.exp}
