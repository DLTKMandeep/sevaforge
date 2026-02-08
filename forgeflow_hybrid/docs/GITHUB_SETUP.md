# GitHub Integration Setup for ForgeFlow

This guide explains how to set up GitHub credentials to enable the `bridge` command for full GitHub integration.

## Prerequisites

- Git installed on your system
- A GitHub account
- A GitHub repository (can be created during setup)

## Authentication Methods

ForgeFlow supports multiple authentication methods for GitHub integration:

### Method 1: GitHub CLI (Recommended)

The GitHub CLI (`gh`) provides the easiest authentication experience.

#### Installation

**macOS:**
```bash
brew install gh
```

**Ubuntu/Debian:**
```bash
sudo apt install gh
```

**Windows:**
```bash
winget install GitHub.cli
```

#### Authentication

```bash
# Login to GitHub
gh auth login

# Choose:
# - GitHub.com
# - HTTPS
# - Login with web browser (or paste token)
```

#### Verify

```bash
gh auth status
```

### Method 2: Personal Access Token (PAT)

Create a Personal Access Token for Git operations.

#### Create Token

1. Go to [GitHub Settings → Developer Settings → Personal Access Tokens](https://github.com/settings/tokens)
2. Click "Generate new token (classic)"
3. Select scopes:
   - `repo` (Full control of private repositories)
   - `workflow` (Update GitHub Action workflows)
4. Copy the generated token

#### Configure Git

**Option A: Environment Variable (Recommended for CI/CD)**
```bash
export GITHUB_TOKEN=ghp_your_token_here
```

**Option B: Git Credential Store**
```bash
# Store credentials in plaintext (less secure)
git config --global credential.helper store

# Or cache for limited time
git config --global credential.helper 'cache --timeout=3600'
```

**Option C: Use Token in Remote URL**
```bash
# When pushing, use:
git remote set-url origin https://YOUR_TOKEN@github.com/owner/repo.git
```

### Method 3: SSH Keys

For users who prefer SSH authentication.

#### Generate SSH Key

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

#### Add to SSH Agent

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

#### Add to GitHub

1. Copy your public key:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
2. Go to [GitHub Settings → SSH Keys](https://github.com/settings/keys)
3. Click "New SSH key" and paste

#### Use SSH Remote

```bash
git remote set-url origin git@github.com:owner/repo.git
```

## Using ForgeFlow Bridge Command

Once authentication is configured, you can use the bridge command:

### Initialize Repository
```bash
forgeflow bridge --operation init --repo owner/repo
```

### Create Feature Branch
```bash
forgeflow bridge --operation branch --branch feature/my-feature
```

### Push Changes
```bash
forgeflow bridge --operation push --repo owner/repo --branch feature/my-feature
```

### Create Pull Request
```bash
forgeflow bridge --operation pr --repo owner/repo \
  --branch feature/my-feature \
  --base-branch main \
  --pr-title "My Feature" \
  --pr-body "Description of changes"
```

### Check Status
```bash
forgeflow bridge --operation status --repo owner/repo
```

## Full Pipeline Example

Run the complete pipeline with GitHub integration:

```bash
# Using the full pipeline script
./scripts/full_pipeline.sh /path/to/project --repo owner/repo --branch feature/update

# Or manually:
forgeflow discover --path .
forgeflow normalize --path .
forgeflow scan --path .
forgeflow generate --path .
forgeflow review --path .
forgeflow bridge --operation init --repo owner/repo
forgeflow bridge --operation branch --branch feature/forgeflow-update
forgeflow bridge --operation push --repo owner/repo
forgeflow bridge --operation pr --repo owner/repo --base-branch main
```

## Troubleshooting

### Authentication Failed

```
Error: Authentication failed
```

**Solutions:**
1. Verify your token hasn't expired
2. Check token has required scopes
3. Run `gh auth login` to re-authenticate

### Permission Denied

```
Error: Permission denied (publickey)
```

**Solutions:**
1. Ensure SSH key is added to agent: `ssh-add -l`
2. Verify key is added to GitHub account
3. Test connection: `ssh -T git@github.com`

### Repository Not Found

```
Error: Repository not found
```

**Solutions:**
1. Verify repository exists on GitHub
2. Check you have access to the repository
3. Ensure `owner/repo` format is correct

### Push Rejected

```
Error: Updates were rejected
```

**Solutions:**
1. Pull latest changes: `git pull origin main`
2. Resolve any conflicts
3. Push again

## Environment Variables Reference

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | Personal Access Token for GitHub API |
| `GH_TOKEN` | Alternative variable for GitHub CLI |
| `GIT_AUTHOR_NAME` | Name for Git commits |
| `GIT_AUTHOR_EMAIL` | Email for Git commits |

## Security Best Practices

1. **Never commit tokens** - Use environment variables or credential helpers
2. **Use minimal scopes** - Only grant necessary permissions to tokens
3. **Rotate tokens regularly** - Especially for CI/CD environments
4. **Use SSH keys** - More secure than HTTPS with tokens
5. **Enable 2FA** - Adds extra security layer to your GitHub account

## CI/CD Integration

For automated pipelines, configure GitHub credentials as secrets:

### GitHub Actions

```yaml
jobs:
  forgeflow:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Git
        run: |
          git config user.name "GitHub Actions"
          git config user.email "actions@github.com"
      
      - name: Run ForgeFlow Pipeline
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          pip install forgeflow
          forgeflow audit --path .
          forgeflow bridge --operation push --repo ${{ github.repository }}
```

### GitLab CI

```yaml
forgeflow:
  script:
    - pip install forgeflow
    - forgeflow audit --path .
    - forgeflow bridge --operation push --repo "$CI_PROJECT_PATH"
  variables:
    GITHUB_TOKEN: $GITHUB_TOKEN
```

## Related Documentation

- [ForgeFlow README](../README.md)
- [Agent Architecture](./AGENT_ARCHITECTURE.md)
- [Local Setup Guide](../LOCAL_SETUP.md)
