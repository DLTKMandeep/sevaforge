"""
AppDeployerPersona -- Generates container build artifacts and K8s rollout
manifests (Dockerfile + Helm charts) from a deployment intent.
"""

from __future__ import annotations

import logging
import textwrap
from typing import Any

from sevaforge.agents.base_agent import (
    AgentConfig,
    AgentCapability,
    AgentExecutionContext,
)
from sevaforge.agents.personas.base_persona import BasePersona

logger = logging.getLogger(__name__)

# Language -> (base image, install command, entrypoint pattern)
BASE_IMAGES: dict[str, dict[str, str]] = {
    "python": {
        "base": "python:3.12-slim",
        "install": "pip install --no-cache-dir -r requirements.txt",
        "entrypoint": 'CMD ["python", "-m", "app"]',
    },
    "node": {
        "base": "node:20-alpine",
        "install": "npm ci --production",
        "entrypoint": 'CMD ["node", "dist/index.js"]',
    },
    "go": {
        "base": "golang:1.22-alpine",
        "install": "go mod download",
        "entrypoint": 'ENTRYPOINT ["/app"]',
    },
    "java": {
        "base": "eclipse-temurin:21-jre-alpine",
        "install": "./mvnw package -DskipTests",
        "entrypoint": 'ENTRYPOINT ["java", "-jar", "target/app.jar"]',
    },
    "ruby": {
        "base": "ruby:3.3-slim",
        "install": "bundle install --without development test",
        "entrypoint": 'CMD ["bundle", "exec", "ruby", "app.rb"]',
    },
    "rust": {
        "base": "rust:1.78-slim",
        "install": "cargo build --release",
        "entrypoint": 'ENTRYPOINT ["./target/release/app"]',
    },
}


class AppDeployerPersona(BasePersona):
    """Generates Dockerfiles and Helm/K8s manifests."""

    persona_name = "app-deployer"
    owned_paths = ["Dockerfile", "deploy/helm/", "deploy/k8s/"]

    def __init__(self) -> None:
        super().__init__(
            AgentConfig(
                agent_id="persona-app-deployer",
                name="App Deployer Persona",
                description=(
                    "Generates container build artifacts (Dockerfile) and "
                    "Kubernetes rollout manifests (Helm charts)."
                ),
                capabilities=[
                    AgentCapability(
                        name="generate_dockerfile",
                        description="Produce a language-aware Dockerfile",
                    ),
                    AgentCapability(
                        name="generate_helm_chart",
                        description="Produce a Helm chart skeleton with values",
                    ),
                    AgentCapability(
                        name="generate_k8s_manifests",
                        description="Produce raw K8s Deployment / Service / HPA manifests",
                    ),
                ],
                tags=["persona", "deploy", "containers", "helm"],
            )
        )

    # ------------------------------------------------------------------
    # Artifact generation
    # ------------------------------------------------------------------

    async def _produce_artifacts(
        self,
        intent: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        artifacts: list[dict[str, Any]] = []
        findings: list[str] = []

        app_name = intent.get("app_name", params.get("app_name", "myapp"))
        language = intent.get("language", params.get("language", "python")).lower()
        port = int(intent.get("port", params.get("port", 8080)))
        replicas = int(intent.get("replicas", params.get("replicas", 2)))
        namespace = intent.get("namespace", params.get("namespace", "default"))

        # -- Dockerfile --------------------------------------------------
        dockerfile = self._generate_dockerfile(language, port)
        artifacts.append(self.write_artifact("Dockerfile", dockerfile))

        if language not in BASE_IMAGES:
            findings.append(
                f"Unknown language '{language}'; fell back to generic Dockerfile."
            )

        # -- Helm chart ---------------------------------------------------
        chart_yaml = self._generate_chart_yaml(app_name)
        values_yaml = self._generate_values_yaml(app_name, port, replicas)
        deployment_yaml = self._generate_deployment_yaml(app_name)
        service_yaml = self._generate_service_yaml(app_name)
        hpa_yaml = self._generate_hpa_yaml(app_name)

        artifacts.append(self.write_artifact("deploy/helm/Chart.yaml", chart_yaml))
        artifacts.append(self.write_artifact("deploy/helm/values.yaml", values_yaml))
        artifacts.append(
            self.write_artifact("deploy/helm/templates/deployment.yaml", deployment_yaml)
        )
        artifacts.append(
            self.write_artifact("deploy/helm/templates/service.yaml", service_yaml)
        )
        artifacts.append(
            self.write_artifact("deploy/helm/templates/hpa.yaml", hpa_yaml)
        )

        findings.append(f"Generated Helm chart for '{app_name}' ({language}, port {port}).")

        return {"artifacts": artifacts, "findings": findings}

    # ------------------------------------------------------------------
    # Private generators
    # ------------------------------------------------------------------

    def _generate_dockerfile(self, language: str, port: int) -> str:
        lang = BASE_IMAGES.get(language, BASE_IMAGES["python"])
        return textwrap.dedent(f"""\
            # Auto-generated by SevaForge app-deployer persona
            FROM {lang["base"]} AS build
            WORKDIR /app
            COPY . .
            RUN {lang["install"]}

            FROM {lang["base"]}
            WORKDIR /app
            COPY --from=build /app /app
            EXPOSE {port}
            ENV PORT={port}
            {lang["entrypoint"]}
        """)

    @staticmethod
    def _generate_chart_yaml(app_name: str) -> str:
        return textwrap.dedent(f"""\
            apiVersion: v2
            name: {app_name}
            description: Helm chart for {app_name} (generated by SevaForge)
            type: application
            version: 0.1.0
            appVersion: "1.0.0"
        """)

    @staticmethod
    def _generate_values_yaml(app_name: str, port: int, replicas: int) -> str:
        return textwrap.dedent(f"""\
            replicaCount: {replicas}
            image:
              repository: gcr.io/PROJECT_ID/{app_name}
              tag: latest
              pullPolicy: IfNotPresent
            service:
              type: ClusterIP
              port: {port}
            resources:
              requests:
                cpu: 100m
                memory: 128Mi
              limits:
                cpu: 500m
                memory: 512Mi
            autoscaling:
              enabled: true
              minReplicas: {replicas}
              maxReplicas: {replicas * 5}
              targetCPUUtilizationPercentage: 70
        """)

    @staticmethod
    def _generate_deployment_yaml(app_name: str) -> str:
        return textwrap.dedent(f"""\
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: {{{{{{ include "{app_name}.fullname" . }}}}}}
              labels:
                {{{{{{- include "{app_name}.labels" . | nindent 4 }}}}}}
            spec:
              replicas: {{{{{{ .Values.replicaCount }}}}}}
              selector:
                matchLabels:
                  {{{{{{- include "{app_name}.selectorLabels" . | nindent 6 }}}}}}
              template:
                metadata:
                  labels:
                    {{{{{{- include "{app_name}.selectorLabels" . | nindent 8 }}}}}}
                spec:
                  containers:
                    - name: {{{{{{ .Chart.Name }}}}}}
                      image: "{{{{{{ .Values.image.repository }}}}}}:{{{{{{ .Values.image.tag }}}}}}"
                      imagePullPolicy: {{{{{{ .Values.image.pullPolicy }}}}}}
                      ports:
                        - containerPort: {{{{{{ .Values.service.port }}}}}}
                      resources:
                        {{{{{{- toYaml .Values.resources | nindent 12 }}}}}}
                      livenessProbe:
                        httpGet:
                          path: /healthz
                          port: {{{{{{ .Values.service.port }}}}}}
                        initialDelaySeconds: 15
                        periodSeconds: 20
                      readinessProbe:
                        httpGet:
                          path: /readyz
                          port: {{{{{{ .Values.service.port }}}}}}
                        initialDelaySeconds: 5
                        periodSeconds: 10
        """)

    @staticmethod
    def _generate_service_yaml(app_name: str) -> str:
        return textwrap.dedent(f"""\
            apiVersion: v1
            kind: Service
            metadata:
              name: {{{{{{ include "{app_name}.fullname" . }}}}}}
              labels:
                {{{{{{- include "{app_name}.labels" . | nindent 4 }}}}}}
            spec:
              type: {{{{{{ .Values.service.type }}}}}}
              ports:
                - port: {{{{{{ .Values.service.port }}}}}}
                  targetPort: {{{{{{ .Values.service.port }}}}}}
                  protocol: TCP
                  name: http
              selector:
                {{{{{{- include "{app_name}.selectorLabels" . | nindent 4 }}}}}}
        """)

    @staticmethod
    def _generate_hpa_yaml(app_name: str) -> str:
        return textwrap.dedent(f"""\
            {{{{{{- if .Values.autoscaling.enabled }}}}}}
            apiVersion: autoscaling/v2
            kind: HorizontalPodAutoscaler
            metadata:
              name: {{{{{{ include "{app_name}.fullname" . }}}}}}
              labels:
                {{{{{{- include "{app_name}.labels" . | nindent 4 }}}}}}
            spec:
              scaleTargetRef:
                apiVersion: apps/v1
                kind: Deployment
                name: {{{{{{ include "{app_name}.fullname" . }}}}}}
              minReplicas: {{{{{{ .Values.autoscaling.minReplicas }}}}}}
              maxReplicas: {{{{{{ .Values.autoscaling.maxReplicas }}}}}}
              metrics:
                - type: Resource
                  resource:
                    name: cpu
                    target:
                      type: Utilization
                      averageUtilization: {{{{{{ .Values.autoscaling.targetCPUUtilizationPercentage }}}}}}
            {{{{{{- end }}}}}}
        """)
