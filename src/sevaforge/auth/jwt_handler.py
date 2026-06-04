"""
SevaForge Auth Layer — JWT Handler

HMAC-SHA256 token creation, validation, refresh, and revocation.
Zero external dependencies — uses stdlib hmac, hashlib, base64, json.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sevaforge.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TokenPayload:
    user_id: str
    tenant_id: str
    roles: list[str]
    exp: float
    iat: float
    jti: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.exp

    @property
    def remaining_seconds(self) -> float:
        return self.exp - time.time()


class TokenError(Exception):
    pass

class TokenExpiredError(TokenError):
    pass

class TokenInvalidError(TokenError):
    pass

class TokenRevokedError(TokenError):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class JWTHandler:
    def __init__(self, secret: str | None = None, algorithm: str | None = None, expire_minutes: int | None = None):
        settings = get_settings()
        self._secret = secret or settings.jwt_secret
        self._algorithm = algorithm or settings.jwt_algorithm
        self._expire_minutes = expire_minutes or settings.jwt_expire_minutes
        self._revoked: set[str] = set()
        self._stats = {"tokens_created": 0, "tokens_validated": 0, "tokens_refreshed": 0, "tokens_revoked": 0, "validation_failures": 0}

    def create_token(self, user_id: str, tenant_id: str, roles: list[str] | None = None, extra_claims: dict[str, Any] | None = None, expire_minutes: int | None = None) -> str:
        now = time.time()
        exp_minutes = expire_minutes or self._expire_minutes
        jti = str(uuid.uuid4())
        payload: dict[str, Any] = {"user_id": user_id, "tenant_id": tenant_id, "roles": roles or [], "exp": now + (exp_minutes * 60), "iat": now, "jti": jti}
        if extra_claims:
            payload.update(extra_claims)
        token = self._encode(payload)
        self._stats["tokens_created"] += 1
        return token

    def validate_token(self, token: str) -> TokenPayload:
        payload = self._decode(token)
        jti = payload.get("jti", "")
        if self.is_revoked(jti):
            self._stats["validation_failures"] += 1
            raise TokenRevokedError(f"Token {jti} has been revoked")
        exp = payload.get("exp", 0)
        if time.time() > exp:
            self._stats["validation_failures"] += 1
            raise TokenExpiredError("Token has expired")
        self._stats["tokens_validated"] += 1
        known_keys = {"user_id", "tenant_id", "roles", "exp", "iat", "jti"}
        extra = {k: v for k, v in payload.items() if k not in known_keys}
        return TokenPayload(user_id=payload.get("user_id", ""), tenant_id=payload.get("tenant_id", ""), roles=payload.get("roles", []), exp=float(payload.get("exp", 0)), iat=float(payload.get("iat", 0)), jti=payload.get("jti", ""), extra=extra)

    def refresh_token(self, token: str) -> str:
        payload = self.validate_token(token)
        new_token = self.create_token(user_id=payload.user_id, tenant_id=payload.tenant_id, roles=payload.roles, extra_claims=payload.extra or None)
        self._stats["tokens_refreshed"] += 1
        return new_token

    def revoke_token(self, jti: str) -> None:
        self._revoked.add(jti)
        self._stats["tokens_revoked"] += 1

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    def stats(self) -> dict[str, Any]:
        return {**self._stats, "revoked_count": len(self._revoked), "expire_minutes": self._expire_minutes, "algorithm": self._algorithm}

    def reset(self) -> None:
        self._revoked.clear()
        self._stats = {k: 0 for k in self._stats}

    def _encode(self, payload: dict[str, Any]) -> str:
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.new(self._secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        sig_b64 = _b64url_encode(signature)
        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def _decode(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Token must have three dot-separated parts")
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(self._secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        try:
            actual_sig = _b64url_decode(sig_b64)
        except Exception:
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Malformed signature encoding")
        if not hmac.compare_digest(expected_sig, actual_sig):
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Invalid token signature")
        try:
            payload_bytes = _b64url_decode(payload_b64)
            payload: dict[str, Any] = json.loads(payload_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Malformed token payload")
        return payload
