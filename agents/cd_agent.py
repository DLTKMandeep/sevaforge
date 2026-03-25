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
      name: '{{{{app_name}}}}-{{{{environment}}}}'
    spec:
      project: {app_name}
      source:
        repoURL: {repo_url}
        targetRevision: HEAD
        path: 'infrastructure/k8s/overlays/{{{{environment}}}}'
      destination:
        server: https://kubernetes.default.svc
        namespace: '{{{{app_name}}}}-{{{{environment}}}}'
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
            status=$(curl -s -o /dev/null -w "%{{http_code}}" "${{{{ vars.PROD_URL }}}}/health" || echo "000")
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
            }})
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
# 3. Branch protection on main  (use --input with heredoc for clean JSON)
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
# 4. Summary
# ---------------------------------------------------------------------------
echo ""
echo "================================================================"
echo " GitHub setup complete for $REPO"
echo "================================================================"
echo ""
echo " One remaining manual step:"
echo "  → https://github.com/$REPO/settings/environments"
echo "     production → Required reviewers → add yourself or your team"
echo ""
echo " Update real URLs once infrastructure is deployed:"
echo "  → STAGING_URL  (staging environment)"
echo "  → PROD_URL     (production environment)"
echo ""
echo " Pipeline flow on every merge to main:"
echo "  build image → deploy staging → E2E + DAST (parallel)"
echo "  → reviewer approval → deploy prod → health check"
echo "  → auto-rollback + incident issue if health check fails"
echo ""
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
        overwrite = params.get("greenfield", False)
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

        # Generate deploy.yml — pilot-to-prod pipeline with gates
        deploy_actions = self._generate_deploy_workflow(repo_path, app_name, overwrite)
        actions.extend(deploy_actions)

        # Generate GitHub setup script
        setup_actions = self._generate_github_setup(repo_path, app_name, overwrite)
        actions.extend(setup_actions)

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
                "deploy_pipeline": ".github/workflows/deploy.yml",
                "github_setup":    "scripts/setup-github.sh",
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
  kubectl get ingress -n {{{{ .Release.Namespace }}}}

2. Check deployment status:
  kubectl rollout status deployment/{app_name} -n {{{{ .Release.Namespace }}}}
'''
        actions.append(self._safe_write(templates_path / "NOTES.txt", notes, overwrite))

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
        """Generate scripts/setup-github.sh — GitHub Environments + branch protection."""
        actions = []
        scripts_path = repo_path / "scripts"
        scripts_path.mkdir(exist_ok=True)
        content = GITHUB_SETUP_SCRIPT.format(app_name=app_name)
        result = self._safe_write(scripts_path / "setup-github.sh", content, overwrite)
        # Make it executable
        script_file = scripts_path / "setup-github.sh"
        if script_file.exists():
            script_file.chmod(0o755)
        actions.append(result)
        return actions
