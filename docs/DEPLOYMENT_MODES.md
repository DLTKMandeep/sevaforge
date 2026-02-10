# ForgeFlow Deployment Modes

ForgeFlow supports three deployment modes to accommodate different use cases:

## Overview

| Mode | Description | Internet Required | Setup Complexity |
|------|-------------|-------------------|------------------|
| **LOCAL** | All MCPs run locally | ❌ No | Low |
| **HYBRID** | Mix of local and cloud MCPs | ⚠️ Partial | Medium |
| **PUBLIC** | All MCPs run in cloud | ✅ Yes | Low |

---

## 💻 LOCAL Mode (Default)

All MCP servers and Agents run locally on your machine.

### Characteristics
- **Full offline capability** - No internet required
- **Complete control** - All processing happens on your machine
- **No external dependencies** - Self-contained operation
- **Best for**: Development, air-gapped environments, privacy-sensitive projects

### Usage
```bash
# Default mode (no flag needed)
forgeflow discover --path ./my-repo

# Explicit local mode
forgeflow --mode local scan --severity high
```

### Configuration
The default `forgeflow-config.yaml` is pre-configured for local mode:
```yaml
mode: local

local:
  mcp_servers:
    discovery-mcp-server:
      type: local
      command: "python3"
      args: ["mcp_servers/discovery_mcp/server.py"]
    # ... other servers
```

---

## 🌐 HYBRID Mode

Mix of local MCPs for core functionality and public/remote MCPs for enhanced features.

### Characteristics
- **Selective cloud integration** - Core features work offline
- **Enhanced capabilities** - Access to external services (GitHub, cloud providers)
- **Graceful fallback** - Falls back to local if remote unavailable
- **Best for**: Teams with partial connectivity, enterprise environments

### Usage
```bash
forgeflow --mode hybrid discover --path ./my-repo
forgeflow --mode hybrid bridge --repo owner/repo
```

### Configuration
```yaml
mode: hybrid

hybrid:
  # Core MCPs run locally
  local_mcps:
    discovery-mcp-server:
      type: local
      command: "python3"
      args: ["mcp_servers/discovery_mcp/server.py"]
  
  # Enhanced MCPs use external services
  public_mcps:
    github-mcp-server:
      type: public
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      fallback:
        type: local
        command: "python3"
        args: ["mcp_servers/github_mcp/server.py"]
```

---

## ☁️ PUBLIC Mode (Cloud)

All MCP servers and Agents run remotely in the ForgeFlow cloud service. The CLI acts as a thin client.

### Characteristics
- **Zero local dependencies** - Only CLI runs locally
- **Always up-to-date** - Server-side updates automatically
- **Scalable processing** - Cloud resources handle heavy workloads
- **Team collaboration** - Centralized results and reports
- **Best for**: CI/CD pipelines, teams, managed service users

### Prerequisites
1. **API Key**: Obtain from ForgeFlow cloud dashboard
2. **Internet connection**: Required for all operations

### Setup

#### 1. Set Environment Variables
```bash
# Required: Your ForgeFlow API key
export FORGEFLOW_API_KEY=your_api_key_here

# Optional: Custom API endpoint (for enterprise deployments)
export FORGEFLOW_API_URL=https://api.forgeflow.io
```

Or create a `.env` file:
```bash
FORGEFLOW_API_KEY=your_api_key_here
FORGEFLOW_API_URL=https://api.forgeflow.io
```

#### 2. Run Commands
```bash
# Use public mode
forgeflow --mode public discover --path ./my-repo
forgeflow --mode public scan --severity high
forgeflow --mode public run-all ./my-repo
```

### Configuration
```yaml
mode: public

public:
  # Base URL for all MCP endpoints
  api_base_url: "https://forgeflow.example.com/api/v1"
  
  # Or individual endpoint URLs (takes precedence)
  endpoints:
    discovery: "https://api.forgeflow.io/mcp/discovery"
    normalize: "https://api.forgeflow.io/mcp/normalize"
    security: "https://api.forgeflow.io/mcp/security"
    deployment: "https://api.forgeflow.io/mcp/deployment"
    docs: "https://api.forgeflow.io/mcp/docs"
    github: "https://api.forgeflow.io/mcp/github"
    git: "https://api.forgeflow.io/mcp/git"
    cicd: "https://api.forgeflow.io/mcp/cicd"
    cloud: "https://api.forgeflow.io/mcp/cloud"
    observability: "https://api.forgeflow.io/mcp/observability"
  
  # Authentication
  auth:
    type: api_key  # api_key, oauth, or token
    api_key_env: "FORGEFLOW_API_KEY"
  
  # Connection settings
  connection:
    timeout: 60        # Request timeout in seconds
    retries: 3         # Number of retry attempts
    retry_delay: 2     # Delay between retries
    verify_ssl: true   # SSL verification
  
  # Streaming (Server-Sent Events)
  streaming:
    enabled: true
    heartbeat_interval: 30
```

### API Authentication Types

#### API Key (Default)
```yaml
auth:
  type: api_key
  api_key_env: "FORGEFLOW_API_KEY"
```
```bash
export FORGEFLOW_API_KEY=ff_live_xxxxx
```

#### OAuth 2.0
```yaml
auth:
  type: oauth
  oauth:
    client_id_env: "FORGEFLOW_CLIENT_ID"
    client_secret_env: "FORGEFLOW_CLIENT_SECRET"
    token_url: "https://auth.forgeflow.io/oauth/token"
```

#### Bearer Token
```yaml
auth:
  type: token
  token_env: "FORGEFLOW_TOKEN"
```

---

## Health Check

Verify your deployment mode configuration:

```bash
# Check system health for any mode
forgeflow doctor

# Output includes mode-specific checks:
# - LOCAL: Verifies MCP server scripts exist
# - HYBRID: Verifies both local scripts and public endpoints
# - PUBLIC: Verifies API key and remote service connectivity
```

---

## Mode Comparison

| Feature | LOCAL | HYBRID | PUBLIC |
|---------|-------|--------|--------|
| Offline capable | ✅ Full | ⚠️ Core only | ❌ No |
| External integrations | ❌ Limited | ✅ Yes | ✅ Yes |
| Setup complexity | Low | Medium | Low |
| Processing location | Local | Mixed | Cloud |
| Auto-updates | Manual | Mixed | Auto |
| API key required | ❌ No | ⚠️ Optional | ✅ Yes |
| Enterprise SSO | ❌ No | ⚠️ Partial | ✅ Yes |

---

## Switching Modes

You can switch modes per-command without changing configuration:

```bash
# Use local for discovery (works offline)
forgeflow discover --path ./my-repo

# Switch to public for security scan (uses cloud scanners)
forgeflow --mode public scan --severity high

# Use hybrid for GitHub operations
forgeflow --mode hybrid bridge --repo owner/repo
```

Or set default mode in `forgeflow-config.yaml`:

```yaml
# Change default mode
mode: public  # local | hybrid | public
```

---

## Troubleshooting

### PUBLIC Mode Issues

#### "API key not set"
```bash
# Set the API key environment variable
export FORGEFLOW_API_KEY=your_key_here

# Or check if it's set
echo $FORGEFLOW_API_KEY
```

#### "Connection failed"
```bash
# Check if API endpoint is reachable
curl -I https://api.forgeflow.io/health

# Check your network/proxy settings
```

#### "Authentication failed"
- Verify API key is correct and not expired
- Check API key permissions in ForgeFlow dashboard
- Ensure no extra whitespace in the key

### HYBRID Mode Issues

#### "Public server unavailable, using fallback"
This is expected behavior - hybrid mode falls back to local servers when public services are unavailable.

#### External integration not working
- Check if the integration is enabled in config
- Verify required environment variables are set (e.g., `SNYK_API_KEY`)

---

## Security Considerations

### LOCAL Mode
- All data stays on your machine
- No network exposure
- Full audit trail locally

### PUBLIC Mode
- Data sent to ForgeFlow cloud servers
- Encrypted in transit (TLS 1.3)
- API key should be kept secret
- Consider using secrets manager for CI/CD

### HYBRID Mode
- Core data stays local
- Only specific data sent to enabled integrations
- Review `public_mcps` configuration for data exposure

---

## Enterprise Deployment

For enterprise deployments with custom ForgeFlow servers:

```yaml
public:
  api_base_url: "https://forgeflow.yourcompany.com/api/v1"
  
  auth:
    type: oauth
    oauth:
      client_id_env: "FORGEFLOW_CLIENT_ID"
      client_secret_env: "FORGEFLOW_CLIENT_SECRET"
      token_url: "https://sso.yourcompany.com/oauth/token"
  
  connection:
    verify_ssl: true  # Always verify in production
```

Contact ForgeFlow sales for enterprise deployment options.
