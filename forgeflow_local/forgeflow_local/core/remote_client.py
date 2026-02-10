"""
ForgeFlow Remote Client

HTTP/SSE client for connecting to remote MCP endpoints in PUBLIC mode.
Handles authentication, retries, timeouts, and both REST and streaming responses.

Usage:
    client = RemoteClient(config)
    result = client.dispatch("discovery", {"path": "/my/repo"})
"""
import os
import json
import time
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, Any, Optional, Generator, Callable
from datetime import datetime


class RemoteClientError(Exception):
    """Exception raised for remote client errors."""
    pass


class AuthenticationError(RemoteClientError):
    """Exception raised for authentication failures."""
    pass


class ConnectionError(RemoteClientError):
    """Exception raised for connection failures."""
    pass


class RemoteClient:
    """
    HTTP client for remote MCP endpoints.
    
    Supports:
    - API key, OAuth, and token authentication
    - Request retries with exponential backoff
    - Configurable timeouts
    - REST and SSE streaming responses
    """
    
    # Map command names to endpoint keys
    COMMAND_TO_ENDPOINT = {
        "discover": "discovery",
        "normalize": "normalize",
        "scan": "security",
        "generate": "deployment",
        "docs": "docs",
        "review": "git",
        "test": "cicd",
        "deploy": "cloud",
        "monitor": "observability",
        "bridge": "github",
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the remote client with public mode configuration.
        
        Args:
            config: Public mode configuration from forgeflow-config.yaml
        """
        self.config = config
        self.base_url = config.get("api_base_url", "")
        self.endpoints = config.get("endpoints", {})
        self.auth_config = config.get("auth", {})
        self.connection_config = config.get("connection", {})
        self.streaming_config = config.get("streaming", {})
        
        # Connection settings
        self.timeout = self.connection_config.get("timeout", 60)
        self.retries = self.connection_config.get("retries", 3)
        self.retry_delay = self.connection_config.get("retry_delay", 2)
        self.verify_ssl = self.connection_config.get("verify_ssl", True)
        
        # Auth token (loaded lazily)
        self._auth_token: Optional[str] = None
        self._oauth_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def get_api_key(self) -> Optional[str]:
        """Get API key from environment variable."""
        env_var = self.auth_config.get("api_key_env", "FORGEFLOW_API_KEY")
        return os.environ.get(env_var)
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers based on auth type."""
        auth_type = self.auth_config.get("type", "api_key")
        headers = {}
        
        if auth_type == "api_key":
            api_key = self.get_api_key()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                headers["X-API-Key"] = api_key
        
        elif auth_type == "oauth":
            token = self._get_oauth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        
        elif auth_type == "token":
            token_env = self.auth_config.get("token_env", "FORGEFLOW_TOKEN")
            token = os.environ.get(token_env)
            if token:
                headers["Authorization"] = f"Bearer {token}"
        
        return headers
    
    def _get_oauth_token(self) -> Optional[str]:
        """Get or refresh OAuth token."""
        # Check if we have a valid cached token
        if self._oauth_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._oauth_token
        
        # Get new token
        oauth_config = self.auth_config.get("oauth", {})
        client_id = os.environ.get(oauth_config.get("client_id_env", ""))
        client_secret = os.environ.get(oauth_config.get("client_secret_env", ""))
        token_url = oauth_config.get("token_url", "")
        
        if not all([client_id, client_secret, token_url]):
            return None
        
        try:
            data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret
            }).encode()
            
            req = urllib.request.Request(token_url, data=data, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode())
                self._oauth_token = result.get("access_token")
                expires_in = result.get("expires_in", 3600)
                self._token_expiry = datetime.now()
                return self._oauth_token
                
        except Exception as e:
            raise AuthenticationError(f"OAuth token refresh failed: {str(e)}")
    
    def get_endpoint_url(self, command: str) -> str:
        """
        Get the endpoint URL for a given command.
        
        Args:
            command: CLI command name (discover, scan, etc.)
            
        Returns:
            Full endpoint URL
        """
        endpoint_key = self.COMMAND_TO_ENDPOINT.get(command, command)
        
        # Check for specific endpoint URL
        if endpoint_key in self.endpoints:
            return self.endpoints[endpoint_key]
        
        # Fall back to base URL with endpoint path
        if self.base_url:
            return f"{self.base_url.rstrip('/')}/mcp/{endpoint_key}"
        
        raise RemoteClientError(f"No endpoint configured for command '{command}'")
    
    def is_configured(self) -> bool:
        """Check if the remote client is properly configured."""
        # Must have either base_url or endpoints
        if not self.base_url and not self.endpoints:
            return False
        
        # Must have some form of authentication configured
        api_key = self.get_api_key()
        if not api_key and self.auth_config.get("type") == "api_key":
            return False
        
        return True
    
    def check_api_key(self) -> tuple[bool, str]:
        """
        Check if API key is configured and valid.
        
        Returns:
            Tuple of (is_valid, message)
        """
        api_key = self.get_api_key()
        if not api_key:
            env_var = self.auth_config.get("api_key_env", "FORGEFLOW_API_KEY")
            return False, f"API key not set. Set {env_var} environment variable."
        
        # Basic validation (actual validation would be server-side)
        if len(api_key) < 10:
            return False, "API key appears to be invalid (too short)"
        
        return True, "API key configured"
    
    def dispatch(
        self, 
        command: str, 
        params: Dict[str, Any],
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Dispatch a task to a remote MCP endpoint.
        
        Args:
            command: CLI command name (discover, scan, etc.)
            params: Parameters to send to the MCP server
            stream_callback: Optional callback for streaming responses
            
        Returns:
            Result dictionary from the remote MCP server
        """
        url = self.get_endpoint_url(command)
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        
        # Add streaming header if callback provided
        if stream_callback and self.streaming_config.get("enabled", True):
            headers["Accept"] = "text/event-stream"
        
        # Build request payload
        payload = {
            "command": command,
            "params": params,
            "timestamp": datetime.now().isoformat(),
            "client_version": "1.0.0"
        }
        
        # Retry loop
        last_error = None
        for attempt in range(self.retries):
            try:
                result = self._make_request(url, headers, payload, stream_callback)
                return result
                
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise AuthenticationError(f"Authentication failed: {e.reason}")
                elif e.code == 403:
                    raise AuthenticationError(f"Access forbidden: {e.reason}")
                elif e.code >= 500:
                    # Server error, retry
                    last_error = e
                    if attempt < self.retries - 1:
                        delay = self.retry_delay * (2 ** attempt)
                        time.sleep(delay)
                        continue
                else:
                    # Client error, don't retry
                    error_body = e.read().decode() if hasattr(e, 'read') else str(e)
                    raise RemoteClientError(f"Request failed ({e.code}): {error_body}")
                    
            except urllib.error.URLError as e:
                last_error = e
                if attempt < self.retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
                    
            except Exception as e:
                last_error = e
                if attempt < self.retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    time.sleep(delay)
                    continue
        
        # All retries exhausted
        raise ConnectionError(f"Failed to connect after {self.retries} attempts: {str(last_error)}")
    
    def _make_request(
        self, 
        url: str, 
        headers: Dict[str, str], 
        payload: Dict[str, Any],
        stream_callback: Optional[Callable[[str], None]] = None
    ) -> Dict[str, Any]:
        """
        Make the actual HTTP request.
        
        Args:
            url: Endpoint URL
            headers: Request headers
            payload: Request payload
            stream_callback: Optional callback for streaming responses
            
        Returns:
            Parsed response data
        """
        data = json.dumps(payload).encode('utf-8')
        
        req = urllib.request.Request(url, data=data, method="POST")
        for key, value in headers.items():
            req.add_header(key, value)
        
        # SSL context for verification
        import ssl
        if self.verify_ssl:
            context = ssl.create_default_context()
        else:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=self.timeout, context=context) as response:
            content_type = response.headers.get('Content-Type', '')
            
            # Handle streaming response
            if 'text/event-stream' in content_type and stream_callback:
                return self._handle_sse_response(response, stream_callback)
            
            # Handle regular JSON response
            response_data = response.read().decode('utf-8')
            return json.loads(response_data)
    
    def _handle_sse_response(
        self, 
        response, 
        callback: Callable[[str], None]
    ) -> Dict[str, Any]:
        """
        Handle Server-Sent Events streaming response.
        
        Args:
            response: HTTP response object
            callback: Function to call for each event
            
        Returns:
            Final result after stream ends
        """
        final_result = None
        buffer = ""
        
        while True:
            chunk = response.read(1024).decode('utf-8')
            if not chunk:
                break
            
            buffer += chunk
            
            # Parse SSE events
            while '\n\n' in buffer:
                event_str, buffer = buffer.split('\n\n', 1)
                event = self._parse_sse_event(event_str)
                
                if event:
                    event_type = event.get('event', 'message')
                    event_data = event.get('data', '')
                    
                    if event_type == 'progress':
                        callback(event_data)
                    elif event_type == 'result':
                        final_result = json.loads(event_data)
                    elif event_type == 'error':
                        raise RemoteClientError(f"Server error: {event_data}")
        
        return final_result or {"status": "success", "summary": "Streaming completed"}
    
    def _parse_sse_event(self, event_str: str) -> Optional[Dict[str, str]]:
        """Parse a single SSE event string."""
        event = {}
        for line in event_str.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                event[key.strip()] = value.strip()
        return event if event else None
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check the health of the remote ForgeFlow service.
        
        Returns:
            Health status dictionary
        """
        # Try to reach the base health endpoint
        if self.base_url:
            health_url = f"{self.base_url.rstrip('/')}/health"
        else:
            # Use first available endpoint with /health suffix
            first_endpoint = list(self.endpoints.values())[0] if self.endpoints else None
            if not first_endpoint:
                return {"status": "error", "message": "No endpoints configured"}
            # Extract base from endpoint
            parts = first_endpoint.rsplit('/mcp/', 1)
            health_url = f"{parts[0]}/health" if len(parts) > 1 else f"{first_endpoint}/health"
        
        try:
            headers = self._get_auth_headers()
            req = urllib.request.Request(health_url, method="GET")
            for key, value in headers.items():
                req.add_header(key, value)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                return {
                    "status": "healthy",
                    "endpoint": health_url,
                    "details": data
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "endpoint": health_url,
                "error": str(e)
            }
    
    def get_service_info(self) -> Dict[str, Any]:
        """Get information about the connected remote service."""
        return {
            "mode": "public",
            "base_url": self.base_url,
            "endpoints_configured": len(self.endpoints),
            "auth_type": self.auth_config.get("type", "api_key"),
            "streaming_enabled": self.streaming_config.get("enabled", True),
            "timeout": self.timeout,
            "retries": self.retries
        }


def create_remote_client(forgeflow_config: Dict[str, Any]) -> RemoteClient:
    """
    Factory function to create a RemoteClient from ForgeFlow config.
    
    Args:
        forgeflow_config: Full ForgeFlow configuration dictionary
        
    Returns:
        Configured RemoteClient instance
    """
    public_config = forgeflow_config.get("public", {})
    return RemoteClient(public_config)
