<p align="center">
  <img src="docs/images/forgeflow-logo.png" alt="ForgeFlow Logo" width="200"/>
</p>

<h1 align="center">ForgeFlow</h1>

<p align="center">
  <strong>AI-Powered Platform Engineering CLI</strong><br>
  Automate discovery, security scanning, deployment artifact generation, and CI/CD workflows
</p>

<p align="center">
  <a href="https://i.ytimg.com/vi/GlqQGLz6hfs/sddefault.jpg">
    <img src="https://lh3.googleusercontent.com/sMTI8LLt1ASmaOfe9lJuoN21GzS0Fw9Vp_gPKxQwN0WUeKInZKDbgWwD79La8Qo-yvCW6dXT7_AQQPmpDKn1bT39vZ68UTJKyM4-kfOkwFYrrXtydsihlDQ-UdYCwLQ3ljjz31rE0tuN1TJ6Dg" alt="Build Status"/>
  </a>
  <a href="https://github.com/forgeflow/forgeflow/releases">
    <img src="https://img.shields.io/github/v/release/forgeflow/forgeflow" alt="Version"/>
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/>
  </a>
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.9+-blue.svg" alt="Python 3.9+"/>
  </a>
</p>

---

## 🚀 Overview

ForgeFlow is a comprehensive AI-powered platform engineering tool that automates the entire software delivery pipeline. It uses a modular **Agent-MCP (Model Context Protocol) architecture** to provide intelligent code analysis, security scanning, infrastructure generation, and deployment automation.

### Key Features

| Feature | Description |
|---------|-------------|
| 🔍 **Discovery** | Scan and inventory repository structure, languages, and components |
| 📐 **Normalization** | Standardize project structure with best practices |
| 🔒 **Security Scanning** | Detect vulnerabilities, hardcoded secrets, and misconfigurations |
| ⚙️ **Generation** | Auto-generate Terraform, Docker, Kubernetes, and CI/CD configs |
| 📝 **Documentation** | Generate architecture diagrams and API documentation |
| 🧪 **Testing** | Run tests and identify CI/CD configurations |
| 🔍 **Code Review** | Analyze Git history and code quality |
| 🌉 **GitHub Bridge** | Push code, create PRs, and manage repositories |
| 📊 **Monitoring** | Set up Prometheus and Grafana configurations |
| ☁️ **Deployment** | Deploy to AWS, GCP, or Azure |

---

## 📦 Installation

### Prerequisites

- Python 3.9+
- Git
- GitHub CLI (`gh`) - for bridge operations

### Quick Install

```bash
# Clone the repository
git clone https://github.com/forgeflow/forgeflow.git
cd forgeflow

# Run setup script (Mac/Linux)
./scripts/setup_mac.sh

# Or install manually
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Verify Installation

```bash
python3 scripts/test_installation.py
```

---

## 🎯 Quick Start

### Choose Your Deployment Mode

ForgeFlow supports three deployment modes:

| Mode | Description | Use Case |
|------|-------------|----------|
| `local` | All MCPs run locally (default) | Offline development, full control |
| `hybrid` | Mix of local and cloud MCPs | Best of both worlds |
| `cloud` | All MCPs in cloud (thin client) | Enterprise, team collaboration |

### Basic Commands

```bash
# Discover repository structure
forgeflow discover --path ./my-repo

# Run security scan
forgeflow scan --path ./my-repo --severity high

# Generate deployment artifacts
forgeflow generate --path ./my-repo --stack kubernetes

# Run full audit pipeline
forgeflow audit --path ./my-repo

# Run complete pipeline with GitHub push
forgeflow run-all ./my-repo
```

### Using Different Modes

```bash
# Local mode (default)
forgeflow discover --path ./my-repo

# Hybrid mode
forgeflow --mode hybrid discover --path ./my-repo

# Cloud mode (requires API key)
export FORGEFLOW_API_KEY=your_key
forgeflow --mode cloud discover --path ./my-repo
```

---

## 📚 Command Reference

### All Commands

| Command | Description | MCP Server | Agent |
|---------|-------------|------------|-------|
| `discover` | Scan repository structure | discovery-mcp | DiscoveryAgent |
| `normalize` | Standardize project structure | normalize-mcp | NormalizationAgent |
| `scan` | Security vulnerability scan | security-mcp | SecurityAgent |
| `generate` | Generate deployment artifacts | deployment-mcp | GenerationAgent |
| `review` | Code review and Git analysis | git-mcp | CodeReviewAgent |
| `test` | Run tests and CI/CD checks | cicd-mcp | TestingAgent |
| `deploy` | Deploy to cloud infrastructure | cloud-mcp | DeploymentAgent |
| `monitor` | Set up monitoring configs | observability-mcp | MonitoringAgent |
| `docs` | Generate documentation | diagram-generator-mcp | DocumentationAgent |
| `bridge` | GitHub integration | github-mcp | BridgeAgent |
| `status` | Check pipeline status | - | - |
| `doctor` | System health check | - | - |
| `audit` | Full audit pipeline | Multiple | Multiple |
| `run-all` | Complete pipeline + GitHub | Multiple | Multiple |

### Command Options

```bash
# Discover
forgeflow discover --path PATH

# Scan with severity filter
forgeflow scan --path PATH --severity [low|medium|high|critical]

# Generate with stack
forgeflow generate --path PATH --stack [auto|docker|kubernetes|terraform|helm]

# Deploy to target
forgeflow deploy --path PATH --target [dev|staging|production]

# Bridge operations
forgeflow bridge --operation [init|push|pr|branch|status] --repo owner/repo

# Run all with post-merge stages
forgeflow run-all PATH --include-post-merge
```

---

## 🔄 Pipeline Architecture

### Execution Sequence

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ForgeFlow Pipeline                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌──────────┐   ┌───────────┐   ┌──────┐   ┌──────────┐               │
│   │ DISCOVER │ → │ NORMALIZE │ → │ DOCS │ → │ GENERATE │               │
│   └──────────┘   └───────────┘   └──────┘   └──────────┘               │
│                                                                          │
│   ┌──────────┐   ┌──────┐   ┌──────┐   ┌───────────────┐               │
│   │  REVIEW  │ → │ TEST │ → │ SCAN │ → │ APPROVAL GATE │               │
│   └──────────┘   └──────┘   └──────┘   └───────────────┘               │
│                                              │                           │
│                                              ▼                           │
│                                        ┌──────────┐                      │
│                                        │  BRIDGE  │                      │
│                                        └──────────┘                      │
│                                              │                           │
│                          ┌───────────────────┴───────────────────┐      │
│                          │         Post-Merge (Optional)          │      │
│                          │   ┌────────┐        ┌─────────┐       │      │
│                          │   │ DEPLOY │   →    │ MONITOR │       │      │
│                          │   └────────┘        └─────────┘       │      │
│                          └───────────────────────────────────────┘      │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent-MCP Architecture

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌─────────┐
│  CLI/User   │  →   │ Orchestrator │  →   │ MCP Server  │  →   │  Agent  │
└─────────────┘      └──────────────┘      └─────────────┘      └─────────┘
                            │                     │                   │
                            │   Lazy Start        │   Protocol        │   Business
                            │   Subprocess        │   Bridge          │   Logic
                            │   Management        │                   │
```

---

## 🏗️ Project Structure

```
forgeflow/
├── cli/
│   └── forgeflow.py          # CLI entry point
├── core/
│   ├── mission_control.py    # Command orchestration
│   ├── orchestrator.py       # MCP server management
│   ├── display.py            # Rich console output
│   └── remote_client.py      # Cloud mode client
├── agents/
│   ├── base_agent.py         # Agent base class
│   ├── discovery_agent.py    # Repository discovery
│   ├── normalization_agent.py
│   ├── security_agent.py
│   ├── generation_agent.py
│   ├── deployment_agent.py
│   ├── testing_agent.py
│   ├── monitoring_agent.py
│   ├── documentation_agent.py
│   ├── code_review_agent.py
│   └── bridge_agent.py       # GitHub integration
├── mcp_servers/
│   ├── discovery_mcp/
│   ├── normalize_mcp/
│   ├── security_mcp/
│   ├── deployment_mcp/
│   ├── cloud_mcp/
│   ├── cicd_mcp/
│   ├── observability_mcp/
│   ├── diagram_generator_mcp/
│   ├── git_mcp/
│   └── github_mcp/
├── config/
│   └── forgeflow-config.yaml # Deployment configuration
├── docs/
├── tests/
├── scripts/
├── mcp-config.yaml           # MCP server definitions
├── requirements.txt
├── pyproject.toml
└── Makefile
```

---

## ⚙️ Configuration

### Deployment Mode Configuration

Edit `config/forgeflow-config.yaml`:

```yaml
# Set deployment mode
mode: local  # local, hybrid, or cloud

# Configure pipeline sequence
pipeline:
  sequence:
    - discover
    - normalize
    - docs
    - generate
    - review
    - test
    - scan
```

### Environment Variables

```bash
# For hybrid/cloud modes
export FORGEFLOW_API_KEY=your_api_key

# For cloud integrations
export AWS_REGION=us-east-1
export GITHUB_TOKEN=ghp_xxx
export SNYK_API_KEY=xxx
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for full configuration options.

---

## 🧪 Development

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test
pytest tests/test_agents.py -v
```

### Code Quality

```bash
# Run linter
make lint

# Format code
make format

# Type checking
make typecheck
```

### Pre-commit Hooks

```bash
# Install hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🔗 Links

- [Documentation](docs/)
- [User Guide](docs/USER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Changelog](docs/CHANGELOG.md)
- [Issue Tracker](https://github.com/forgeflow/forgeflow/issues)

---

<p align="center">
  Made with ❤️ by the ForgeFlow Team
</p>
