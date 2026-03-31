#!/usr/bin/env python3
"""
LifecycleAgent — GitHub Actions CI/CD Lifecycle Workflow Generation.

Generates three properly workflow_run-chained GitHub Actions files:

  .github/workflows/ci.yml        push/PR → lint → security scan → build → push image
  .github/workflows/test.yml      workflow_run(ci) → unit → integration → E2E → coverage
  .github/workflows/cd.yml        workflow_run(test, main only) → staging → validate →
                                  production approval gate → prod deploy → validate →
                                  auto-rollback on failure → Slack notify

This sits downstream of BridgeAgent/SecretsAgent: secrets must be bootstrapped
(see docs/DEPLOYMENT_GUIDE.md) before these workflows can succeed.

Architecture:
  forgeflow lifecycle <path> → lifecycle_mcp → LifecycleAgent
"""
from pathlib import Path
from typing import Dict, Any, List, Optional

from .base_agent import BaseAgent


# =============================================================================
# CI WORKFLOW
# Triggers: push to main/develop/feature/*, PR to main/develop
# Jobs: lint → security-scan → build-push (needs both)
# Emits: workflow_run event consumed by test.yml
# =============================================================================

CI_WORKFLOW = '''\
# =============================================================================
# ForgeFlow — CI Workflow
# Stage 1 of 3: Lint · Security Scan · Build · Push Image
# Triggers test.yml on success via workflow_run.
# =============================================================================
name: CI

on:
  push:
    branches: [main, develop, "feature/**", "fix/**"]
  pull_request:
    branches: [main, develop]

concurrency:
  group: ci-${{{{ github.ref }}}}
  cancel-in-progress: true

env:
  REGISTRY: {registry}
  IMAGE_NAME: ${{{{ github.repository }}}}

jobs:
  # ---------------------------------------------------------------------------
  # 1. Lint & Static Analysis
  # ---------------------------------------------------------------------------
  lint:
    name: "🔍 Lint"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

{lint_steps}

  # ---------------------------------------------------------------------------
  # 2. Security Scan (Trivy + Gitleaks)
  # ---------------------------------------------------------------------------
  security-scan:
    name: "🔒 Security Scan"
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # full history for secret scanning

      - name: Gitleaks — secret detection
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Trivy — filesystem vulnerability scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: "fs"
          scan-ref: "."
          format: "table"
          exit-code: "1"
          severity: "CRITICAL,HIGH"
          ignore-unfixed: true

  # ---------------------------------------------------------------------------
  # 3. Build & Push Container Image
  # ---------------------------------------------------------------------------
  build-push:
    name: "🐳 Build & Push"
    runs-on: ubuntu-latest
    needs: [lint, security-scan]
    permissions:
      contents: read
      packages: write
    outputs:
      image-tag: ${{{{ steps.meta.outputs.tags }}}}
      image-digest: ${{{{ steps.build.outputs.digest }}}}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to {registry_name}
        uses: docker/login-action@v3
        with:
{registry_login}

      - name: Extract Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}
          tags: |
            type=ref,event=branch
            type=ref,event=pr
            type=sha,prefix=sha-,format=short
            type=raw,value=latest,enable=${{{{ github.ref == \'refs/heads/main\' }}}}

      - name: Build and push image
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          push: ${{{{ github.event_name != \'pull_request\' }}}}
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          provenance: true
          sbom: true

      - name: Image security scan (built image)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ github.sha }}}}
          format: "sarif"
          output: "trivy-results.sarif"
          severity: "CRITICAL,HIGH"
        continue-on-error: true    # informational on already-pushed image

      - name: Upload scan results
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: "trivy-results.sarif"
        continue-on-error: true
'''

# =============================================================================
# TEST WORKFLOW
# Triggers: workflow_run[CI] completed successfully
# Jobs: unit → integration (service containers) → e2e → coverage upload
# =============================================================================

TEST_WORKFLOW = '''\
# =============================================================================
# ForgeFlow — Test Workflow
# Stage 2 of 3: Unit · Integration · E2E · Coverage
# Triggered automatically when CI workflow succeeds (workflow_run).
# Triggers cd.yml on success via workflow_run.
# =============================================================================
name: Tests

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main, develop]

jobs:
  # Guard: only proceed if CI passed
  check-ci:
    name: "🚦 CI Status Gate"
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == \'success\' }}}}
    steps:
      - name: CI passed — proceeding with tests
        run: echo "CI conclusion=${{{{ github.event.workflow_run.conclusion }}}}"

  # ---------------------------------------------------------------------------
  # 1. Unit Tests
  # ---------------------------------------------------------------------------
  unit:
    name: "🧪 Unit Tests"
    runs-on: ubuntu-latest
    needs: check-ci
{unit_matrix}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

{unit_steps}

      - name: Upload coverage artifact
        uses: actions/upload-artifact@v4
        with:
          name: coverage-unit-${{{{ matrix.{lang}-version || \'default\' }}}}
          path: {coverage_path}
          retention-days: 7

  # ---------------------------------------------------------------------------
  # 2. Integration Tests (with service containers)
  # ---------------------------------------------------------------------------
  integration:
    name: "🔗 Integration Tests"
    runs-on: ubuntu-latest
    needs: unit
    services:
{service_containers}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

{integration_steps}

  # ---------------------------------------------------------------------------
  # 3. End-to-End Tests
  # ---------------------------------------------------------------------------
  e2e:
    name: "🌐 E2E Tests"
    runs-on: ubuntu-latest
    needs: integration
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

{e2e_steps}

  # ---------------------------------------------------------------------------
  # 4. Coverage Aggregation & Upload
  # ---------------------------------------------------------------------------
  coverage:
    name: "📊 Coverage Report"
    runs-on: ubuntu-latest
    needs: [unit, integration, e2e]
    if: always()
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

      - name: Download all coverage artifacts
        uses: actions/download-artifact@v4
        with:
          pattern: coverage-*
          merge-multiple: true
          path: coverage/

      - name: Upload combined coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          directory: coverage/
          token: ${{{{ secrets.CODECOV_TOKEN }}}}
          fail_ci_if_error: false
          verbose: true

  # Final gate that cd.yml watches
  tests-passed:
    name: "✅ All Tests Passed"
    runs-on: ubuntu-latest
    needs: [unit, integration, e2e, coverage]
    if: success()
    steps:
      - name: Tests gate passed
        run: echo "All test suites succeeded — CD workflow will trigger."
'''

# =============================================================================
# CD WORKFLOW
# Triggers: workflow_run[Tests] completed successfully, HEAD is on main
# Jobs: deploy-staging → validate-staging → prod-approval → deploy-prod →
#       validate-prod → rollback (on failure) → notify
# =============================================================================

CD_WORKFLOW = '''\
# =============================================================================
# ForgeFlow — CD Workflow
# Stage 3 of 3: Deploy Staging → Validate → Approval → Deploy Prod → Validate
# Auto-rollback on failure. Slack notification on every outcome.
# Triggered automatically when Tests workflow succeeds on main (workflow_run).
# =============================================================================
name: CD

on:
  workflow_run:
    workflows: ["Tests"]
    types: [completed]
    branches: [main]           # CD only from main; develop stays in staging

env:
  REGISTRY: {registry}
  IMAGE_NAME: ${{{{ github.repository }}}}
  IMAGE_TAG: ${{{{ github.event.workflow_run.head_sha }}}}
  APP_NAME: {app_name}

jobs:
  # Guard: only proceed if Tests passed
  check-tests:
    name: "🚦 Test Gate"
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == \'success\' }}}}
    steps:
      - name: Tests passed — proceeding with deployment
        run: echo "Tests conclusion=${{{{ github.event.workflow_run.conclusion }}}}"

  # ---------------------------------------------------------------------------
  # 1. Deploy to Staging
  # ---------------------------------------------------------------------------
  deploy-staging:
    name: "🚀 Deploy → Staging"
    runs-on: ubuntu-latest
    needs: check-tests
    environment:
      name: staging
      url: https://{domain}/staging
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

{deploy_staging_steps}

      - name: Update staging image tag (Kustomize)
        run: |
          cd infrastructure/k8s/overlays/staging
          kustomize edit set image ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}=${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          cat kustomization.yaml

      - name: Commit & push staging manifest
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add infrastructure/k8s/overlays/staging/kustomization.yaml
          git diff --cached --quiet && echo "No manifest change" && exit 0
          git commit -m "chore(cd): staging image → ${{{{ env.IMAGE_TAG }}}}"
          git push

      - name: Wait for ArgoCD staging sync
        run: |
          echo "Waiting for ArgoCD to sync staging application..."
          for i in $(seq 1 30); do
            STATUS=$(argocd app get ${{{{ env.APP_NAME }}}}-staging \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.sync.status' 2>/dev/null || echo "Unknown")
            HEALTH=$(argocd app get ${{{{ env.APP_NAME }}}}-staging \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.health.status' 2>/dev/null || echo "Unknown")
            echo "[$i/30] Sync=$STATUS  Health=$HEALTH"
            if [[ "$STATUS" == "Synced" && "$HEALTH" == "Healthy" ]]; then
              echo "✅ Staging is Synced and Healthy"
              exit 0
            fi
            sleep 10
          done
          echo "❌ ArgoCD staging sync timed out"
          exit 1

  # ---------------------------------------------------------------------------
  # 2. Validate Staging (health check + smoke tests)
  # ---------------------------------------------------------------------------
  validate-staging:
    name: "✅ Validate Staging"
    runs-on: ubuntu-latest
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

      - name: Health check — staging
        run: |
          BASE=https://{domain}/staging
          echo "Hitting $BASE/health ..."
          for i in $(seq 1 12); do
            CODE=$(curl -sf -o /dev/null -w "%{{http_code}}" "$BASE/health" || echo "000")
            echo "  attempt $i: HTTP $CODE"
            if [[ "$CODE" == "200" ]]; then
              echo "✅ Health check passed"
              exit 0
            fi
            sleep 10
          done
          echo "❌ Staging health check failed after 2 minutes"
          exit 1

      - name: Smoke tests — staging
        run: |
          BASE=https://{domain}/staging
          echo "Running smoke tests against $BASE ..."
{smoke_test_steps}
          echo "✅ Smoke tests passed"

  # ---------------------------------------------------------------------------
  # 3. Production Approval Gate (GitHub Environment protection rule)
  # ---------------------------------------------------------------------------
  production-approval:
    name: "🔐 Production Approval"
    runs-on: ubuntu-latest
    needs: validate-staging
    environment:
      name: production           # configure required reviewers in repo Settings
      url: https://{domain}
    steps:
      - name: Approval granted
        run: echo "Production deployment approved — proceeding."

  # ---------------------------------------------------------------------------
  # 4. Deploy to Production
  # ---------------------------------------------------------------------------
  deploy-production:
    name: "🚀 Deploy → Production"
    runs-on: ubuntu-latest
    needs: production-approval
    environment:
      name: production
      url: https://{domain}
    outputs:
      previous-tag: ${{{{ steps.prev-tag.outputs.tag }}}}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}
          fetch-depth: 2

      - name: Record previous production image tag
        id: prev-tag
        run: |
          PREV=$(cd infrastructure/k8s/overlays/production && \
            grep 'newTag:' kustomization.yaml | awk '{{print $2}}' | head -1 || echo "")
          echo "tag=$PREV" >> $GITHUB_OUTPUT
          echo "Previous production tag: $PREV"

{deploy_prod_steps}

      - name: Update production image tag (Kustomize)
        run: |
          cd infrastructure/k8s/overlays/production
          kustomize edit set image ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}=${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ env.IMAGE_TAG }}}}
          cat kustomization.yaml

      - name: Commit & push production manifest
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add infrastructure/k8s/overlays/production/kustomization.yaml
          git diff --cached --quiet && echo "No manifest change" && exit 0
          git commit -m "chore(cd): production image → ${{{{ env.IMAGE_TAG }}}}"
          git push

      - name: Wait for ArgoCD production sync
        run: |
          echo "Waiting for ArgoCD to sync production application..."
          for i in $(seq 1 60); do
            STATUS=$(argocd app get ${{{{ env.APP_NAME }}}}-production \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.sync.status' 2>/dev/null || echo "Unknown")
            HEALTH=$(argocd app get ${{{{ env.APP_NAME }}}}-production \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.health.status' 2>/dev/null || echo "Unknown")
            echo "[$i/60] Sync=$STATUS  Health=$HEALTH"
            if [[ "$STATUS" == "Synced" && "$HEALTH" == "Healthy" ]]; then
              echo "✅ Production is Synced and Healthy"
              exit 0
            fi
            sleep 10
          done
          echo "❌ ArgoCD production sync timed out"
          exit 1

  # ---------------------------------------------------------------------------
  # 5. Validate Production
  # ---------------------------------------------------------------------------
  validate-production:
    name: "✅ Validate Production"
    runs-on: ubuntu-latest
    needs: deploy-production
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_sha }}}}

      - name: Health check — production
        run: |
          BASE=https://{domain}
          echo "Hitting $BASE/health ..."
          for i in $(seq 1 12); do
            CODE=$(curl -sf -o /dev/null -w "%{{http_code}}" "$BASE/health" || echo "000")
            echo "  attempt $i: HTTP $CODE"
            if [[ "$CODE" == "200" ]]; then
              echo "✅ Production health check passed"
              exit 0
            fi
            sleep 10
          done
          echo "❌ Production health check failed"
          exit 1

      - name: Production smoke tests
        run: |
          BASE=https://{domain}
          echo "Running production smoke tests against $BASE ..."
{smoke_test_steps}
          echo "✅ Production smoke tests passed"

  # ---------------------------------------------------------------------------
  # 6. Auto-Rollback on Failure
  # Runs only if deploy-production or validate-production failed
  # ---------------------------------------------------------------------------
  rollback:
    name: "⏪ Auto-Rollback"
    runs-on: ubuntu-latest
    needs: [deploy-production, validate-production]
    if: |
      always() &&
      (needs.deploy-production.result == \'failure\' ||
       needs.validate-production.result == \'failure\')
    steps:
      - uses: actions/checkout@v4

      - name: Restore previous image tag
        env:
          PREV_TAG: ${{{{ needs.deploy-production.outputs.previous-tag }}}}
        run: |
          if [[ -z "$PREV_TAG" ]]; then
            echo "⚠️  No previous tag found — cannot auto-rollback"
            exit 1
          fi
          echo "Rolling back production to: $PREV_TAG"
          cd infrastructure/k8s/overlays/production
          kustomize edit set image ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}=${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:$PREV_TAG
          cat kustomization.yaml

      - name: Commit & push rollback manifest
        env:
          PREV_TAG: ${{{{ needs.deploy-production.outputs.previous-tag }}}}
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add infrastructure/k8s/overlays/production/kustomization.yaml
          git diff --cached --quiet && echo "Already rolled back" && exit 0
          git commit -m "chore(rollback): production reverted to $PREV_TAG"
          git push

      - name: Wait for ArgoCD rollback sync
        run: |
          echo "Waiting for ArgoCD rollback sync..."
          for i in $(seq 1 30); do
            STATUS=$(argocd app get ${{{{ env.APP_NAME }}}}-production \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.sync.status' 2>/dev/null || echo "Unknown")
            HEALTH=$(argocd app get ${{{{ env.APP_NAME }}}}-production \
              --auth-token ${{{{ secrets.ARGOCD_TOKEN }}}} \
              --server     ${{{{ secrets.ARGOCD_SERVER }}}} \
              --grpc-web \
              -o json 2>/dev/null | jq -r '.status.health.status' 2>/dev/null || echo "Unknown")
            echo "[$i/30] Sync=$STATUS  Health=$HEALTH"
            if [[ "$STATUS" == "Synced" && "$HEALTH" == "Healthy" ]]; then
              echo "✅ Rollback succeeded"
              exit 0
            fi
            sleep 10
          done
          echo "❌ Rollback sync timed out — manual intervention required"
          exit 1

  # ---------------------------------------------------------------------------
  # 7. Slack Notification (success or failure)
  # ---------------------------------------------------------------------------
  notify:
    name: "📣 Notify"
    runs-on: ubuntu-latest
    needs: [validate-production, rollback]
    if: always()
    steps:
      - name: Set notification vars
        id: vars
        run: |
          if [[ "${{{{ needs.validate-production.result }}}}" == "success" ]]; then
            echo "status=✅ Production deployment succeeded" >> $GITHUB_OUTPUT
            echo "color=#28a745" >> $GITHUB_OUTPUT
          elif [[ "${{{{ needs.rollback.result }}}}" == "success" ]]; then
            echo "status=⏪ Rollback completed — previous version restored" >> $GITHUB_OUTPUT
            echo "color=#f0ad4e" >> $GITHUB_OUTPUT
          else
            echo "status=❌ Deployment failed — manual intervention required" >> $GITHUB_OUTPUT
            echo "color=#dc3545" >> $GITHUB_OUTPUT
          fi

      - name: Send Slack notification
        uses: slackapi/slack-github-action@v1.26.0
        with:
          payload: |
            {{
              "attachments": [
                {{
                  "color": "${{{{ steps.vars.outputs.color }}}}",
                  "blocks": [
                    {{
                      "type": "section",
                      "text": {{
                        "type": "mrkdwn",
                        "text": "*${{{{ steps.vars.outputs.status }}}}*\\n*App:* `${{{{ env.APP_NAME }}}}`  *Tag:* `${{{{ env.IMAGE_TAG }}}}`\\n*Triggered by:* <${{{{ github.event.workflow_run.html_url }}}}|workflow run>  *Commit:* <${{{{ github.server_url }}}}/${{{{ github.repository }}}}/commit/${{{{ env.IMAGE_TAG }}}}|${{{{ env.IMAGE_TAG }}}}>\\n*Branch:* `${{{{ github.event.workflow_run.head_branch }}}}`"
                      }}
                    }}
                  ]
                }}
              ]
            }}
        env:
          SLACK_WEBHOOK_URL: ${{{{ secrets.SLACK_WEBHOOK_URL }}}}
          SLACK_WEBHOOK_TYPE: INCOMING_WEBHOOK
        continue-on-error: true   # never fail the workflow over a notification
'''


# =============================================================================
# Language-specific lint steps
# =============================================================================

LINT_STEPS = {
    "python": """\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install lint tools
        run: pip install ruff mypy --quiet

      - name: Ruff — lint
        run: ruff check .

      - name: Ruff — format check
        run: ruff format --check .

      - name: Mypy — type check
        run: mypy . --ignore-missing-imports
        continue-on-error: true
""",
    "node": """\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: ESLint
        run: npm run lint

      - name: Prettier format check
        run: npm run format:check
        continue-on-error: true
""",
    "go": """\
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true

      - name: golangci-lint
        uses: golangci/golangci-lint-action@v4
        with:
          version: latest
""",
    "java": """\
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: "temurin"
          cache: "maven"

      - name: Checkstyle
        run: mvn checkstyle:check -q
""",
}

# =============================================================================
# Language-specific unit test steps + matrix
# =============================================================================

UNIT_MATRIX = {
    "python": """\
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
""",
    "node": """\
    strategy:
      fail-fast: false
      matrix:
        node-version: ["18", "20", "22"]
""",
    "go": "",
    "java": """\
    strategy:
      fail-fast: false
      matrix:
        java-version: ["17", "21"]
""",
}

UNIT_STEPS = {
    "python": """\
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt pytest pytest-cov --quiet

      - name: Run unit tests with coverage
        run: pytest tests/unit/ -v --cov=. --cov-report=xml --cov-report=term-missing
""",
    "node": """\
      - name: Set up Node.js ${{ matrix.node-version }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Run unit tests with coverage
        run: npm run test:unit -- --coverage --coverageReporters=lcov
""",
    "go": """\
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true

      - name: Run unit tests with coverage
        run: go test ./... -v -coverprofile=coverage.out -covermode=atomic

      - name: Convert coverage to lcov
        run: go tool cover -func=coverage.out
""",
    "java": """\
      - name: Set up JDK ${{ matrix.java-version }}
        uses: actions/setup-java@v4
        with:
          java-version: ${{ matrix.java-version }}
          distribution: "temurin"
          cache: "maven"

      - name: Run unit tests with coverage
        run: mvn test jacoco:report -q
""",
}

COVERAGE_PATH = {
    "python": "coverage.xml",
    "node": "coverage/lcov.info",
    "go": "coverage.out",
    "java": "target/site/jacoco/",
}

# =============================================================================
# Service containers for integration tests
# =============================================================================

SERVICE_CONTAINERS = {
    "python": """\
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
""",
    "node": """\
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
""",
    "go": """\
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
""",
    "java": """\
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
""",
}

INTEGRATION_STEPS = {
    "python": """\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt pytest --quiet

      - name: Run integration tests
        run: pytest tests/integration/ -v
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379
""",
    "node": """\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Run integration tests
        run: npm run test:integration
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379
""",
    "go": """\
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true

      - name: Run integration tests
        run: go test ./tests/integration/... -v -tags=integration
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
""",
    "java": """\
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: "temurin"
          cache: "maven"

      - name: Run integration tests
        run: mvn verify -Pintegration-tests -q
        env:
          SPRING_DATASOURCE_URL: jdbc:postgresql://localhost:5432/testdb
          SPRING_DATASOURCE_USERNAME: test
          SPRING_DATASOURCE_PASSWORD: test
""",
}

E2E_STEPS = {
    "python": """\
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install Playwright + dependencies
        run: |
          pip install playwright pytest-playwright --quiet
          playwright install --with-deps chromium

      - name: Run E2E tests
        run: pytest tests/e2e/ -v --screenshot=on-failure
        env:
          BASE_URL: ${{ vars.STAGING_URL || 'http://localhost:8000' }}

      - name: Upload E2E screenshots/videos
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: e2e-screenshots
          path: test-results/
          retention-days: 7
""",
    "node": """\
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - name: Install dependencies
        run: npm ci

      - name: Install Playwright browsers
        run: npx playwright install --with-deps chromium

      - name: Run E2E tests
        run: npm run test:e2e
        env:
          BASE_URL: ${{ vars.STAGING_URL || 'http://localhost:3000' }}

      - name: Upload Playwright report
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: playwright-report/
          retention-days: 7
""",
    "go": """\
      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: "1.22"
          cache: true

      - name: Run E2E tests
        run: go test ./tests/e2e/... -v -tags=e2e
        env:
          BASE_URL: ${{ vars.STAGING_URL || 'http://localhost:8080' }}
""",
    "java": """\
      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          java-version: "21"
          distribution: "temurin"
          cache: "maven"

      - name: Run E2E tests
        run: mvn verify -Pe2e-tests -q
        env:
          BASE_URL: ${{ vars.STAGING_URL || 'http://localhost:8080' }}
""",
}

# =============================================================================
# Registry-specific login steps
# =============================================================================

REGISTRY_LOGIN = {
    "ghcr": (
        "ghcr.io",
        "GitHub Container Registry (ghcr.io)",
        """\
          registry: ghcr.io
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}""",
    ),
    "ecr": (
        "${{ secrets.AWS_ACCOUNT_ID }}.dkr.ecr.${{ secrets.AWS_REGION }}.amazonaws.com",
        "Amazon ECR",
        """\
          registry: ${{{{ secrets.AWS_ACCOUNT_ID }}}}.dkr.ecr.${{{{ secrets.AWS_REGION }}}}.amazonaws.com
          username: ${{{{ secrets.AWS_ACCESS_KEY_ID }}}}
          password: ${{{{ secrets.AWS_SECRET_ACCESS_KEY }}}}""",
    ),
    "gcr": (
        "gcr.io",
        "Google Container Registry (gcr.io)",
        """\
          registry: gcr.io
          username: _json_key
          password: ${{{{ secrets.GCP_SA_KEY }}}}""",
    ),
    "dockerhub": (
        "docker.io",
        "Docker Hub",
        """\
          username: ${{{{ secrets.DOCKERHUB_USERNAME }}}}
          password: ${{{{ secrets.DOCKERHUB_TOKEN }}}}""",
    ),
}

# Cloud-specific deploy steps
DEPLOY_STAGING_STEPS = {
    "aws": """\
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{{{ secrets.AWS_ACCESS_KEY_ID }}}}
          aws-secret-access-key: ${{{{ secrets.AWS_SECRET_ACCESS_KEY }}}}
          aws-region: ${{{{ secrets.AWS_REGION }}}}

      - name: Install tools (kubectl + kustomize + argocd)
        run: |
          curl -sLO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
          chmod +x kubectl && sudo mv kubectl /usr/local/bin/
          curl -sLO "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.3.0/kustomize_v5.3.0_linux_amd64.tar.gz"
          tar -xzf kustomize_*.tar.gz && sudo mv kustomize /usr/local/bin/
          curl -sSL -o argocd-linux-amd64 https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
          aws eks update-kubeconfig --name ${{{{ secrets.EKS_CLUSTER_NAME }}}} --region ${{{{ secrets.AWS_REGION }}}}
""",
    "gcp": """\
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{{{ secrets.GCP_SA_KEY }}}}

      - name: Set up gcloud + kubectl
        uses: google-github-actions/setup-gcloud@v2

      - name: Install kustomize + argocd
        run: |
          curl -sLO "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.3.0/kustomize_v5.3.0_linux_amd64.tar.gz"
          tar -xzf kustomize_*.tar.gz && sudo mv kustomize /usr/local/bin/
          curl -sSL -o argocd-linux-amd64 https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
          gcloud container clusters get-credentials ${{{{ secrets.GKE_CLUSTER_NAME }}}} \
            --zone ${{{{ secrets.GCP_ZONE }}}} --project ${{{{ secrets.GCP_PROJECT_ID }}}}
""",
    "azure": """\
      - name: Log in to Azure
        uses: azure/login@v2
        with:
          creds: ${{{{ secrets.AZURE_CREDENTIALS }}}}

      - name: Set up kubectl + kustomize + argocd
        run: |
          az aks get-credentials --resource-group ${{{{ secrets.AZURE_RESOURCE_GROUP }}}} \
            --name ${{{{ secrets.AKS_CLUSTER_NAME }}}}
          curl -sLO "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2Fv5.3.0/kustomize_v5.3.0_linux_amd64.tar.gz"
          tar -xzf kustomize_*.tar.gz && sudo mv kustomize /usr/local/bin/
          curl -sSL -o argocd-linux-amd64 https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          sudo install -m 555 argocd-linux-amd64 /usr/local/bin/argocd
""",
}

SMOKE_TEST_STEPS = """\
          # Verify key API endpoints are responding
          curl -sf "https://{domain}/health"        | jq '.status' | grep -q '"ok"'
          curl -sf "https://{domain}/api/version"   | jq '.' > /dev/null
          echo "  ✅ /health — OK"
          echo "  ✅ /api/version — OK"
"""


# =============================================================================
# Agent class
# =============================================================================

class LifecycleAgent(BaseAgent):
    """
    Generates three chained GitHub Actions workflows that implement the full
    CI → Test → CD lifecycle for any repo pushed through ForgeFlow.

    Workflow chain:
      push/PR → ci.yml → [CI passes] → test.yml → [Tests pass, main] → cd.yml
                                                                        ↓
                                          staging deploy → validate → prod approval
                                          → prod deploy → validate → rollback (on fail)
                                          → Slack notify
    """

    def __init__(self):
        super().__init__(
            name="lifecycle_agent",
            description="Generate CI/CD lifecycle workflows: ci.yml → test.yml → cd.yml"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate the three workflow files.

        Params:
            path         : repo root path (required)
            overwrite    : overwrite existing workflow files (default: False)
            app_name     : application name (default: folder name)
            domain       : production domain hint (default: example.com)
            registry     : ghcr | ecr | gcr | dockerhub (default: ghcr)
            cloud        : aws | gcp | azure (default: aws)
            lang         : python | node | go | java (default: python)
        """
        repo_path = Path(params.get("path", ".") or ".").resolve()
        overwrite  = params.get("overwrite", False)
        app_name   = params.get("app_name") or repo_path.name
        domain     = params.get("domain") or self._detect_domain(repo_path)
        registry   = params.get("registry") or self._detect_registry(repo_path)
        cloud      = params.get("cloud") or self._detect_cloud(repo_path)
        lang       = params.get("lang") or self._detect_lang(repo_path)

        self.log(f"Generating lifecycle workflows: lang={lang} cloud={cloud} "
                 f"registry={registry} domain={domain}")

        workflow_dir = repo_path / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)

        actions: List[Dict[str, Any]] = []

        # --- ci.yml ---
        ci_content = self._render_ci(lang, registry)
        actions.append(self._safe_write(workflow_dir / "ci.yml", ci_content, overwrite))

        # --- test.yml ---
        test_content = self._render_test(lang)
        actions.append(self._safe_write(workflow_dir / "test.yml", test_content, overwrite))

        # --- cd.yml ---
        cd_content = self._render_cd(app_name, domain, registry, cloud)
        actions.append(self._safe_write(workflow_dir / "cd.yml", cd_content, overwrite))

        created   = [a["file"] for a in actions if a["action"] == "created"]
        updated   = [a["file"] for a in actions if a["action"] == "updated"]
        skipped   = [a["file"] for a in actions if a["action"] == "exists"]

        findings = [
            "📋 CI/CD Lifecycle — three chained GitHub Actions workflows",
            "",
            "Workflow chain:",
            "  push/PR  →  ci.yml  →  test.yml  →  cd.yml",
            "                                          ↓",
            "                     staging deploy → validate → prod approval",
            "                     → prod deploy  → validate → auto-rollback",
            "                                              → Slack notify",
            "",
        ]
        if created:
            findings.append(f"✅ Created: {', '.join(created)}")
        if updated:
            findings.append(f"♻️  Updated: {', '.join(updated)}")
        if skipped:
            findings.append(f"⏭️  Skipped (already exist): {', '.join(skipped)}")

        findings += [
            "",
            "Required GitHub Secrets (see docs/DEPLOYMENT_GUIDE.md):",
            "  ARGOCD_TOKEN, ARGOCD_SERVER — ArgoCD access",
            "  SLACK_WEBHOOK_URL          — Slack notifications",
            f"  Cloud secrets for {cloud.upper()} (see SecretsAgent output)",
            "",
            "GitHub Environment Setup:",
            "  1. Go to repo Settings → Environments",
            "  2. Create 'staging' environment",
            "  3. Create 'production' environment with required reviewers",
            "     (this is the manual approval gate before prod deploys)",
        ]

        status = "success" if (created or updated) else "warning"
        summary = (f"Generated lifecycle workflows: "
                   f"{len(created)} created, {len(updated)} updated, {len(skipped)} skipped")

        result = self.create_result(
            status=status,
            summary=summary,
            data={
                "workflow_dir": str(workflow_dir),
                "app_name": app_name,
                "domain": domain,
                "registry": registry,
                "cloud": cloud,
                "lang": lang,
                "files": {
                    "ci":   str(workflow_dir / "ci.yml"),
                    "test": str(workflow_dir / "test.yml"),
                    "cd":   str(workflow_dir / "cd.yml"),
                },
            },
            findings=findings,
            actions=actions,
        )
        self.save_result(result)
        return result

    # -------------------------------------------------------------------------
    # Renderers
    # -------------------------------------------------------------------------

    def _render_ci(self, lang: str, registry: str) -> str:
        lint_steps = LINT_STEPS.get(lang, LINT_STEPS["python"])
        reg_url, reg_name, reg_login = REGISTRY_LOGIN.get(registry, REGISTRY_LOGIN["ghcr"])
        return CI_WORKFLOW.format(
            registry=reg_url,
            registry_name=reg_name,
            registry_login=reg_login,
            lint_steps=lint_steps,
        )

    def _render_test(self, lang: str) -> str:
        matrix       = UNIT_MATRIX.get(lang, "")
        unit_steps   = UNIT_STEPS.get(lang, UNIT_STEPS["python"])
        cov_path     = COVERAGE_PATH.get(lang, "coverage.xml")
        svc          = SERVICE_CONTAINERS.get(lang, SERVICE_CONTAINERS["python"])
        integ_steps  = INTEGRATION_STEPS.get(lang, INTEGRATION_STEPS["python"])
        e2e_steps    = E2E_STEPS.get(lang, E2E_STEPS["python"])

        # matrix token needs the right key
        matrix_key_map = {"python": "python", "node": "node", "go": "go", "java": "java"}
        mk = matrix_key_map.get(lang, "python")

        return TEST_WORKFLOW.format(
            lang=mk,
            unit_matrix=matrix,
            unit_steps=unit_steps,
            coverage_path=cov_path,
            service_containers=svc,
            integration_steps=integ_steps,
            e2e_steps=e2e_steps,
        )

    def _render_cd(self, app_name: str, domain: str, registry: str, cloud: str) -> str:
        reg_url, _, _ = REGISTRY_LOGIN.get(registry, REGISTRY_LOGIN["ghcr"])
        deploy_steps  = DEPLOY_STAGING_STEPS.get(cloud, DEPLOY_STAGING_STEPS["aws"])
        smoke         = SMOKE_TEST_STEPS.format(domain=domain)
        return CD_WORKFLOW.format(
            registry=reg_url,
            app_name=app_name,
            domain=domain,
            deploy_staging_steps=deploy_steps,
            deploy_prod_steps=deploy_steps,
            smoke_test_steps=smoke,
        )

    # -------------------------------------------------------------------------
    # Detection helpers
    # -------------------------------------------------------------------------

    def _detect_lang(self, repo_path: Path) -> str:
        checks = [
            (["requirements.txt", "setup.py", "pyproject.toml"], "python"),
            (["package.json"],                                    "node"),
            (["go.mod"],                                          "go"),
            (["pom.xml", "build.gradle"],                         "java"),
        ]
        for files, lang in checks:
            if any((repo_path / f).exists() for f in files):
                self.log(f"Detected language: {lang}")
                return lang
        self.log("Language not detected — defaulting to python")
        return "python"

    def _detect_registry(self, repo_path: Path) -> str:
        """Infer container registry from existing workflow files or IaC."""
        search_files = list(repo_path.glob(".github/workflows/*.yml")) + \
                       list(repo_path.glob("infrastructure/**/*.tf"))
        for fp in search_files:
            try:
                text = fp.read_text(errors="ignore").lower()
                if "ecr" in text or "amazonaws.com" in text:
                    return "ecr"
                if "gcr.io" in text or "artifact-registry" in text:
                    return "gcr"
                if "azurecr.io" in text:
                    return "acr"
                if "docker.io" in text or "dockerhub" in text:
                    return "dockerhub"
            except Exception:
                pass
        return "ghcr"

    def _detect_cloud(self, repo_path: Path) -> str:
        """Infer cloud provider from .tf files or existing workflows."""
        search_files = list(repo_path.glob("**/*.tf")) + \
                       list(repo_path.glob(".github/workflows/*.yml"))
        for fp in search_files[:20]:
            try:
                text = fp.read_text(errors="ignore").lower()
                if "aws" in text or "amazon" in text or "eks" in text:
                    return "aws"
                if "google" in text or "gcp" in text or "gke" in text:
                    return "gcp"
                if "azure" in text or "aks" in text:
                    return "azure"
            except Exception:
                pass
        return "aws"

    def _detect_domain(self, repo_path: Path) -> str:
        """Try to read domain hint from ingress YAML or ArgoCD app."""
        candidates = (
            list(repo_path.glob("infrastructure/**/ingress*.yaml")) +
            list(repo_path.glob("infrastructure/**/ingress*.yml")) +
            list(repo_path.glob("infrastructure/**/*.yaml"))
        )
        for fp in candidates[:10]:
            try:
                text = fp.read_text(errors="ignore")
                for line in text.splitlines():
                    if "host:" in line or "hostname:" in line:
                        parts = line.strip().split(":", 1)
                        if len(parts) == 2:
                            val = parts[1].strip().strip('"').strip("'")
                            if "." in val and not val.startswith("$"):
                                self.log(f"Detected domain from {fp.name}: {val}")
                                return val
            except Exception:
                pass
        return "example.com"
