"""
SevaForge Observability MCP Server

Provides observability operations: metrics queries, log search,
trace inspection, alert management, and dashboard data.

Tools:
  - query_metrics:     Query time-series metrics
  - search_logs:       Search and filter logs
  - list_traces:       List distributed traces
  - get_trace:         Get trace detail with spans
  - list_alerts:       List active alerts
  - create_alert_rule: Create a new alert rule
  - get_dashboard:     Get dashboard data for a service
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sevaforge.mcp.base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter

logger = logging.getLogger(__name__)


class ObservabilityMCPServer(BaseMCPServer):
    """
    Observability MCP server for metrics, logs, traces, and alerts.

    Provides a unified interface for querying observability data
    across the SevaForge platform.
    """

    def __init__(self):
        self._alert_rules: list[dict[str, Any]] = []
        super().__init__(
            server_id="observability",
            name="Observability MCP Server",
            description="Metrics, logs, traces, and alerting for platform observability",
            version="2.0.0",
        )

    def _register_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="query_metrics",
                description="Query time-series metrics for services",
                category="metrics",
                parameters=[
                    MCPToolParameter(name="metric", type="string", required=True,
                                     description="Metric name (e.g., http_requests_total, cpu_usage)"),
                    MCPToolParameter(name="service", type="string", description="Filter by service"),
                    MCPToolParameter(name="time_range", type="string", default="1h",
                                     enum=["5m", "15m", "1h", "6h", "24h", "7d"]),
                    MCPToolParameter(name="aggregation", type="string", default="avg",
                                     enum=["avg", "sum", "max", "min", "p50", "p95", "p99"]),
                ],
                handler=self._query_metrics,
            ),
            MCPTool(
                name="search_logs",
                description="Search and filter application logs",
                category="logs",
                parameters=[
                    MCPToolParameter(name="query", type="string", required=True),
                    MCPToolParameter(name="service", type="string"),
                    MCPToolParameter(name="severity", type="string", default="all",
                                     enum=["all", "error", "warn", "info", "debug"]),
                    MCPToolParameter(name="time_range", type="string", default="1h"),
                    MCPToolParameter(name="limit", type="integer", default=50),
                ],
                handler=self._search_logs,
            ),
            MCPTool(
                name="list_traces",
                description="List distributed traces",
                category="traces",
                parameters=[
                    MCPToolParameter(name="service", type="string"),
                    MCPToolParameter(name="operation", type="string"),
                    MCPToolParameter(name="min_duration_ms", type="integer"),
                    MCPToolParameter(name="status", type="string", default="all",
                                     enum=["all", "ok", "error"]),
                    MCPToolParameter(name="limit", type="integer", default=20),
                ],
                handler=self._list_traces,
            ),
            MCPTool(
                name="get_trace",
                description="Get detailed trace with all spans",
                category="traces",
                parameters=[
                    MCPToolParameter(name="trace_id", type="string", required=True),
                ],
                handler=self._get_trace,
            ),
            MCPTool(
                name="list_alerts",
                description="List active and recent alerts",
                category="alerts",
                parameters=[
                    MCPToolParameter(name="status", type="string", default="active",
                                     enum=["active", "resolved", "silenced", "all"]),
                    MCPToolParameter(name="severity", type="string", default="all"),
                    MCPToolParameter(name="limit", type="integer", default=20),
                ],
                handler=self._list_alerts,
            ),
            MCPTool(
                name="create_alert_rule",
                description="Create a new alerting rule",
                category="alerts",
                parameters=[
                    MCPToolParameter(name="name", type="string", required=True),
                    MCPToolParameter(name="metric", type="string", required=True),
                    MCPToolParameter(name="condition", type="string", required=True,
                                     description="e.g., '> 90' or '< 10'"),
                    MCPToolParameter(name="severity", type="string", required=True,
                                     enum=["critical", "warning", "info"]),
                    MCPToolParameter(name="duration", type="string", default="5m",
                                     description="How long condition must hold before firing"),
                    MCPToolParameter(name="notification_channels", type="array",
                                     description="Channels: slack, email, pagerduty"),
                ],
                handler=self._create_alert_rule,
            ),
            MCPTool(
                name="get_dashboard",
                description="Get dashboard overview data for a service",
                category="dashboard",
                parameters=[
                    MCPToolParameter(name="service", type="string", required=True),
                    MCPToolParameter(name="time_range", type="string", default="24h"),
                ],
                handler=self._get_dashboard,
            ),
        ]

    # ── Tool Handlers ────────────────────────────────────────────────

    async def _query_metrics(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        metric = params["metric"]
        time_range = params.get("time_range", "1h")
        aggregation = params.get("aggregation", "avg")

        # Generate mock time-series data
        data_points = []
        now = datetime.utcnow()
        intervals = {"5m": 5, "15m": 15, "1h": 12, "6h": 24, "24h": 48, "7d": 84}
        n_points = intervals.get(time_range, 12)

        import random
        base_value = {"http_requests_total": 150, "cpu_usage": 45, "memory_usage_mb": 512,
                      "error_rate": 0.5, "latency_p99_ms": 120, "active_connections": 80}.get(metric, 50)

        for i in range(n_points):
            ts = now - timedelta(minutes=i * 5)
            value = base_value + random.uniform(-base_value * 0.2, base_value * 0.2)
            data_points.append({"timestamp": ts.isoformat(), "value": round(value, 2)})

        data_points.reverse()

        return {
            "metric": metric,
            "service": params.get("service", "all"),
            "time_range": time_range,
            "aggregation": aggregation,
            "data_points": data_points,
            "summary": {
                "min": round(min(d["value"] for d in data_points), 2),
                "max": round(max(d["value"] for d in data_points), 2),
                "avg": round(sum(d["value"] for d in data_points) / len(data_points), 2),
                "current": data_points[-1]["value"],
            },
        }

    async def _search_logs(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        query = params["query"]
        return {
            "query": query,
            "total_results": 5,
            "logs": [
                {"timestamp": "2025-06-01T12:00:01Z", "severity": "error",
                 "service": "gateway", "message": f"Failed to process request: {query}",
                 "trace_id": "sf-abc123", "metadata": {"status_code": 500}},
                {"timestamp": "2025-06-01T12:00:05Z", "severity": "warn",
                 "service": "auth", "message": "Rate limit approaching threshold",
                 "trace_id": "sf-def456"},
                {"timestamp": "2025-06-01T12:00:10Z", "severity": "info",
                 "service": "agents", "message": "Code review agent completed analysis",
                 "trace_id": "sf-ghi789", "metadata": {"agent_id": "code-review", "duration_ms": 2500}},
                {"timestamp": "2025-06-01T12:00:15Z", "severity": "info",
                 "service": "finops", "message": "Cost tracking: $0.05 for execution",
                 "trace_id": "sf-jkl012"},
                {"timestamp": "2025-06-01T12:00:20Z", "severity": "debug",
                 "service": "orchestration", "message": "A2A message delivered to security agent",
                 "trace_id": "sf-mno345"},
            ][:params.get("limit", 50)],
        }

    async def _list_traces(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "total_count": 3,
            "traces": [
                {"trace_id": "sf-abc123def", "service": "gateway", "operation": "agent.execute",
                 "duration_ms": 2500, "spans": 8, "status": "ok",
                 "started_at": "2025-06-01T12:00:00Z"},
                {"trace_id": "sf-456ghi789", "service": "agents", "operation": "code-review.run",
                 "duration_ms": 5200, "spans": 12, "status": "ok",
                 "started_at": "2025-06-01T11:55:00Z"},
                {"trace_id": "sf-jkl012mno", "service": "auth", "operation": "token.validate",
                 "duration_ms": 15, "spans": 3, "status": "ok",
                 "started_at": "2025-06-01T11:50:00Z"},
            ][:params.get("limit", 20)],
        }

    async def _get_trace(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        trace_id = params["trace_id"]
        return {
            "trace_id": trace_id,
            "service": "gateway",
            "operation": "agent.execute",
            "duration_ms": 2500,
            "status": "ok",
            "spans": [
                {"span_id": "s1", "operation": "http.request", "service": "gateway",
                 "duration_ms": 2500, "parent": None, "status": "ok"},
                {"span_id": "s2", "operation": "auth.validate", "service": "auth",
                 "duration_ms": 12, "parent": "s1", "status": "ok"},
                {"span_id": "s3", "operation": "guardrails.check_input", "service": "trust",
                 "duration_ms": 5, "parent": "s1", "status": "ok"},
                {"span_id": "s4", "operation": "agent.code-review.execute", "service": "agents",
                 "duration_ms": 2200, "parent": "s1", "status": "ok"},
                {"span_id": "s5", "operation": "llm.call", "service": "gateway",
                 "duration_ms": 1800, "parent": "s4", "status": "ok",
                 "attributes": {"model": "claude-sonnet-4-20250514", "tokens": 3500}},
                {"span_id": "s6", "operation": "guardrails.check_output", "service": "trust",
                 "duration_ms": 3, "parent": "s1", "status": "ok"},
                {"span_id": "s7", "operation": "cost.track", "service": "finops",
                 "duration_ms": 2, "parent": "s1", "status": "ok"},
                {"span_id": "s8", "operation": "audit.record", "service": "trust",
                 "duration_ms": 1, "parent": "s1", "status": "ok"},
            ],
        }

    async def _list_alerts(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        alerts = [
            {"id": "ALT-001", "name": "High Error Rate", "severity": "warning",
             "status": "active", "metric": "error_rate", "condition": "> 5%",
             "current_value": "6.2%", "service": "gateway",
             "fired_at": "2025-06-01T11:30:00Z"},
            {"id": "ALT-002", "name": "Memory Usage Critical", "severity": "critical",
             "status": "active", "metric": "memory_usage_mb", "condition": "> 900",
             "current_value": "945 MB", "service": "agents",
             "fired_at": "2025-06-01T11:45:00Z"},
            {"id": "ALT-003", "name": "Latency Spike", "severity": "warning",
             "status": "resolved", "metric": "latency_p99_ms", "condition": "> 500",
             "current_value": "320 ms", "service": "gateway",
             "fired_at": "2025-06-01T10:00:00Z", "resolved_at": "2025-06-01T10:15:00Z"},
        ]

        status_filter = params.get("status", "active")
        if status_filter != "all":
            alerts = [a for a in alerts if a["status"] == status_filter]

        return {"total_count": len(alerts), "alerts": alerts[:params.get("limit", 20)]}

    async def _create_alert_rule(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        rule = {
            "id": f"RULE-{str(uuid.uuid4())[:6].upper()}",
            "name": params["name"],
            "metric": params["metric"],
            "condition": params["condition"],
            "severity": params["severity"],
            "duration": params.get("duration", "5m"),
            "notification_channels": params.get("notification_channels", ["slack"]),
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "created_by": kwargs.get("user_id", "system"),
        }
        self._alert_rules.append(rule)
        return rule

    async def _get_dashboard(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        service = params["service"]
        return {
            "service": service,
            "time_range": params.get("time_range", "24h"),
            "summary": {
                "status": "healthy",
                "uptime_percent": 99.95,
                "total_requests_24h": 15420,
                "error_rate_percent": 0.3,
                "avg_latency_ms": 125,
                "p99_latency_ms": 450,
            },
            "resource_usage": {
                "cpu_percent": 42.5,
                "memory_mb": 512,
                "memory_limit_mb": 1024,
                "disk_usage_percent": 35.0,
            },
            "top_endpoints": [
                {"path": "/api/v1/agents/execute", "requests": 3200, "avg_ms": 2100, "errors": 5},
                {"path": "/api/v1/auth/token", "requests": 2800, "avg_ms": 15, "errors": 0},
                {"path": "/api/v1/health", "requests": 8640, "avg_ms": 2, "errors": 0},
            ],
            "recent_errors": [
                {"timestamp": "2025-06-01T12:00:01Z", "path": "/api/v1/agents/execute",
                 "status_code": 500, "message": "LLM provider timeout"},
            ],
            "active_alerts": 1,
        }
