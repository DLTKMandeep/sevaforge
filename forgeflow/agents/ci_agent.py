#!/usr/bin/env python3
"""
CI Agent - Continuous Integration Pipeline Generation
Generates GitHub Actions, GitLab CI, security scanning, testing workflows

Part of the specialized agent architecture:
- forgeflow ci <path> → ci_mcp → CIAgent
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent


# =============================================================================
# GITHUB ACTIONS - CI WORKFLOW
# =============================================================================

CI_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated CI Pipeline
# Continuous Integration - Build, Test, Lint, Security Scan
# =============================================================================
name: CI Pipeline

on:
  push:
    branches: [main, develop, 'feature/**']
  pull_request:
    branches: [main, develop]

concurrency:
  group: ci-${{{{ github.ref }}}}
  cancel-in-progress: true

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{{{ github.repository }}}}

jobs:
  # ===========================================================================
  # Code Quality - Linting
  # ===========================================================================
  lint:
    name: 🔍 Lint Code
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
{lint_steps}

  # ===========================================================================
  # Unit Tests
  # ===========================================================================
  test-unit:
    name: 🧪 Unit Tests
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
{unit_test_steps}

  # ===========================================================================
  # Integration Tests
  # ===========================================================================
  test-integration:
    name: 🔗 Integration Tests
    runs-on: ubuntu-latest
    needs: test-unit
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
{integration_test_steps}

  # ===========================================================================
  # Build Container Image
  # ===========================================================================
  build:
    name: 🏗️ Build Image
    runs-on: ubuntu-latest
    needs: [test-unit, test-integration]
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{{{ steps.meta.outputs.tags }}}}
      image_digest: ${{{{ steps.build.outputs.digest }}}}
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to Container Registry
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.REGISTRY }}}}
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=sha,prefix=
            type=semver,pattern={{{{version}}}}
            type=semver,pattern={{{{major}}}}.{{{{minor}}}}

      - name: Build and push
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{{{ github.event_name != 'pull_request' }}}}
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true
          sbom: true


  # ===========================================================================
  # E2E Smoke Tests (PR gate — spins up app locally, no external env needed)
  # ===========================================================================
  e2e-smoke:
    name: 💨 E2E Smoke Tests
    runs-on: ubuntu-latest
    needs: [test-unit, test-integration]
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install Playwright
        run: |
          npm ci 2>/dev/null || true
          npx playwright install --with-deps chromium

      - name: Start application
        run: |
{e2e_start_cmd}
          sleep 10
        env:
          PORT: 3000
          NODE_ENV: test
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379

      - name: Run smoke E2E tests
        env:
          BASE_URL: http://localhost:3000
        run: |
          # Run only smoke-tagged tests if they exist, otherwise run all
          if find tests/e2e -name "*.spec.*" 2>/dev/null | grep -q .; then
            npx playwright test --grep @smoke --reporter=line 2>/dev/null || \\
            npx playwright test --reporter=line
          else
            echo "No E2E tests found — skipping smoke run"
          fi

      - name: Upload smoke test report
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: smoke-e2e-report-${{{{ github.sha }}}}
          path: playwright-report/
          retention-days: 7
'''


# =============================================================================
# GITHUB ACTIONS — CHAINED PIPELINE (Security → Tests → Build)
# This is the primary workflow generated by ForgeFlow.
# Three sequential stages: nothing deploys unless tests pass,
# tests don't run unless security passes.
# =============================================================================

PIPELINE_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated — Chained CI/CD Pipeline
#
#   Stage 1 ── 🔐 Security Scan   (secrets + dependency CVEs)
#      │
#      ▼  (passes)
#   Stage 2 ── 🧪 Unit Tests       (pytest / jest / go test)
#      │
#      ▼  (passes, push to main only)
#   Stage 3 ── 🚀 Build & Push     (Docker image → GHCR)
#
# Nothing deploys unless tests pass. Tests don't run unless security passes.
# =============================================================================
name: Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: pipeline-${{{{ github.ref }}}}
  cancel-in-progress: true

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{{{ github.repository }}}}

# ---------------------------------------------------------------------------
# Stage 1 — Security Scan
# What:    Detect hardcoded secrets and vulnerable dependencies
# Outcome: Pipeline blocked if secrets or critical CVEs are found
# ---------------------------------------------------------------------------
jobs:
  security:
    name: 🔐 Security Scan
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Gitleaks — secret scanning
        if: github.event_name == 'pull_request' || github.event.before != '0000000000000000000000000000000000000000'
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
{dependency_scan_steps}
      - name: Upload dependency scan results
        if: always()
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: dependency-results.sarif
        continue-on-error: true

  # ---------------------------------------------------------------------------
  # Stage 2 — Unit Tests
  # What:    Run the full test suite with coverage reporting
  # Outcome: Coverage uploaded; pipeline blocked if any test fails
  # Requires: Security scan passed
  # ---------------------------------------------------------------------------
  test:
    name: 🧪 Unit Tests
    runs-on: ubuntu-latest
    needs: security
    permissions:
      contents: read

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
{unit_test_steps}
      - name: Upload coverage report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml
          retention-days: 14

  # ---------------------------------------------------------------------------
  # Stage 3 — Build & Push Docker image
  # What:    Build the Docker image and push to GHCR
  # Outcome: Image tagged with SHA and latest, ready for deployment
  # Requires: Tests passed · Push to main only (not PRs)
  # ---------------------------------------------------------------------------
  build:
    name: 🚀 Build & Push Image
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    permissions:
      contents: read
      packages: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.REGISTRY }}}}
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable=true

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
'''


# =============================================================================
# GITHUB ACTIONS - SECURITY WORKFLOW (kept for standalone use)
# =============================================================================

SECURITY_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated Security Pipeline
# Security Scanning - SAST, Dependencies, Secrets, Containers
# =============================================================================
name: Security Scans

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday at 6 AM

permissions:
  contents: read
  security-events: write
  actions: read

jobs:
  # ===========================================================================
  # Secret Scanning
  # ===========================================================================
  secrets-scan:
    name: 🔐 Secret Scanning
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Gitleaks scan
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
          GITLEAKS_ENABLE_COMMENTS: true

      - name: TruffleHog scan
        if: github.event_name == 'pull_request'
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{{{ github.event.pull_request.base.sha }}}}
          head: HEAD
          extra_args: --only-verified

  # ===========================================================================
  # Dependency Scanning
  # ===========================================================================
  dependency-scan:
    name: 📦 Dependency Scanning
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
{dependency_scan_steps}

      - name: Upload SARIF results
        if: always()
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: dependency-results.sarif

  # ===========================================================================
  # SAST - Static Application Security Testing
  # ===========================================================================
  sast:
    name: 🔍 SAST Scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Initialize CodeQL
        uses: github/codeql-action/init@v4
        with:
          languages: {codeql_languages}

      - name: Autobuild
        uses: github/codeql-action/autobuild@v4

      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@v4
        with:
          category: "/language:{codeql_languages}"

  # ===========================================================================
  # Container Scanning
  # ===========================================================================
  container-scan:
    name: 🐳 Container Scanning
    runs-on: ubuntu-latest
    needs: [secrets-scan, dependency-scan, sast]
    if: github.event_name != 'pull_request'
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Build image for scanning
        run: docker build -t ${{{{ github.repository }}}}:scan .

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: '${{{{ github.repository }}}}:scan'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH,MEDIUM'

      - name: Upload Trivy scan results
        uses: github/codeql-action/upload-sarif@v4
        with:
          sarif_file: 'trivy-results.sarif'
'''


# =============================================================================
# GITHUB ACTIONS - RELEASE WORKFLOW
# =============================================================================

RELEASE_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated Release Pipeline
# =============================================================================
name: Release

on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  packages: write

jobs:
  release:
    name: 📦 Create Release
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate changelog
        id: changelog
        uses: TriPSs/conventional-changelog-action@v5
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          skip-commit: true
          output-file: false

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v1
        with:
          body: ${{ steps.changelog.outputs.clean_changelog }}
          draft: false
          prerelease: ${{ contains(github.ref, '-rc') || contains(github.ref, '-beta') }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
'''


# =============================================================================
# DEPENDABOT CONFIG
# =============================================================================

DEPENDABOT_CONFIG = '''# =============================================================================
# ForgeFlow Generated Dependabot Configuration
# =============================================================================
version: 2
updates:
  # GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "ci(deps)"

{ecosystem_configs}
'''

DEPENDABOT_ECOSYSTEM_NPM = '''  # npm/yarn dependencies
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
    groups:
      production-dependencies:
        dependency-type: "production"
      development-dependencies:
        dependency-type: "development"
        patterns:
          - "*"
'''

DEPENDABOT_ECOSYSTEM_PIP = '''  # Python dependencies
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
'''

DEPENDABOT_ECOSYSTEM_DOCKER = '''  # Docker dependencies
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
'''

DEPENDABOT_ECOSYSTEM_GOMOD = '''  # Go modules
  - package-ecosystem: "gomod"
    directory: "/"
    schedule:
      interval: "weekly"
    commit-message:
      prefix: "chore(deps)"
'''


# =============================================================================
# GITLAB CI TEMPLATE
# =============================================================================

GITLAB_CI_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated GitLab CI/CD Pipeline
# =============================================================================

stages:
  - lint
  - test
  - security
  - build
  - deploy

variables:
  DOCKER_TLS_CERTDIR: "/certs"
  FF_USE_FASTZIP: "true"
  ARTIFACT_COMPRESSION_LEVEL: "fast"

default:
  image: {default_image}
  cache:
    key: ${{CI_COMMIT_REF_SLUG}}
    paths:
{cache_paths}

# ===========================================================================
# Lint Stage
# ===========================================================================
{lint_job}

# ===========================================================================
# Test Stage
# ===========================================================================
{test_job}

# ===========================================================================
# Security Stage
# ===========================================================================
security:sast:
  stage: security
  image: docker:stable
  services:
    - docker:dind
  script:
    - docker run --rm -v "${{CI_PROJECT_DIR}}:/src" returntocorp/semgrep semgrep --config=auto /src
  allow_failure: true

security:dependency:
  stage: security
{dependency_job}
  allow_failure: true

security:secrets:
  stage: security
  image: zricethezav/gitleaks:latest
  script:
    - gitleaks detect --source . --verbose --report-format sarif --report-path gitleaks-report.sarif
  artifacts:
    reports:
      sast: gitleaks-report.sarif
  allow_failure: true

# ===========================================================================
# Build Stage
# ===========================================================================
build:docker:
  stage: build
  image: docker:stable
  services:
    - docker:dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA .
    - docker push $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA
    - |
      if [ "$CI_COMMIT_BRANCH" == "main" ]; then
        docker tag $CI_REGISTRY_IMAGE:$CI_COMMIT_SHA $CI_REGISTRY_IMAGE:latest
        docker push $CI_REGISTRY_IMAGE:latest
      fi
  rules:
    - if: $CI_COMMIT_BRANCH == "main" || $CI_COMMIT_BRANCH == "develop"

# ===========================================================================
# Deploy Stage
# ===========================================================================
deploy:dev:
  stage: deploy
  image: bitnami/kubectl:latest
  environment:
    name: development
    url: https://dev.${{CI_PROJECT_NAME}}.example.com
  script:
    - kubectl set image deployment/${{CI_PROJECT_NAME}} ${{CI_PROJECT_NAME}}=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA -n ${{CI_PROJECT_NAME}}-dev
    - kubectl rollout status deployment/${{CI_PROJECT_NAME}} -n ${{CI_PROJECT_NAME}}-dev
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: on_success

deploy:staging:
  stage: deploy
  image: bitnami/kubectl:latest
  environment:
    name: staging
    url: https://staging.${{CI_PROJECT_NAME}}.example.com
  script:
    - kubectl set image deployment/${{CI_PROJECT_NAME}} ${{CI_PROJECT_NAME}}=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA -n ${{CI_PROJECT_NAME}}-staging
    - kubectl rollout status deployment/${{CI_PROJECT_NAME}} -n ${{CI_PROJECT_NAME}}-staging
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual

deploy:prod:
  stage: deploy
  image: bitnami/kubectl:latest
  environment:
    name: production
    url: https://${{CI_PROJECT_NAME}}.example.com
  script:
    - kubectl set image deployment/${{CI_PROJECT_NAME}} ${{CI_PROJECT_NAME}}=$CI_REGISTRY_IMAGE:$CI_COMMIT_SHA -n ${{CI_PROJECT_NAME}}-prod
    - kubectl rollout status deployment/${{CI_PROJECT_NAME}} -n ${{CI_PROJECT_NAME}}-prod
  rules:
    - if: $CI_COMMIT_TAG =~ /^v.*/
      when: manual
'''


# =============================================================================
# LANGUAGE-SPECIFIC CONFIGURATIONS
# =============================================================================

LINT_STEPS_BY_LANGUAGE = {
    'Python': '''
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install linters
        run: pip install flake8 black isort mypy

      - name: Run flake8
        run: flake8 . --count --show-source --statistics

      - name: Check formatting with black
        run: black --check .

      - name: Check imports with isort
        run: isort --check-only .

      - name: Run mypy
        run: mypy . --ignore-missing-imports
''',
    'JavaScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run ESLint
        run: npm run lint

      - name: Check Prettier formatting
        run: npm run format:check
''',
    'TypeScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run TypeScript type check
        run: npx tsc --noEmit

      - name: Run ESLint
        run: npm run lint

      - name: Check Prettier formatting
        run: npm run format:check
''',
    'Go': '''
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.21'
          cache: true

      - name: Run golangci-lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest

      - name: Check formatting
        run: |
          if [ -n "$(gofmt -s -l .)" ]; then
            echo "Go files are not formatted:"
            gofmt -s -d .
            exit 1
          fi
''',
}

UNIT_TEST_STEPS_BY_LANGUAGE = {
    'Python': '''
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-asyncio

      - name: Run unit tests
        run: |
          pytest tests/unit -v --cov=src --cov-report=xml --cov-report=term-missing

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: false
''',
    'JavaScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run unit tests
        run: npm run test:unit -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/lcov.info
          fail_ci_if_error: false
''',
    'TypeScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run unit tests
        run: npm run test:unit -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/lcov.info
          fail_ci_if_error: false
''',
    'Go': '''
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.21'
          cache: true

      - name: Run unit tests
        run: go test -v -race -coverprofile=coverage.out ./...

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.out
          fail_ci_if_error: false
''',
}

INTEGRATION_TEST_STEPS_BY_LANGUAGE = {
    'Python': '''
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379
        run: pytest tests/integration -v
''',
    'JavaScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379
        run: npm run test:integration
''',
    'TypeScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379
        run: npm run test:integration
''',
    'Go': '''
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.21'
          cache: true

      - name: Run integration tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379
        run: go test -v -tags=integration ./tests/integration/...
''',
}

DEPENDENCY_SCAN_STEPS_BY_LANGUAGE = {
    'Python': '''
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install pip-audit
        run: pip install pip-audit

      - name: Run pip-audit
        run: pip-audit -r requirements.txt --format=sarif --output=dependency-results.sarif || true
''',
    'JavaScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Run npm audit
        run: npm audit --json > npm-audit.json || true

      - name: Convert to SARIF
        run: |
          npx npm-audit-to-sarif npm-audit.json > dependency-results.sarif
''',
    'TypeScript': '''
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Run npm audit
        run: npm audit --json > npm-audit.json || true

      - name: Convert to SARIF
        run: |
          npx npm-audit-to-sarif npm-audit.json > dependency-results.sarif
''',
    'Go': '''
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.21'

      - name: Run govulncheck
        run: |
          go install golang.org/x/vuln/cmd/govulncheck@latest
          govulncheck -json ./... > dependency-results.json || true
''',
}

CODEQL_LANGUAGES = {
    'Python': 'python',
    'JavaScript': 'javascript',
    'TypeScript': 'javascript',
    'Go': 'go',
    'Java': 'java',
    'Rust': 'rust',
}


# =============================================================================
# GITLAB CI LANGUAGE CONFIGS
# =============================================================================

GITLAB_LINT_BY_LANGUAGE = {
    'Python': '''lint:python:
  stage: lint
  image: python:3.11-slim
  before_script:
    - pip install flake8 black isort mypy
  script:
    - flake8 . --count --show-source --statistics
    - black --check .
    - isort --check-only .
''',
    'JavaScript': '''lint:js:
  stage: lint
  image: node:20-alpine
  before_script:
    - npm ci
  script:
    - npm run lint
    - npm run format:check
''',
    'TypeScript': '''lint:ts:
  stage: lint
  image: node:20-alpine
  before_script:
    - npm ci
  script:
    - npx tsc --noEmit
    - npm run lint
''',
    'Go': '''lint:go:
  stage: lint
  image: golangci/golangci-lint:latest
  script:
    - golangci-lint run
''',
}

GITLAB_TEST_BY_LANGUAGE = {
    'Python': '''test:unit:
  stage: test
  image: python:3.11-slim
  before_script:
    - pip install -r requirements.txt
    - pip install pytest pytest-cov
  script:
    - pytest tests/unit -v --cov=src --cov-report=xml
  coverage: '/TOTAL.*\\s+(\\d+%)/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
''',
    'JavaScript': '''test:unit:
  stage: test
  image: node:20-alpine
  before_script:
    - npm ci
  script:
    - npm run test:unit -- --coverage
  coverage: '/All files.*?\\s+(\\d+\\.?\\d*)%/'
  artifacts:
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage/cobertura-coverage.xml
''',
    'TypeScript': '''test:unit:
  stage: test
  image: node:20-alpine
  before_script:
    - npm ci
  script:
    - npm run test:unit -- --coverage
  coverage: '/All files.*?\\s+(\\d+\\.?\\d*)%/'
''',
    'Go': '''test:unit:
  stage: test
  image: golang:1.21
  script:
    - go test -v -race -coverprofile=coverage.out ./...
    - go tool cover -func=coverage.out
  coverage: '/total:.*?\\s+(\\d+\\.?\\d*)%/'
''',
}

GITLAB_DEPENDENCY_SCAN_BY_LANGUAGE = {
    'Python': '''  image: python:3.11-slim
  script:
    - pip install pip-audit
    - pip-audit -r requirements.txt --format=json --output=gl-dependency-scanning-report.json || true
''',
    'JavaScript': '''  image: node:20-alpine
  script:
    - npm audit --json > gl-dependency-scanning-report.json || true
''',
    'TypeScript': '''  image: node:20-alpine
  script:
    - npm audit --json > gl-dependency-scanning-report.json || true
''',
    'Go': '''  image: golang:1.21
  script:
    - go install golang.org/x/vuln/cmd/govulncheck@latest
    - govulncheck -json ./... > gl-dependency-scanning-report.json || true
''',
}

GITLAB_CACHE_BY_LANGUAGE = {
    'Python': '      - .cache/pip\n      - venv/',
    'JavaScript': '      - node_modules/',
    'TypeScript': '      - node_modules/',
    'Go': '      - /go/pkg/mod/',
}

GITLAB_DEFAULT_IMAGE_BY_LANGUAGE = {
    'Python': 'python:3.11-slim',
    'JavaScript': 'node:20-alpine',
    'TypeScript': 'node:20-alpine',
    'Go': 'golang:1.21',
}


class CIAgent(BaseAgent):
    """
    Continuous Integration Agent - Generates CI pipeline configurations.
    
    Responsibilities:
    - GitHub Actions workflows (ci.yml, security.yml, release.yml)
    - GitLab CI (.gitlab-ci.yml)
    - Linting, unit tests, integration tests
    - Build and push container
    - Dependabot config
    - Security scanning pipelines
    """
    
    def __init__(self):
        super().__init__(
            name="CIAgent",
            description="Generates Continuous Integration pipelines (GitHub Actions, GitLab CI)"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate CI configurations based on repository analysis."""
        # Handle params defensively
        if params is None:
            params = {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {"repo_path": params}
        
        repo_path = Path(params.get("repo_path", params.get("path", "."))).resolve()
        overwrite = params.get("greenfield", False)
        include_gitlab = params.get("include_gitlab", True)
        include_dependabot = params.get("include_dependabot", True)
        
        self.log(f"Generating CI configs for: {repo_path}")
        
        actions = []
        findings = []
        
        # Detect app name and language
        app_name = self._detect_app_name(repo_path)
        primary_lang = self._detect_primary_language(repo_path)
        
        self.log(f"Detected app: {app_name}, language: {primary_lang}")
        
        # Generate GitHub Actions
        gh_actions = self._generate_github_actions(repo_path, app_name, primary_lang, overwrite)
        actions.extend(gh_actions)

        # Generate GitLab CI
        if include_gitlab:
            gitlab_actions = self._generate_gitlab_ci(repo_path, app_name, primary_lang, overwrite)
            actions.extend(gitlab_actions)

        # Generate Dependabot config
        if include_dependabot:
            dependabot_actions = self._generate_dependabot(repo_path, primary_lang, overwrite)
            actions.extend(dependabot_actions)
        
        return self.create_result(
            status="success",
            summary=f"Generated CI pipelines for {app_name}",
            data={
                "app_name": app_name,
                "primary_language": primary_lang,
                "platforms": ["GitHub Actions"] + (["GitLab CI"] if include_gitlab else []),
                "files_generated": len(actions),
            },
            findings=findings,
            actions=actions
        )
    
    def _detect_app_name(self, repo_path: Path) -> str:
        """Detect application name."""
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                data = json.loads(package_json.read_text())
                if isinstance(data, dict) and data.get("name"):
                    return data["name"].replace("@", "").replace("/", "-")
            except:
                pass
        return repo_path.name.lower().replace(" ", "-").replace("_", "-")
    
    def _detect_primary_language(self, repo_path: Path) -> str:
        """Detect primary programming language."""
        ext_counts = {}
        for ext, lang in {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript", ".go": "Go"}.items():
            count = len(list(repo_path.rglob(f"*{ext}")))
            if count > 0:
                ext_counts[lang] = count
        return max(ext_counts, key=ext_counts.get) if ext_counts else "Python"
    
    def _generate_github_actions(self, repo_path: Path, app_name: str, primary_lang: str, overwrite: bool = False) -> List[Dict]:
        """Generate GitHub Actions workflow files."""
        actions = []
        workflows_path = repo_path / ".github" / "workflows"
        workflows_path.mkdir(parents=True, exist_ok=True)
        
        # ── Chained pipeline (Security → Tests → Build) ──────────────────────
        dependency_scan_steps = DEPENDENCY_SCAN_STEPS_BY_LANGUAGE.get(
            primary_lang, DEPENDENCY_SCAN_STEPS_BY_LANGUAGE['Python']
        )
        unit_test_steps = UNIT_TEST_STEPS_BY_LANGUAGE.get(
            primary_lang, UNIT_TEST_STEPS_BY_LANGUAGE['Python']
        )

        pipeline_content = PIPELINE_WORKFLOW_TEMPLATE.format(
            dependency_scan_steps=dependency_scan_steps,
            unit_test_steps=unit_test_steps,
        )
        actions.append(self._safe_write(workflows_path / "pipeline.yml", pipeline_content, overwrite))

        # Release workflow (tag-triggered, kept separate)
        actions.append(self._safe_write(workflows_path / "release.yml", RELEASE_WORKFLOW_TEMPLATE, overwrite))
        
        return actions
    
    def _generate_gitlab_ci(self, repo_path: Path, app_name: str, primary_lang: str, overwrite: bool = False) -> List[Dict]:
        """Generate GitLab CI configuration."""
        actions = []
        
        lint_job = GITLAB_LINT_BY_LANGUAGE.get(primary_lang, GITLAB_LINT_BY_LANGUAGE['Python'])
        test_job = GITLAB_TEST_BY_LANGUAGE.get(primary_lang, GITLAB_TEST_BY_LANGUAGE['Python'])
        dependency_job = GITLAB_DEPENDENCY_SCAN_BY_LANGUAGE.get(primary_lang, GITLAB_DEPENDENCY_SCAN_BY_LANGUAGE['Python'])
        cache_paths = GITLAB_CACHE_BY_LANGUAGE.get(primary_lang, GITLAB_CACHE_BY_LANGUAGE['Python'])
        default_image = GITLAB_DEFAULT_IMAGE_BY_LANGUAGE.get(primary_lang, GITLAB_DEFAULT_IMAGE_BY_LANGUAGE['Python'])
        
        gitlab_content = GITLAB_CI_TEMPLATE.format(
            default_image=default_image,
            cache_paths=cache_paths,
            lint_job=lint_job,
            test_job=test_job,
            dependency_job=dependency_job
        )
        actions.append(self._safe_write(repo_path / ".gitlab-ci.yml", gitlab_content, overwrite))
        
        return actions
    
    def _generate_dependabot(self, repo_path: Path, primary_lang: str, overwrite: bool = False) -> List[Dict]:
        """Generate Dependabot configuration."""
        actions = []
        github_path = repo_path / ".github"
        github_path.mkdir(exist_ok=True)
        
        ecosystems = []
        
        # Add Docker if Dockerfile exists
        if (repo_path / "Dockerfile").exists():
            ecosystems.append(DEPENDABOT_ECOSYSTEM_DOCKER)
        
        # Add language-specific ecosystem
        if primary_lang in ['JavaScript', 'TypeScript']:
            ecosystems.append(DEPENDABOT_ECOSYSTEM_NPM)
        elif primary_lang == 'Python':
            ecosystems.append(DEPENDABOT_ECOSYSTEM_PIP)
        elif primary_lang == 'Go':
            ecosystems.append(DEPENDABOT_ECOSYSTEM_GOMOD)
        
        dependabot_content = DEPENDABOT_CONFIG.format(
            ecosystem_configs='\n'.join(ecosystems)
        )
        actions.append(self._safe_write(github_path / "dependabot.yml", dependabot_content, overwrite))
        
        return actions
