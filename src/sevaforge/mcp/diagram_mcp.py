"""
SevaForge Diagram Generator MCP Server

Provides diagram generation operations: architecture diagrams,
sequence diagrams, deployment diagrams, and diagram type listing.
All diagrams are returned in Mermaid syntax.

Tools:
  - generate_architecture: Create an architecture diagram in Mermaid
  - generate_sequence:     Create a sequence diagram in Mermaid
  - generate_deployment:   Create a deployment diagram in Mermaid
  - list_diagram_types:    List supported diagram types and examples
"""

from __future__ import annotations

import logging
from typing import Any

from sevaforge.mcp.base_mcp_server import BaseMCPServer, MCPTool, MCPToolParameter

logger = logging.getLogger(__name__)


class DiagramMCPServer(BaseMCPServer):
    """
    Diagram Generator MCP server.

    Generates architecture, sequence, and deployment diagrams in
    Mermaid syntax. In mock mode, returns realistic pre-built
    diagram definitions.
    """

    def __init__(self):
        super().__init__(
            server_id="diagram-mcp",
            name="Diagram Generator MCP Server",
            description="Generate architecture, sequence, and deployment diagrams in Mermaid syntax",
            version="2.0.0",
        )

    def _register_tools(self) -> list[MCPTool]:
        return [
            MCPTool(
                name="generate_architecture",
                description="Create an architecture diagram in Mermaid syntax",
                category="generation",
                tags=["diagram", "architecture", "mermaid"],
                parameters=[
                    MCPToolParameter(name="title", type="string", required=True,
                                     description="Diagram title"),
                    MCPToolParameter(name="services", type="array",
                                     description="List of service names to include"),
                    MCPToolParameter(name="style", type="string", default="LR",
                                     enum=["LR", "TB", "RL", "BT"],
                                     description="Graph direction"),
                    MCPToolParameter(name="include_databases", type="boolean", default=True),
                ],
                handler=self._generate_architecture,
            ),
            MCPTool(
                name="generate_sequence",
                description="Create a sequence diagram in Mermaid syntax",
                category="generation",
                tags=["diagram", "sequence", "mermaid"],
                parameters=[
                    MCPToolParameter(name="title", type="string", required=True),
                    MCPToolParameter(name="flow", type="string", required=True,
                                     description="Flow to diagram",
                                     enum=["auth", "agent_execute", "deployment",
                                           "mcp_tool_call", "custom"]),
                    MCPToolParameter(name="participants", type="array",
                                     description="Custom participant list (for custom flow)"),
                ],
                handler=self._generate_sequence,
            ),
            MCPTool(
                name="generate_deployment",
                description="Create a deployment diagram in Mermaid syntax",
                category="generation",
                tags=["diagram", "deployment", "mermaid", "infrastructure"],
                parameters=[
                    MCPToolParameter(name="title", type="string", required=True),
                    MCPToolParameter(name="environment", type="string", default="production",
                                     enum=["dev", "staging", "production"]),
                    MCPToolParameter(name="cloud_provider", type="string", default="gcp",
                                     enum=["gcp", "aws", "azure"]),
                ],
                handler=self._generate_deployment,
            ),
            MCPTool(
                name="list_diagram_types",
                description="List supported diagram types with descriptions and examples",
                category="reference",
                tags=["diagram", "help", "reference"],
                parameters=[],
                handler=self._list_diagram_types,
            ),
        ]

    # ── Tool Handlers ────────────────────────────────────────────────

    async def _generate_architecture(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        title = params["title"]
        style = params.get("style", "LR")
        include_db = params.get("include_databases", True)

        mermaid = (
            f"graph {style}\n"
            f"  %% {title}\n"
            "  Client([Client / Browser])\n"
            "  LB[Load Balancer]\n"
            "  GW[API Gateway<br/>FastAPI]\n"
            "  AUTH[Auth Service<br/>JWT + RBAC]\n"
            "  ORCH[Agent Orchestrator<br/>A2A Protocol]\n"
            "  AGENTS[Agent Pool<br/>Code Review, Security, FinOps]\n"
            "  MCP[MCP Server Registry<br/>Tool Providers]\n"
            "  LLM[LLM Router<br/>Claude, GPT, Gemini]\n"
        )

        if include_db:
            mermaid += (
                "  PG[(PostgreSQL)]\n"
                "  REDIS[(Redis Cache)]\n"
                "  S3[(Object Storage)]\n"
            )

        mermaid += (
            "\n"
            "  Client --> LB\n"
            "  LB --> GW\n"
            "  GW --> AUTH\n"
            "  GW --> ORCH\n"
            "  ORCH --> AGENTS\n"
            "  ORCH --> MCP\n"
            "  AGENTS --> LLM\n"
        )

        if include_db:
            mermaid += (
                "  GW --> PG\n"
                "  AUTH --> REDIS\n"
                "  AGENTS --> S3\n"
            )

        mermaid += (
            "\n"
            "  style GW fill:#4A90D9,color:#fff\n"
            "  style AUTH fill:#E8A838,color:#fff\n"
            "  style ORCH fill:#7B68EE,color:#fff\n"
            "  style LLM fill:#50C878,color:#fff\n"
        )

        return {
            "title": title,
            "type": "architecture",
            "format": "mermaid",
            "direction": style,
            "mermaid": mermaid,
            "node_count": 11 if include_db else 8,
        }

    async def _generate_sequence(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        title = params["title"]
        flow = params.get("flow", "agent_execute")

        sequences = {
            "auth": (
                "sequenceDiagram\n"
                f"  title {title}\n"
                "  participant C as Client\n"
                "  participant GW as Gateway\n"
                "  participant AUTH as Auth Service\n"
                "  participant DB as PostgreSQL\n"
                "  C->>GW: POST /auth/token {credentials}\n"
                "  GW->>AUTH: Validate credentials\n"
                "  AUTH->>DB: Lookup user\n"
                "  DB-->>AUTH: User record\n"
                "  AUTH->>AUTH: Verify password hash\n"
                "  AUTH->>AUTH: Generate JWT\n"
                "  AUTH-->>GW: {access_token, refresh_token}\n"
                "  GW-->>C: 200 OK {tokens}\n"
            ),
            "agent_execute": (
                "sequenceDiagram\n"
                f"  title {title}\n"
                "  participant C as Client\n"
                "  participant GW as Gateway\n"
                "  participant AUTH as Auth\n"
                "  participant ORCH as Orchestrator\n"
                "  participant AG as Agent\n"
                "  participant LLM as LLM Router\n"
                "  participant MCP as MCP Tools\n"
                "  C->>GW: POST /agents/execute\n"
                "  GW->>AUTH: Validate JWT\n"
                "  AUTH-->>GW: OK\n"
                "  GW->>ORCH: Execute agent task\n"
                "  ORCH->>AG: Dispatch to agent\n"
                "  AG->>LLM: Generate response\n"
                "  LLM-->>AG: LLM completion\n"
                "  AG->>MCP: Call tools if needed\n"
                "  MCP-->>AG: Tool results\n"
                "  AG-->>ORCH: Agent result\n"
                "  ORCH-->>GW: Execution result\n"
                "  GW-->>C: 200 OK {result}\n"
            ),
            "deployment": (
                "sequenceDiagram\n"
                f"  title {title}\n"
                "  participant DEV as Developer\n"
                "  participant CI as CI/CD Pipeline\n"
                "  participant REG as Container Registry\n"
                "  participant K8S as Kubernetes\n"
                "  participant MON as Monitoring\n"
                "  DEV->>CI: Push to main\n"
                "  CI->>CI: Run tests & lint\n"
                "  CI->>CI: Build Docker image\n"
                "  CI->>REG: Push image\n"
                "  CI->>K8S: Apply deployment\n"
                "  K8S->>K8S: Rolling update\n"
                "  K8S->>MON: Health check\n"
                "  MON-->>K8S: Healthy\n"
                "  K8S-->>CI: Deployment complete\n"
                "  CI-->>DEV: Success notification\n"
            ),
            "mcp_tool_call": (
                "sequenceDiagram\n"
                f"  title {title}\n"
                "  participant AG as Agent\n"
                "  participant REG as MCP Registry\n"
                "  participant SRV as MCP Server\n"
                "  participant TOOL as Tool Handler\n"
                "  AG->>REG: tools/list\n"
                "  REG-->>AG: Available tools\n"
                "  AG->>REG: tools/call {name, args}\n"
                "  REG->>SRV: Route to server\n"
                "  SRV->>TOOL: Execute handler\n"
                "  TOOL-->>SRV: Result\n"
                "  SRV-->>REG: JSON-RPC response\n"
                "  REG-->>AG: Tool result\n"
            ),
        }

        mermaid = sequences.get(flow, sequences["agent_execute"])

        return {
            "title": title,
            "type": "sequence",
            "flow": flow,
            "format": "mermaid",
            "mermaid": mermaid,
        }

    async def _generate_deployment(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        title = params["title"]
        environment = params.get("environment", "production")
        cloud = params.get("cloud_provider", "gcp")

        replicas = {"dev": 1, "staging": 2, "production": 3}
        r = replicas.get(environment, 3)

        mermaid = (
            "graph TB\n"
            f"  %% {title} — {environment} on {cloud.upper()}\n"
            f"  subgraph {cloud.upper()} Cloud\n"
            "    subgraph VPC\n"
            f"      subgraph K8s Cluster - {environment}\n"
            f"        GW[Gateway x{r}]\n"
            f"        AUTH[Auth Service x{r}]\n"
            f"        ORCH[Orchestrator x{r}]\n"
            f"        WORKER[Worker x{r * 2}]\n"
            "      end\n"
            "      subgraph Data Layer\n"
            "        PG[(PostgreSQL HA)]\n"
            "        REDIS[(Redis Cluster)]\n"
            "        MQ[RabbitMQ]\n"
            "      end\n"
            "    end\n"
            "    LB[Cloud Load Balancer]\n"
            "    CDN[CDN / Static Assets]\n"
            "    LOGS[Cloud Logging]\n"
            "  end\n"
            "\n"
            "  Users([Users]) --> CDN\n"
            "  Users --> LB\n"
            "  LB --> GW\n"
            "  GW --> AUTH\n"
            "  GW --> ORCH\n"
            "  ORCH --> WORKER\n"
            "  WORKER --> MQ\n"
            "  GW --> PG\n"
            "  AUTH --> REDIS\n"
            "  GW --> LOGS\n"
        )

        return {
            "title": title,
            "type": "deployment",
            "environment": environment,
            "cloud_provider": cloud,
            "format": "mermaid",
            "mermaid": mermaid,
            "replica_count": r,
        }

    async def _list_diagram_types(self, params: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return {
            "supported_types": [
                {"type": "architecture", "tool": "generate_architecture",
                 "description": "System architecture showing services and their connections",
                 "output_format": "Mermaid graph"},
                {"type": "sequence", "tool": "generate_sequence",
                 "description": "Sequence diagram showing message flow between components",
                 "output_format": "Mermaid sequenceDiagram",
                 "built_in_flows": ["auth", "agent_execute", "deployment", "mcp_tool_call"]},
                {"type": "deployment", "tool": "generate_deployment",
                 "description": "Deployment topology showing infrastructure and scaling",
                 "output_format": "Mermaid graph",
                 "supported_clouds": ["gcp", "aws", "azure"]},
            ],
            "total_types": 3,
            "output_format": "mermaid",
            "render_tip": "Paste the Mermaid syntax into mermaid.live or a Markdown viewer.",
        }
