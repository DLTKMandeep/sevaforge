"""
SevaForge API Connector Framework — US-049

Pluggable external API integration layer with authentication, retry,
rate limiting, and observability. Designed for zero external dependencies
in mock mode; real HTTP clients are injected via configure_client().

Architecture:
    ConnectorConfig → Register → call(method, path, ...) → Auth + Retry + Rate Limit → APIResponse
    Mock mode: _http_client is None → simulated responses for development/testing
    Production: configure_client(httpx.AsyncClient) or any compatible client
"""

from __future__ import annotations

import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class AuthScheme(str, Enum):
    """Supported authentication schemes for API connectors."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class ConnectorConfig:
    """
    Configuration for an external API connector.

    Holds connection details, authentication, retry policy, and
    rate limiting parameters for a single API integration.
    """

    connector_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    base_url: str = ""
    auth_scheme: AuthScheme = AuthScheme.NONE
    auth_config: dict[str, Any] = field(default_factory=dict)
    default_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 30
    retry_max: int = 3
    retry_backoff_factor: float = 0.5
    rate_limit_rpm: int = 60
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise config, redacting sensitive auth values."""
        auth_safe = {k: "***" for k in self.auth_config}
        return {
            "connector_id": self.connector_id,
            "name": self.name,
            "base_url": self.base_url,
            "auth_scheme": self.auth_scheme.value,
            "auth_config_keys": list(self.auth_config.keys()),
            "default_headers": {
                k: (v if "auth" not in k.lower() and "key" not in k.lower() else "***")
                for k, v in self.default_headers.items()
            },
            "timeout_seconds": self.timeout_seconds,
            "retry_max": self.retry_max,
            "retry_backoff_factor": self.retry_backoff_factor,
            "rate_limit_rpm": self.rate_limit_rpm,
            "is_active": self.is_active,
        }


@dataclass
class APIResponse:
    """
    Structured response from an external API call.

    Captures status, headers, body, timing, and provenance metadata
    for observability and debugging.
    """

    status_code: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    elapsed_ms: float = 0.0
    connector_id: str = ""
    request_url: str = ""
    request_method: str = ""

    @property
    def success(self) -> bool:
        """True when the status code indicates success (2xx)."""
        return 200 <= self.status_code < 300

    def to_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "success": self.success,
            "elapsed_ms": round(self.elapsed_ms, 2),
            "connector_id": self.connector_id,
            "request_url": self.request_url,
            "request_method": self.request_method,
            "body_preview": str(self.body)[:200] if self.body else None,
        }


# ── HTTP Client Protocol ─────────────────────────────────────────────


@runtime_checkable
class HTTPClient(Protocol):
    """
    Protocol that pluggable HTTP clients must satisfy.

    Any object implementing this interface can be injected via
    APIConnector.configure_client(). Compatible with httpx, aiohttp
    wrappers, or custom test doubles.
    """

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        timeout: int | None = None,
    ) -> Any:
        """
        Execute an HTTP request.

        Must return an object with:
            .status_code (int)
            .headers (dict-like)
            .json() or .text (response body)
        """
        ...


# ── Rate Limiter ─────────────────────────────────────────────────────


class _TokenBucketRateLimiter:
    """
    Simple token-bucket rate limiter per connector.

    Tracks request timestamps within a rolling 60-second window
    and rejects calls that would exceed the configured RPM.
    """

    def __init__(self) -> None:
        # connector_id → list of request timestamps
        self._windows: dict[str, list[float]] = {}

    def allow(self, connector_id: str, rpm: int) -> bool:
        """Return True if the request is within rate limits."""
        now = time.monotonic()
        window = self._windows.setdefault(connector_id, [])

        # Prune timestamps older than 60 seconds
        cutoff = now - 60.0
        self._windows[connector_id] = [t for t in window if t > cutoff]
        window = self._windows[connector_id]

        if len(window) >= rpm:
            return False

        window.append(now)
        return True

    def reset(self, connector_id: str | None = None) -> None:
        """Clear rate limit state."""
        if connector_id:
            self._windows.pop(connector_id, None)
        else:
            self._windows.clear()


# ── API Connector ────────────────────────────────────────────────────


class APIConnector:
    """
    External API connector framework.

    Manages multiple API integrations, each identified by a ConnectorConfig.
    Handles authentication injection, retry with exponential backoff,
    per-connector rate limiting, and observability.

    Mock mode (default):
        When no HTTP client is configured, call() returns simulated
        responses for development and testing.

    Production mode:
        Inject a real HTTP client via configure_client(client).

    Usage:
        connector = APIConnector()
        connector.register_connector(ConnectorConfig(
            name="github",
            base_url="https://api.github.com",
            auth_scheme=AuthScheme.BEARER,
            auth_config={"token": "ghp_xxx"},
        ))
        response = connector.call("github-id", "GET", "/repos/owner/repo")
    """

    # Retryable HTTP status codes
    _RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(self) -> None:
        self._connectors: dict[str, ConnectorConfig] = {}
        self._http_client: HTTPClient | None = None
        self._rate_limiter = _TokenBucketRateLimiter()
        self._stats = {
            "total_requests": 0,
            "successes": 0,
            "failures": 0,
            "retries": 0,
            "rate_limited": 0,
        }

    # ── Client Configuration ─────────────────────────────────────────

    def configure_client(self, client: HTTPClient) -> None:
        """
        Inject a real HTTP client for production use.

        The client must satisfy the HTTPClient protocol:
            client.request(method, url, headers, params, json, timeout) → response

        Args:
            client: An HTTP client instance (e.g. httpx.Client wrapper).
        """
        self._http_client = client
        logger.info(
            "API connector configured with HTTP client: %s",
            type(client).__name__,
        )

    # ── Connector Registration ───────────────────────────────────────

    def register_connector(self, config: ConnectorConfig) -> ConnectorConfig:
        """
        Register an external API connector.

        Args:
            config: The connector configuration to register.

        Returns:
            The registered ConnectorConfig.
        """
        self._connectors[config.connector_id] = config
        logger.info(
            "Registered connector '%s' (id=%s, base_url=%s, auth=%s)",
            config.name,
            config.connector_id,
            config.base_url,
            config.auth_scheme.value,
        )
        return config

    def unregister_connector(self, connector_id: str) -> bool:
        """
        Remove a connector from the registry.

        Also clears its rate limit state.

        Returns:
            True if found and removed, False otherwise.
        """
        if connector_id not in self._connectors:
            logger.warning("Unregister failed: connector_id '%s' not found", connector_id)
            return False

        name = self._connectors[connector_id].name
        del self._connectors[connector_id]
        self._rate_limiter.reset(connector_id)
        logger.info("Unregistered connector '%s' (id=%s)", name, connector_id)
        return True

    def get_connector(self, connector_id: str) -> ConnectorConfig | None:
        """Look up a connector by ID."""
        return self._connectors.get(connector_id)

    def list_connectors(self, active_only: bool = True) -> list[ConnectorConfig]:
        """
        Return registered connectors.

        Args:
            active_only: When True (default), exclude inactive connectors.
        """
        return [
            c for c in self._connectors.values()
            if not active_only or c.is_active
        ]

    # ── API Call ─────────────────────────────────────────────────────

    def call(
        self,
        connector_id: str,
        method: str,
        path: str = "",
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> APIResponse:
        """
        Execute an API call through a registered connector.

        Builds the full URL, injects authentication headers, applies
        rate limiting, and retries on transient failures with
        exponential backoff.

        Args:
            connector_id: The registered connector to use.
            method: HTTP method (GET, POST, PUT, DELETE, PATCH).
            path: URL path appended to the connector's base_url.
            params: Query parameters.
            headers: Additional request headers (merged with defaults).
            body: Request body (serialised as JSON).

        Returns:
            APIResponse with status, headers, body, and timing.

        Raises:
            ValueError: If the connector_id is not registered or inactive.
        """
        config = self._connectors.get(connector_id)
        if config is None:
            raise ValueError(f"Unknown connector: '{connector_id}'")
        if not config.is_active:
            raise ValueError(f"Connector '{connector_id}' is inactive")

        # Rate limiting
        if not self._rate_limiter.allow(connector_id, config.rate_limit_rpm):
            self._stats["rate_limited"] += 1
            logger.warning(
                "Rate limited: connector '%s' exceeded %d RPM",
                config.name,
                config.rate_limit_rpm,
            )
            return APIResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                body={"error": "Rate limit exceeded", "rpm_limit": config.rate_limit_rpm},
                elapsed_ms=0.0,
                connector_id=connector_id,
                request_url=self._build_url(config.base_url, path),
                request_method=method.upper(),
            )

        # Build request
        url = self._build_url(config.base_url, path)
        merged_headers = {**config.default_headers}
        merged_headers.update(self._build_auth_headers(config))
        if headers:
            merged_headers.update(headers)

        self._stats["total_requests"] += 1

        # Execute with retry
        response = self._execute_with_retry(
            config=config,
            method=method.upper(),
            url=url,
            headers=merged_headers,
            params=params,
            body=body,
        )

        if response.success:
            self._stats["successes"] += 1
        else:
            self._stats["failures"] += 1

        return response

    def _execute_with_retry(
        self,
        config: ConnectorConfig,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        body: Any | None,
    ) -> APIResponse:
        """
        Execute the HTTP request with exponential backoff retry.

        Retries on status codes 429, 500, 502, 503, 504 up to
        config.retry_max times.
        """
        last_response: APIResponse | None = None

        for attempt in range(config.retry_max + 1):
            start = time.monotonic()

            try:
                response = self._do_request(
                    config=config,
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    body=body,
                )
            except Exception as exc:
                elapsed = (time.monotonic() - start) * 1000
                logger.error(
                    "Request error: connector='%s' method=%s url=%s attempt=%d error=%s",
                    config.name, method, url, attempt + 1, exc,
                )
                last_response = APIResponse(
                    status_code=0,
                    headers={},
                    body={"error": str(exc)},
                    elapsed_ms=elapsed,
                    connector_id=config.connector_id,
                    request_url=url,
                    request_method=method,
                )
                if not self._should_retry(0, attempt, config.retry_max):
                    break
                self._stats["retries"] += 1
                self._backoff_sleep(attempt, config.retry_backoff_factor)
                continue

            elapsed = (time.monotonic() - start) * 1000
            api_response = APIResponse(
                status_code=response.get("status_code", 200),
                headers=response.get("headers", {}),
                body=response.get("body"),
                elapsed_ms=elapsed,
                connector_id=config.connector_id,
                request_url=url,
                request_method=method,
            )
            last_response = api_response

            if not self._should_retry(api_response.status_code, attempt, config.retry_max):
                break

            self._stats["retries"] += 1
            logger.info(
                "Retrying: connector='%s' status=%d attempt=%d/%d",
                config.name, api_response.status_code, attempt + 1, config.retry_max,
            )
            self._backoff_sleep(attempt, config.retry_backoff_factor)

        return last_response  # type: ignore[return-value]

    def _do_request(
        self,
        config: ConnectorConfig,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        body: Any | None,
    ) -> dict[str, Any]:
        """
        Perform the actual HTTP request.

        If a real HTTP client is configured, delegates to it.
        Otherwise returns a mock/simulated response for development.
        """
        if self._http_client is not None:
            raw = self._http_client.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body,
                timeout=config.timeout_seconds,
            )
            # Normalise the response into a plain dict
            resp_headers: dict[str, str] = {}
            if hasattr(raw, "headers"):
                try:
                    resp_headers = dict(raw.headers)
                except Exception:
                    resp_headers = {}

            resp_body: Any = None
            if hasattr(raw, "json"):
                try:
                    resp_body = raw.json()
                except Exception:
                    resp_body = getattr(raw, "text", str(raw))
            else:
                resp_body = getattr(raw, "text", str(raw))

            return {
                "status_code": getattr(raw, "status_code", 200),
                "headers": resp_headers,
                "body": resp_body,
            }

        # ── Mock mode ────────────────────────────────────────────────
        logger.debug(
            "Mock request: %s %s (connector='%s')",
            method, url, config.name,
        )
        return {
            "status_code": 200,
            "headers": {
                "Content-Type": "application/json",
                "X-SevaForge-Mock": "true",
            },
            "body": {
                "mock": True,
                "connector": config.name,
                "method": method,
                "url": url,
                "message": "Mock response — configure a real HTTP client for production.",
            },
        }

    # ── Auth Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _build_auth_headers(config: ConnectorConfig) -> dict[str, str]:
        """
        Build authentication headers based on the connector's auth scheme.

        Supported schemes:
            API_KEY: Injects an API key via a configurable header name.
            BEARER: Adds a Bearer token in the Authorization header.
            BASIC: Base64-encodes username:password for Basic auth.
            OAUTH2: Adds the OAuth2 access token as a Bearer token.
            NONE: Returns empty headers.
        """
        scheme = config.auth_scheme
        auth = config.auth_config

        if scheme == AuthScheme.API_KEY:
            header_name = auth.get("header", "X-API-Key")
            api_key = auth.get("api_key", "")
            if api_key:
                return {header_name: api_key}

        elif scheme == AuthScheme.BEARER:
            token = auth.get("token", "")
            if token:
                return {"Authorization": f"Bearer {token}"}

        elif scheme == AuthScheme.BASIC:
            username = auth.get("username", "")
            password = auth.get("password", "")
            if username:
                credentials = base64.b64encode(
                    f"{username}:{password}".encode()
                ).decode("ascii")
                return {"Authorization": f"Basic {credentials}"}

        elif scheme == AuthScheme.OAUTH2:
            access_token = auth.get("access_token", "")
            if access_token:
                return {"Authorization": f"Bearer {access_token}"}

        return {}

    # ── Retry Helpers ────────────────────────────────────────────────

    @classmethod
    def _should_retry(cls, status_code: int, attempt: int, max_retries: int) -> bool:
        """
        Determine whether the request should be retried.

        Retries on connection errors (status_code == 0) and transient
        server errors (429, 500, 502, 503, 504).
        """
        if attempt >= max_retries:
            return False
        if status_code == 0:
            return True  # Connection error
        return status_code in cls._RETRYABLE_STATUSES

    @staticmethod
    def _backoff_sleep(attempt: int, factor: float) -> None:
        """Sleep with exponential backoff: factor * 2^attempt seconds."""
        delay = factor * (2 ** attempt)
        time.sleep(delay)

    @staticmethod
    def _build_url(base_url: str, path: str) -> str:
        """
        Combine base URL and path, ensuring exactly one slash between them.
        """
        if not path:
            return base_url.rstrip("/")
        return base_url.rstrip("/") + "/" + path.lstrip("/")

    # ── Stats & Reset ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return connector-level statistics."""
        return {
            **self._stats,
            "registered_connectors": len(self._connectors),
            "active_connectors": sum(
                1 for c in self._connectors.values() if c.is_active
            ),
            "mock_mode": self._http_client is None,
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._connectors.clear()
        self._http_client = None
        self._rate_limiter.reset()
        self._stats = {k: 0 for k in self._stats}
