#!/bin/bash
#
# ForgeFlow Full Pipeline Script
# ================================
# Runs the complete end-to-end pipeline from local code to GitHub.
#
# Usage:
#   ./full_pipeline.sh <path> [--repo owner/repo] [--branch feature-branch]
#
# Example:
#   ./full_pipeline.sh /path/to/project --repo myuser/myrepo --branch feature/new-feature
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TARGET_PATH="${1:-.}"
GITHUB_REPO=""
BRANCH="feature/forgeflow-$(date +%Y%m%d-%H%M%S)"
BASE_BRANCH="main"

# Parse arguments
shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --repo|-r)
            GITHUB_REPO="$2"
            shift 2
            ;;
        --branch|-b)
            BRANCH="$2"
            shift 2
            ;;
        --base|-B)
            BASE_BRANCH="$2"
            shift 2
            ;;
        --help|-h)
            echo "ForgeFlow Full Pipeline"
            echo ""
            echo "Usage: $0 <path> [options]"
            echo ""
            echo "Options:"
            echo "  --repo, -r     GitHub repository (owner/repo)"
            echo "  --branch, -b   Feature branch name (default: auto-generated)"
            echo "  --base, -B     Base branch for PR (default: main)"
            echo "  --help, -h     Show this help message"
            echo ""
            echo "Pipeline Stages:"
            echo "  1. discover   - Scan repository structure"
            echo "  2. normalize  - Standardize repository structure"
            echo "  3. scan       - Security vulnerability scanning"
            echo "  4. generate   - Create deployment artifacts"
            echo "  5. review     - Code review analysis"
            echo "  6. bridge     - Push to GitHub and create PR"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Resolve path
TARGET_PATH=$(cd "$TARGET_PATH" && pwd)

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          ForgeFlow Full Pipeline Execution                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Target Path:${NC}  $TARGET_PATH"
echo -e "${YELLOW}GitHub Repo:${NC}  ${GITHUB_REPO:-'(not specified)'}"
echo -e "${YELLOW}Branch:${NC}       $BRANCH"
echo -e "${YELLOW}Base Branch:${NC}  $BASE_BRANCH"
echo ""

# Function to run a pipeline stage
run_stage() {
    local stage_num=$1
    local stage_name=$2
    local command=$3
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}Stage $stage_num: $stage_name${NC}"
    echo -e "${YELLOW}Command: $command${NC}"
    echo ""
    
    if eval "$command"; then
        echo -e "${GREEN}✓ Stage $stage_num completed successfully${NC}"
    else
        echo -e "${RED}✗ Stage $stage_num failed${NC}"
        return 1
    fi
    echo ""
}

# Stage 1: Discovery
run_stage 1 "Discovery - Scan repository structure" \
    "forgeflow discover --path '$TARGET_PATH'"

# Stage 2: Normalize
run_stage 2 "Normalize - Standardize structure" \
    "forgeflow normalize --path '$TARGET_PATH'"

# Stage 3: Security Scan
run_stage 3 "Security Scan - Check for vulnerabilities" \
    "forgeflow scan --path '$TARGET_PATH'"

# Stage 4: Generate Artifacts
run_stage 4 "Generate - Create deployment artifacts" \
    "forgeflow generate --path '$TARGET_PATH'"

# Stage 5: Code Review
run_stage 5 "Review - Code review analysis" \
    "forgeflow review --path '$TARGET_PATH'"

# Stage 6: Bridge to GitHub
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Stage 6: Bridge - Push to GitHub${NC}"
echo ""

# Initialize git if needed
if [ ! -d "$TARGET_PATH/.git" ]; then
    echo -e "${YELLOW}Initializing git repository...${NC}"
    forgeflow bridge --path "$TARGET_PATH" --operation init ${GITHUB_REPO:+--repo "$GITHUB_REPO"}
fi

# Create feature branch
echo -e "${YELLOW}Creating/switching to branch: $BRANCH${NC}"
forgeflow bridge --path "$TARGET_PATH" --operation branch --branch "$BRANCH"

# Push changes
if [ -n "$GITHUB_REPO" ]; then
    echo -e "${YELLOW}Pushing to remote...${NC}"
    forgeflow bridge --path "$TARGET_PATH" --operation push --repo "$GITHUB_REPO" --branch "$BRANCH" \
        --message "ForgeFlow pipeline update"
    
    # Create PR
    echo -e "${YELLOW}Creating pull request...${NC}"
    forgeflow bridge --path "$TARGET_PATH" --operation pr --repo "$GITHUB_REPO" \
        --branch "$BRANCH" --base-branch "$BASE_BRANCH" \
        --pr-title "ForgeFlow: Automated Pipeline Update" \
        --pr-body "This PR was automatically created by ForgeFlow pipeline.

## Pipeline Summary
- Discovery: ✓ Completed
- Normalization: ✓ Completed
- Security Scan: ✓ Completed
- Artifact Generation: ✓ Completed
- Code Review: ✓ Completed

Generated on: $(date)"
else
    echo -e "${YELLOW}No GitHub repo specified. Checking local status...${NC}"
    forgeflow bridge --path "$TARGET_PATH" --operation status
    echo ""
    echo -e "${YELLOW}To complete GitHub integration, run:${NC}"
    echo -e "  forgeflow bridge --path '$TARGET_PATH' --operation push --repo owner/repo --branch $BRANCH"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          ForgeFlow Pipeline Complete!                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Summary:${NC}"
echo "  • All stages executed successfully"
echo "  • Repository analyzed and artifacts generated"
if [ -n "$GITHUB_REPO" ]; then
    echo "  • Changes pushed to: https://github.com/$GITHUB_REPO"
    echo "  • PR created: https://github.com/$GITHUB_REPO/compare/$BASE_BRANCH...$BRANCH"
fi
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "  1. Review generated artifacts in .forgeflow/"
echo "  2. Check Dockerfile, docker-compose.yml, and CI/CD workflows"
echo "  3. Review and merge the pull request (if created)"
echo ""
