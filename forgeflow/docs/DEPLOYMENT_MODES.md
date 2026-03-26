# ForgeFlow Deployment Modes

ForgeFlow supports two deployment modes that control where MCP servers run.

---

## Overview

| Mode | MCPs run where? | Internet needed? | When to use |
|------|-----------------|------------------|-------------|
| `local` | On your machine as Python modules | No | Development, offline, full control |
| `cloud` | On ForgeFlow cloud endpoints | Yes | Teams, CI/CD, managed service |

---

## Local Mode (Default)

All MCP servers run as Python modules imported directly by the orchestrator. No network calls, no external dependencies, fully offline capable.

```bash
# No flag needed — local is the default
forgeflow cd --path ./my-repo

# Explicit
forgeflow --mode local cd --path ./my-repo
```

**Best for:**
- Running ForgeFlow on a developer machine
- Air-gapped or privacy-sensitive environments
- CI/CD jobs that need zero external dependencies
- Development and testing of ForgeFlow itself

---

## Cloud Mode

All MCP servers run on ForgeFlow cloud endpoints. The CLI sends requests to `https://api.forgeflow.io/v1` and streams results back. Requires a `FORGEFLOW_API_KEY`.

```bash
export FORGEFLOW_API_KEY=your_api_key
forgeflow --mode cloud cd --path ./my-repo
```

**Best for:**
- Teams sharing a single ForgeFlow deployment
- CI/CD pipelines that should use centralised, up-to-date agents
- Enterprise environments with managed ForgeFlow infrastructure

### Cloud Configuration

Edit `config/forgeflow-config.yaml` to set cloud endpoints:

```yaml
mode: local  # change to "cloud" to make cloud the default

cloud:
  api_base_url: "https://api.forgeflow.io/v1"
  auth:
    type: api_key
    api_key_env: "FORGEFLOW_API_KEY"
  connection:
    timeout: 60
    retries: 3
    verify_ssl: true
```

### Authentication

```bash
# API key (default)
export FORGEFLOW_API_KEY=ff_live_xxxxx

# Or set in config
cloud:
  auth:
    type: api_key
    api_key_env: "FORGEFLOW_API_KEY"
```

OAuth 2.0 is also supported for enterprise deployments:

```yaml
cloud:
  auth:
    type: oauth
    oauth:
      client_id_env: "FORGEFLOW_CLIENT_ID"
      client_secret_env: "FORGEFLOW_CLIENT_SECRET"
      token_url: "https://auth.forgeflow.io/oauth/token"
```

---

## Checking Your Mode

Every command prints the active mode in its output header:

```
[LOCAL]  Dispatching 'cd' to cd-mcp-server
[CLOUD]  Dispatching 'cd' to cd-mcp-server
```

You can also run:

```bash
forgeflow doctor
```

---

## What Happened to Hybrid Mode?

Hybrid mode (mix of local + cloud MCPs per stage) was removed. It added routing complexity without clear benefit — developers had no way to know which MCP ran where, and debugging was harder.

Cloud mode now handles the same use case cleanly: it routes all requests to cloud endpoints and falls back to local automatically if an endpoint is unavailable. One flag, consistent behaviour.
