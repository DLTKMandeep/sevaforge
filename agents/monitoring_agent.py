#!/usr/bin/env python3
"""
Monitoring Agent - Sets up monitoring and observability.
Mapped to: monitor command → observability_mcp
"""
from pathlib import Path
from typing import Dict, Any, List

from .base_agent import BaseAgent


PROMETHEUS_CONFIG = '''global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'app'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: /metrics
'''

GRAFANA_DASHBOARD = '''{
  "dashboard": {
    "title": "ForgeFlow App Metrics",
    "panels": [
      {
        "title": "Request Rate",
        "type": "graph",
        "datasource": "Prometheus"
      },
      {
        "title": "Error Rate",
        "type": "graph",
        "datasource": "Prometheus"
      }
    ]
  }
}
'''


class MonitoringAgent(BaseAgent):
    """Agent that sets up monitoring and observability."""
    
    def __init__(self):
        super().__init__(
            name="monitoring_agent",
            description="Sets up monitoring, metrics, logging, alerting"
        )
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Set up monitoring and observability."""
        repo_path = Path(params.get('path', '.'))
        configs = []
        
        self.log("Setting up monitoring...")
        
        # Create monitoring directory
        monitoring_dir = repo_path / 'monitoring'
        monitoring_dir.mkdir(exist_ok=True)
        
        # Generate Prometheus config
        configs.append(self._generate_prometheus_config(monitoring_dir))
        
        # Generate Grafana dashboard
        grafana_result = self._generate_grafana_dashboard(monitoring_dir)
        if grafana_result:
            configs.append(grafana_result)
        
        # Check for existing monitoring integrations
        integrations = self._detect_integrations(repo_path)
        
        summary = f"Monitoring setup: {len(configs)} configs, {len(integrations)} integrations"
        self.log(summary)
        
        return self.create_result(
            status='success',
            summary=summary,
            data={
                'configs': configs,
                'integrations': integrations,
                'monitoring_dir': str(monitoring_dir)
            },
            findings=[
                f"{c['type']}: {c['file']} - {c['status']}" for c in configs
            ] + [f"Integration detected: {i}" for i in integrations]
        )
    
    def _generate_prometheus_config(self, monitoring_dir: Path) -> Dict[str, Any]:
        """Generate Prometheus config."""
        prom_config = monitoring_dir / 'prometheus.yml'
        if not prom_config.exists():
            prom_config.write_text(PROMETHEUS_CONFIG)
            return {
                'file': 'monitoring/prometheus.yml',
                'type': 'metrics',
                'status': 'created'
            }
        return {
            'file': 'monitoring/prometheus.yml',
            'type': 'metrics',
            'status': 'exists'
        }
    
    def _generate_grafana_dashboard(self, monitoring_dir: Path) -> Dict[str, Any]:
        """Generate Grafana dashboard."""
        grafana_dir = monitoring_dir / 'grafana' / 'dashboards'
        grafana_dir.mkdir(parents=True, exist_ok=True)
        dashboard_file = grafana_dir / 'app-dashboard.json'
        
        if not dashboard_file.exists():
            dashboard_file.write_text(GRAFANA_DASHBOARD)
            return {
                'file': 'monitoring/grafana/dashboards/app-dashboard.json',
                'type': 'dashboard',
                'status': 'created'
            }
        return None
    
    def _detect_integrations(self, repo_path: Path) -> List[str]:
        """Check for existing monitoring integrations."""
        integrations = []
        compose_file = repo_path / 'docker-compose.yml'
        
        if compose_file.exists():
            try:
                compose_content = compose_file.read_text().lower()
                if 'prometheus' in compose_content:
                    integrations.append('prometheus')
                if 'grafana' in compose_content:
                    integrations.append('grafana')
            except Exception:
                pass
        
        return integrations
