# ForgeFlow Release Notes

## Release v1.0.0

**Release Date:** February 8, 2026

---

## Overview

ForgeFlow v1.0.0 is the first stable release of the AI-Powered Platform Engineering CLI. This release includes three deployment modes to suit different use cases.

---

## Release Files

| File | Mode | Description |
|------|------|-------------|
| `forgeflow_local_release.zip` | Local | Full offline capability, all MCPs run locally |
| `forgeflow_hybrid_release.zip` | Hybrid | Mix of local and cloud integrations |
| `forgeflow_cloud_release.zip` | Cloud | Thin client, all processing in cloud |

---

## GitHub Branch Strategy

This project uses three branches to manage different deployment modes:

| Branch | Mode | Config Setting |
|--------|------|----------------|
| `main` | Local (default) | `mode: local` |
| `hybrid` | Hybrid | `mode: hybrid` |
| `cloud` | Cloud | `mode: cloud` |

---

## How to Set Up GitHub Repository with Three Branches

### Step 1: Create GitHub Repository

```bash
# Create a new repository on GitHub (via web UI or gh CLI)
gh repo create forgeflow/forgeflow --public --description "AI-Powered Platform Engineering CLI"
```

### Step 2: Initialize and Push Main Branch (Local Mode)

```bash
# Extract the local release
unzip forgeflow_local_release.zip
cd forgeflow_local

# Initialize git
git init
git add .
git commit -m "Initial release v1.0.0 - Local mode"

# Add remote and push to main
git remote add origin https://github.com/YOUR_ORG/forgeflow.git
git branch -M main
git push -u origin main
```

### Step 3: Create and Push Hybrid Branch

```bash
# Go back to releases directory
cd ..

# Extract hybrid release to a temp location
unzip forgeflow_hybrid_release.zip -d temp_hybrid
cd forgeflow_local

# Create hybrid branch
git checkout -b hybrid

# Copy hybrid config
cp ../temp_hybrid/forgeflow_hybrid/config/forgeflow-config.yaml config/
cp ../temp_hybrid/forgeflow_hybrid/mcp-config.yaml .

# Commit and push
git add .
git commit -m "Configure hybrid deployment mode"
git push -u origin hybrid

# Clean up
cd ..
rm -rf temp_hybrid
```

### Step 4: Create and Push Cloud Branch

```bash
# Extract cloud release to a temp location
unzip forgeflow_cloud_release.zip -d temp_cloud
cd forgeflow_local

# Create cloud branch from main
git checkout main
git checkout -b cloud

# Copy cloud config
cp ../temp_cloud/forgeflow_cloud/config/forgeflow-config.yaml config/
cp ../temp_cloud/forgeflow_cloud/mcp-config.yaml .

# Commit and push
git add .
git commit -m "Configure cloud deployment mode"
git push -u origin cloud

# Clean up
cd ..
rm -rf temp_cloud
```

### Step 5: Set Up Branch Protection (Optional)

Via GitHub UI or CLI:

```bash
# Protect main branch
gh api repos/YOUR_ORG/forgeflow/branches/main/protection -X PUT \
  -f required_status_checks='{"strict":true,"contexts":["test"]}' \
  -f enforce_admins=false \
  -f required_pull_request_reviews='{"required_approving_review_count":1}'
```

---

## Alternative: Quick Setup Script

Save this as `setup_github.sh` and run it:

```bash
#!/bin/bash
# ForgeFlow GitHub Setup Script

REPO_NAME="forgeflow"
ORG_NAME="YOUR_ORG"  # Change this

# Unzip all releases
unzip -q forgeflow_local_release.zip
unzip -q forgeflow_hybrid_release.zip
unzip -q forgeflow_cloud_release.zip

# Setup main branch (local mode)
cd forgeflow_local
git init
git add .
git commit -m "Initial release v1.0.0 - Local mode"
git remote add origin "https://github.com/${ORG_NAME}/${REPO_NAME}.git"
git branch -M main
git push -u origin main

# Create hybrid branch
git checkout -b hybrid
cp ../forgeflow_hybrid/config/forgeflow-config.yaml config/
cp ../forgeflow_hybrid/mcp-config.yaml .
git add .
git commit -m "Configure hybrid deployment mode"
git push -u origin hybrid

# Create cloud branch
git checkout main
git checkout -b cloud
cp ../forgeflow_cloud/config/forgeflow-config.yaml config/
cp ../forgeflow_cloud/mcp-config.yaml .
git add .
git commit -m "Configure cloud deployment mode"
git push -u origin cloud

# Return to main
git checkout main

echo "✅ Setup complete! Repository has three branches:"
echo "   - main (local mode)"
echo "   - hybrid (hybrid mode)"
echo "   - cloud (cloud mode)"
```

---

## Using the Branches

### For Users

```bash
# Clone specific branch for your deployment mode
git clone -b main https://github.com/YOUR_ORG/forgeflow.git    # Local mode
git clone -b hybrid https://github.com/YOUR_ORG/forgeflow.git  # Hybrid mode
git clone -b cloud https://github.com/YOUR_ORG/forgeflow.git   # Cloud mode
```

### For Developers

When making changes:

1. **Feature development** - Work on `main` branch
2. **Merge to other branches** - After merging to `main`, cherry-pick config changes to `hybrid` and `cloud` branches
3. **Mode-specific changes** - Make directly on the appropriate branch

---

## Release Checklist

Before each release:

- [ ] Run all tests: `make test`
- [ ] Run linter: `make lint`
- [ ] Update version in `pyproject.toml`
- [ ] Update `CHANGELOG.md`
- [ ] Create release tag: `git tag v1.0.x`
- [ ] Push tags: `git push --tags`
- [ ] Create GitHub release with release notes
- [ ] Update all three branches with new code
- [ ] Create new zip files for each mode

---

## What's New in v1.0.0

### Features
- 10 specialized agents for platform engineering tasks
- 14 CLI commands covering the full DevOps lifecycle
- Three deployment modes (local, hybrid, cloud)
- Agent-MCP architecture for modularity
- Rich CLI output with progress indicators
- Comprehensive security scanning
- Terraform, Docker, and K8s generation
- GitHub integration for CI/CD

### Documentation
- Complete user guide
- Architecture documentation
- Configuration reference
- Contributing guidelines
- Deployment guide

### CI/CD
- GitHub Actions workflows
- Pre-commit hooks
- pytest test suite
- Code quality tools (flake8, black, isort, mypy)

---

## Support

- **Issues:** https://github.com/YOUR_ORG/forgeflow/issues
- **Discussions:** https://github.com/YOUR_ORG/forgeflow/discussions
- **Documentation:** https://github.com/YOUR_ORG/forgeflow/tree/main/docs

---

## License

MIT License - See [LICENSE](LICENSE) for details.
