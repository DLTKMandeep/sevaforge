# ForgeFlow Configuration Guide

Complete reference for all ForgeFlow configuration options.

---

## Configuration Files

### Main Configuration (`config/forgeflow-config.yaml`)

Controls deployment mode and runtime behavior.

### MCP Configuration (`mcp-config.yaml`)

Defines MCP servers and command mappings.

---

## Deployment Mode Configuration

```yaml
# config/forgeflow-config.yaml

# Deployment mode: 'local' or 'cloud'
mode: local
```

### Local Mode Options

```yaml
mode: local

local:
  mcp_servers:
    discovery-mcp-server:
      type: local
      command: "python3"
      args: ["mcp_servers/discovery_mcp/server.py"]
```

### Hybrid Mode (Removed)

> **Note:** Hybrid mode was removed in v2.0. Cloud mode now falls back to local automatically if an endpoint is unavailable, achieving the same effect without the routing complexity.

### Cloud Mode Options

```yaml
mode: cloud

public:
  # API endpoint
  api_base_url: "https://api.forgeflow.io/v1"

  # Authentication
  auth:
    type: api_key  # api_key, oauth, or token
    api_key_env: "FORGEFLOW_API_KEY"

  # Connection settings
  connection:
    timeout: 60
    retries: 3
    retry_delay: 2
    verify_ssl: true

  # Streaming (SSE)
  streaming:
    enabled: true
    heartbeat_interval: 30
```

---

## Pipeline Configuration

```yaml
pipeline:
  # Default sequence for run-all
  sequence:
    - discover
    - normalize
    - docs
    - generate
    - review
    - test
    - scan

  # Post-merge stages (optional)
  post_merge:
    - deploy
    - monitor

  # Approval gates
  approval_gates:
    - bridge
```

---

## Feature Flags

```yaml
features:
  # Enable rich CLI display
  rich_display: true

  # Auto-save reports to staging folder
  auto_save_reports: true

  # Enable telemetry (anonymous usage stats)
  telemetry: false

  # Enable parallel stage execution
  parallel_execution: false
```

---

## Default Parameters

```yaml
defaults:
  security:
    severity_threshold: medium  # low, medium, high, critical

  generation:
    stack: auto  # auto, docker, kubernetes, terraform, helm
    cloud_provider: gcp  # gcp (default), aws, azure, oci

  deployment:
    target: staging  # dev, staging, production

  bridge:
    default_branch: main
    auto_create_repo: true
```

---

## MCP Server Configuration

```yaml
# mcp-config.yaml

mcp_version: "1.0"
deployment_mode: local

servers:
  discovery-mcp-server:
    command: "python3"
    args: ["mcp_servers/discovery_mcp/server.py"]
    capabilities: ["discover", "inventory", "scan_files"]
    agent: "DiscoveryAgent"
    type: local

  security-mcp-server:
    command: "python3"
    args: ["mcp_servers/security_mcp/server.py"]
    capabilities: ["scan", "security", "vulnerabilities"]
    agent: "SecurityAgent"
    type: local
    optional_integrations:
      - snyk
      - trivy
      - sonarqube

command_mapping:
  discover: "discovery-mcp-server"
  normalize: "normalize-mcp-server"
  scan: "security-mcp-server"
  generate: "deployment-mcp-server"
  deploy: "cloud-mcp-server"
  test: "cicd-mcp-server"
  monitor: "observability-mcp-server"
  docs: "diagram-generator-mcp-server"
  review: "git-mcp-server"
  bridge: "github-mcp-server"
```

---

## Environment Variables

### Core Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FORGEFLOW_MODE` | `local` | Default deployment mode |
| `FORGEFLOW_DEBUG` | `false` | Enable debug logging |
| `FORGEFLOW_CONFIG` | `config/forgeflow-config.yaml` | Config file path |

### Authentication Variables

| Variable | Mode | Description |
|----------|------|-------------|
| `FORGEFLOW_API_KEY` | Cloud | Cloud API key |
| `GITHUB_TOKEN` | Hybrid | GitHub API token |
| `SNYK_API_KEY` | Hybrid | Snyk security scanning |

### Cloud Provider Variables

| Variable | Provider | Description |
|----------|----------|-------------|
| `AWS_REGION` | AWS | Default region |
| `AWS_PROFILE` | AWS | Credentials profile |
| `GCP_PROJECT` | GCP | Project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP | Service account path |
| `AZURE_SUBSCRIPTION_ID` | Azure | Subscription ID |

### Observability Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `PROMETHEUS_URL` | Prometheus | Server endpoint |
| `GRAFANA_URL` | Grafana | Dashboard URL |
| `GRAFANA_API_KEY` | Grafana | API key |
| `DD_API_KEY` | Datadog | API key |

---

## Security Patterns Configuration

The SecurityAgent uses regex patterns for detection:

```python
# In agents/security_agent.py

SECURITY_PATTERNS = {
    "hardcoded-secret": [
        r"password\s*=\s*[\"'][^\"']+[\"']",
        r"api_key\s*=\s*[\"'][^\"']+[\"']",
        r"secret\s*=\s*[\"'][^\"']+[\"']",
        r"token\s*=\s*[\"'][A-Za-z0-9_-]{20,}[\"']",
    ],
    "sql-injection": [
        r"execute\([^)]*%[^)]*\)",
        r"f\"[^\"]*SELECT[^\"]*\{[^}]+\}",
    ],
    "command-injection": [
        r"os\.system\([^)]*\+[^)]*\)",
        r"subprocess\.call\([^)]*shell=True[^)]*\)",
    ]
}

SEVERITY_MAP = {
    "hardcoded-secret": "critical",
    "sql-injection": "high",
    "command-injection": "high",
}
```

---

## Customizing Agents

To add custom detection patterns:

```python
# Extend SecurityAgent
class CustomSecurityAgent(SecurityAgent):
    CUSTOM_PATTERNS = {
        "custom-vulnerability": [r"your_pattern_here"]
    }

    def execute(self, params):
        # Merge custom patterns
        self.SECURITY_PATTERNS.update(self.CUSTOM_PATTERNS)
        return super().execute(params)
```

---

## Troubleshooting Configuration

### Validate Configuration

```bash
forgeflow doctor
```

### Debug Mode

```bash
export FORGEFLOW_DEBUG=1
forgeflow discover --path ./repo
```

### Check MCP Server Status

```bash
forgeflow status --path ./repo
```
