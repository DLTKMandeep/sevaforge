"""
SevaForge Auth Layer — JWT Handler

HMAC-SHA256 token creation, validation, refresh, and revocation.
Zero external dependencies — uses stdlib hmac, hashlib, base64, json.

Tokens follow the standard JWT structure:
    base64url(header) . base64url(payload) . base64url(signature)
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


# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class TokenPayload:
    """Decoded JWT payload with all standard and custom claims."""

    user_id: str
    tenant_id: str
    roles: list[str]
    exp: float          # Expiry timestamp (epoch seconds)
    iat: float          # Issued-at timestamp (epoch seconds)
    jti: str            # Unique token identifier
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check whether this token has expired."""
        return time.time() > self.exp

    @property
    def remaining_seconds(self) -> float:
        """Seconds until expiry (negative if already expired)."""
        return self.exp - time.time()


# ── Exceptions ───────────────────────────────────────────────────────


class TokenError(Exception):
    """Base exception for all token-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a token has passed its expiry time."""


class TokenInvalidError(TokenError):
    """Raised when a token signature is invalid or structure is malformed."""


class TokenRevokedError(TokenError):
    """Raised when a token has been explicitly revoked."""


# ── Helpers ──────────────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    """Base64url-encode bytes without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64url-decode a string, restoring padding."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


# ── JWT Handler ──────────────────────────────────────────────────────


class JWTHandler:
    """
    HMAC-SHA256 JWT handler for SevaForge.

    Creates, validates, refreshes, and revokes tokens using only the
    Python standard library.  Tokens are standard three-part JWTs that
    can be inspected with any JWT debugger.

    Usage::

        handler = JWTHandler()
        token = handler.create_token("user-42", "tenant-1", ["admin"])
        payload = handler.validate_token(token)
        print(payload.user_id)  # "user-42"
    """

    def __init__(
        self,
        secret: str | None = None,
        algorithm: str | None = None,
        expire_minutes: int | None = None,
    ):
        settings = get_settings()
        self._secret = secret or settings.jwt_secret
        self._algorithm = algorithm or settings.jwt_algorithm
        self._expire_minutes = expire_minutes or settings.jwt_expire_minutes

        # Revocation set — jti values of revoked tokens
        self._revoked: set[str] = set()

        # Observability counters
        self._stats = {
            "tokens_created": 0,
            "tokens_validated": 0,
            "tokens_refreshed": 0,
            "tokens_revoked": 0,
            "validation_failures": 0,
        }

    # ── Token Creation ───────────────────────────────────────────────

    def create_token(
        self,
        user_id: str,
        tenant_id: str,
        roles: list[str] | None = None,
        extra_claims: dict[str, Any] | None = None,
        expire_minutes: int | None = None,
    ) -> str:
        """
        Create a signed JWT for the given user.

        Args:
            user_id:        Unique user identifier.
            tenant_id:      Tenant / organisation identifier.
            roles:          List of role strings (e.g. ``["admin", "viewer"]``).
            extra_claims:   Arbitrary additional claims merged into the payload.
            expire_minutes: Override default expiry for this token.

        Returns:
            A compact JWT string: ``header.payload.signature``.
        """
        now = time.time()
        exp_minutes = expire_minutes or self._expire_minutes
        jti = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "roles": roles or [],
            "exp": now + (exp_minutes * 60),
            "iat": now,
            "jti": jti,
        }
        if extra_claims:
            payload.update(extra_claims)

        token = self._encode(payload)
        self._stats["tokens_created"] += 1
        logger.debug(
            "Token created: user=%s tenant=%s jti=%s exp_min=%d",
            user_id, tenant_id, jti, exp_minutes,
        )
        return token

    # ── Token Validation ─────────────────────────────────────────────

    def validate_token(self, token: str) -> TokenPayload:
        """
        Validate a JWT and return the decoded payload.

        Raises:
            TokenInvalidError:  Malformed token or bad signature.
            TokenExpiredError:  Token has passed its ``exp`` claim.
            TokenRevokedError:  Token ``jti`` is in the revocation set.
        """
        payload = self._decode(token)

        # Check revocation
        jti = payload.get("jti", "")
        if self.is_revoked(jti):
            self._stats["validation_failures"] += 1
            raise TokenRevokedError(f"Token {jti} has been revoked")

        # Check expiry
        exp = payload.get("exp", 0)
        if time.time() > exp:
            self._stats["validation_failures"] += 1
            raise TokenExpiredError("Token has expired")

        self._stats["tokens_validated"] += 1

        # Extract known fields; anything else goes into ``extra``
        known_keys = {"user_id", "tenant_id", "roles", "exp", "iat", "jti"}
        extra = {k: v for k, v in payload.items() if k not in known_keys}

        return TokenPayload(
            user_id=payload.get("user_id", ""),
            tenant_id=payload.get("tenant_id", ""),
            roles=payload.get("roles", []),
            exp=float(payload.get("exp", 0)),
            iat=float(payload.get("iat", 0)),
            jti=payload.get("jti", ""),
            extra=extra,
        )

    # ── Token Refresh ────────────────────────────────────────────────

    def refresh_token(self, token: str) -> str:
        """
        Issue a new token if the existing one is still valid.

        The old token is **not** automatically revoked — call
        :meth:`revoke_token` explicitly if you want single-use refresh.

        Raises:
            Same exceptions as :meth:`validate_token`.
        """
        payload = self.validate_token(token)
        new_token = self.create_token(
            user_id=payload.user_id,
            tenant_id=payload.tenant_id,
            roles=payload.roles,
            extra_claims=payload.extra or None,
        )
        self._stats["tokens_refreshed"] += 1
        logger.debug("Token refreshed: user=%s old_jti=%s", payload.user_id, payload.jti)
        return new_token

    # ── Revocation ───────────────────────────────────────────────────

    def revoke_token(self, jti: str) -> None:
        """
        Add a token's JTI to the revocation set.

        Once revoked, any future :meth:`validate_token` call for this
        JTI will raise :exc:`TokenRevokedError`.
        """
        self._revoked.add(jti)
        self._stats["tokens_revoked"] += 1
        logger.info("Token revoked: jti=%s", jti)

    def is_revoked(self, jti: str) -> bool:
        """Check whether a JTI has been revoked."""
        return jti in self._revoked

    # ── Stats & Admin ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return handler statistics for observability dashboards."""
        return {
            **self._stats,
            "revoked_count": len(self._revoked),
            "expire_minutes": self._expire_minutes,
            "algorithm": self._algorithm,
        }

    def reset(self) -> None:
        """Clear all state — for testing only."""
        self._revoked.clear()
        self._stats = {k: 0 for k in self._stats}

    # ── Internal Encoding / Decoding ─────────────────────────────────

    def _encode(self, payload: dict[str, Any]) -> str:
        """Build a signed JWT from a payload dict."""
        header = {"alg": "HS256", "typ": "JWT"}
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())

        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self._secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()
        sig_b64 = _b64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{sig_b64}"

    def _decode(self, token: str) -> dict[str, Any]:
        """Verify signature and return the payload dict."""
        parts = token.split(".")
        if len(parts) != 3:
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Token must have three dot-separated parts")

        header_b64, payload_b64, sig_b64 = parts

        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}"
        expected_sig = hmac.new(
            self._secret.encode(),
            signing_input.encode(),
            hashlib.sha256,
        ).digest()

        try:
            actual_sig = _b64url_decode(sig_b64)
        except Exception:
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Malformed signature encoding")

        if not hmac.compare_digest(expected_sig, actual_sig):
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Invalid token signature")

        # Decode payload
        try:
            payload_bytes = _b64url_decode(payload_b64)
            payload: dict[str, Any] = json.loads(payload_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._stats["validation_failures"] += 1
            raise TokenInvalidError("Malformed token payload")

        return payload
