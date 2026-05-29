"""
SevaForge OpenTelemetry Manager — US-063

Stdlib-based OpenTelemetry-compatible tracing and metrics collection.
Provides W3C Trace Context propagation, span management, and metric
recording without requiring the OpenTelemetry SDK as a runtime dependency.

Architecture:
    Request → OTelManager.start_span() → [processing] → end_span() → export buffer
    Metrics → record_metric() → in-memory aggregation → get_metrics()
    Headers → context_propagation_headers() ↔ extract_context()

In production, the export buffer would forward spans to an OTLP collector
(e.g., Jaeger, Grafana Tempo, Datadog) via a background exporter.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# W3C Trace Context version
_TRACEPARENT_VERSION = "00"


# ── Data Models ───────────────────────────────────────────────────────


@dataclass
class SpanEvent:
    """An event (annotation) attached to a span."""
    name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "attributes": self.attributes,
        }


@dataclass
class SpanContext:
    """
    A trace span compatible with the OpenTelemetry data model.

    Attributes:
        trace_id: 32 hex-char trace identifier (W3C format).
        span_id: 16 hex-char span identifier.
        parent_span_id: Parent span ID (empty string for root spans).
        operation_name: The logical operation this span represents.
        service_name: The service producing this span.
        start_time: When the span started.
        end_time: When the span ended (None if still open).
        attributes: Key-value metadata attached to the span.
        events: Timestamped annotations within the span.
        status: Span status — "ok", "error", or "unset".
    """
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    operation_name: str = ""
    service_name: str = "sevaforge"
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: datetime | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[SpanEvent] = field(default_factory=list)
    status: str = "unset"

    @property
    def duration_ms(self) -> float | None:
        """Span duration in milliseconds, or None if not yet ended."""
        if self.end_time is None:
            return None
        delta = self.end_time - self.start_time
        return delta.total_seconds() * 1000

    @property
    def is_root(self) -> bool:
        """True if this is a root span (no parent)."""
        return not self.parent_span_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation_name": self.operation_name,
            "service_name": self.service_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "events": [e.to_dict() for e in self.events],
            "status": self.status,
            "is_root": self.is_root,
        }


# ── Metric Types ──────────────────────────────────────────────────────


@dataclass
class MetricPoint:
    """A single metric data point."""
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metric_type: str = "counter"  # counter, gauge, histogram


# ── OTel Manager ──────────────────────────────────────────────────────


class OTelManager:
    """
    Lightweight OpenTelemetry-compatible tracing and metrics manager.

    Provides:
    - Distributed tracing with parent/child span relationships
    - W3C Trace Context propagation (traceparent header)
    - Metric recording (counters, gauges, histograms)
    - In-memory span export buffer
    - Context extraction from incoming HTTP headers

    This is a stdlib-only implementation. In production, spans from the
    export buffer are forwarded to an OTLP-compatible backend.

    Usage:
        otel = OTelManager(service_name="sevaforge-api")
        span = otel.start_span("handle_request")
        otel.set_attribute(span, "http.method", "POST")
        otel.add_event(span, "cache_miss")
        otel.end_span(span)
        otel.record_metric("request_count", 1, labels={"endpoint": "/api/v1/execute"})
    """

    def __init__(
        self,
        service_name: str = "sevaforge",
        max_export_buffer: int = 10_000,
        max_traces: int = 1_000,
    ):
        self._service_name = service_name
        self._max_export_buffer = max_export_buffer
        self._max_traces = max_traces

        # Active spans keyed by span_id
        self._active_spans: dict[str, SpanContext] = {}

        # Export buffer: completed spans ready for OTLP export
        self._export_buffer: list[SpanContext] = []

        # Traces: trace_id → list of completed spans
        self._traces: dict[str, list[SpanContext]] = defaultdict(list)
        self._trace_order: list[str] = []  # Ordered by creation time

        # Metrics
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._metric_labels: dict[str, dict[str, str]] = {}

        self._stats = {
            "spans_created": 0,
            "spans_exported": 0,
            "metrics_recorded": 0,
        }

    # ── Span Management ───────────────────────────────────────────────

    def start_span(
        self,
        operation_name: str,
        parent: SpanContext | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> SpanContext:
        """
        Start a new trace span.

        If a parent span is provided, the new span inherits the parent's
        trace_id and records the parent's span_id. Otherwise, a new
        trace is started with a fresh trace_id.

        Args:
            operation_name: Logical name for this operation.
            parent: Optional parent span for creating child spans.
            attributes: Initial key-value attributes for the span.

        Returns:
            A new SpanContext representing the open span.
        """
        trace_id = parent.trace_id if parent else self._generate_trace_id()
        parent_span_id = parent.span_id if parent else ""

        span = SpanContext(
            trace_id=trace_id,
            span_id=self._generate_span_id(),
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            service_name=self._service_name,
            start_time=datetime.now(timezone.utc),
            attributes=attributes or {},
        )

        self._active_spans[span.span_id] = span
        self._stats["spans_created"] += 1

        logger.debug(
            "OTel: started span '%s' (trace=%s, span=%s, parent=%s)",
            operation_name, trace_id[:8], span.span_id[:8],
            parent_span_id[:8] if parent_span_id else "root",
        )

        return span

    def end_span(self, span: SpanContext, status: str = "ok") -> None:
        """
        End an open span, record its end time, and export it.

        Args:
            span: The span to close.
            status: Final status — "ok", "error", or "unset".
        """
        span.end_time = datetime.now(timezone.utc)
        span.status = status

        # Remove from active, add to export buffer and traces
        self._active_spans.pop(span.span_id, None)
        self._export_buffer.append(span)
        self._traces[span.trace_id].append(span)

        # Track trace ordering
        if span.trace_id not in self._trace_order or span.is_root:
            if span.trace_id not in self._trace_order:
                self._trace_order.append(span.trace_id)

        self._stats["spans_exported"] += 1

        # Trim export buffer
        if len(self._export_buffer) > self._max_export_buffer:
            self._export_buffer = self._export_buffer[-self._max_export_buffer:]

        # Trim trace history
        while len(self._trace_order) > self._max_traces:
            oldest_trace_id = self._trace_order.pop(0)
            self._traces.pop(oldest_trace_id, None)

        logger.debug(
            "OTel: ended span '%s' (duration=%.1fms, status=%s)",
            span.operation_name,
            span.duration_ms or 0.0,
            status,
        )

    def add_event(
        self,
        span: SpanContext,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """
        Add a timestamped event (annotation) to an open span.

        Args:
            span: The span to annotate.
            name: Event name (e.g., "cache_hit", "retry").
            attributes: Optional event attributes.
        """
        event = SpanEvent(
            name=name,
            attributes=attributes or {},
        )
        span.events.append(event)

    def set_attribute(self, span: SpanContext, key: str, value: Any) -> None:
        """
        Set a key-value attribute on a span.

        Args:
            span: The span to update.
            key: Attribute key (e.g., "http.method", "db.statement").
            value: Attribute value (should be str, int, float, or bool).
        """
        span.attributes[key] = value

    # ── Metrics ───────────────────────────────────────────────────────

    def record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        metric_type: str = "counter",
    ) -> None:
        """
        Record a metric data point.

        Supported metric types:
        - counter: Monotonically increasing value (accumulated).
        - gauge: Instantaneous point-in-time value (overwritten).
        - histogram: Distribution of values (appended).

        Args:
            name: Metric name (e.g., "request_count", "latency_ms").
            value: The numeric value to record.
            labels: Optional labels for metric dimensions.
            metric_type: One of "counter", "gauge", "histogram".
        """
        label_key = self._label_key(name, labels)

        if metric_type == "counter":
            self._counters[label_key] += value
        elif metric_type == "gauge":
            self._gauges[label_key] = value
        elif metric_type == "histogram":
            self._histograms[label_key].append(value)
        else:
            logger.warning("OTel: unknown metric type '%s' for '%s'", metric_type, name)
            return

        if labels:
            self._metric_labels[label_key] = labels

        self._stats["metrics_recorded"] += 1

    def get_metrics(self) -> dict[str, Any]:
        """
        Return all recorded metrics organized by type.

        Returns:
            Dict with keys "counters", "gauges", "histograms",
            each containing metric name → value mappings.
        """
        histograms_summary: dict[str, Any] = {}
        for key, values in self._histograms.items():
            if not values:
                continue
            sorted_vals = sorted(values)
            count = len(sorted_vals)
            histograms_summary[key] = {
                "count": count,
                "min": sorted_vals[0],
                "max": sorted_vals[-1],
                "mean": sum(sorted_vals) / count,
                "p50": sorted_vals[count // 2],
                "p95": sorted_vals[int(count * 0.95)] if count >= 20 else sorted_vals[-1],
                "p99": sorted_vals[int(count * 0.99)] if count >= 100 else sorted_vals[-1],
            }

        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": histograms_summary,
        }

    # ── Trace Retrieval ───────────────────────────────────────────────

    def get_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Return recent traces with all their spans.

        Each trace is a dict with trace_id, span_count, duration,
        and the list of spans.

        Args:
            limit: Maximum number of traces to return.

        Returns:
            List of trace dicts, most recent first.
        """
        traces: list[dict[str, Any]] = []
        recent_trace_ids = self._trace_order[-limit:]

        for trace_id in reversed(recent_trace_ids):
            spans = self._traces.get(trace_id, [])
            if not spans:
                continue

            # Find root span for trace-level info
            root_spans = [s for s in spans if s.is_root]
            root = root_spans[0] if root_spans else spans[0]

            traces.append({
                "trace_id": trace_id,
                "operation": root.operation_name,
                "service": root.service_name,
                "span_count": len(spans),
                "start_time": root.start_time.isoformat(),
                "duration_ms": root.duration_ms,
                "status": root.status,
                "spans": [s.to_dict() for s in spans],
            })

        return traces

    # ── W3C Trace Context Propagation ─────────────────────────────────

    def context_propagation_headers(self, span: SpanContext) -> dict[str, str]:
        """
        Generate W3C Trace Context headers for outgoing requests.

        Produces a `traceparent` header in the format:
            {version}-{trace_id}-{span_id}-{trace_flags}

        Args:
            span: The current span whose context should be propagated.

        Returns:
            Dict with "traceparent" header (and optionally "tracestate").
        """
        # trace-flags: 01 = sampled
        traceparent = f"{_TRACEPARENT_VERSION}-{span.trace_id}-{span.span_id}-01"
        headers = {"traceparent": traceparent}

        # Include tracestate if there are custom attributes to propagate
        if span.service_name:
            headers["tracestate"] = f"sevaforge={span.service_name}"

        return headers

    def extract_context(self, headers: dict[str, str]) -> SpanContext | None:
        """
        Extract a SpanContext from incoming W3C Trace Context headers.

        Parses the `traceparent` header to recover trace_id, span_id,
        and trace flags for continued distributed tracing.

        Args:
            headers: Incoming HTTP headers (case-insensitive lookup).

        Returns:
            SpanContext with extracted IDs, or None if header is missing/invalid.
        """
        # Case-insensitive header lookup
        traceparent = None
        for key, value in headers.items():
            if key.lower() == "traceparent":
                traceparent = value
                break

        if not traceparent:
            return None

        parts = traceparent.split("-")
        if len(parts) != 4:
            logger.warning("OTel: invalid traceparent format: %s", traceparent)
            return None

        version, trace_id, span_id, _trace_flags = parts

        # Validate lengths
        if len(trace_id) != 32 or len(span_id) != 16:
            logger.warning("OTel: invalid traceparent ID lengths: trace=%d, span=%d",
                           len(trace_id), len(span_id))
            return None

        return SpanContext(
            trace_id=trace_id,
            span_id=span_id,
            service_name=self._service_name,
        )

    # ── ID Generation ─────────────────────────────────────────────────

    @staticmethod
    def _generate_trace_id() -> str:
        """Generate a 32-character hex trace ID (W3C compatible)."""
        return uuid.uuid4().hex

    @staticmethod
    def _generate_span_id() -> str:
        """Generate a 16-character hex span ID (W3C compatible)."""
        return uuid.uuid4().hex[:16]

    @staticmethod
    def _label_key(name: str, labels: dict[str, str] | None) -> str:
        """Build a composite key from metric name and labels."""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    # ── Stats & Reset ─────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return manager statistics."""
        return {
            **self._stats,
            "active_spans": len(self._active_spans),
            "export_buffer_size": len(self._export_buffer),
            "traces_stored": len(self._traces),
            "service_name": self._service_name,
        }

    def reset(self) -> None:
        """Clear all state (for testing)."""
        self._active_spans.clear()
        self._export_buffer.clear()
        self._traces.clear()
        self._trace_order.clear()
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._metric_labels.clear()
        self._stats = {k: 0 for k in self._stats}
