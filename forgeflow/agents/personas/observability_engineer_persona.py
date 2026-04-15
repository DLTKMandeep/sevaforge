"""
ObservabilityEngineerPersona — metrics, logs, traces, SLOs, alerts.

Artifacts:
  deploy/observability/prometheus-values.yaml  — kube-prometheus-stack values
  deploy/observability/servicemonitor.yaml     — scrape config for the app
  deploy/observability/slo.yaml                — SLO definitions
  deploy/observability/alerts.yaml             — PrometheusRule alerts
  deploy/observability/grafana-dashboard.json  — starter dashboard
  deploy/observability/README.md               — how to install the stack
"""
import json
from typing import Any, Dict, List

import yaml

from .base_persona import BasePersona


class ObservabilityEngineerPersona(BasePersona):
    """Generates observability stack configs aligned to SLOs in the intent."""

    persona_name = "observability-engineer"
    owned_paths = ["deploy/observability/"]

    def __init__(self):
        super().__init__(
            name="observability_engineer_persona",
            description="Emits Prometheus/Grafana configs, SLOs, and alerts",
        )

    def produce_artifacts(self, overwrite=True):
        stack = self.intent["observability"]["stack"]
        if stack == "minimal":
            return [self.write_file(
                "deploy/observability/README.md",
                "# Minimal observability\n\nStack: container stdout logs only. "
                "Upgrade by re-running deploy-intent and selecting a richer stack.\n",
                overwrite,
            )], ["Minimal observability stack selected"], {"stack": stack}

        if stack == "prometheus-grafana":
            return self._prometheus_grafana(overwrite)
        if stack == "datadog":
            return self._datadog(overwrite)
        if stack == "cloud-native":
            return self._cloud_native(overwrite)

        return [], [f"Unknown observability stack: {stack}"], None

    # -------------------------------------------------------- Prometheus+Grafana

    def _prometheus_grafana(self, overwrite: bool):
        app = self.intent["app"]["name"]
        port = self.intent["app"]["port"]
        slo_avail = self.intent["observability"]["slo"]["availability_target"]
        slo_p99 = self.intent["observability"]["slo"]["latency_p99_ms"]
        metrics = self.intent["observability"]["metrics"]
        logs = self.intent["observability"]["logs"]
        traces = self.intent["observability"]["traces"]

        values = {
            "prometheus": {"prometheusSpec": {"retention": "15d"}},
            "grafana": {"adminPassword": "CHANGE_ME_VIA_SECRET", "persistence": {"enabled": True, "size": "5Gi"}},
            "alertmanager": {"enabled": True},
            "kubeStateMetrics": {"enabled": metrics},
        }

        service_monitor = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "ServiceMonitor",
            "metadata": {"name": f"{app}-monitor", "labels": {"release": "kube-prometheus-stack"}},
            "spec": {
                "selector": {"matchLabels": {"app.kubernetes.io/name": app}},
                "endpoints": [{"port": "http", "path": "/metrics", "interval": "30s"}],
            },
        }

        slo_doc = {
            "slos": [
                {
                    "name": f"{app}-availability",
                    "objective": slo_avail,
                    "window": "30d",
                    "sli": {
                        "good": f'sum(rate(http_requests_total{{app="{app}",code!~"5.."}}[5m]))',
                        "total": f'sum(rate(http_requests_total{{app="{app}"}}[5m]))',
                    },
                },
                {
                    "name": f"{app}-latency",
                    "objective": 95.0,
                    "window": "30d",
                    "threshold_ms": slo_p99,
                },
            ]
        }

        alerts = {
            "apiVersion": "monitoring.coreos.com/v1",
            "kind": "PrometheusRule",
            "metadata": {"name": f"{app}-alerts"},
            "spec": {
                "groups": [{
                    "name": f"{app}.rules",
                    "rules": [
                        {
                            "alert": f"{app}HighErrorRate",
                            "expr": f'sum(rate(http_requests_total{{app="{app}",code=~"5.."}}[5m])) / sum(rate(http_requests_total{{app="{app}"}}[5m])) > 0.05',
                            "for": "5m",
                            "labels": {"severity": "page"},
                            "annotations": {"summary": f"{app} error rate > 5% for 5m"},
                        },
                        {
                            "alert": f"{app}HighLatency",
                            "expr": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{app="{app}"}}[5m])) by (le)) > {slo_p99 / 1000}',
                            "for": "10m",
                            "labels": {"severity": "warn"},
                            "annotations": {"summary": f"{app} p99 latency > {slo_p99}ms for 10m"},
                        },
                        {
                            "alert": f"{app}PodCrashLooping",
                            "expr": f'rate(kube_pod_container_status_restarts_total{{pod=~"{app}-.*"}}[15m]) > 0',
                            "for": "5m",
                            "labels": {"severity": "page"},
                            "annotations": {"summary": f"{app} pod is crash-looping"},
                        },
                    ],
                }],
            },
        }

        dashboard = {
            "title": f"{app} — Service Overview",
            "panels": [
                {"title": "Request rate", "type": "graph",
                 "targets": [{"expr": f'sum(rate(http_requests_total{{app="{app}"}}[5m]))'}]},
                {"title": "Error rate", "type": "graph",
                 "targets": [{"expr": f'sum(rate(http_requests_total{{app="{app}",code=~"5.."}}[5m]))'}]},
                {"title": "p99 latency", "type": "graph",
                 "targets": [{"expr": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{app="{app}"}}[5m])) by (le))'}]},
                {"title": "Running pods", "type": "stat",
                 "targets": [{"expr": f'count(kube_pod_info{{pod=~"{app}-.*"}})'}]},
            ],
            "schemaVersion": 16,
        }

        readme = f"""# Observability — {app}

Stack: **kube-prometheus-stack** (Prometheus + Grafana + Alertmanager).

## Install (one-time)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \\
  -n observability --create-namespace \\
  -f deploy/observability/prometheus-values.yaml
```

## Apply app-specific resources

```bash
kubectl apply -f deploy/observability/servicemonitor.yaml
kubectl apply -f deploy/observability/alerts.yaml
```

## SLOs

- Availability target: {slo_avail}% over 30 days
- Latency p99 target: {slo_p99}ms
- Metrics enabled: {metrics}
- Logs enabled: {logs}
- Traces enabled: {traces}

## Grafana dashboard

Import `grafana-dashboard.json` from the Grafana UI (Dashboards → Import → paste JSON).
"""

        return [
            self.write_file("deploy/observability/prometheus-values.yaml",
                            yaml.safe_dump(values, sort_keys=False), overwrite),
            self.write_file("deploy/observability/servicemonitor.yaml",
                            yaml.safe_dump(service_monitor, sort_keys=False), overwrite),
            self.write_file("deploy/observability/slo.yaml",
                            yaml.safe_dump(slo_doc, sort_keys=False), overwrite),
            self.write_file("deploy/observability/alerts.yaml",
                            yaml.safe_dump(alerts, sort_keys=False), overwrite),
            self.write_file("deploy/observability/grafana-dashboard.json",
                            json.dumps(dashboard, indent=2), overwrite),
            self.write_file("deploy/observability/README.md", readme, overwrite),
        ], [
            f"SLO: {slo_avail}% availability / {slo_p99}ms p99",
            "Install kube-prometheus-stack in-cluster to activate",
        ], {"stack": "prometheus-grafana"}

    # ------------------------------------------------------------------ Datadog

    def _datadog(self, overwrite: bool):
        app = self.intent["app"]["name"]
        values = {
            "datadog": {
                "apiKey": "${DATADOG_API_KEY}",
                "appKey": "${DATADOG_APP_KEY}",
                "logs": {"enabled": self.intent["observability"]["logs"], "containerCollectAll": True},
                "apm": {"enabled": self.intent["observability"]["traces"]},
                "orchestratorExplorer": {"enabled": True},
            },
            "clusterAgent": {"enabled": True, "metricsProvider": {"enabled": True}},
        }
        readme = f"""# Observability — {app} (Datadog)

```bash
helm repo add datadog https://helm.datadoghq.com
helm upgrade --install datadog datadog/datadog \\
  -n datadog --create-namespace \\
  -f deploy/observability/datadog-values.yaml \\
  --set datadog.apiKey=$DATADOG_API_KEY \\
  --set datadog.appKey=$DATADOG_APP_KEY
```

Add `DATADOG_API_KEY` and `DATADOG_APP_KEY` to your GitHub secrets.
"""
        return [
            self.write_file("deploy/observability/datadog-values.yaml",
                            yaml.safe_dump(values, sort_keys=False), overwrite),
            self.write_file("deploy/observability/README.md", readme, overwrite),
        ], ["Datadog agent configured — add DATADOG_API_KEY + DATADOG_APP_KEY to secrets"], {"stack": "datadog"}

    # --------------------------------------------------------------- Cloud-native

    def _cloud_native(self, overwrite: bool):
        cloud = self.intent["cloud"]["provider"]
        app = self.intent["app"]["name"]
        msg = {
            "gcp": "Cloud Monitoring + Cloud Logging are auto-enabled on GKE. Dashboards: https://console.cloud.google.com/monitoring",
            "aws": "CloudWatch Container Insights — enable via EKS addon `amazon-cloudwatch-observability`.",
            "azure": "Azure Monitor for Containers — enable via AKS addon `monitoring`.",
            "oci": "OCI Logging Analytics + APM — enable via OKE addon.",
        }.get(cloud, "Cloud-native observability — consult your cloud's docs.")

        readme = f"# Observability — {app} (cloud-native)\n\n{msg}\n"
        return [self.write_file("deploy/observability/README.md", readme, overwrite)], \
               [f"Cloud-native observability via {cloud}"], {"stack": "cloud-native"}
