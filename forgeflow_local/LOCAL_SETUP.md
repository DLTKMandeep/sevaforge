# ForgeFlow Local Setup Guide (Mac/Linux)

This guide will help you set up ForgeFlow on your local Mac or Linux machine.

## Prerequisites

- **Python 3.9+** (Check with `python3 --version`)
- **Git** (optional, for code review features)

## Quick Start (Recommended)

### Option 1: Using the Setup Script

```bash
# 1. Unzip the forgeflow package
unzip forgeflow_local.zip
cd forgeflow

# 2. Run the setup script
chmod +x scripts/setup_mac.sh
./scripts/setup_mac.sh

# 3. Activate the virtual environment
source venv/bin/activate

# 4. Test ForgeFlow
python3 cli/forgeflow.py --help
```

### Option 2: Manual Setup

```bash
# 1. Unzip and navigate to the directory
unzip forgeflow_local.zip
cd forgeflow

# 2. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify installation
python3 scripts/test_installation.py

# 5. Test ForgeFlow
python3 cli/forgeflow.py --help
```

## Basic Usage

```bash
# Always activate the virtual environment first
cd forgeflow
source venv/bin/activate

# Discover repository structure
python3 cli/forgeflow.py discover /path/to/your/repo

# Run security scan
python3 cli/forgeflow.py scan /path/to/your/repo

# Generate deployment artifacts (Dockerfile, CI/CD)
python3 cli/forgeflow.py generate /path/to/your/repo

# Run full audit (comprehensive analysis)
python3 cli/forgeflow.py audit /path/to/your/repo

# See all available commands
python3 cli/forgeflow.py --help
```

## Available Commands

| Command | Description |
|---------|-------------|
| `discover` | Scan and analyze repository structure |
| `normalize` | Standardize repository with common files |
| `scan` | Run security vulnerability scan |
| `generate` | Generate Dockerfile and CI/CD configs |
| `deploy` | Generate Terraform infrastructure |
| `test` | Run tests and identify CI/CD configs |
| `monitor` | Set up monitoring (Prometheus/Grafana) |
| `docs` | Generate documentation and diagrams |
| `review` | Git analysis and code review |
| `bridge` | GitHub integration helpers |
| `audit` | Run comprehensive analysis |

## Troubleshooting

### Python version issues
```bash
# Check your Python version
python3 --version

# If below 3.9, install a newer version:
# Mac with Homebrew:
brew install python@3.11
```

### Module not found errors
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Permission denied
```bash
chmod +x scripts/setup_mac.sh
```

## Project Structure

```
forgeflow/
├── cli/                    # Command-line interface
│   └── forgeflow.py        # Main entry point
├── core/                   # Core orchestration
│   └── orchestrator.py     # MCP server orchestrator
├── agents/                 # Business logic agents
│   ├── discovery_agent.py
│   ├── security_agent.py
│   └── ...                 # Other agents
├── mcp_servers/            # MCP protocol servers
├── config/                 # Configuration files
├── mcp-config.yaml         # Server definitions
├── requirements.txt        # Python dependencies
└── scripts/                # Setup/test scripts
```
