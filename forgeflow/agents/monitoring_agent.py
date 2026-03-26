#!/usr/bin/env python3
"""
Monitoring Agent - Generates production-ready observability stack.
Mapped to: monitor command → observability_mcp

Stack:
- Prometheus: scrape configs tailored to detected framework + alerting rules
- Grafana: complete dashboard JSON with real PromQL panels
- Alertmanager: routing + notification config
- docker-compose.monitoring.yml: full stack composition
- Framework detection: FastAPI, Flask, Django, Express, Go HTTP
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .base_agent import BaseAgent


class MonitoringAgent(BaseAgent):
    """Agent that generates a complete, production-ready observability stack."""

    def __init__(self):
        super().__init__(
            name="monitoring_agent",
            description="Generates Prometheus, Grafana, Alertmanager, and docker-compose monitoring stack"
        )

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        repo_path = Path(params.get('path', '.'))
        app_name = repo_path.name.lower().replace(' ', '-').replace('_', '-')
        dry_run = params.get('dry_run', False)

        self.log(f"Generating observability stack for {repo_path.absolute()}...")

        framework, port, metrics_path = self._detect_framework(repo_path)
        self.log(f"Detected framework: {framework} on port {port}, metrics: {metrics_path}")

        monitoring_dir = repo_path / 'monitoring'
        generated = []

        if not dry_run:
            monitoring_dir.mkdir(exist_ok=True)
            (monitoring_dir / 'grafana').mkdir(exist_ok=True)
            (monitoring_dir / 'grafana' / 'dashboards').mkdir(exist_ok=True)
            (monitoring_dir / 'grafana' / 'provisioning').mkdir(exist_ok=True)
            (monitoring_dir / 'grafana' / 'provisioning' / 'dashboards').mkdir(exist_ok=True)
            (monitoring_dir / 'grafana' / 'provisioning' / 'datasources').mkdir(exist_ok=True)
            (monitoring_dir / 'rules').mkdir(exist_ok=True)

        # 1. Prometheus config + alert rules
        generated.extend(self._write_prometheus_config(
            monitoring_dir, app_name, port, metrics_path, dry_run
        ))

        # 2. Alert rules
        generated.extend(self._write_alert_rules(monitoring_dir, app_name, dry_run))

        # 3. Alertmanager config
        generated.extend(self._write_alertmanager_config(monitoring_dir, app_name, dry_run))

        # 4. Grafana dashboard
        generated.extend(self._write_grafana_dashboard(
            monitoring_dir, app_name, framework, dry_run
        ))

        # 5. Grafana provisioning
        generated.extend(self._write_grafana_provisioning(
            monitoring_dir, app_name, dry_run
        ))

        # 6. docker-compose monitoring stack
        generated.extend(self._write_docker_compose(
            repo_path, app_name, port, dry_run
        ))

        # 7. Detect existing monitoring setup
        existing = self._detect_existing_monitoring(repo_path)

        created = [g for g in generated if g['status'] == 'created']
        skipped = [g for g in generated if g['status'] == 'exists']

        summary = (
            f"Observability stack ({framework}): "
            f"{len(created)} files generated"
            + (f", {len(skipped)} already exist" if skipped else "")
            + (f", detected: {', '.join(existing)}" if existing else "")
        )
        self.log(summary)

        return self.create_result(
            status='success',
            summary=summary,
            data={
                'framework': framework,
                'app_port': port,
                'metrics_path': metrics_path,
                'files_generated': len(created),
                'files_skipped': len(skipped),
                'existing_integrations': existing,
                'monitoring_dir': str(monitoring_dir),
                'generated': [g['file'] for g in created],
            },
            findings=[f"{g['status'].upper()}: {g['file']}" for g in generated]
        )

    # ── Framework Detection ────────────────────────────────────────────────────

    def _detect_framework(self, repo_path: Path) -> Tuple[str, int, str]:
        """Returns (framework_name, app_port, metrics_endpoint)."""
        # FastAPI / uvicorn
        for f in repo_path.rglob('*.py'):
            if '__pycache__' in str(f) or '.venv' in str(f):
                continue
            try:
                content = f.read_text(errors='ignore')
                if 'FastAPI' in content or 'fastapi' in content:
                    return 'fastapi', 8000, '/metrics'
                if 'Flask' in content or 'flask' in content:
                    return 'flask', 5000, '/metrics'
                if 'django' in content.lower() and 'settings' in f.name.lower():
                    return 'django', 8000, '/metrics'
            except Exception:
                pass

        # Node.js / Express
        pkg = repo_path / 'package.json'
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
                if 'express' in deps:
                    return 'express', 3000, '/metrics'
                if 'fastify' in deps:
                    return 'fastify', 3000, '/metrics'
                if 'next' in deps:
                    return 'nextjs', 3000, '/metrics'
            except Exception:
                pass

        # Go
        if list(repo_path.rglob('go.mod')):
            return 'go-http', 8080, '/metrics'

        return 'generic', 8000, '/metrics'

    # ── Prometheus Config ──────────────────────────────────────────────────────

    def _write_prometheus_config(self, monitoring_dir: Path, app_name: str,
                                  port: int, metrics_path: str,
                                  dry_run: bool) -> List[Dict]:
        config = f"""global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    app: '{app_name}'
    environment: 'production'

rule_files:
  - 'rules/*.yml'

alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

scrape_configs:
  - job_name: '{app_name}'
    static_configs:
      - targets: ['host.docker.internal:{port}']
    metrics_path: {metrics_path}
    scrape_interval: 10s
    scrape_timeout: 5s

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
    relabel_configs:
      - source_labels: [__address__]
        target_label: instance
"""
        return self._write_file(
            monitoring_dir / 'prometheus.yml', config, dry_run,
            'monitoring/prometheus.yml'
        )

    # ── Alert Rules ────────────────────────────────────────────────────────────

    def _write_alert_rules(self, monitoring_dir: Path, app_name: str,
                            dry_run: bool) -> List[Dict]:
        rules = f"""groups:
  - name: {app_name}_availability
    interval: 30s
    rules:
      - alert: ServiceDown
        expr: up{{job="{app_name}"}} == 0
        for: 1m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Service {app_name} is down"
          description: "{{{{ $labels.instance }}}} has been down for more than 1 minute."
          runbook_url: "https://runbooks.example.com/{app_name}/service-down"

      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{{job="{app_name}",status=~"5.."}}[5m]))
            /
            sum(rate(http_requests_total{{job="{app_name}"}}[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High HTTP error rate on {app_name}"
          description: "Error rate is {{{{ $value | humanizePercentage }}}} (threshold 5%)."

      - alert: HighLatencyP99
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket{{job="{app_name}"}}[5m])) by (le)
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High p99 latency on {app_name}"
          description: "p99 latency is {{{{ $value }}}}s (threshold 2s)."

  - name: {app_name}_resources
    rules:
      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes{{job="{app_name}"}} / 1024 / 1024 > 512
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {app_name}"
          description: "Process memory is {{{{ $value | humanize }}}}MB (threshold 512MB)."

      - alert: NodeHighCPU
        expr: 100 - (avg by(instance)(irate(node_cpu_seconds_total{{mode="idle"}}[5m])) * 100) > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High CPU on {{{{ $labels.instance }}}}"
          description: "CPU usage is {{{{ $value }}}}% (threshold 80%)."

      - alert: NodeDiskSpaceLow
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 15
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space on {{{{ $labels.instance }}}}"
          description: "{{{{ $labels.mountpoint }}}} has only {{{{ $value | humanizePercentage }}}} free."
"""
        return self._write_file(
            monitoring_dir / 'rules' / 'alerts.yml', rules, dry_run,
            'monitoring/rules/alerts.yml'
        )

    # ── Alertmanager Config ────────────────────────────────────────────────────

    def _write_alertmanager_config(self, monitoring_dir: Path, app_name: str,
                                    dry_run: bool) -> List[Dict]:
        config = f"""global:
  resolve_timeout: 5m
  # smtp_smarthost: 'smtp.example.com:587'
  # smtp_from: 'alerts@example.com'
  # slack_api_url: 'https://hooks.slack.com/services/...'

route:
  group_by: ['alertname', 'job']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: critical
      repeat_interval: 1h
    - match:
        severity: warning
      receiver: warnings

receivers:
  - name: 'default'
    # Configure your default notification channel here

  - name: 'critical'
    # slack_configs:
    #   - channel: '#alerts-critical'
    #     title: '{{ template "slack.default.title" . }}'
    #     text: '{{ template "slack.default.text" . }}'
    # email_configs:
    #   - to: 'oncall@example.com'

  - name: 'warnings'
    # slack_configs:
    #   - channel: '#alerts-warnings'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'job', 'instance']
"""
        return self._write_file(
            monitoring_dir / 'alertmanager.yml', config, dry_run,
            'monitoring/alertmanager.yml'
        )

    # ── Grafana Dashboard ──────────────────────────────────────────────────────

    def _write_grafana_dashboard(self, monitoring_dir: Path, app_name: str,
                                  framework: str, dry_run: bool) -> List[Dict]:
        title = f"{app_name.replace('-', ' ').title()} — Service Metrics"
        dashboard = {
            "uid": f"{app_name}-overview",
            "title": title,
            "description": f"Auto-generated by ForgeFlow for {framework} application",
            "tags": [app_name, framework, "forgeflow"],
            "timezone": "browser",
            "schemaVersion": 38,
            "version": 1,
            "refresh": "30s",
            "time": {"from": "now-1h", "to": "now"},
            "templating": {
                "list": [
                    {
                        "name": "instance",
                        "type": "query",
                        "datasource": "Prometheus",
                        "query": f'label_values(up{{job="{app_name}"}}, instance)',
                        "label": "Instance",
                        "multi": True,
                        "includeAll": True,
                        "current": {"selected": False, "text": "All", "value": "$__all"}
                    }
                ]
            },
            "panels": [
                self._panel_stat(1, "Service Status", 0, 0, 4, 3,
                    f'up{{job="{app_name}"}}',
                    mappings=[{"type": "value", "options": {
                        "0": {"text": "DOWN", "color": "red"},
                        "1": {"text": "UP", "color": "green"}
                    }}]),
                self._panel_stat(2, "Request Rate (RPS)", 4, 0, 5, 3,
                    f'sum(rate(http_requests_total{{job="{app_name}"}}[2m]))',
                    unit="reqps"),
                self._panel_stat(3, "Error Rate", 9, 0, 5, 3,
                    f'sum(rate(http_requests_total{{job="{app_name}",status=~"5.."}}[5m])) / sum(rate(http_requests_total{{job="{app_name}"}}[5m]))',
                    unit="percentunit",
                    thresholds=[0.01, 0.05]),
                self._panel_stat(4, "p99 Latency", 14, 0, 5, 3,
                    f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{job="{app_name}"}}[5m])) by (le))',
                    unit="s",
                    thresholds=[0.5, 2.0]),
                self._panel_timeseries(5, "Request Rate by Status", 0, 3, 12, 8,
                    [
                        {"expr": f'sum by (status) (rate(http_requests_total{{job="{app_name}"}}[2m]))',
                         "legendFormat": "{{status}}"}
                    ], unit="reqps"),
                self._panel_timeseries(6, "Response Latency Percentiles", 12, 3, 12, 8,
                    [
                        {"expr": f'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{{job="{app_name}"}}[5m])) by (le))',
                         "legendFormat": "p50"},
                        {"expr": f'histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{{job="{app_name}"}}[5m])) by (le))',
                         "legendFormat": "p95"},
                        {"expr": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{job="{app_name}"}}[5m])) by (le))',
                         "legendFormat": "p99"},
                    ], unit="s"),
                self._panel_timeseries(7, "Memory Usage", 0, 11, 8, 8,
                    [{"expr": f'process_resident_memory_bytes{{job="{app_name}"}}',
                      "legendFormat": "RSS Memory"}], unit="bytes"),
                self._panel_timeseries(8, "CPU Usage", 8, 11, 8, 8,
                    [{"expr": 'rate(process_cpu_seconds_total{job="' + app_name + '"}[2m]) * 100',
                      "legendFormat": "CPU %"}], unit="percent"),
                self._panel_timeseries(9, "Active Goroutines / Threads", 16, 11, 8, 8,
                    [{"expr": f'go_goroutines{{job="{app_name}"}}',
                      "legendFormat": "Goroutines (Go)"},
                     {"expr": f'process_open_fds{{job="{app_name}"}}',
                      "legendFormat": "Open FDs"}], unit="short"),
                self._panel_timeseries(10, "GC Pause Duration", 0, 19, 12, 7,
                    [{"expr": f'rate(go_gc_duration_seconds_sum{{job="{app_name}"}}[5m]) / rate(go_gc_duration_seconds_count{{job="{app_name}"}}[5m])',
                      "legendFormat": "Mean GC Pause"}], unit="s"),
                self._panel_timeseries(11, "Node CPU", 12, 19, 12, 7,
                    [{"expr": '100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
                      "legendFormat": "{{instance}} CPU %"}], unit="percent"),
            ]
        }

        content = json.dumps({"dashboard": dashboard, "overwrite": True, "folderId": 0}, indent=2)
        return self._write_file(
            monitoring_dir / 'grafana' / 'dashboards' / f'{app_name}-overview.json',
            content, dry_run,
            f'monitoring/grafana/dashboards/{app_name}-overview.json'
        )

    def _panel_stat(self, pid, title, x, y, w, h, expr, unit="short",
                    mappings=None, thresholds=None) -> Dict:
        panel = {
            "id": pid, "type": "stat", "title": title,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": "Prometheus",
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": self._build_threshold_steps(thresholds)
                    },
                    "mappings": mappings or []
                }
            },
            "targets": [{"expr": expr, "instant": True, "legendFormat": ""}],
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "orientation": "auto"}
        }
        return panel

    def _panel_timeseries(self, pid, title, x, y, w, h, targets, unit="short") -> Dict:
        return {
            "id": pid, "type": "timeseries", "title": title,
            "gridPos": {"x": x, "y": y, "w": w, "h": h},
            "datasource": "Prometheus",
            "fieldConfig": {
                "defaults": {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10}}
            },
            "targets": [
                {"expr": t["expr"], "legendFormat": t.get("legendFormat", ""), "refId": chr(65 + i)}
                for i, t in enumerate(targets)
            ],
            "options": {"tooltip": {"mode": "multi"}, "legend": {"displayMode": "list"}}
        }

    def _build_threshold_steps(self, thresholds) -> List[Dict]:
        if not thresholds:
            return [{"color": "green", "value": None}]
        steps = [{"color": "green", "value": None}]
        colors = ["yellow", "red"]
        for i, val in enumerate(thresholds):
            steps.append({"color": colors[min(i, len(colors) - 1)], "value": val})
        return steps

    # ── Grafana Provisioning ───────────────────────────────────────────────────

    def _write_grafana_provisioning(self, monitoring_dir: Path, app_name: str,
                                     dry_run: bool) -> List[Dict]:
        results = []
        datasource = """apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    jsonData:
      httpMethod: POST
      timeInterval: 15s
"""
        results.extend(self._write_file(
            monitoring_dir / 'grafana' / 'provisioning' / 'datasources' / 'prometheus.yml',
            datasource, dry_run,
            'monitoring/grafana/provisioning/datasources/prometheus.yml'
        ))

        dashboard_prov = f"""apiVersion: 1
providers:
  - name: '{app_name}'
    orgId: 1
    type: file
    disableDeletion: false
    updateIntervalSeconds: 60
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: false
"""
        results.extend(self._write_file(
            monitoring_dir / 'grafana' / 'provisioning' / 'dashboards' / 'dashboards.yml',
            dashboard_prov, dry_run,
            'monitoring/grafana/provisioning/dashboards/dashboards.yml'
        ))
        return results

    # ── Docker Compose Monitoring Stack ────────────────────────────────────────

    def _write_docker_compose(self, repo_path: Path, app_name: str,
                               app_port: int, dry_run: bool) -> List[Dict]:
        compose = f"""# ForgeFlow Auto-generated Monitoring Stack
# Usage: docker compose -f docker-compose.monitoring.yml up -d

services:
  prometheus:
    image: prom/prometheus:v2.49.0
    container_name: {app_name}-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./monitoring/rules:/etc/prometheus/rules:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=15d'
      - '--web.enable-lifecycle'
      - '--web.enable-admin-api'
    ports:
      - "9090:9090"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.3.0
    container_name: {app_name}-grafana
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning:ro
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
      - GF_SERVER_ROOT_URL=http://localhost:3001
      - GF_DASHBOARDS_DEFAULT_HOME_DASHBOARD_PATH=/var/lib/grafana/dashboards/{app_name}-overview.json
    ports:
      - "3001:3000"
    depends_on:
      - prometheus
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:v0.26.0
    container_name: {app_name}-alertmanager
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
      - alertmanager_data:/alertmanager
    command:
      - '--config.file=/etc/alertmanager/alertmanager.yml'
      - '--storage.path=/alertmanager'
    ports:
      - "9093:9093"
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:v1.7.0
    container_name: {app_name}-node-exporter
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
    command:
      - '--path.procfs=/host/proc'
      - '--path.rootfs=/rootfs'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
    ports:
      - "9100:9100"
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
  alertmanager_data:
"""
        return self._write_file(
            repo_path / 'docker-compose.monitoring.yml', compose, dry_run,
            'docker-compose.monitoring.yml'
        )

    # ── Detect Existing Monitoring ─────────────────────────────────────────────

    def _detect_existing_monitoring(self, repo_path: Path) -> List[str]:
        detected = []
        checks = {
            'prometheus': ['monitoring/prometheus.yml', 'prometheus.yml'],
            'grafana': ['monitoring/grafana', 'grafana'],
            'datadog': ['datadog.yaml', '.datadog-agent'],
            'newrelic': ['newrelic.ini', 'newrelic.yml'],
            'opentelemetry': ['otel-collector-config.yml', 'opentelemetry.yml'],
            'sentry': ['sentry.properties'],
        }
        for tool, paths in checks.items():
            if any((repo_path / p).exists() for p in paths):
                detected.append(tool)

        # Check requirements for monitoring libs
        req = repo_path / 'requirements.txt'
        if req.exists():
            try:
                reqs = req.read_text().lower()
                if 'prometheus' in reqs or 'prometheus-client' in reqs:
                    if 'prometheus' not in detected:
                        detected.append('prometheus-client')
                if 'opentelemetry' in reqs:
                    if 'opentelemetry' not in detected:
                        detected.append('opentelemetry-sdk')
                if 'sentry-sdk' in reqs:
                    if 'sentry' not in detected:
                        detected.append('sentry-sdk')
            except Exception:
                pass
        return detected

    # ── File Writer Helper ─────────────────────────────────────────────────────

    def _write_file(self, path: Path, content: str, dry_run: bool,
                    display_path: str) -> List[Dict]:
        if path.exists():
            return [{'file': display_path, 'status': 'exists'}]
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return [{'file': display_path, 'status': 'created'}]
