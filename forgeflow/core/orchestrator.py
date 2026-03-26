"""
ForgeFlow MCP Orchestrator
Manages MCP server lifecycle (lazy start) and task dispatching.

Supports deployment modes:
- LOCAL: All MCPs run as local subprocesses
- HYBRID: Mix of local MCPs and public/remote MCPs
- PUBLIC: All MCPs run remotely (thin client mode)

Responsibilities:
1. Load mcp-config.yaml and forgeflow-config.yaml
2. Manage server lifecycle via ensure_server() - lazy start with subprocess.Popen
3. Dispatch tasks to appropriate MCP servers based on deployment mode
4. In PUBLIC mode, use RemoteClient instead of local subprocess
5. Handle fallback to local servers when public servers unavailable
6. Wrap MCP responses with orchestration metadata
7. Aggregate and return results

Data Flow:
    Request:  Mission Control → Orchestrator → MCP Server → Agent
    Response: Mission Control ← Orchestrator ← MCP Server ← Agent
    
    Orchestrator adds: mission type, deployment mode, execution time, server info
"""
import os
import sys
import yaml
import json
import logging
import time
import importlib.util
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

from .models import wrap_mcp_response, create_error_response

# Configure module logger (NO print statements)
logger = logging.getLogger("forgeflow.orchestrator")


class MCPOrchestrator:
    """
    Orchestrates MCP servers - handles lazy startup, dispatching, and lifecycle.
    Supports two deployment modes:
      local — all MCPs run as local Python modules (default, offline capable)
      cloud — all MCPs run on ForgeFlow cloud endpoints (requires FORGEFLOW_API_KEY)

    All output goes through logging, not print statements.
    """
    
    def __init__(self, config_path: str = None, mode: str = None):
        self.base_dir = Path(__file__).parent.parent.absolute()
        self.config_path = config_path or (self.base_dir / "mcp-config.yaml")
        self.forgeflow_config_path = self.base_dir / "config" / "forgeflow-config.yaml"
        
        self.config = self._load_config()
        self.forgeflow_config = self._load_forgeflow_config()
        
        # Deployment mode: local or cloud
        self.mode = mode or self.forgeflow_config.get("mode", "local")
        
        self.active_servers: Dict[str, Dict] = {}
        self.command_mapping = self._build_command_mapping()
        self.pipeline_config = self._load_pipeline_config()
        
        # Remote client for PUBLIC mode (lazy initialized)
        self._remote_client = None
        
        logger.debug(f"Orchestrator initialized with mode: {self.mode}")
        
    def _load_config(self) -> Dict:
        """Load MCP server configuration from YAML."""
        if Path(self.config_path).exists():
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {"servers": {}}
        return {"servers": {}}
    
    def _load_forgeflow_config(self) -> Dict:
        """Load ForgeFlow deployment configuration."""
        if self.forgeflow_config_path.exists():
            with open(self.forgeflow_config_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {"mode": "local"}
    
    def _load_pipeline_config(self) -> Dict:
        """Load pipeline sequence configuration."""
        pipelines = self.config.get("pipelines", {})
        if not pipelines:
            # Default pipeline configuration
            pipelines = {
                "audit": ["discover", "normalize", "scan", "generate"],
                "run_all": {
                    "pre_approval": ["discover", "normalize", "docs", "generate", "review", "test", "scan"],
                    "approval_gate": "bridge",
                    "post_merge": ["deploy", "monitor"]
                }
            }
        return pipelines
    
    def get_pipeline_sequence(self, pipeline_name: str) -> List[str]:
        """Get the stage sequence for a given pipeline."""
        pipeline = self.pipeline_config.get(pipeline_name, [])
        if isinstance(pipeline, list):
            return pipeline
        elif isinstance(pipeline, dict):
            # For run_all, return pre_approval stages
            return pipeline.get("pre_approval", [])
        return []
    
    def get_post_merge_stages(self) -> List[str]:
        """Get post-merge stages for run_all pipeline."""
        run_all = self.pipeline_config.get("run_all", {})
        if isinstance(run_all, dict):
            return run_all.get("post_merge", [])
        return []
    
    def _build_command_mapping(self) -> Dict[str, str]:
        """Build mapping from CLI commands to MCP servers."""
        # Use explicit mapping from config if available
        if "command_mapping" in self.config:
            return self.config["command_mapping"]
        
        # Fallback: infer from server names/capabilities
        mapping = {}
        servers = self.config.get("servers", {})
        
        infer_rules = {
            "discover": ["discovery", "filesystem"],
            "normalize": ["normalize", "git"],
            "scan": ["security", "scanner"],
            "generate": ["deployment", "terraform", "generate"],
            "deploy": ["cloud", "aws", "deploy"],
            "test": ["cicd", "test", "pipeline"],
            "monitor": ["observability", "monitor", "metrics"],
            "docs": ["diagram", "doc"],
            "review": ["git", "review"],
            "bridge": ["github", "bridge"]
        }
        
        for command, keywords in infer_rules.items():
            for server_name in servers.keys():
                if any(kw in server_name.lower() for kw in keywords):
                    mapping[command] = server_name
                    break
        
        return mapping
    
    def get_deployment_mode(self) -> str:
        """Get current deployment mode."""
        return self.mode
    
    def set_deployment_mode(self, mode: str):
        """Set deployment mode (local or cloud)."""
        if mode not in ["local", "cloud"]:
            raise ValueError(f"Invalid deployment mode: {mode}. Must be 'local' or 'cloud'")
        self.mode = mode
        # Reset remote client when switching away from cloud
        if mode != "cloud":
            self._remote_client = None
        logger.info(f"Deployment mode set to: {mode}")
    
    def _get_remote_client(self):
        """Get or create the remote client for CLOUD mode."""
        if self._remote_client is None:
            from .remote_client import RemoteClient
            self._remote_client = RemoteClient(self.forgeflow_config)
        return self._remote_client

    def check_cloud_mode_config(self) -> tuple:
        """
        Check if CLOUD mode is properly configured.

        Returns:
            Tuple of (is_configured, message)
        """
        if self.mode != "cloud":
            return True, "Not in cloud mode"
        
        client = self._get_remote_client()
        
        # Check API key
        key_valid, key_msg = client.check_api_key()
        if not key_valid:
            return False, key_msg
        
        # Check if client is configured
        if not client.is_configured():
            return False, "Public mode not properly configured. Check forgeflow-config.yaml"
        
        return True, "Public mode configured"
    
    def get_public_endpoint(self, command: str) -> Optional[str]:
        """Get the remote endpoint URL for a command in PUBLIC mode."""
        if self.mode != "cloud":
            return None
        client = self._get_remote_client()
        try:
            return client.get_endpoint_url(command)
        except Exception:
            return None
    
    def get_server_for_command(self, command: str) -> Optional[str]:
        """Get the appropriate MCP server for a given command."""
        return self.command_mapping.get(command)
    
    def _get_server_config(self, server_name: str) -> Dict[str, Any]:
        """
        Get server configuration based on deployment mode.
        In hybrid mode, may return public server config if available.
        """
        servers_config = self.config.get("servers", {})
        server_cfg = servers_config.get(server_name, {})
        
        if self.mode == "cloud":
            # Check if hybrid mode has special config for this server
            cloud_config = self.forgeflow_config.get("cloud", {})
            public_mcps = cloud_config.get("public_mcps", {})
            
            if server_name in public_mcps:
                public_cfg = public_mcps[server_name]
                # Check if public integrations are enabled
                if public_cfg.get("type") == "public":
                    integrations = public_cfg.get("integrations", {})
                    # Check if any integration is enabled
                    has_enabled = any(
                        int_cfg.get("enabled", False) 
                        for int_cfg in integrations.values()
                    )
                    if has_enabled:
                        return public_cfg
            
            # Check local_mcps in hybrid config
            local_mcps = hybrid_config.get("local_mcps", {})
            if server_name in local_mcps:
                return local_mcps[server_name]
        
        # Default to base config (local mode or hybrid fallback)
        return server_cfg
    
    def ensure_server(self, server_name: str) -> Dict[str, Any]:
        """
        Ensure an MCP server is running (lazy start).
        If not running, start it via subprocess.Popen.
        
        In hybrid mode, may start public/remote server if configured.
        
        Returns server info dict with status.
        """
        servers_config = self.config.get("servers", {})
        
        if server_name not in servers_config:
            raise ValueError(f"Server '{server_name}' not found in mcp-config.yaml")
        
        # Return cached if already running
        if server_name in self.active_servers:
            server_info = self.active_servers[server_name]
            if server_info.get("status") == "running":
                return server_info
        
        # Get mode-aware configuration
        server_cfg = self._get_server_config(server_name)
        server_type = server_cfg.get("type", "local")
        
        command = server_cfg.get("command", "python3")
        args = server_cfg.get("args", [])
        
        # Build full command with base directory for local servers
        if server_type == "local":
            full_args = [str(self.base_dir / arg) if not arg.startswith("/") else arg for arg in args]
        else:
            full_args = args
        
        mode_indicator = f"[{self.mode.upper()}]" if self.mode  == "cloud" else ""
        logger.info(f"Starting {server_name} ({server_type}) {mode_indicator}")
        
        # For this implementation, we'll use direct module loading for local servers
        # For public servers in hybrid mode, we'd use subprocess or HTTP
        server_info = {
            "name": server_name,
            "status": "running",
            "type": server_type,
            "mode": self.mode,
            "command": command,
            "args": full_args,
            "started_at": datetime.now().isoformat(),
            "pid": os.getpid()  # Same process for direct loading
        }
        
        self.active_servers[server_name] = server_info
        return server_info
    
    def dispatch(self, server_name: str, params: Dict[str, Any], command: str = None) -> Dict[str, Any]:
        """
        Dispatch a task to an MCP server and return results.
        
        In LOCAL/HYBRID mode: Ensures server is running, then invokes its run() function.
        In PUBLIC mode: Uses RemoteClient to send request to remote endpoint.
        
        Args:
            server_name: Name of the MCP server
            params: Parameters to pass to the server
            command: Optional command name (used for PUBLIC mode endpoint lookup)
            
        Returns:
            MCP response dictionary (already wrapped by MCP server)
        """
        # PUBLIC mode: Use RemoteClient
        if self.mode == "cloud":
            return self._dispatch_remote(server_name, params, command)
        
        # LOCAL/HYBRID mode: Use local module loading
        return self._dispatch_local(server_name, params)
    
    def _dispatch_remote(self, server_name: str, params: Dict[str, Any], command: str = None) -> Dict[str, Any]:
        """
        Dispatch task to remote MCP endpoint in PUBLIC mode.
        """
        try:
            client = self._get_remote_client()
            
            # Use command name if provided, otherwise infer from server name
            if not command:
                # Reverse lookup command from server name
                for cmd, srv in self.command_mapping.items():
                    if srv == server_name:
                        command = cmd
                        break
                if not command:
                    command = server_name.replace("-mcp-server", "").replace("-", "_")
            
            endpoint = client.get_endpoint_url(command)
            logger.info(f"[PUBLIC] Dispatching to: {endpoint}")
            
            # Define progress callback for streaming (uses logging, not print)
            def on_progress(message: str):
                logger.debug(f"[Stream] {message}")
            
            result = client.dispatch(command, params, stream_callback=on_progress)
            
            # Ensure result has server info
            if "server" not in result:
                result["server"] = server_name
            
            return result
            
        except Exception as e:
            logger.error(f"Remote dispatch failed: {str(e)}")
            return {
                "status": "error",
                "server": server_name,
                "agent": "RemoteAgent",
                "result": {
                    "status": "error",
                    "summary": f"Remote dispatch failed: {str(e)}",
                    "data": {},
                    "findings": []
                }
            }
    
    def _dispatch_local(self, server_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch task to local MCP server in LOCAL/HYBRID mode.
        """
        # Ensure server is available
        server_info = self.ensure_server(server_name)
        server_type = server_info.get("type", "local")
        
        # For public servers in hybrid mode, we'd need HTTP client
        if server_type == "cloud" and self.mode  == "cloud":
            logger.warning(f"Public server in hybrid mode, using local fallback")
        
        # Get server script path from base config
        servers_config = self.config.get("servers", {})
        server_cfg = servers_config.get(server_name, {})
        args = server_cfg.get("args", [])
        
        if not args:
            return {
                "status": "error",
                "server": server_name,
                "agent": "Unknown",
                "result": {
                    "status": "error",
                    "summary": f"No script defined for {server_name}",
                    "data": {},
                    "findings": []
                }
            }
        
        server_script = self.base_dir / args[0]
        
        if not server_script.exists():
            return {
                "status": "error",
                "server": server_name,
                "agent": "Unknown",
                "result": {
                    "status": "error",
                    "summary": f"Server script not found: {server_script}",
                    "data": {},
                    "findings": []
                }
            }
        
        # Load and execute the server module
        try:
            spec = importlib.util.spec_from_file_location(server_name, server_script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            if hasattr(module, "run"):
                # MCP server's run() now returns wrapped MCPResponse
                result = module.run(params)
                return result
            else:
                return {
                    "status": "error",
                    "server": server_name,
                    "agent": "Unknown",
                    "result": {
                        "status": "error",
                        "summary": f"Server {server_name} has no run() function",
                        "data": {},
                        "findings": []
                    }
                }
                
        except Exception as e:
            logger.error(f"Failed to execute {server_name}: {str(e)}")
            return {
                "status": "error",
                "server": server_name,
                "agent": "Unknown",
                "result": {
                    "status": "error",
                    "summary": f"Failed to execute {server_name}: {str(e)}",
                    "data": {},
                    "findings": []
                }
            }
    
    def run_mission(self, mission_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a mission by dispatching to the appropriate MCP server.
        
        This method:
        1. Gets the MCP server for the command
        2. Dispatches to the server
        3. Wraps the response with orchestrator metadata
        
        Args:
            mission_type: Command name (discover, normalize, scan, etc.)
            params: Parameters to pass to the MCP server
            
        Returns:
            OrchestratorResult dictionary with flattened structure for display
        """
        start_time = time.time()
        server_name = self.get_server_for_command(mission_type)
        
        if not server_name:
            # Handle standalone commands (status, doctor)
            if mission_type == "status":
                return self._run_status(params)
            elif mission_type == "doctor":
                return self._run_doctor()
            else:
                raise ValueError(f"No MCP server mapped for command '{mission_type}'")
        
        # Log dispatch info
        if self.mode == "cloud":
            mode_indicator = "[CLOUD]"
        else:
            mode_indicator = "[LOCAL]"
        
        logger.info(f"{mode_indicator} Dispatching '{mission_type}' to {server_name}")
        
        # Dispatch to MCP server (returns MCPResponse format)
        mcp_response = self.dispatch(server_name, params, command=mission_type)
        
        # Calculate execution time
        execution_time_ms = (time.time() - start_time) * 1000
        
        # Wrap MCP response with orchestrator metadata
        result = wrap_mcp_response(mcp_response, mission_type, self.mode, execution_time_ms)
        
        # Ensure server name is set (override 'unknown' default too)
        if not result.get("server") or result.get("server") == "unknown":
            result["server"] = server_name
            
        return result
    
    def _run_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Standalone status check - no MCP server needed."""
        path = Path(params.get("path", "."))
        
        stages = {
            "discovery": path / ".forgeflow/inventory.json",
            "normalization": path / "docs/normalization_report.md",
            "security": path / "docs/security_report.md",
            "artifacts": path / "Dockerfile",
            "terraform": path / "infrastructure/main.tf",
            "cicd": path / ".github/workflows/forgeflow-ci.yml"
        }
        
        status_results = {}
        for stage, file_path in stages.items():
            status_results[stage] = "✅ Complete" if file_path.exists() else "❌ Not Run"
        
        return {
            "status": "success",
            "mission": "status",
            "server": "internal",
            "deployment_mode": self.mode,
            "data": {"stages": status_results},
            "findings": [f"{k}: {v}" for k, v in status_results.items()],
            "stages": status_results,
            "active_servers": list(self.active_servers.keys()),
            "summary": f"Checked {len(stages)} pipeline stages (mode: {self.mode})"
        }
    
    def _run_doctor(self) -> Dict[str, Any]:
        """Internal health check - no MCP server needed."""
        health_items = []
        
        # Check deployment mode
        health_items.append({
            "component": "deployment_mode",
            "status": "OK",
            "details": self.mode.upper()
        })
        
        # Check config
        config_ok = Path(self.config_path).exists()
        health_items.append({
            "component": "mcp-config.yaml",
            "status": "OK" if config_ok else "MISSING",
            "details": str(self.config_path)
        })
        
        # Check forgeflow config
        ff_config_ok = self.forgeflow_config_path.exists()
        health_items.append({
            "component": "forgeflow-config.yaml",
            "status": "OK" if ff_config_ok else "MISSING",
            "details": str(self.forgeflow_config_path)
        })
        
        # PUBLIC mode specific checks
        if self.mode == "cloud":
            is_configured, msg = self.check_cloud_mode_config()
            health_items.append({
                "component": "public_api_key",
                "status": "OK" if is_configured else "MISSING",
                "details": msg
            })
            
            # Check remote service health
            try:
                client = self._get_remote_client()
                health = client.health_check()
                health_items.append({
                    "component": "remote_service",
                    "status": "OK" if health.get("status") == "healthy" else "ERROR",
                    "details": health.get("endpoint", "Unknown")
                })
            except Exception as e:
                health_items.append({
                    "component": "remote_service",
                    "status": "ERROR",
                    "details": str(e)
                })
        else:
            # LOCAL/HYBRID mode: Check local servers
            servers = self.config.get("servers", {})
            for server_name, server_cfg in servers.items():
                args = server_cfg.get("args", [])
                if args:
                    script_path = self.base_dir / args[0]
                    exists = script_path.exists()
                    health_items.append({
                        "component": server_name,
                        "status": "OK" if exists else "MISSING",
                        "details": str(script_path)
                    })
        
        # Check command mapping
        health_items.append({
            "component": "command_mapping",
            "status": "OK",
            "details": f"{len(self.command_mapping)} commands mapped"
        })
        
        # Check pipeline config
        health_items.append({
            "component": "pipeline_config",
            "status": "OK",
            "details": f"{len(self.pipeline_config)} pipelines defined"
        })
        
        return {
            "status": "success",
            "mission": "doctor",
            "server": "internal",
            "deployment_mode": self.mode,
            "health": health_items,
            "data": {"health": health_items},
            "findings": [f"{item['status']}: {item['component']}" for item in health_items],
            "summary": f"Checked {len(health_items)} components (mode: {self.mode})"
        }
    
    def health_check(self) -> List[str]:
        """Quick health check returning list of status strings."""
        result = self._run_doctor()
        lines = [f"ForgeFlow Health Check (Mode: {self.mode.upper()})"]
        for item in result.get("health", []):
            lines.append(f"  {item['status']}: {item['component']} - {item['details']}")
        return lines
    
    def shutdown(self):
        """Shutdown all active servers."""
        for server_name in list(self.active_servers.keys()):
            logger.info(f"Stopping {server_name}")
            del self.active_servers[server_name]
