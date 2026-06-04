"""
SevaForge CD Agent

Generates Continuous Deployment configurations: ArgoCD applications,
Kustomize overlays, Kubernetes manifests, and deployment workflows.

Capabilities:
  - generate_argocd:         ArgoCD Application and AppProject manifests
  - generate_kustomize:      Kustomize base and environment overlays
  - generate_deploy_workflow: GitHub Actions deployment workflow
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sevaforge.agents.base_agent import (
    AgentCapability,
    AgentConfig,
    AgentExecutionContext,
    BaseAgent,
)

logger = logging.getLogger(__name__)


# ── K8s manifest templates ───────────────────────────────────────────

_K8S_DEPLOYMENT = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}
  labels:
    app.kubernetes.io/name: {app_name}
spec:
  replicas: {replicas}
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
    spec:
      serviceAccountName: {app_name}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: {app_name}
          image: {image}
          ports:
            - containerPort: {port}
          resources:
            requests:
              cpu: "{cpu_request}"
              memory: "{mem_request}"
            limits:
              cpu: "{cpu_limit}"
              memory: "{mem_limit}"
          livenessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
"""

_K8S_SERVICE = """apiVersion: v1
kind: Service
metadata:
  name: {app_name}
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: {port}
  selector:
    app.kubernetes.io/name: {app_name}
"""

_K8S_HPA = """apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {app_name}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {app_name}
  minReplicas: {min_replicas}
  maxReplicas: {max_replicas}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
"""

# ── Environment-specific resource defaults ───────────────────────────

_ENV_DEFAULTS: dict[str, dict[str, Any]] = {
    "dev": {"replicas": 1, "cpu_request": "100m", "mem_request": "128Mi",
            "cpu_limit": "500m", "mem_limit": "256Mi", "min_replicas": 1, "max_replicas": 3},
    "staging": {"replicas": 2, "cpu_request": "200m", "mem_request": "256Mi",
                "cpu_limit": "1000m", "mem_limit": "512Mi", "min_replicas": 2, "max_replicas": 5},
    "production": {"replicas": 3, "cpu_request": "500m", "mem_request": "512Mi",
                   "cpu_limit": "2000m", "mem_limit": "1Gi", "min_replicas": 3, "max_replicas": 10},
}

_PORT_BY_LANGUAGE: dict[str, int] = {
    "python": 8000,
    "javascript": 3000,
    "typescript": 3000,
    "go": 8080,
}


class CDAgent(BaseAgent):
    """
    Generates CD pipeline configurations with pattern-based Kubernetes
    templates enhanced by LLM-powered deployment strategy recommendations.
    """

    SYSTEM_PROMPT = """You are a Kubernetes and GitOps deployment expert specializing in
ArgoCD, Kustomize, and progressive delivery strategies.

When given a project description, you:
1. Recommend deployment strategies (rolling, blue-green, canary)
2. Suggest resource limits based on application type
3. Advise on health check configurations
4. Recommend namespace and RBAC patterns
5. Suggest monitoring and alerting for deployments

Provide specific, actionable Kubernetes and ArgoCD configuration advice."""

    def __init__(self):
        super().__init__(AgentConfig(
            agent_id="cd-pipeline",
            name="CD Pipeline Agent",
            description="Generates CD configs (ArgoCD, Kustomize, K8s manifests, deploy workflows)",
            version="2.0.0",
            capabilities=[
                AgentCapability(
                    name="generate_argocd",
                    description="Generate ArgoCD Application and AppProject manifests",
                ),
                AgentCapability(
                    name="generate_kustomize",
                    description="Generate Kustomize base and environment overlays",
                ),
                AgentCapability(
                    name="generate_deploy_workflow",
                    description="Generate GitHub Actions deployment workflow",
                ),
            ],
            system_prompt=self.SYSTEM_PROMPT,
            default_model="claude-sonnet-4-20250514",
            tags=["cd", "deployment", "kubernetes", "argocd", "kustomize"],
        ))

    async def execute(self, ctx: AgentExecutionContext) -> dict[str, Any]:
        """
        Generate CD pipeline configurations.

        ctx.input: project description or source code
        ctx.params:
          - app_name: str
          - language: str
          - repo_url: str
          - environment: str (dev/staging/production)
          - image: str (container image)
        """
        code = ctx.input
        app_name = ctx.params.get("app_name", "my-app")
        language = ctx.params.get("language", "python").lower()
        repo_url = ctx.params.get("repo_url", f"https://github.com/org/{app_name}")
        environment = ctx.params.get("environment", "dev")
        image = ctx.params.get("image", f"ghcr.io/org/{app_name}:latest")
        port = _PORT_BY_LANGUAGE.get(language, 8000)

        configs: dict[str, str] = {}

        # ── Pattern-based generation ──
        configs["argocd_application"] = self._generate_argocd_app(app_name, repo_url, environment)
        configs["argocd_project"] = self._generate_argocd_project(app_name, repo_url)
        configs["kustomize_base"] = self._generate_kustomize_base(app_name)

        env_defaults = _ENV_DEFAULTS.get(environment, _ENV_DEFAULTS["dev"])
        configs["deployment"] = _K8S_DEPLOYMENT.format(
            app_name=app_name, image=image, port=port, **env_defaults,
        )
        configs["service"] = _K8S_SERVICE.format(app_name=app_name, port=port)
        configs["hpa"] = _K8S_HPA.format(
            app_name=app_name,
            min_replicas=env_defaults["min_replicas"],
            max_replicas=env_defaults["max_replicas"],
        )
        configs["deploy_workflow"] = self._generate_deploy_workflow(app_name, environment)

        # ── LLM enhancement ──
        llm_recommendations = None
        try:
            prompt = self._build_strategy_prompt(code, app_name, language, environment)
            llm_response = await self.call_llm(ctx, prompt)
            llm_recommendations = llm_response.content
            model_used = llm_response.model
            input_tokens = llm_response.input_tokens
            output_tokens = llm_response.output_tokens
        except Exception as exc:
            logger.warning("LLM deployment strategy unavailable: %s", exc)
            model_used = "pattern-only"
            input_tokens = 0
            output_tokens = 0

        return {
            "configs": configs,
            "app_name": app_name,
            "environment": environment,
            "language": language,
            "port": port,
            "files_generated": len(configs),
            "llm_recommendations": llm_recommendations,
            "model_used": model_used,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "confidence": 0.9 if llm_recommendations else 0.7,
        }

    # ── ArgoCD Generation ────────────────────────────────────────────

    def _generate_argocd_app(self, app_name: str, repo_url: str, environment: str) -> str:
        """Generate an ArgoCD Application manifest."""
        return (
            f"apiVersion: argoproj.io/v1alpha1\nkind: Application\nmetadata:\n"
            f"  name: {app_name}-{environment}\n  namespace: argocd\n"
            f"  labels:\n    app.kubernetes.io/name: {app_name}\n"
            f"    environment: {environment}\n"
            f"  finalizers:\n    - resources-finalizer.argocd.argoproj.io\n"
            f"spec:\n  project: {app_name}\n"
            f"  source:\n    repoURL: {repo_url}\n    targetRevision: HEAD\n"
            f"    path: infrastructure/k8s/overlays/{environment}\n"
            f"  destination:\n    server: https://kubernetes.default.svc\n"
            f"    namespace: {app_name}-{environment}\n"
            f"  syncPolicy:\n    automated:\n      prune: true\n      selfHeal: true\n"
            f"    syncOptions:\n      - CreateNamespace=true\n"
            f"    retry:\n      limit: 5\n      backoff:\n"
            f"        duration: 5s\n        factor: 2\n        maxDuration: 3m\n"
        )

    def _generate_argocd_project(self, app_name: str, repo_url: str) -> str:
        """Generate an ArgoCD AppProject manifest."""
        return (
            f"apiVersion: argoproj.io/v1alpha1\nkind: AppProject\nmetadata:\n"
            f"  name: {app_name}\n  namespace: argocd\n"
            f"spec:\n  description: '{app_name} project managed by SevaForge'\n"
            f"  sourceRepos:\n    - '{repo_url}'\n"
            f"  destinations:\n    - namespace: {app_name}-*\n"
            f"      server: https://kubernetes.default.svc\n"
            f"  clusterResourceWhitelist:\n    - group: ''\n      kind: Namespace\n"
        )

    # ── Kustomize Generation ─────────────────────────────────────────

    def _generate_kustomize_base(self, app_name: str) -> str:
        """Generate Kustomize base kustomization.yaml."""
        return (
            f"apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n\n"
            f"resources:\n  - deployment.yaml\n  - service.yaml\n"
            f"  - hpa.yaml\n  - serviceaccount.yaml\n\n"
            f"commonLabels:\n  app.kubernetes.io/name: {app_name}\n"
            f"  app.kubernetes.io/managed-by: kustomize\n"
            f"  generator: sevaforge\n"
        )

    # ── Deploy Workflow Generation ───────────────────────────────────

    def _generate_deploy_workflow(self, app_name: str, environment: str) -> str:
        """Generate a GitHub Actions deployment workflow."""
        return (
            f"name: Deploy to {environment}\n\n"
            f"on:\n  workflow_dispatch:\n    inputs:\n"
            f"      environment:\n        description: Target environment\n"
            f"        default: {environment}\n"
            f"        type: choice\n        options: [dev, staging, production]\n\n"
            f"jobs:\n  deploy:\n    name: Deploy {app_name}\n"
            f"    runs-on: ubuntu-latest\n"
            f"    environment: ${{{{ inputs.environment }}}}\n"
            f"    steps:\n      - uses: actions/checkout@v4\n"
            f"      - name: Deploy via ArgoCD\n"
            f"        run: |\n"
            f"          argocd app sync {app_name}-${{{{ inputs.environment }}}} --force\n"
            f"          argocd app wait {app_name}-${{{{ inputs.environment }}}} --timeout 300\n"
        )

    # ── LLM Prompt ───────────────────────────────────────────────────

    def _build_strategy_prompt(
        self, code: str, app_name: str, language: str, environment: str,
    ) -> str:
        """Build prompt for LLM deployment strategy recommendations."""
        return (
            f"Analyze deployment needs for '{app_name}' ({language}) targeting {environment}.\n\n"
            f"Project context:\n```\n{code[:3000]}\n```\n\n"
            f"Recommend:\n"
            f"1. Deployment strategy (rolling vs blue-green vs canary)\n"
            f"2. Resource sizing for this application type\n"
            f"3. Health check and readiness probe configuration\n"
            f"4. Rollback strategy\n"
            f"5. Progressive delivery considerations\n"
        )
