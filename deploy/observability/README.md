# Observability — sevaforge-unified

Stack: **kube-prometheus-stack** (Prometheus + Grafana + Alertmanager).

## Install (one-time)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  -n observability --create-namespace \
  -f deploy/observability/prometheus-values.yaml
```

## Apply app-specific resources

```bash
kubectl apply -f deploy/observability/servicemonitor.yaml
kubectl apply -f deploy/observability/alerts.yaml
```

## SLOs

- Availability target: 99.5% over 30 days
- Latency p99 target: 500ms
- Metrics enabled: True
- Logs enabled: True
- Traces enabled: False

## Grafana dashboard

Import `grafana-dashboard.json` from the Grafana UI (Dashboards → Import → paste JSON).
