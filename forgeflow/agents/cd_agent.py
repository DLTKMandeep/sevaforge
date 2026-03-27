#!/usr/bin/env python3
"""
CD Agent - Continuous Deployment Configuration Generation
Generates ArgoCD, Kustomize, Kubernetes manifests, FluxCD, Helm charts

Part of the specialized agent architecture:
- forgeflow cd <path> → cd_mcp → CDAgent
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_agent import BaseAgent


# =============================================================================
# ARGOCD TEMPLATES
# =============================================================================

ARGOCD_APPLICATION = '''apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}-{environment}
  namespace: argocd
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/instance: {app_name}-{environment}
    environment: {environment}
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: {app_name}
  source:
    repoURL: {repo_url}
    targetRevision: HEAD
    path: infrastructure/k8s/overlays/{environment}
  destination:
    server: https://kubernetes.default.svc
    namespace: {app_name}-{environment}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - PruneLast=true
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
  revisionHistoryLimit: 10
'''

ARGOCD_PROJECT = '''apiVersion: argoproj.io/v1alpha1
kind: AppProject
metadata:
  name: {app_name}
  namespace: argocd
  labels:
    app.kubernetes.io/name: {app_name}
spec:
  description: "{app_name} project managed by ForgeFlow"
  sourceRepos:
    - '{repo_url}'
    - 'https://charts.helm.sh/stable'
  destinations:
    - namespace: {app_name}-*
      server: https://kubernetes.default.svc
    - namespace: argocd
      server: https://kubernetes.default.svc
  clusterResourceWhitelist:
    - group: ''
      kind: Namespace
    - group: 'rbac.authorization.k8s.io'
      kind: ClusterRole
    - group: 'rbac.authorization.k8s.io'
      kind: ClusterRoleBinding
  namespaceResourceBlacklist:
    - group: ''
      kind: ResourceQuota
    - group: ''
      kind: LimitRange
  roles:
    - name: developer
      description: Developer access to {app_name}
      policies:
        - p, proj:{app_name}:developer, applications, get, {app_name}/*, allow
        - p, proj:{app_name}:developer, applications, sync, {app_name}/*, allow
      groups:
        - {app_name}-developers
'''

ARGOCD_APPLICATIONSET = '''apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: {app_name}
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - environment: dev
            replicas: "1"
            cpu_request: "100m"
            memory_request: "128Mi"
          - environment: staging
            replicas: "2"
            cpu_request: "200m"
            memory_request: "256Mi"
          - environment: prod
            replicas: "3"
            cpu_request: "500m"
            memory_request: "512Mi"
  template:
    metadata:
      name: '{{{{app_name}}-{{{{environment}}'
    spec:
      project: {app_name}
      source:
        repoURL: {repo_url}
        targetRevision: HEAD
        path: 'infrastructure/k8s/overlays/{{{{environment}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{{{app_name}}-{{{{environment}}'
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
'''


# =============================================================================
# KUSTOMIZE TEMPLATES
# =============================================================================

KUSTOMIZE_BASE = '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - deployment.yaml
  - service.yaml
  - configmap.yaml
  - hpa.yaml
  - ingress.yaml
  - serviceaccount.yaml

commonLabels:
  app.kubernetes.io/name: {app_name}
  app.kubernetes.io/managed-by: kustomize
  generator: forgeflow

commonAnnotations:
  forgeflow.io/generated: "true"
'''

KUSTOMIZE_OVERLAY_DEV = '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {app_name}-dev

resources:
  - ../../base

commonLabels:
  environment: dev

replicas:
  - name: {app_name}
    count: 1

patches:
  - path: deployment-patch.yaml

configMapGenerator:
  - name: {app_name}-config
    behavior: merge
    literals:
      - ENVIRONMENT=development
      - LOG_LEVEL=debug
      - DEBUG=true
'''

KUSTOMIZE_OVERLAY_STAGING = '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {app_name}-staging

resources:
  - ../../base

commonLabels:
  environment: staging

replicas:
  - name: {app_name}
    count: 2

patches:
  - path: deployment-patch.yaml

configMapGenerator:
  - name: {app_name}-config
    behavior: merge
    literals:
      - ENVIRONMENT=staging
      - LOG_LEVEL=info
      - DEBUG=false
'''

KUSTOMIZE_OVERLAY_PROD = '''apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: {app_name}-prod

resources:
  - ../../base

commonLabels:
  environment: production

replicas:
  - name: {app_name}
    count: 3

patches:
  - path: deployment-patch.yaml

configMapGenerator:
  - name: {app_name}-config
    behavior: merge
    literals:
      - ENVIRONMENT=production
      - LOG_LEVEL=warn
      - DEBUG=false
'''


# =============================================================================
# KUBERNETES MANIFESTS
# =============================================================================

K8S_DEPLOYMENT = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
    app.kubernetes.io/component: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app.kubernetes.io/name: {app_name}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app_name}
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "{port}"
        prometheus.io/path: "/metrics"
    spec:
      serviceAccountName: {app_name}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      containers:
        - name: {app_name}
          image: {image}:{tag}
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: {port}
              protocol: TCP
          envFrom:
            - configMapRef:
                name: {app_name}-config
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {{}}
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app.kubernetes.io/name: {app_name}
                topologyKey: kubernetes.io/hostname
'''

K8S_SERVICE = '''apiVersion: v1
kind: Service
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
spec:
  type: ClusterIP
  ports:
    - name: http
      port: 80
      targetPort: {port}
      protocol: TCP
  selector:
    app.kubernetes.io/name: {app_name}
'''

K8S_CONFIGMAP = '''apiVersion: v1
kind: ConfigMap
metadata:
  name: {app_name}-config
  labels:
    app.kubernetes.io/name: {app_name}
data:
  ENVIRONMENT: "dev"
  LOG_LEVEL: "info"
  APP_NAME: "{app_name}"
'''

K8S_HPA = '''apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {app_name}
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Percent
          value: 100
          periodSeconds: 15
        - type: Pods
          value: 4
          periodSeconds: 15
      selectPolicy: Max
'''

K8S_INGRESS = '''apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - {app_name}.example.com
      secretName: {app_name}-tls
  rules:
    - host: {app_name}.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {app_name}
                port:
                  number: 80
'''

K8S_SERVICEACCOUNT = '''apiVersion: v1
kind: ServiceAccount
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
  annotations:
    # For AWS EKS IRSA (IAM Roles for Service Accounts)
    # eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT_ID:role/{app_name}-role
'''

DEPLOYMENT_PATCH_DEV = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
spec:
  template:
    spec:
      containers:
        - name: {app_name}
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "256Mi"
'''

DEPLOYMENT_PATCH_STAGING = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
spec:
  template:
    spec:
      containers:
        - name: {app_name}
          resources:
            requests:
              cpu: "100m"
              memory: "128Mi"
            limits:
              cpu: "500m"
              memory: "512Mi"
'''

DEPLOYMENT_PATCH_PROD = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
spec:
  template:
    spec:
      containers:
        - name: {app_name}
          resources:
            requests:
              cpu: "200m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "1Gi"
'''


# =============================================================================
# FLUXCD TEMPLATES (Optional)
# =============================================================================

FLUX_GITREPOSITORY = '''apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: {app_name}
  namespace: flux-system
spec:
  interval: 1m
  url: {repo_url}
  ref:
    branch: main
  secretRef:
    name: {app_name}-git-credentials
'''

FLUX_KUSTOMIZATION = '''apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: {app_name}-{environment}
  namespace: flux-system
spec:
  interval: 10m
  targetNamespace: {app_name}-{environment}
  sourceRef:
    kind: GitRepository
    name: {app_name}
  path: ./infrastructure/k8s/overlays/{environment}
  prune: true
  healthChecks:
    - apiVersion: apps/v1
      kind: Deployment
      name: {app_name}
      namespace: {app_name}-{environment}
'''


# =============================================================================
# HELM CHART TEMPLATES (Optional)
# =============================================================================

HELM_CHART_YAML = '''apiVersion: v2
name: {app_name}
description: A Helm chart for {app_name}
type: application
version: 0.1.0
appVersion: "1.0.0"
maintainers:
  - name: ForgeFlow
    email: forgeflow@example.com
'''

HELM_VALUES_YAML = '''# Default values for {app_name}
replicaCount: 2

image:
  repository: ghcr.io/org/{app_name}
  pullPolicy: IfNotPresent
  tag: "latest"

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: {app_name}.example.com
      paths:
        - path: /
          pathType: Prefix

resources:
  limits:
    cpu: 500m
    memory: 512Mi
  requests:
    cpu: 100m
    memory: 128Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

nodeSelector: {{}}
tolerations: []
affinity: {{}}
'''


# =============================================================================
# DEPLOY WORKFLOW — pilot to prod with gates
# =============================================================================

DEPLOY_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated Deploy Pipeline
# Full pilot-to-prod: build → staging → E2E gate → DAST → approval → prod → rollback
# =============================================================================
name: Deploy Pipeline

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        default: staging
        type: choice
        options: [staging, production]

# Top-level permissions required for GHCR push on new repos
permissions:
  contents: write
  packages: write
  issues: write

# Never cancel in-flight deploys — a deploy must always finish or roll back
concurrency:
  group: deploy-${{{{ github.ref }}}}
  cancel-in-progress: false

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{{{ github.repository }}}}

jobs:
  # ===========================================================================
  # 1 ── Build & push container image
  # ===========================================================================
  build:
    name: 🏗️ Build & Push Image
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{{{ github.sha }}}}
      image:     ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ github.sha }}}}
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
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
            type=sha,prefix=
            type=raw,value=latest,enable=${{{{ github.ref == 'refs/heads/main' }}}}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{{{ steps.meta.outputs.tags }}}}
          labels: ${{{{ steps.meta.outputs.labels }}}}
          cache-from: type=gha
          cache-to:   type=gha,mode=max
          provenance: true
          sbom: true

  # ===========================================================================
  # 2 ── Deploy to staging (GitOps — update kustomize overlay)
  # ===========================================================================
  deploy-staging:
    name: 🚀 Deploy → Staging
    runs-on: ubuntu-latest
    needs: build
    environment: staging
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{{{ secrets.GITHUB_TOKEN }}}}
          fetch-depth: 0

      - name: Update staging image tag
        run: |
          cd infrastructure/k8s/overlays/staging
          kustomize edit set image app=${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ needs.build.outputs.image_tag }}}}
          git config user.name  "ForgeFlow Bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "chore(deploy/staging): ${{{{ needs.build.outputs.image_tag }}}} [skip ci]"
          git push

      - name: Wait for ArgoCD sync
        run: |
          echo "⏳ Waiting 60s for ArgoCD to pick up staging update..."
          sleep 60
          echo "✅ Staging deployment triggered"
          # If ArgoCD CLI is available:
          # argocd app wait {app_name}-staging --health --sync --timeout 300

  # ===========================================================================
  # 3 ── E2E tests against staging  (gate — must pass to reach prod)
  # ===========================================================================
  e2e-staging:
    name: 🧪 E2E Gate → Staging
    runs-on: ubuntu-latest
    needs: deploy-staging
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: npm

      - name: Install Playwright
        run: |
          npm ci
          npx playwright install --with-deps chromium

      - name: Run E2E tests
        env:
          BASE_URL: ${{{{ vars.STAGING_URL }}}}
        run: npx playwright test --reporter=html

      - name: Upload E2E report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-report-${{{{ github.sha }}}}
          path: playwright-report/
          retention-days: 14

  # ===========================================================================
  # 4 ── DAST scan against staging  (gate — blocks on CRITICAL findings)
  # ===========================================================================
  dast-staging:
    name: 🔒 DAST Gate → Staging
    runs-on: ubuntu-latest
    needs: deploy-staging
    permissions:
      issues: write
    steps:
      - name: OWASP ZAP Baseline Scan
        uses: zaproxy/action-baseline@v0.11.0
        with:
          target:       ${{{{ vars.STAGING_URL }}}}
          fail_action:  true        # CRITICAL findings block the pipeline
          issue_title:  "DAST Scan – ${{{{ github.sha }}}}"

  # ===========================================================================
  # 5 ── Production deployment  (requires manual approval via GitHub Environment)
  # ===========================================================================
  deploy-prod:
    name: 🚀 Deploy → Production
    runs-on: ubuntu-latest
    needs: [e2e-staging, dast-staging]
    environment: production          # ← required reviewers + wait timer enforced here
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{{{ secrets.GITHUB_TOKEN }}}}
          fetch-depth: 0
          ref: main                  # Always deploy from latest main

      - name: Update production image tag
        run: |
          cd infrastructure/k8s/overlays/prod
          kustomize edit set image app=${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE_NAME }}}}:${{{{ needs.build.outputs.image_tag }}}}
          git config user.name  "ForgeFlow Bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "chore(deploy/prod): ${{{{ needs.build.outputs.image_tag }}}} [skip ci]"
          git push

      - name: Wait for ArgoCD sync
        run: |
          echo "⏳ Waiting 90s for ArgoCD to pick up prod update..."
          sleep 90
          echo "✅ Production deployment triggered"

  # ===========================================================================
  # 6 ── Health check  (polls /health for up to 5 minutes)
  # ===========================================================================
  health-check:
    name: ❤️ Health Check → Production
    runs-on: ubuntu-latest
    needs: deploy-prod
    outputs:
      healthy: ${{{{ steps.check.outputs.healthy }}}}
    steps:
      - name: Poll health endpoint
        id: check
        run: |
          echo "healthy=false" >> $GITHUB_OUTPUT
          for i in $(seq 1 10); do
            status=$(curl -s -o /dev/null -w "%{{http_code}}}}" "${{{{ vars.PROD_URL }}}}/health" || echo "000")
            echo "Attempt $i/10: HTTP $status"
            if [ "$status" = "200" ]; then
              echo "healthy=true" >> $GITHUB_OUTPUT
              echo "✅ Production is healthy"
              exit 0
            fi
            sleep 30
          done
          echo "❌ Health check failed after 10 attempts"
          exit 1

  # ===========================================================================
  # 7 ── Automatic rollback if health check fails
  # ===========================================================================
  rollback:
    name: ⏪ Auto-Rollback Production
    runs-on: ubuntu-latest
    needs: health-check
    if: failure()
    permissions:
      contents: write
      issues:   write
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{{{ secrets.GITHUB_TOKEN }}}}
          fetch-depth: 5

      - name: Revert production image tag
        run: |
          git config user.name  "ForgeFlow Bot"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git revert HEAD --no-edit
          git push
          echo "⏪ Production rolled back"

      - name: Open incident issue
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({{
              owner: context.repo.owner,
              repo:  context.repo.repo,
              title: `🚨 Production rollback — ${{{{ github.sha }}}}`,
              body: [
                `Production deployment of \`${{{{ github.sha }}}}\` failed health checks.`,
                `Auto-rollback completed.`,
                ``,
                `**Workflow run:** ${{{{ github.server_url }}}}/${{{{ github.repository }}}}/actions/runs/${{{{ github.run_id }}}}`,
              ].join("\\n"),
              labels: ["incident", "production", "auto-rollback"],
            }}}})
'''


# =============================================================================
# GITHUB ENVIRONMENTS SETUP SCRIPT
# =============================================================================

GITHUB_SETUP_SCRIPT = '''#!/usr/bin/env bash
# =============================================================================
# ForgeFlow — GitHub Environments & Branch Protection Setup
# Run once after pushing to GitHub:  bash scripts/setup-github.sh
#
# Prerequisites: gh CLI authenticated (gh auth login)
# =============================================================================
set -euo pipefail

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
APP=$(basename "$REPO")
echo "Configuring GitHub for: $REPO"

# ---------------------------------------------------------------------------
# 1. Create GitHub Environments  (JSON body via --input to avoid escaping issues)
# ---------------------------------------------------------------------------
echo "Creating environments..."

gh api --method PUT "repos/$REPO/environments/staging" \\
  --input - <<'ENDJSON'
{{"wait_timer": 0, "deployment_branch_policy": null}}
ENDJSON
echo "  ✅ staging environment created"

gh api --method PUT "repos/$REPO/environments/production" \\
  --input - <<'ENDJSON'
{{"wait_timer": 5, "deployment_branch_policy": null}}
ENDJSON
echo "  ✅ production environment created (5-min wait timer)"
echo "  ℹ️  Add required reviewers: GitHub → Settings → Environments → production"

# ---------------------------------------------------------------------------
# 2. Add environment variables
# ---------------------------------------------------------------------------
echo ""
echo "Setting environment variables..."

gh variable set STAGING_URL --env staging --body "https://staging.$APP.yourdomain.com" 2>/dev/null || true
echo "  ✅ STAGING_URL set for staging"

gh variable set PROD_URL --env production --body "https://$APP.yourdomain.com" 2>/dev/null || true
echo "  ✅ PROD_URL set for production"
echo "  ℹ️  Update with real URLs: GitHub → Settings → Environments → [env] → Variables"

# ---------------------------------------------------------------------------
# 3. Bootstrap GitHub Actions secrets (placeholder values — fill in real ones)
# ---------------------------------------------------------------------------
echo ""
echo "Bootstrapping GitHub Actions secrets..."
echo "  (Created with placeholders — fill in real values in GitHub → Settings → Secrets)"
echo ""

bootstrap_secret() {{
  local name="$1"
  local placeholder="$2"
  local description="$3"
  if gh secret list 2>/dev/null | grep -q "^$name"; then
    echo "  ⏭️  $name already set — skipping"
  else
    echo -n "$placeholder" | gh secret set "$name"
    echo "  ✅ $name  ←  $description"
  fi
}}

# AWS / Cloud
bootstrap_secret "AWS_ACCESS_KEY_ID"     "REPLACE_WITH_REAL_VALUE" "IAM access key"
bootstrap_secret "AWS_SECRET_ACCESS_KEY" "REPLACE_WITH_REAL_VALUE" "IAM secret key"
bootstrap_secret "AWS_ACCOUNT_ID"        "REPLACE_WITH_REAL_VALUE" "12-digit AWS account ID"
bootstrap_secret "AWS_REGION"            "us-east-1"               "AWS region for EKS"
bootstrap_secret "EKS_CLUSTER_NAME"      "REPLACE_WITH_REAL_VALUE" "EKS cluster name (terraform output)"

# ArgoCD
bootstrap_secret "ARGOCD_SERVER"         "REPLACE_WITH_REAL_VALUE" "ArgoCD server host (kubectl get svc -n argocd argocd-server)"
bootstrap_secret "ARGOCD_AUTH_TOKEN"     "REPLACE_WITH_REAL_VALUE" "ArgoCD API token (argocd account generate-token)"

# Code quality & scanning
bootstrap_secret "SONAR_TOKEN"           "REPLACE_WITH_REAL_VALUE" "SonarCloud token (sonarcloud.io → Account → Security)"
bootstrap_secret "SNYK_TOKEN"            "REPLACE_WITH_REAL_VALUE" "[optional] Snyk API token"
bootstrap_secret "SLACK_WEBHOOK_URL"     "REPLACE_WITH_REAL_VALUE" "[optional] Slack Incoming Webhook URL"

echo ""
echo "  ⚠️  Open GitHub → Settings → Secrets → Actions"
echo "     Replace every REPLACE_WITH_REAL_VALUE entry."
echo "     See RUNBOOK.md for step-by-step instructions."
echo ""

# ---------------------------------------------------------------------------
# 4. Branch protection on main  (use --input with heredoc for clean JSON)
# ---------------------------------------------------------------------------
echo ""
echo "Configuring branch protection on main..."

gh api --method PUT "repos/$REPO/branches/main/protection" \\
  --input - <<'ENDJSON'
{{
  "required_status_checks": {{
    "strict": true,
    "contexts": ["lint", "test-unit", "test-integration", "build"]
  }},
  "enforce_admins": false,
  "required_pull_request_reviews": {{
    "required_approving_review_count": 1,
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false
  }},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}}
ENDJSON
echo "  ✅ Branch protection on main:"
echo "     - 1 PR approval required"
echo "     - Stale reviews dismissed on new commits"
echo "     - CI (lint, test, build) must pass before merge"

# ---------------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo " GitHub setup complete for $REPO"
echo "================================================================"
echo ""
echo " ✅ Done automatically:"
echo "   - staging + production environments created"
echo "   - STAGING_URL and PROD_URL variables set (update with real URLs)"
echo "   - All required secrets bootstrapped with placeholder values"
echo "   - Branch protection on main configured"
echo ""
echo " ⚠️  Fill in real secret values:"
echo "   → https://github.com/$REPO/settings/secrets/actions"
echo "   See RUNBOOK.md for where to get each value."
echo ""
echo " ⚠️  Add production reviewer:"
echo "   → https://github.com/$REPO/settings/environments"
echo "      production → Required reviewers → add yourself or your team"
echo ""
echo " Next step — Bootstrap ArgoCD on EKS:"
echo "   export EKS_CLUSTER_NAME=<your-cluster>   # terraform output eks_cluster_name"
echo "   export AWS_REGION=us-east-1"
echo "   export GITHUB_PAT=<repo-scoped-PAT>"
echo "   bash scripts/setup-argocd.sh"
echo ""
echo " Pipeline flow on every merge to main:"
echo "  build → staging → E2E gate + DAST gate → approval → prod"
echo "  → health check → auto-rollback if failed"
echo ""
'''


# =============================================================================
# GITHUB SECRETS BOOTSTRAP SCRIPT
# Appended to setup-github.sh — creates all secrets with placeholder values
# so the consumer only has to fill in real values, never create from scratch.
# =============================================================================

GITHUB_SECRETS_SECTION = '''
# ---------------------------------------------------------------------------
# {section_num}. Bootstrap GitHub Actions secrets (placeholder values)
#    Secrets are created empty — fill real values in GitHub → Settings → Secrets
# ---------------------------------------------------------------------------
echo ""
echo "Bootstrapping GitHub Actions secrets..."
echo "  (All created with placeholder values — fill in real values afterwards)"
echo ""

bootstrap_secret() {{
  local name="$1"
  local placeholder="$2"
  local description="$3"
  # Only create if it doesn't already exist; never overwrite a real value
  if gh secret list | grep -q "^$name"; then
    echo "  ⏭️  $name already exists — skipping"
  else
    echo -n "$placeholder" | gh secret set "$name"
    echo "  ✅ $name  →  $description"
  fi
}}

# ── AWS / Cloud credentials ────────────────────────────────────────────────
bootstrap_secret "AWS_ACCESS_KEY_ID"     "REPLACE_WITH_REAL_VALUE" "IAM access key (IAM → Users → Security credentials)"
bootstrap_secret "AWS_SECRET_ACCESS_KEY" "REPLACE_WITH_REAL_VALUE" "IAM secret key (IAM → Users → Security credentials)"
bootstrap_secret "AWS_ACCOUNT_ID"        "REPLACE_WITH_REAL_VALUE" "12-digit AWS account ID (aws sts get-caller-identity)"
bootstrap_secret "AWS_REGION"            "us-east-1"               "AWS region where EKS cluster lives"
bootstrap_secret "EKS_CLUSTER_NAME"      "REPLACE_WITH_REAL_VALUE" "EKS cluster name (terraform output eks_cluster_name)"

# ── ArgoCD ─────────────────────────────────────────────────────────────────
bootstrap_secret "ARGOCD_SERVER"         "REPLACE_WITH_REAL_VALUE" "ArgoCD server host (kubectl get svc -n argocd argocd-server)"
bootstrap_secret "ARGOCD_AUTH_TOKEN"     "REPLACE_WITH_REAL_VALUE" "ArgoCD API token (argocd account generate-token --account admin)"

# ── Code quality & security scanning ──────────────────────────────────────
bootstrap_secret "SONAR_TOKEN"           "REPLACE_WITH_REAL_VALUE" "SonarCloud token (sonarcloud.io → My Account → Security)"
bootstrap_secret "SNYK_TOKEN"            "REPLACE_WITH_REAL_VALUE" "Snyk API token (app.snyk.io → Account Settings) [optional]"

# ── Notifications ──────────────────────────────────────────────────────────
bootstrap_secret "SLACK_WEBHOOK_URL"     "REPLACE_WITH_REAL_VALUE" "Slack Incoming Webhook URL [optional]"

echo ""
echo "  ⚠️  Open GitHub → Settings → Secrets and fill in all REPLACE_WITH_REAL_VALUE entries."
echo "  See RUNBOOK.md in the repo root for step-by-step instructions for each secret."
echo ""
'''


# =============================================================================
# ARGOCD BOOTSTRAP SCRIPT
# Installs ArgoCD to EKS, creates repo creds, registers ForgeFlow-generated apps.
# Run ONCE after Terraform provisions the cluster.
# =============================================================================

ARGOCD_SETUP_SCRIPT = '''#!/usr/bin/env bash
# =============================================================================
# ForgeFlow — ArgoCD Bootstrap Script
# Sets up ArgoCD on EKS and wires it to this repository.
#
# Run once after:
#   1. Terraform has created the EKS cluster
#   2. You have configured kubectl (aws eks update-kubeconfig ...)
#   3. scripts/setup-github.sh has been run (GitHub secrets exist)
#
# Prerequisites:
#   kubectl, helm, argocd CLI, aws CLI (all authenticated)
# =============================================================================
set -euo pipefail

REPO=$(git remote get-url origin | sed 's/\\.git$//')
APP={app_name}
ARGOCD_NAMESPACE=argocd
ARGOCD_VERSION="v2.10.0"   # Pin to a known-good version

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   ForgeFlow — ArgoCD Bootstrap for $APP"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ---------------------------------------------------------------------------
# 1. Update kubeconfig for EKS
# ---------------------------------------------------------------------------
echo "1/7  Configuring kubectl for EKS..."
aws eks update-kubeconfig \\
  --region  "${{AWS_REGION:-us-east-1}}" \\
  --name    "${{EKS_CLUSTER_NAME:?Set EKS_CLUSTER_NAME env var}}"
echo "     ✅ kubectl configured"

# ---------------------------------------------------------------------------
# 2. Install ArgoCD via Helm
# ---------------------------------------------------------------------------
echo "2/7  Installing ArgoCD $ARGOCD_VERSION..."
helm repo add argo https://argoproj.github.io/argo-helm --force-update
helm upgrade --install argocd argo/argo-cd \\
  --namespace "$ARGOCD_NAMESPACE" \\
  --create-namespace \\
  --version "$(helm search repo argo/argo-cd --output json | python3 -c "import sys,json; print([c[\'version\'] for c in json.load(sys.stdin) if c[\'name\']==\'argo/argo-cd\'][0])")" \\
  --set server.service.type=LoadBalancer \\
  --set configs.params."server\\.insecure"=true \\
  --wait --timeout 5m
echo "     ✅ ArgoCD installed"

# ---------------------------------------------------------------------------
# 3. Retrieve ArgoCD admin password and server address
# ---------------------------------------------------------------------------
echo "3/7  Retrieving ArgoCD credentials..."
ARGOCD_PASSWORD=$(kubectl -n "$ARGOCD_NAMESPACE" get secret argocd-initial-admin-secret \\
  -o jsonpath="{{.data.password}}" | base64 --decode)
ARGOCD_HOST=$(kubectl -n "$ARGOCD_NAMESPACE" get svc argocd-server \\
  -o jsonpath="{{.status.loadBalancer.ingress[0].hostname}}")

echo "     ArgoCD server: $ARGOCD_HOST"
echo ""
echo "     ⚠️  Save these credentials and update GitHub secrets:"
echo "        ARGOCD_SERVER     = $ARGOCD_HOST"
echo "        ARGOCD_AUTH_TOKEN = (generate below after login)"
echo ""

# ---------------------------------------------------------------------------
# 4. Log in with ArgoCD CLI and generate an API token
# ---------------------------------------------------------------------------
echo "4/7  Logging into ArgoCD CLI..."
argocd login "$ARGOCD_HOST" \\
  --username admin \\
  --password "$ARGOCD_PASSWORD" \\
  --insecure

ARGOCD_TOKEN=$(argocd account generate-token --account admin)
echo "     ArgoCD API token generated."
echo ""
echo "     ⚠️  Update ARGOCD_AUTH_TOKEN GitHub secret:"
echo "        gh secret set ARGOCD_AUTH_TOKEN --body \\"$ARGOCD_TOKEN\\""
echo ""

# ---------------------------------------------------------------------------
# 5. Register this repository with ArgoCD
# ---------------------------------------------------------------------------
echo "5/7  Adding repository to ArgoCD..."
argocd repo add "$REPO" \\
  --username git \\
  --password "${{GITHUB_PAT:?Set GITHUB_PAT env var to a repo-scoped PAT}}" \\
  --insecure-skip-server-verification || true
echo "     ✅ Repository registered"

# ---------------------------------------------------------------------------
# 6. Install External Secrets Operator (reads from AWS Secrets Manager)
# ---------------------------------------------------------------------------
echo "6/7  Installing External Secrets Operator..."
helm repo add external-secrets https://charts.external-secrets.io --force-update
helm upgrade --install external-secrets external-secrets/external-secrets \\
  --namespace external-secrets \\
  --create-namespace \\
  --set installCRDs=true \\
  --wait --timeout 3m

# Apply the SecretStore pointing to AWS Secrets Manager
kubectl apply -f infrastructure/k8s/secrets/secret-store.yaml
echo "     ✅ External Secrets Operator installed"

# ---------------------------------------------------------------------------
# 7. Apply ArgoCD application manifests
# ---------------------------------------------------------------------------
echo "7/7  Registering apps with ArgoCD..."
kubectl apply -n "$ARGOCD_NAMESPACE" -f infrastructure/k8s/argocd/project.yaml
kubectl apply -n "$ARGOCD_NAMESPACE" -f infrastructure/k8s/argocd/applicationset.yaml
echo "     ✅ ArgoCD apps registered — ArgoCD will sync automatically"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Bootstrap complete! Open ArgoCD UI:"
echo "║   https://$ARGOCD_HOST"
echo "║   Username: admin"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Update ARGOCD_AUTH_TOKEN in GitHub secrets (command printed above)"
echo "  2. Update STAGING_URL and PROD_URL in GitHub environment variables"
echo "  3. Merge a PR to main to trigger the first deploy pipeline"
echo ""
'''


# =============================================================================
# GITHUB ACTIONS WORKFLOW TEMPLATES — INFRASTRUCTURE & BOOTSTRAP
# These are generated by CDAgent into every consumer project's .github/workflows/
# so that Terraform provisioning and ArgoCD bootstrap happen 100% in the cloud —
# zero developer desktop tooling required beyond the 4 secrets set by setup-github.sh.
# =============================================================================

INFRA_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated — Infrastructure Workflow
# Provisions AWS EKS, VPC, IAM via Terraform.
# Triggers automatically when terraform files change — no desktop tooling needed.
#
# After apply, captures Terraform outputs and stores them as GitHub
# Actions variables so downstream workflows (bootstrap, deploy) can use them.
# Then triggers bootstrap.yml to install ArgoCD on the new cluster.
#
# Required secrets (set ONCE via scripts/setup-github.sh, never again):
#   AWS_ACCESS_KEY_ID     IAM access key
#   AWS_SECRET_ACCESS_KEY IAM secret key
#   AWS_REGION            Target region (e.g. us-east-1)
#   GH_PAT                GitHub PAT with repo+secrets scope (for writing back secrets)
# =============================================================================
name: Infrastructure

on:
  push:
    branches: [main]
    paths:
      - 'infrastructure/terraform/**'
  pull_request:
    branches: [main]
    paths:
      - 'infrastructure/terraform/**'
  workflow_dispatch:
    inputs:
      destroy:
        description: 'Destroy infrastructure (type "destroy" to confirm)'
        required: false
        default: ''

concurrency:
  group: terraform-${{ github.ref }}
  cancel-in-progress: false   # Never cancel infra changes mid-flight

env:
  TF_DIR: infrastructure/terraform
  # S3 bucket for Terraform state — derived from repo name (no manual setup needed)
  TF_STATE_BUCKET: ${{ github.repository_owner }}-${{ github.event.repository.name }}-tfstate
  TF_STATE_KEY: infrastructure/terraform.tfstate

jobs:
  terraform:
    name: "\U0001f3d7\ufe0f Terraform ${{ github.event_name == 'pull_request' && 'Plan' || 'Apply' }}"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # Post plan output as PR comment
      id-token: write        # For OIDC (future)
    outputs:
      eks_cluster_name: ${{ steps.outputs.outputs.eks_cluster_name }}
      infra_changed: ${{ steps.apply.outputs.infra_changed }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id:     ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region:            ${{ secrets.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.7.0"
          terraform_wrapper: false   # Cleaner output for capture

      # ── Ensure S3 state bucket exists (idempotent — safe to run every time) ──
      - name: Bootstrap Terraform state bucket
        run: |
          REGION="${{ secrets.AWS_REGION }}"
          BUCKET="${TF_STATE_BUCKET}"
          echo "State bucket: $BUCKET"

          # Create bucket if it doesn\'t exist
          if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
            echo "Creating state bucket..."
            if [ "$REGION" = "us-east-1" ]; then
              aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
            else
              aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \\
                --create-bucket-configuration LocationConstraint="$REGION"
            fi
          fi

          # Enable versioning and encryption (idempotent)
          aws s3api put-bucket-versioning --bucket "$BUCKET" \\
            --versioning-configuration Status=Enabled
          aws s3api put-bucket-encryption --bucket "$BUCKET" \\
            --server-side-encryption-configuration \\
            \'{{"Rules":[{{"ApplyServerSideEncryptionByDefault":{{"SSEAlgorithm":"AES256"}}}}]}}}}\'
          aws s3api put-public-access-block --bucket "$BUCKET" \\
            --public-access-block-configuration \\
            \'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true\'

          echo "✅ State bucket ready: $BUCKET"

      - name: Terraform Init
        run: |
          cd $TF_DIR
          terraform init \\
            -backend-config="bucket=${TF_STATE_BUCKET}" \\
            -backend-config="key=${TF_STATE_KEY}" \\
            -backend-config="region=${{ secrets.AWS_REGION }}" \\
            -backend-config="encrypt=true"

      - name: Terraform Validate
        run: cd $TF_DIR && terraform validate

      - name: Terraform Plan
        id: plan
        run: |
          cd $TF_DIR
          terraform plan -out=tfplan -no-color 2>&1 | tee plan.txt
          echo "exit_code=${PIPESTATUS[0]}" >> $GITHUB_OUTPUT

      # Post plan as PR comment so reviewers can see exactly what will change
      - name: Post plan to PR
        if: github.event_name == \'pull_request\'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require(\'fs\');
            const plan = fs.readFileSync(\'${{ env.TF_DIR }}/plan.txt\', \'utf8\');
            const truncated = plan.length > 60000 ? plan.substring(0, 60000) + \'\\n... (truncated)\' : plan;
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo:  context.repo.repo,
              issue_number: context.issue.number,
              body: `## \U0001f3d7\ufe0f Terraform Plan\\n\\`\\`\\`\\n${truncated}\\n\\`\\`\\``
            }}}});

      # ── Apply only on push to main (not PRs) ──
      - name: Terraform Apply
        id: apply
        if: github.ref == \'refs/heads/main\' && github.event_name != \'pull_request\'
        run: |
          cd $TF_DIR
          terraform apply tfplan
          echo "infra_changed=true" >> $GITHUB_OUTPUT

      # ── Terraform Destroy (only if explicitly requested via workflow_dispatch) ──
      - name: Terraform Destroy
        if: github.event.inputs.destroy == \'destroy\'
        run: |
          cd $TF_DIR
          terraform destroy -auto-approve
          echo "⚠️ Infrastructure destroyed"

      # ── Capture outputs and store as GitHub variables ──
      - name: Capture Terraform outputs
        id: outputs
        if: github.ref == \'refs/heads/main\' && github.event_name != \'pull_request\' && github.event.inputs.destroy != \'destroy\'
        env:
          GH_TOKEN: ${{ secrets.GH_PAT }}
        run: |
          cd $TF_DIR
          EKS_CLUSTER_NAME=$(terraform output -raw eks_cluster_name)
          VPC_ID=$(terraform output -raw vpc_id)

          echo "eks_cluster_name=$EKS_CLUSTER_NAME" >> $GITHUB_OUTPUT

          # Store as GitHub Actions variables (readable by all workflows, not sensitive)
          gh variable set EKS_CLUSTER_NAME --body "$EKS_CLUSTER_NAME"
          gh variable set VPC_ID           --body "$VPC_ID"
          gh variable set AWS_REGION       --body "${{ secrets.AWS_REGION }}"

          echo "✅ GitHub variables updated:"
          echo "   EKS_CLUSTER_NAME = $EKS_CLUSTER_NAME"
          echo "   VPC_ID           = $VPC_ID"

  # ── After infra is provisioned, bootstrap ArgoCD automatically ──
  trigger-bootstrap:
    name: "\U0001f680 Trigger ArgoCD Bootstrap"
    runs-on: ubuntu-latest
    needs: terraform
    if: |
      needs.terraform.outputs.infra_changed == \'true\' &&
      github.ref == \'refs/heads/main\' &&
      github.event.inputs.destroy != \'destroy\'
    steps:
      - name: Dispatch bootstrap workflow
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.GH_PAT }}
          script: |
            await github.rest.actions.createWorkflowDispatch({{
              owner: context.repo.owner,
              repo:  context.repo.repo,
              workflow_id: \'bootstrap.yml\',
              ref: \'main\',
              inputs: {{
                eks_cluster_name: \'${{ needs.terraform.outputs.eks_cluster_name }}\'
              }}}}
            }}}});
            console.log(\'✅ Bootstrap workflow triggered\');
'''

BOOTSTRAP_WORKFLOW_TEMPLATE = '''# =============================================================================
# ForgeFlow Generated — ArgoCD Bootstrap Workflow
# Installs ArgoCD on the EKS cluster, wires it to this repo, installs the
# External Secrets Operator, and writes ARGOCD_SERVER + ARGOCD_AUTH_TOKEN
# back as GitHub secrets automatically — no developer intervention needed.
#
# Triggered automatically by infra.yml after Terraform provisions the cluster.
# Can also be run manually: Actions → Bootstrap ArgoCD → Run workflow.
#
# Required secrets (already set by setup-github.sh):
#   AWS_ACCESS_KEY_ID     IAM access key
#   AWS_SECRET_ACCESS_KEY IAM secret key
#   AWS_REGION            Target region
#   GH_PAT                GitHub PAT with repo+secrets scope
# =============================================================================
name: Bootstrap ArgoCD

on:
  workflow_dispatch:
    inputs:
      eks_cluster_name:
        description: EKS cluster name (leave blank to read from GitHub variable)
        required: false
        default: \'\'
  workflow_call:
    inputs:
      eks_cluster_name:
        type: string
        required: true

concurrency:
  group: bootstrap
  cancel-in-progress: false

jobs:
  bootstrap:
    name: "\U0001f39b\ufe0f Bootstrap ArgoCD on EKS"
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id:     ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region:            ${{ secrets.AWS_REGION }}

      # Resolve cluster name — use input, fall back to GitHub variable
      - name: Resolve EKS cluster name
        id: cluster
        run: |
          NAME="${{ inputs.eks_cluster_name }}"
          if [ -z "$NAME" ]; then
            NAME="${{ vars.EKS_CLUSTER_NAME }}"
          fi
          if [ -z "$NAME" ]; then
            echo "❌ EKS_CLUSTER_NAME not provided. Run infra.yml first or pass it as input."
            exit 1
          fi
          echo "name=$NAME" >> $GITHUB_OUTPUT
          echo "Using cluster: $NAME"

      - name: Configure kubectl
        run: |
          aws eks update-kubeconfig \\
            --region ${{ secrets.AWS_REGION }} \\
            --name ${{ steps.cluster.outputs.name }}
          kubectl cluster-info

      - name: Setup Helm
        uses: azure/setup-helm@v3
        with:
          version: \'3.13.0\'

      # ── 1. Install ArgoCD ──────────────────────────────────────────────────
      - name: Install ArgoCD
        run: |
          helm repo add argo https://argoproj.github.io/argo-helm --force-update

          # Install or upgrade — idempotent
          helm upgrade --install argocd argo/argo-cd \\
            --namespace argocd \\
            --create-namespace \\
            --set server.service.type=LoadBalancer \\
            --set configs.params."server\\.insecure"=true \\
            --set configs.cm."application\\.resourceTrackingMethod"=annotation \\
            --wait --timeout 8m

          echo "✅ ArgoCD installed"

      # ── 2. Wait for LoadBalancer to get a hostname ────────────────────────
      - name: Wait for ArgoCD LoadBalancer
        id: argocd_host
        run: |
          echo "Waiting for ArgoCD LoadBalancer hostname..."
          for i in $(seq 1 30); do
            HOST=$(kubectl -n argocd get svc argocd-server \\
              -o jsonpath=\'{.status.loadBalancer.ingress[0].hostname}\' 2>/dev/null || true)
            if [ -n "$HOST" ]; then
              echo "host=$HOST" >> $GITHUB_OUTPUT
              echo "✅ ArgoCD host: $HOST"
              break
            fi
            echo "  attempt $i/30 — waiting 15s..."
            sleep 15
          done
          if [ -z "$HOST" ]; then
            echo "❌ Timed out waiting for LoadBalancer"
            exit 1
          fi

      # ── 3. Get admin password and generate an API token ───────────────────
      - name: Generate ArgoCD API token
        id: argocd_token
        run: |
          # Get initial admin password
          PASSWORD=$(kubectl -n argocd get secret argocd-initial-admin-secret \\
            -o jsonpath=\'{.data.password}\' | base64 --decode)

          # Download argocd CLI
          curl -sSL -o /usr/local/bin/argocd \\
            https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
          chmod +x /usr/local/bin/argocd

          # Login
          HOST="${{ steps.argocd_host.outputs.host }}"
          argocd login "$HOST" \\
            --username admin \\
            --password "$PASSWORD" \\
            --insecure \\
            --grpc-web

          # Generate a non-expiring API token
          TOKEN=$(argocd account generate-token \\
            --account admin \\
            --server "$HOST" \\
            --insecure \\
            --grpc-web)

          echo "token=$TOKEN" >> $GITHUB_OUTPUT
          echo "✅ ArgoCD API token generated"

      # ── 4. Write ArgoCD credentials back as GitHub secrets ────────────────
      - name: Store ArgoCD secrets in GitHub
        env:
          GH_TOKEN: ${{ secrets.GH_PAT }}
        run: |
          echo "${{ steps.argocd_token.outputs.token }}" | \\
            gh secret set ARGOCD_AUTH_TOKEN
          echo "${{ steps.argocd_host.outputs.host }}" | \\
            gh secret set ARGOCD_SERVER

          echo "✅ ARGOCD_SERVER and ARGOCD_AUTH_TOKEN written to GitHub secrets"
          echo "   Downstream deploy.yml will use these automatically."

      # ── 5. Register this repo with ArgoCD ─────────────────────────────────
      - name: Register repository with ArgoCD
        run: |
          HOST="${{ steps.argocd_host.outputs.host }}"
          REPO="https://github.com/${{ github.repository }}"

          argocd repo add "$REPO" \\
            --username git \\
            --password "${{ secrets.GH_PAT }}" \\
            --server "$HOST" \\
            --insecure \\
            --grpc-web || true

          echo "✅ Repository registered: $REPO"

      # ── 6. Install External Secrets Operator ──────────────────────────────
      - name: Install External Secrets Operator
        run: |
          helm repo add external-secrets https://charts.external-secrets.io --force-update
          helm upgrade --install external-secrets external-secrets/external-secrets \\
            --namespace external-secrets \\
            --create-namespace \\
            --set installCRDs=true \\
            --wait --timeout 5m

          # Apply the ClusterSecretStore pointing to AWS Secrets Manager
          kubectl apply -f infrastructure/k8s/secrets/secret-store.yaml || true
          echo "✅ External Secrets Operator installed"

      # ── 7. Apply ArgoCD project + ApplicationSet ──────────────────────────
      - name: Register apps with ArgoCD
        run: |
          kubectl apply -n argocd -f infrastructure/k8s/argocd/project.yaml
          kubectl apply -n argocd -f infrastructure/k8s/argocd/applicationset.yaml
          echo "✅ ArgoCD apps registered — sync will begin automatically"

      # ── 8. Wait for staging namespace and capture app URLs ────────────────
      - name: Capture and store app URLs
        env:
          GH_TOKEN: ${{ secrets.GH_PAT }}
        run: |
          echo "Waiting 90s for ArgoCD to create namespaces and services..."
          sleep 90

          APP_NAME=$(basename "${{ github.repository }}")

          # Try to get staging ingress / LoadBalancer hostname
          STAGING_HOST=$(kubectl get svc -n "${APP_NAME}-staging" \\
            -o jsonpath=\'{.items[?(@.spec.type=="LoadBalancer")].status.loadBalancer.ingress[0].hostname}\' \\
            2>/dev/null || true)

          PROD_HOST=$(kubectl get svc -n "${APP_NAME}-prod" \\
            -o jsonpath=\'{.items[?(@.spec.type=="LoadBalancer")].status.loadBalancer.ingress[0].hostname}\' \\
            2>/dev/null || true)

          if [ -n "$STAGING_HOST" ]; then
            gh variable set STAGING_URL --env staging --body "http://${STAGING_HOST}"
            echo "✅ STAGING_URL = http://${STAGING_HOST}"
          else
            echo "⚠️  Staging service not yet ready — update STAGING_URL manually once the app is deployed"
            gh variable set STAGING_URL --env staging --body "http://REPLACE_AFTER_FIRST_DEPLOY"
          fi

          if [ -n "$PROD_HOST" ]; then
            gh variable set PROD_URL --env production --body "http://${PROD_HOST}"
            echo "✅ PROD_URL = http://${PROD_HOST}"
          else
            echo "⚠️  Prod service not yet ready — update PROD_URL manually once the app is deployed"
            gh variable set PROD_URL --env production --body "http://REPLACE_AFTER_FIRST_DEPLOY"
          fi

      # ── 9. Summary ────────────────────────────────────────────────────────
      - name: Bootstrap summary
        run: |
          echo ""
          echo "╔══════════════════════════════════════════════════════════╗"
          echo "║   ArgoCD Bootstrap Complete                              ║"
          echo "╚══════════════════════════════════════════════════════════╝"
          echo ""
          echo "  ArgoCD UI:   https://${{ steps.argocd_host.outputs.host }}"
          echo "  Username:    admin"
          echo "  Cluster:     ${{ steps.cluster.outputs.name }}"
          echo ""
          echo "  GitHub secrets written automatically:"
          echo "    ✅ ARGOCD_SERVER"
          echo "    ✅ ARGOCD_AUTH_TOKEN"
          echo ""
          echo "  The next push to main will trigger a full deploy."
          echo ""
'''


# =============================================================================
# KUBERNETES EXTERNAL SECRETS MANIFESTS
# Uses External Secrets Operator to pull values from AWS Secrets Manager.
# Consumers create secrets in AWS SSM/Secrets Manager; K8s picks them up automatically.
# =============================================================================

K8S_SECRET_STORE = '''# =============================================================================
# ForgeFlow Generated — External Secrets Operator: SecretStore
# Points to AWS Secrets Manager in the cluster region.
# Requires IRSA (IAM Roles for Service Accounts) on the pod SA.
# =============================================================================
apiVersion: external-secrets.io/v1beta1
kind: ClusterSecretStore
metadata:
  name: aws-secrets-manager
  annotations:
    forgeflow.io/generated: "true"
spec:
  provider:
    aws:
      service: SecretsManager
      region: {aws_region}   # Override via KUSTOMIZE patch if region differs
      auth:
        jwt:
          serviceAccountRef:
            name: external-secrets-sa
            namespace: external-secrets
'''

K8S_EXTERNAL_SECRET = '''# =============================================================================
# ForgeFlow Generated — ExternalSecret for {app_name}
# Pulls app secrets from AWS Secrets Manager path: forgeflow/{app_name}/{environment}
#
# Create the AWS secret once (team does this, not CI):
#   aws secretsmanager create-secret \\
#     --name "forgeflow/{app_name}/{environment}" \\
#     --secret-string '{{"DATABASE_URL":"<value>","SECRET_KEY":"<value>"}}'
# =============================================================================
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: {app_name}-secrets
  namespace: {app_name}-{environment}
  annotations:
    forgeflow.io/generated: "true"
spec:
  refreshInterval: 5m
  secretStoreRef:
    name: aws-secrets-manager
    kind: ClusterSecretStore
  target:
    name: {app_name}-secrets          # K8s Secret name pods reference
    creationPolicy: Owner
    template:
      engineVersion: v2
      data:
        # Map AWS Secrets Manager keys → K8s Secret keys
        DATABASE_URL: "{{{{ .DATABASE_URL }}"
        SECRET_KEY:   "{{{{ .SECRET_KEY }}"
  data:
    - secretKey: DATABASE_URL
      remoteRef:
        key:      forgeflow/{app_name}/{environment}
        property: DATABASE_URL
    - secretKey: SECRET_KEY
      remoteRef:
        key:      forgeflow/{app_name}/{environment}
        property: SECRET_KEY
'''

K8S_IRSA_SA = '''# =============================================================================
# ForgeFlow Generated — IRSA Service Account for External Secrets Operator
# Annotate with the IAM role ARN output from Terraform.
# =============================================================================
apiVersion: v1
kind: ServiceAccount
metadata:
  name: external-secrets-sa
  namespace: external-secrets
  annotations:
    # Replace with the IAM role ARN from: terraform output external_secrets_role_arn
    eks.amazonaws.com/role-arn: "arn:aws:iam::ACCOUNT_ID:role/REPLACE_WITH_TERRAFORM_OUTPUT"
'''

K8S_SECRETS_README = '''# Kubernetes Secrets — How ForgeFlow Manages Them

ForgeFlow uses the [External Secrets Operator](https://external-secrets.io) pattern so
**no plaintext secrets ever touch your Git repo or CI logs**.

## Architecture

```
AWS Secrets Manager         External Secrets Operator        Your Pod
────────────────────   →   ───────────────────────────   →  ──────────
forgeflow/APP/ENV           ExternalSecret CR                env vars
  DATABASE_URL               syncs every 5 min               from K8s Secret
  SECRET_KEY                 creates K8s Secret
```

## Setup (one-time, per environment)

### 1. Create the secret in AWS Secrets Manager
```bash
# Replace YOUR_APP_NAME and YOUR_ENV with your actual values, e.g. demo-api / staging
aws secretsmanager create-secret \\
  --name "forgeflow/YOUR_APP_NAME/staging" \\
  --secret-string \'{{
    "DATABASE_URL": "postgres://user:pass@host:5432/db",
    "SECRET_KEY": "your-32-char-random-string"
  }}\'
```

### 2. Annotate the IRSA service account with your IAM role ARN
```bash
# Get the role ARN from Terraform outputs
terraform -chdir=terraform output external_secrets_role_arn

# Patch the service account
kubectl annotate sa external-secrets-sa \\
  -n external-secrets \\
  eks.amazonaws.com/role-arn=<ROLE_ARN> \\
  --overwrite
```

### 3. Apply the manifests (done automatically by setup-argocd.sh)
```bash
kubectl apply -f infrastructure/k8s/secrets/
```

## Adding new secrets
1. Add the key to the AWS secret: `aws secretsmanager put-secret-value ...`
2. Add the key mapping to `external-secret-staging.yaml` and `external-secret-prod.yaml`
3. Commit and push — ArgoCD syncs within 3 minutes
'''


# =============================================================================
# RUNBOOK — Complete zero-to-deployed guide
# =============================================================================

RUNBOOK_MD = '''# ForgeFlow Runbook — Desktop to AWS in Production

> Generated by ForgeFlow. This is your complete operational guide from first commit
> to a live, monitored, GitOps-managed production deployment on AWS EKS.
>
> **Key principle:** You run `forgeflow secrets bootstrap` once, then `git push` —
> everything else happens in GitHub Actions.

---

## Table of Contents
1. [Prerequisites](#1-prerequisites)
2. [Required Secrets & Variables](#2-required-secrets--variables)
3. [One-Time Setup Steps (3 commands)](#3-one-time-setup-steps-3-commands)
4. [How the Deploy Pipeline Works](#4-how-the-deploy-pipeline-works)
5. [Day-2 Operations](#5-day-2-operations)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Prerequisites

**All you need:**

| Tool | Version |
|------|---------|
| gh (GitHub CLI) | ≥ 2.x |
| ForgeFlow | Latest |

**Accounts needed:**
- AWS account with permissions: EKS, ECR, IAM, Secrets Manager, VPC
- GitHub account with repo push access

**No local installation required for:** Terraform, kubectl, Helm, ArgoCD CLI, Docker
— all infrastructure provisioning and deployments run in GitHub Actions.

---

## 2. Required Secrets & Variables

### Human-Managed Secrets (set once via `forgeflow secrets bootstrap`)
Interactive wizard prompts for these 4 values and writes them to GitHub Actions:

| Secret | Purpose | How to get the value |
|--------|---------|----------------------|
| `AWS_ACCESS_KEY_ID` | AWS authentication | [IAM Console](https://console.aws.amazon.com/iam) → Users → _your user_ → Security credentials → Create access key |
| `AWS_SECRET_ACCESS_KEY` | AWS authentication | Same as above (shown once at creation) |
| `AWS_REGION` | Target region | e.g. `us-east-1` (default) or your preferred region |
| `GH_PAT` | GitHub repo access | [GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens) → `repo` + `workflow` scopes |

### Auto-Managed Secrets (written by pipeline)
These are **automatically created and updated** — do not set them manually:

| Secret | Written by | Purpose |
|--------|-----------|---------|
| `ARGOCD_SERVER` | `bootstrap.yml` workflow | ArgoCD API host |
| `ARGOCD_AUTH_TOKEN` | `bootstrap.yml` workflow | ArgoCD deployment auth |
| `EKS_CLUSTER_NAME` | `infra.yml` workflow | Target EKS cluster name |

### GitHub Environment Variables (non-sensitive)
Set at: **GitHub → Settings → Environments → [environment] → Variables**

| Variable | Environment | Value |
|----------|-------------|-------|
| `STAGING_URL` | `staging` | `https://staging.{app_name}.yourdomain.com` |
| `PROD_URL` | `production` | `https://{app_name}.yourdomain.com` |

### AWS Secrets Manager (app-level secrets)
These are picked up automatically by the External Secrets Operator — no manual K8s secret creation needed.

```bash
# Staging
aws secretsmanager create-secret \\
  --name "forgeflow/{app_name}/staging" \\
  --secret-string \'{{
    "DATABASE_URL": "postgres://user:pass@host/db",
    "SECRET_KEY":   "your-random-secret-key"
  }}\'

# Production
aws secretsmanager create-secret \\
  --name "forgeflow/{app_name}/production" \\
  --secret-string \'{{
    "DATABASE_URL": "postgres://user:pass@host/db",
    "SECRET_KEY":   "your-random-secret-key"
  }}\'
```

---

## 3. One-Time Setup Steps (3 commands)

After these 3 steps, every `git push main` triggers the full automated pipeline.

### Step 1 — Authenticate with GitHub
```bash
gh auth login
```
Choose your preferred authentication method (web browser or paste token).

### Step 2 — Bootstrap secrets and environments
```bash
forgeflow secrets bootstrap
```
Interactive wizard prompts for:
1. AWS Access Key ID
2. AWS Secret Access Key
3. AWS Region (default: `us-east-1`)
4. GitHub PAT (with `repo` + `workflow` scopes)

The command:
- Creates GitHub Environments (`staging`, `production`)
- Sets branch protection on `main`
- Writes all 4 secrets to GitHub Actions
- Triggers the `infra.yml` workflow (provisions EKS, VPC, ECR, networking)
- Triggers the `bootstrap.yml` workflow (installs ArgoCD, External Secrets Operator)

**Note:** Infrastructure provisioning takes ~15–20 minutes. Monitor progress in GitHub Actions.

### Step 3 — Push code to trigger the deploy pipeline
```bash
git push origin main
```
The `deploy.yml` workflow automatically runs:
`build → deploy staging → E2E gate → DAST gate → approval → deploy prod → health check`

---

## 4. How the Deploy Pipeline Works

```
Workflows run automatically after bootstrap:

  infra.yml (runs once after bootstrap)
     │
     ├─ AWS Terraform: VPC, EKS, ECR, Security Groups
     ├─ Outputs: EKS_CLUSTER_NAME → GitHub secret
     │
     ▼
  bootstrap.yml (runs once after infra)
     │
     ├─ Installs ArgoCD on EKS
     ├─ Installs External Secrets Operator
     ├─ Creates ARGOCD_SERVER, ARGOCD_AUTH_TOKEN → GitHub secrets
     │
     ▼
  deploy.yml (runs on every git push main)
     │
     ▼
┌─────────────┐
│  1. Build   │  Docker build + push to GHCR (uses GITHUB_TOKEN — no setup needed)
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│  2. Deploy       │  kustomize edit set image → git commit → ArgoCD syncs to EKS
│     Staging      │  Waits 60s for ArgoCD to apply
└──────┬───────────┘
       │
    ┌──┴──────────────────────────────────┐
    │  (parallel gates — both must pass)  │
    │                                     │
    ▼                                     ▼
┌────────────┐                    ┌────────────────┐
│  3. E2E    │                    │  4. DAST       │
│  Staging   │  Playwright tests  │  Staging       │  OWASP ZAP scan
│  Gate      │  @smoke tagged     │  Gate          │  CRITICAL = block
└────────────┘                    └────────────────┘
       │
       ▼
┌────────────────────────────────────┐
│  5. Manual Approval (Production)   │  Required reviewer must click Approve
│  GitHub Environment: production    │  5-minute minimum wait timer
└──────────────────┬─────────────────┘
                   │
                   ▼
         ┌──────────────────┐
         │  6. Deploy Prod  │  kustomize → git commit → ArgoCD syncs to EKS
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  7. Health Check │  Polls /health for 5 minutes (10 × 30s)
         └────────┬─────────┘
                  │
        ┌─────────┴──────────┐
     success               failure
        │                    │
        ▼                    ▼
   ✅ Done          ⏪ Auto-rollback
                   📋 GitHub issue opened
```

---

## 5. Day-2 Operations

### Roll back production manually
```bash
# Option A: Revert the kustomize commit
git revert HEAD --no-edit && git push

# Option B: View ArgoCD app history (no CLI needed — use GitHub Actions UI)
# Navigate to Actions → deploy.yml → re-run with previous commit
```

### Rotate AWS credentials
```bash
# Update in GitHub Actions secrets
gh secret set AWS_ACCESS_KEY_ID --body "<new-key>"
gh secret set AWS_SECRET_ACCESS_KEY --body "<new-secret>"
# Next deploy will use the new credentials
```

### Rotate an app secret
```bash
# Update in AWS Secrets Manager — External Secrets Operator picks it up within 5 min
aws secretsmanager put-secret-value \\
  --secret-id "forgeflow/{app_name}/production" \\
  --secret-string \'{{...updated values...}}\'
```

### Scale the app
```bash
# Edit infrastructure/k8s/overlays/prod/kustomization.yaml
# Commit and push — ArgoCD applies the change automatically
```

### Check pipeline status
```bash
gh run list --workflow=deploy.yml --limit=10
gh run view <run-id>
```

### Check infrastructure and ArgoCD status
```bash
# View GitHub Actions workflow runs for infra and bootstrap
gh run list --workflow=infra.yml
gh run list --workflow=bootstrap.yml
```

---

## 6. Troubleshooting

### Infrastructure provisioning fails (infra.yml)
- Check GitHub Actions logs: Actions → `infra.yml` → failed run
- Verify AWS credentials have EKS, VPC, ECR, IAM, and Secrets Manager permissions
- Check AWS account limits (VPC, EKS cluster, security groups)

### Bootstrap fails (bootstrap.yml)
- Confirm `infra.yml` completed successfully and created the EKS cluster
- Check GitHub Actions logs for ArgoCD installation errors
- Verify the EKS cluster is accessible and in `ACTIVE` state

### Pipeline fails at "Build & Push Image"
- Verify the repo has **Packages: write** permission (set automatically for GITHUB_TOKEN)
- Check Docker build logs in the Actions tab

### Pipeline fails at "Deploy Staging" — "kustomize: command not found"
- The runner should have kustomize installed by the action
- Check setup-kustomize action logs; confirm step ran successfully

### ArgoCD not syncing after deploy
- Check GitHub Actions logs for successful git commit to infrastructure repo
- Confirm `ARGOCD_SERVER` and `ARGOCD_AUTH_TOKEN` secrets exist and are valid
- Monitor ArgoCD UI (if accessible) or check EKS pod logs:
  ```bash
  kubectl logs -n argocd deployment/argocd-application-controller --tail=50
  ```

### E2E tests fail — "Cannot connect to STAGING_URL"
- Verify `STAGING_URL` environment variable is set correctly (GitHub → Environments → staging)
- Check that the staging deployment completed: `kubectl rollout status deployment/{app_name} -n {app_name}-staging`
- The `e2e-staging` job waits 60s after `deploy-staging` — increase if ArgoCD is slower

### Health check fails immediately after deploy
- Check pod logs: `kubectl logs -n {app_name}-prod -l app={app_name} --tail=50`
- Verify `/health` endpoint returns HTTP 200 without auth
- Check `PROD_URL` variable is set correctly

### ExternalSecret shows `SecretSyncedError`
```bash
kubectl describe externalsecret {app_name}-secrets -n {app_name}-staging
# Common causes:
# 1. AWS secret doesn\'t exist yet → run the aws secretsmanager create-secret command
# 2. IAM role ARN not annotated on the service account → check bootstrap.yml logs
# 3. Region mismatch in secret-store.yaml → edit and reapply
```

### How do I run Terraform/kubectl/ArgoCD CLI locally if I need to?
- Not required for normal operations — everything runs in GitHub Actions
- If you need to debug locally, install them manually and use GitHub Actions secrets as reference
- For ArgoCD: `argocd login <ARGOCD_SERVER> --auth-token <ARGOCD_AUTH_TOKEN>` (grab values from GitHub secrets)
- For kubectl: `aws eks update-kubeconfig --name <EKS_CLUSTER_NAME> --region <AWS_REGION>` (grab from secrets)
'''


class CDAgent(BaseAgent):
    """
    Continuous Deployment Agent - Generates ArgoCD, Kustomize, and Kubernetes configurations.

    Responsibilities:
    - ArgoCD Application manifests
    - ArgoCD AppProject / ApplicationSet
    - Kustomize base and overlays (dev, staging, prod)
    - Kubernetes manifests (deployment, service, configmap, hpa, ingress)
    - deploy.yml — full pilot-to-prod pipeline with E2E gate, DAST, approval, rollback
    - scripts/setup-github.sh — GitHub Environments + branch protection setup
    - FluxCD support (optional)
    - Helm charts (optional)
    """
    
    def __init__(self):
        super().__init__(
            name="CDAgent",
            description="Generates Continuous Deployment configurations (ArgoCD, Kustomize, K8s)"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Generate CD configurations based on repository analysis."""
        # Handle params defensively
        if params is None:
            params = {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except:
                params = {"repo_path": params}
        
        repo_path = Path(params.get("repo_path", params.get("path", "."))).resolve()
        overwrite = params.get("overwrite", params.get("greenfield", False))
        repo_url = params.get("repo_url", "https://github.com/org/repo.git")
        include_flux = params.get("include_flux", False)
        include_helm = params.get("include_helm", False)
        
        self.log(f"Generating CD configs for: {repo_path}")
        
        actions = []
        findings = []
        
        # Detect app name and language for port
        app_name = self._detect_app_name(repo_path)
        primary_lang = self._detect_primary_language(repo_path)
        port = "3000" if primary_lang in ["JavaScript", "TypeScript"] else "8000"
        image = f"ghcr.io/org/{app_name}"
        
        self.log(f"Detected app: {app_name}, port: {port}")
        
        # Create k8s directory structure
        k8s_path = repo_path / "infrastructure" / "k8s"
        k8s_path.mkdir(parents=True, exist_ok=True)
        
        # Generate ArgoCD configs
        argocd_actions = self._generate_argocd(k8s_path, app_name, repo_url, overwrite)
        actions.extend(argocd_actions)

        # Generate Kustomize base and overlays
        kustomize_actions = self._generate_kustomize(k8s_path, app_name, port, image, overwrite)
        actions.extend(kustomize_actions)

        # Generate infra.yml — Terraform provision workflow (runs entirely in GitHub Actions)
        infra_workflow_actions = self._generate_infra_workflow(repo_path, overwrite)
        actions.extend(infra_workflow_actions)

        # Generate bootstrap.yml — ArgoCD install workflow (runs entirely in GitHub Actions)
        bootstrap_workflow_actions = self._generate_bootstrap_workflow(repo_path, overwrite)
        actions.extend(bootstrap_workflow_actions)

        # Generate deploy.yml — pilot-to-prod pipeline with gates
        deploy_actions = self._generate_deploy_workflow(repo_path, app_name, overwrite)
        actions.extend(deploy_actions)

        # Generate GitHub setup script (sets the 4 human-managed secrets, then push)
        setup_actions = self._generate_github_setup(repo_path, app_name, overwrite)
        actions.extend(setup_actions)

        # Generate ArgoCD bootstrap script (legacy desktop path — kept for advanced users)
        argocd_setup_actions = self._generate_argocd_setup(repo_path, app_name, overwrite)
        actions.extend(argocd_setup_actions)

        # Generate K8s secrets manifests (External Secrets Operator)
        secrets_actions = self._generate_k8s_secrets(k8s_path, app_name, overwrite)
        actions.extend(secrets_actions)

        # Generate RUNBOOK.md
        runbook_actions = self._generate_runbook(repo_path, app_name, overwrite)
        actions.extend(runbook_actions)

        # Generate FluxCD (optional)
        if include_flux:
            flux_actions = self._generate_flux(k8s_path, app_name, repo_url, overwrite)
            actions.extend(flux_actions)

        # Generate Helm chart (optional)
        if include_helm:
            helm_actions = self._generate_helm(k8s_path, app_name, overwrite)
            actions.extend(helm_actions)

        created  = len([a for a in actions if a.get('action') == 'created'])
        existing = len([a for a in actions if a.get('action') == 'exists'])

        return self.create_result(
            status="success",
            summary=f"Generated CD configurations for {app_name} ({created} files created)",
            data={
                "app_name":    app_name,
                "k8s_path":    str(k8s_path),
                "environments": ["dev", "staging", "prod"],
                "files_created":  created,
                "files_existing": existing,
                "deploy_pipeline":       ".github/workflows/deploy.yml",
                "infra_workflow":        ".github/workflows/infra.yml",
                "bootstrap_workflow":    ".github/workflows/bootstrap.yml",
                "github_setup":         "scripts/setup-github.sh",
                "k8s_secrets":          "infrastructure/k8s/secrets/",
                "runbook":              "RUNBOOK.md",
                "onboarding_steps": [
                    "1. Create AWS IAM user with AdministratorAccess",
                    "2. Create GitHub PAT (repo + secrets scope)",
                    "3. Run: bash scripts/setup-github.sh  ← ONE-TIME ONLY",
                    "4. git push origin main  ← everything else is automated",
                    "   infra.yml provisions EKS via Terraform (GitHub Actions)",
                    "   bootstrap.yml installs ArgoCD + writes secrets back (GitHub Actions)",
                    "   deploy.yml builds, stages, gates, and deploys to prod (GitHub Actions)",
                ],
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
    
    def _generate_argocd(self, k8s_path: Path, app_name: str, repo_url: str, overwrite: bool = False) -> List[Dict]:
        """Generate ArgoCD configuration files."""
        actions = []
        argocd_path = k8s_path / "argocd"
        argocd_path.mkdir(exist_ok=True)
        
        # AppProject
        project_content = ARGOCD_PROJECT.format(app_name=app_name, repo_url=repo_url)
        actions.append(self._safe_write(argocd_path / "project.yaml", project_content, overwrite))

        # Applications for each environment
        for env in ["dev", "staging", "prod"]:
            app_content = ARGOCD_APPLICATION.format(
                app_name=app_name,
                environment=env,
                repo_url=repo_url
            )
            actions.append(self._safe_write(argocd_path / f"application-{env}.yaml", app_content, overwrite))

        # ApplicationSet
        appset_content = ARGOCD_APPLICATIONSET.format(app_name=app_name, repo_url=repo_url)
        actions.append(self._safe_write(argocd_path / "applicationset.yaml", appset_content, overwrite))
        
        return actions
    
    def _generate_kustomize(self, k8s_path: Path, app_name: str, port: str, image: str, overwrite: bool = False) -> List[Dict]:
        """Generate Kustomize base and overlays."""
        actions = []
        
        # Base
        base_path = k8s_path / "base"
        base_path.mkdir(exist_ok=True)
        
        actions.append(self._safe_write(base_path / "kustomization.yaml", KUSTOMIZE_BASE.format(app_name=app_name), overwrite))

        actions.append(self._safe_write(base_path / "deployment.yaml", K8S_DEPLOYMENT.format(app_name=app_name, port=port, image=image, tag="latest"), overwrite))

        actions.append(self._safe_write(base_path / "service.yaml", K8S_SERVICE.format(app_name=app_name, port=port), overwrite))

        actions.append(self._safe_write(base_path / "configmap.yaml", K8S_CONFIGMAP.format(app_name=app_name), overwrite))

        actions.append(self._safe_write(base_path / "hpa.yaml", K8S_HPA.format(app_name=app_name), overwrite))

        actions.append(self._safe_write(base_path / "ingress.yaml", K8S_INGRESS.format(app_name=app_name), overwrite))

        actions.append(self._safe_write(base_path / "serviceaccount.yaml", K8S_SERVICEACCOUNT.format(app_name=app_name), overwrite))
        
        # Overlays
        overlays_path = k8s_path / "overlays"
        overlays_path.mkdir(exist_ok=True)
        
        # Dev overlay
        dev_path = overlays_path / "dev"
        dev_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(dev_path / "kustomization.yaml", KUSTOMIZE_OVERLAY_DEV.format(app_name=app_name), overwrite))
        actions.append(self._safe_write(dev_path / "deployment-patch.yaml", DEPLOYMENT_PATCH_DEV.format(app_name=app_name), overwrite))

        # Staging overlay
        staging_path = overlays_path / "staging"
        staging_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(staging_path / "kustomization.yaml", KUSTOMIZE_OVERLAY_STAGING.format(app_name=app_name), overwrite))
        actions.append(self._safe_write(staging_path / "deployment-patch.yaml", DEPLOYMENT_PATCH_STAGING.format(app_name=app_name), overwrite))

        # Prod overlay
        prod_path = overlays_path / "prod"
        prod_path.mkdir(exist_ok=True)
        actions.append(self._safe_write(prod_path / "kustomization.yaml", KUSTOMIZE_OVERLAY_PROD.format(app_name=app_name), overwrite))
        actions.append(self._safe_write(prod_path / "deployment-patch.yaml", DEPLOYMENT_PATCH_PROD.format(app_name=app_name), overwrite))
        
        return actions
    
    def _generate_flux(self, k8s_path: Path, app_name: str, repo_url: str, overwrite: bool = False) -> List[Dict]:
        """Generate FluxCD configuration files."""
        actions = []
        flux_path = k8s_path / "flux"
        flux_path.mkdir(exist_ok=True)
        
        actions.append(self._safe_write(flux_path / "gitrepository.yaml", FLUX_GITREPOSITORY.format(app_name=app_name, repo_url=repo_url), overwrite))

        for env in ["dev", "staging", "prod"]:
            actions.append(self._safe_write(flux_path / f"kustomization-{env}.yaml", FLUX_KUSTOMIZATION.format(app_name=app_name, environment=env, repo_url=repo_url), overwrite))
        
        return actions
    
    def _generate_helm(self, k8s_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate Helm chart structure."""
        actions = []
        helm_path = k8s_path / "helm" / app_name
        helm_path.mkdir(parents=True, exist_ok=True)
        
        actions.append(self._safe_write(helm_path / "Chart.yaml", HELM_CHART_YAML.format(app_name=app_name), overwrite))

        actions.append(self._safe_write(helm_path / "values.yaml", HELM_VALUES_YAML.format(app_name=app_name), overwrite))

        # Create templates directory
        templates_path = helm_path / "templates"
        templates_path.mkdir(exist_ok=True)

        # Add NOTES.txt
        notes = f'''1. Get the application URL by running:
  kubectl get ingress -n {{{{ .Release.Namespace }}

2. Check deployment status:
  kubectl rollout status deployment/{app_name} -n {{{{ .Release.Namespace }}
'''
        actions.append(self._safe_write(templates_path / "NOTES.txt", notes, overwrite))

        return actions

    def _generate_infra_workflow(self, repo_path: Path, overwrite: bool = False) -> List[Dict]:
        """Generate .github/workflows/infra.yml — Terraform infra provisioning in GitHub Actions."""
        actions = []
        workflows_path = repo_path / ".github" / "workflows"
        workflows_path.mkdir(parents=True, exist_ok=True)
        actions.append(self._safe_write(
            workflows_path / "infra.yml",
            INFRA_WORKFLOW_TEMPLATE,
            overwrite
        ))
        return actions

    def _generate_bootstrap_workflow(self, repo_path: Path, overwrite: bool = False) -> List[Dict]:
        """Generate .github/workflows/bootstrap.yml — ArgoCD bootstrap in GitHub Actions."""
        actions = []
        workflows_path = repo_path / ".github" / "workflows"
        workflows_path.mkdir(parents=True, exist_ok=True)
        actions.append(self._safe_write(
            workflows_path / "bootstrap.yml",
            BOOTSTRAP_WORKFLOW_TEMPLATE,
            overwrite
        ))
        return actions

    def _generate_deploy_workflow(self, repo_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate .github/workflows/deploy.yml — full pilot-to-prod pipeline."""
        actions = []
        workflows_path = repo_path / ".github" / "workflows"
        workflows_path.mkdir(parents=True, exist_ok=True)
        actions.append(self._safe_write(
            workflows_path / "deploy.yml",
            DEPLOY_WORKFLOW_TEMPLATE.format(app_name=app_name),
            overwrite
        ))
        return actions

    def _generate_github_setup(self, repo_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate scripts/setup-github.sh — GitHub Environments + branch protection + secrets bootstrap."""
        actions = []
        scripts_path = repo_path / "scripts"
        scripts_path.mkdir(exist_ok=True)
        content = GITHUB_SETUP_SCRIPT.format(app_name=app_name)
        result = self._safe_write(scripts_path / "setup-github.sh", content, overwrite)
        script_file = scripts_path / "setup-github.sh"
        if script_file.exists():
            script_file.chmod(0o755)
        actions.append(result)
        return actions

    def _generate_argocd_setup(self, repo_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate scripts/setup-argocd.sh — bootstrap ArgoCD on EKS."""
        actions = []
        scripts_path = repo_path / "scripts"
        scripts_path.mkdir(exist_ok=True)
        content = ARGOCD_SETUP_SCRIPT.format(app_name=app_name)
        result = self._safe_write(scripts_path / "setup-argocd.sh", content, overwrite)
        script_file = scripts_path / "setup-argocd.sh"
        if script_file.exists():
            script_file.chmod(0o755)
        actions.append(result)
        return actions

    def _generate_k8s_secrets(self, k8s_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate infrastructure/k8s/secrets/ — External Secrets Operator manifests."""
        actions = []
        secrets_path = k8s_path / "secrets"
        secrets_path.mkdir(exist_ok=True)

        # ClusterSecretStore pointing to AWS Secrets Manager
        actions.append(self._safe_write(
            secrets_path / "secret-store.yaml",
            K8S_SECRET_STORE.format(aws_region="${AWS_REGION:-us-east-1}"),
            overwrite
        ))

        # IRSA service account
        actions.append(self._safe_write(
            secrets_path / "irsa-service-account.yaml",
            K8S_IRSA_SA,
            overwrite
        ))

        # ExternalSecret per environment
        for env in ["staging", "prod"]:
            actions.append(self._safe_write(
                secrets_path / f"external-secret-{env}.yaml",
                K8S_EXTERNAL_SECRET.format(app_name=app_name, environment=env),
                overwrite
            ))

        # Human-readable README
        actions.append(self._safe_write(
            secrets_path / "README.md",
            K8S_SECRETS_README.format(app_name=app_name),
            overwrite
        ))

        return actions

    def _generate_runbook(self, repo_path: Path, app_name: str, overwrite: bool = False) -> List[Dict]:
        """Generate RUNBOOK.md — complete zero-to-deployed operational guide."""
        actions = []
        content = RUNBOOK_MD.format(app_name=app_name)
        actions.append(self._safe_write(repo_path / "RUNBOOK.md", content, overwrite))
        return actions
