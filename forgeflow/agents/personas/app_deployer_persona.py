"""
AppDeployerPersona — produces Dockerfile + rollout manifests.

Artifacts:
  Dockerfile                          — if missing
  deploy/helm/<app>/Chart.yaml        — when kubernetes
  deploy/helm/<app>/values.yaml
  deploy/helm/<app>/templates/deployment.yaml
  deploy/helm/<app>/templates/service.yaml
  deploy/helm/<app>/templates/hpa.yaml  — when autoscale enabled
  deploy/k8s/deployment.yaml          — fallback plain manifests
"""
from typing import Any, Dict, List

import yaml

from .base_persona import BasePersona


BASE_IMAGES = {
    "python": "python:3.11-slim",
    "node": "node:20-alpine",
    "go": "golang:1.22-alpine",
    "java": "eclipse-temurin:21-jre",
    "ruby": "ruby:3.2-slim",
    "rust": "rust:1.75",
    "other": "ubuntu:22.04",
}


class AppDeployerPersona(BasePersona):
    """Generates container build + kubernetes rollout artefacts."""

    persona_name = "app-deployer"
    owned_paths = ["Dockerfile", "deploy/helm/", "deploy/k8s/"]

    def __init__(self):
        super().__init__(
            name="app_deployer_persona",
            description="Generates Dockerfile + Helm/K8s rollout manifests",
        )

    def produce_artifacts(self, overwrite=True):
        actions: List[Dict[str, Any]] = []
        findings: List[str] = []

        # Dockerfile — only create if missing (preserve hand-crafted ones)
        dockerfile = self.project_path / "Dockerfile"
        if not dockerfile.exists():
            actions.append(self.write_file("Dockerfile", self._render_dockerfile(), overwrite=False))
        else:
            findings.append("Dockerfile already exists — preserved")

        model = self.intent["compute"]["model"]
        if model == "kubernetes":
            actions.extend(self._helm_chart(overwrite))
        elif model == "serverless":
            findings.append("Serverless mode — no rollout manifests needed (Cloud Run/Lambda handles rollout)")
        elif model == "vm":
            actions.append(self._vm_bootstrap_script(overwrite))

        return actions, findings, {"model": model}

    # ---------------------------------------------------------------- Dockerfile

    def _render_dockerfile(self) -> str:
        lang = self.intent["app"]["language"]
        port = self.intent["app"]["port"]
        base = BASE_IMAGES.get(lang, BASE_IMAGES["other"])

        templates = {
            "python": f'''FROM {base}

WORKDIR /app
COPY requirements.txt* pyproject.toml* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
COPY . .

EXPOSE {port}
CMD ["python", "-m", "app"]
''',
            "node": f'''FROM {base}

WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .

EXPOSE {port}
CMD ["node", "index.js"]
''',
            "go": f'''FROM {base} AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /app ./...

FROM gcr.io/distroless/static
COPY --from=build /app /app
EXPOSE {port}
ENTRYPOINT ["/app"]
''',
            "java": f'''FROM {base}

WORKDIR /app
COPY target/*.jar /app/app.jar
EXPOSE {port}
CMD ["java", "-jar", "/app/app.jar"]
''',
        }
        return templates.get(lang, f'FROM {base}\nWORKDIR /app\nCOPY . .\nEXPOSE {port}\nCMD ["./start.sh"]\n')

    # ---------------------------------------------------------------- Helm

    def _helm_chart(self, overwrite: bool) -> List[Dict[str, Any]]:
        app = self.intent["app"]["name"]
        port = self.intent["app"]["port"]
        replicas = self.intent["compute"]["replicas"]
        autoscale = self.intent["compute"]["autoscale"]
        healthcheck = self.intent["app"]["healthcheck_path"]
        chart_dir = f"deploy/helm/{app}"

        chart_yaml = yaml.safe_dump({
            "apiVersion": "v2",
            "name": app,
            "description": f"Helm chart for {app}",
            "type": "application",
            "version": "0.1.0",
            "appVersion": "1.0.0",
        }, sort_keys=False)

        values_yaml = yaml.safe_dump({
            "image": {"repository": f"gcr.io/{self.intent['cloud'].get('project_id', 'PROJECT')}/{app}", "tag": "latest", "pullPolicy": "IfNotPresent"},
            "replicaCount": replicas,
            "service": {"type": "ClusterIP", "port": 80, "targetPort": port},
            "autoscaling": {
                "enabled": autoscale["enabled"],
                "minReplicas": autoscale["min"],
                "maxReplicas": autoscale["max"],
                "targetCPUUtilizationPercentage": 70,
            },
            "healthcheck": {"path": healthcheck},
            "resources": {
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
        }, sort_keys=False)

        deployment_yaml = f'''apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{{{ include "{app}.fullname" . }}}}
  labels:
    app.kubernetes.io/name: {app}
spec:
  {{{{- if not .Values.autoscaling.enabled }}}}
  replicas: {{{{ .Values.replicaCount }}}}
  {{{{- end }}}}
  selector:
    matchLabels:
      app.kubernetes.io/name: {app}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {app}
    spec:
      containers:
        - name: {app}
          image: "{{{{ .Values.image.repository }}}}:{{{{ .Values.image.tag }}}}"
          imagePullPolicy: {{{{ .Values.image.pullPolicy }}}}
          ports:
            - name: http
              containerPort: {{{{ .Values.service.targetPort }}}}
          livenessProbe:
            httpGet:
              path: {{{{ .Values.healthcheck.path }}}}
              port: http
            initialDelaySeconds: 15
            periodSeconds: 20
          readinessProbe:
            httpGet:
              path: {{{{ .Values.healthcheck.path }}}}
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            {{{{- toYaml .Values.resources | nindent 12 }}}}
'''

        service_yaml = f'''apiVersion: v1
kind: Service
metadata:
  name: {{{{ include "{app}.fullname" . }}}}
  labels:
    app.kubernetes.io/name: {app}
spec:
  type: {{{{ .Values.service.type }}}}
  ports:
    - port: {{{{ .Values.service.port }}}}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    app.kubernetes.io/name: {app}
'''

        hpa_yaml = f'''{{{{- if .Values.autoscaling.enabled }}}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{{{ include "{app}.fullname" . }}}}
  labels:
    app.kubernetes.io/name: {app}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{{{ include "{app}.fullname" . }}}}
  minReplicas: {{{{ .Values.autoscaling.minReplicas }}}}
  maxReplicas: {{{{ .Values.autoscaling.maxReplicas }}}}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}
{{{{- end }}}}
'''

        helpers_tpl = f'''{{{{/*
Common name helpers
*/}}}}
{{{{- define "{app}.fullname" -}}}}
{{{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}}}
{{{{- end }}}}
'''

        return [
            self.write_file(f"{chart_dir}/Chart.yaml", chart_yaml, overwrite),
            self.write_file(f"{chart_dir}/values.yaml", values_yaml, overwrite),
            self.write_file(f"{chart_dir}/templates/_helpers.tpl", helpers_tpl, overwrite),
            self.write_file(f"{chart_dir}/templates/deployment.yaml", deployment_yaml, overwrite),
            self.write_file(f"{chart_dir}/templates/service.yaml", service_yaml, overwrite),
            self.write_file(f"{chart_dir}/templates/hpa.yaml", hpa_yaml, overwrite),
        ]

    # ------------------------------------------------------------------- VM

    def _vm_bootstrap_script(self, overwrite: bool) -> Dict[str, Any]:
        script = f'''#!/usr/bin/env bash
# Cloud-init bootstrap for VM deployment of {self.intent["app"]["name"]}
set -euo pipefail
docker pull ghcr.io/OWNER/{self.intent["app"]["name"]}:latest
docker run -d --restart=always -p {self.intent["app"]["port"]}:{self.intent["app"]["port"]} \\
  ghcr.io/OWNER/{self.intent["app"]["name"]}:latest
'''
        return self.write_file("deploy/vm/cloud-init.sh", script, overwrite)
