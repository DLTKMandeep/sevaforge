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


class CDAgent(BaseAgent):
    """
    Continuous Deployment Agent - Generates ArgoCD, Kustomize, and Kubernetes configurations.
    
    Responsibilities:
    - ArgoCD Application manifests
    - ArgoCD AppProject
    - ArgoCD ApplicationSet
    - Kustomize base and overlays (dev, staging, prod)
    - Kubernetes manifests (deployment, service, configmap, hpa, ingress)
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
        
        repo_path = Path(params.get("repo_path", ".")).resolve()
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
        argocd_actions = self._generate_argocd(k8s_path, app_name, repo_url)
        actions.extend(argocd_actions)
        
        # Generate Kustomize base and overlays
        kustomize_actions = self._generate_kustomize(k8s_path, app_name, port, image)
        actions.extend(kustomize_actions)
        
        # Generate FluxCD (optional)
        if include_flux:
            flux_actions = self._generate_flux(k8s_path, app_name, repo_url)
            actions.extend(flux_actions)
        
        # Generate Helm chart (optional)
        if include_helm:
            helm_actions = self._generate_helm(k8s_path, app_name)
            actions.extend(helm_actions)
        
        return self.create_result(
            status="success",
            summary=f"Generated CD configurations for {app_name}",
            data={
                "app_name": app_name,
                "k8s_path": str(k8s_path),
                "environments": ["dev", "staging", "prod"],
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
    
    def _generate_argocd(self, k8s_path: Path, app_name: str, repo_url: str) -> List[Dict]:
        """Generate ArgoCD configuration files."""
        actions = []
        argocd_path = k8s_path / "argocd"
        argocd_path.mkdir(exist_ok=True)
        
        # AppProject
        project_content = ARGOCD_PROJECT.format(app_name=app_name, repo_url=repo_url)
        (argocd_path / "project.yaml").write_text(project_content)
        actions.append({"action": "created", "file": "infrastructure/k8s/argocd/project.yaml"})
        
        # Applications for each environment
        for env in ["dev", "staging", "prod"]:
            app_content = ARGOCD_APPLICATION.format(
                app_name=app_name,
                environment=env,
                repo_url=repo_url
            )
            (argocd_path / f"application-{env}.yaml").write_text(app_content)
            actions.append({"action": "created", "file": f"infrastructure/k8s/argocd/application-{env}.yaml"})
        
        # ApplicationSet
        appset_content = ARGOCD_APPLICATIONSET.format(app_name=app_name, repo_url=repo_url)
        (argocd_path / "applicationset.yaml").write_text(appset_content)
        actions.append({"action": "created", "file": "infrastructure/k8s/argocd/applicationset.yaml"})
        
        return actions
    
    def _generate_kustomize(self, k8s_path: Path, app_name: str, port: str, image: str) -> List[Dict]:
        """Generate Kustomize base and overlays."""
        actions = []
        
        # Base
        base_path = k8s_path / "base"
        base_path.mkdir(exist_ok=True)
        
        (base_path / "kustomization.yaml").write_text(KUSTOMIZE_BASE.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/kustomization.yaml"})
        
        (base_path / "deployment.yaml").write_text(K8S_DEPLOYMENT.format(app_name=app_name, port=port, image=image, tag="latest"))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/deployment.yaml"})
        
        (base_path / "service.yaml").write_text(K8S_SERVICE.format(app_name=app_name, port=port))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/service.yaml"})
        
        (base_path / "configmap.yaml").write_text(K8S_CONFIGMAP.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/configmap.yaml"})
        
        (base_path / "hpa.yaml").write_text(K8S_HPA.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/hpa.yaml"})
        
        (base_path / "ingress.yaml").write_text(K8S_INGRESS.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/ingress.yaml"})
        
        (base_path / "serviceaccount.yaml").write_text(K8S_SERVICEACCOUNT.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/base/serviceaccount.yaml"})
        
        # Overlays
        overlays_path = k8s_path / "overlays"
        overlays_path.mkdir(exist_ok=True)
        
        # Dev overlay
        dev_path = overlays_path / "dev"
        dev_path.mkdir(exist_ok=True)
        (dev_path / "kustomization.yaml").write_text(KUSTOMIZE_OVERLAY_DEV.format(app_name=app_name))
        (dev_path / "deployment-patch.yaml").write_text(DEPLOYMENT_PATCH_DEV.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/dev/kustomization.yaml"})
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/dev/deployment-patch.yaml"})
        
        # Staging overlay
        staging_path = overlays_path / "staging"
        staging_path.mkdir(exist_ok=True)
        (staging_path / "kustomization.yaml").write_text(KUSTOMIZE_OVERLAY_STAGING.format(app_name=app_name))
        (staging_path / "deployment-patch.yaml").write_text(DEPLOYMENT_PATCH_STAGING.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/staging/kustomization.yaml"})
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/staging/deployment-patch.yaml"})
        
        # Prod overlay
        prod_path = overlays_path / "prod"
        prod_path.mkdir(exist_ok=True)
        (prod_path / "kustomization.yaml").write_text(KUSTOMIZE_OVERLAY_PROD.format(app_name=app_name))
        (prod_path / "deployment-patch.yaml").write_text(DEPLOYMENT_PATCH_PROD.format(app_name=app_name))
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/prod/kustomization.yaml"})
        actions.append({"action": "created", "file": "infrastructure/k8s/overlays/prod/deployment-patch.yaml"})
        
        return actions
    
    def _generate_flux(self, k8s_path: Path, app_name: str, repo_url: str) -> List[Dict]:
        """Generate FluxCD configuration files."""
        actions = []
        flux_path = k8s_path / "flux"
        flux_path.mkdir(exist_ok=True)
        
        (flux_path / "gitrepository.yaml").write_text(FLUX_GITREPOSITORY.format(app_name=app_name, repo_url=repo_url))
        actions.append({"action": "created", "file": "infrastructure/k8s/flux/gitrepository.yaml"})
        
        for env in ["dev", "staging", "prod"]:
            (flux_path / f"kustomization-{env}.yaml").write_text(
                FLUX_KUSTOMIZATION.format(app_name=app_name, environment=env, repo_url=repo_url)
            )
            actions.append({"action": "created", "file": f"infrastructure/k8s/flux/kustomization-{env}.yaml"})
        
        return actions
    
    def _generate_helm(self, k8s_path: Path, app_name: str) -> List[Dict]:
        """Generate Helm chart structure."""
        actions = []
        helm_path = k8s_path / "helm" / app_name
        helm_path.mkdir(parents=True, exist_ok=True)
        
        (helm_path / "Chart.yaml").write_text(HELM_CHART_YAML.format(app_name=app_name))
        actions.append({"action": "created", "file": f"infrastructure/k8s/helm/{app_name}/Chart.yaml"})
        
        (helm_path / "values.yaml").write_text(HELM_VALUES_YAML.format(app_name=app_name))
        actions.append({"action": "created", "file": f"infrastructure/k8s/helm/{app_name}/values.yaml"})
        
        # Create templates directory
        templates_path = helm_path / "templates"
        templates_path.mkdir(exist_ok=True)
        
        # Add NOTES.txt
        notes = f'''1. Get the application URL by running:
  kubectl get ingress -n {{{{ .Release.Namespace }}}}

2. Check deployment status:
  kubectl rollout status deployment/{app_name} -n {{{{ .Release.Namespace }}}}
'''
        (templates_path / "NOTES.txt").write_text(notes)
        actions.append({"action": "created", "file": f"infrastructure/k8s/helm/{app_name}/templates/NOTES.txt"})
        
        return actions
