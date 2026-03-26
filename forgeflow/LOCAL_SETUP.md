# ForgeFlow — Setup Guide

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.9+ | [python.org](https://www.python.org/) or `brew install python@3.11` |
| gh CLI | 2.x+ | `brew install gh` (macOS) / `winget install GitHub.cli` (Windows) |

That's all you need locally. Terraform, kubectl, Helm, and ArgoCD run inside GitHub Actions — nothing else required on your machine.

---

## Install from Source

```bash
git clone https://github.com/DLTKMandeep/sevaforge.git
cd sevaforge
git checkout unified

# Install the forgeflow package
pip install -e forgeflow/

# Verify
forgeflow --help
```

## Install via pip (when published)

```bash
pip install forgeflow
forgeflow --help
```

---

## Run Against Your Repo

```bash
# Full pipeline
forgeflow run-all ~/your-repo

# Or individual stages
forgeflow discover  --path ~/your-repo
forgeflow iac       --path ~/your-repo --cloud aws
forgeflow cd        --path ~/your-repo --repo-url https://github.com/org/repo
forgeflow ci        --path ~/your-repo
forgeflow scan      --path ~/your-repo
```

---

## One-Time Onboarding (New Project)

After running `forgeflow cd`, set up GitHub and push:

```bash
# 1. Authenticate gh CLI
gh auth login

# 2. Run the interactive wizard (no shell scripts)
#    Prompts for AWS credentials + GitHub PAT, sets all secrets, creates environments
forgeflow secrets bootstrap --path ~/your-repo

# 3. Push — GitHub Actions handles everything from here
cd ~/your-repo && git push origin main
```

See `RUNBOOK.md` in your repo root for the complete operational guide.

---

## Deployment Modes

```bash
# Local mode (default) — all MCPs run as Python modules on your machine
forgeflow cd --path ~/your-repo

# Cloud mode — MCPs run on ForgeFlow cloud endpoints
export FORGEFLOW_API_KEY=your_key
forgeflow --mode cloud cd --path ~/your-repo
```

---

## Troubleshooting

**`forgeflow: command not found`**
```bash
# Make sure the install location is on PATH
pip install -e forgeflow/
python3 -m forgeflow.cli.forgeflow --help
```

**`gh: command not found`**
```bash
brew install gh    # macOS
# or: https://cli.github.com/
```

**`ModuleNotFoundError`**
```bash
# Ensure you're in the right virtualenv and forgeflow is installed
pip install -e forgeflow/
```
