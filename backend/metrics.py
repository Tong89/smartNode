# -*- coding: utf-8 -*-
"""Prometheus metrics and OpenTelemetry tracing integration for SmartNode.

Exposes /metrics endpoint with Prometheus text format and injects
OpenTelemetry trace context into Flask request handling.

Usage:
    from backend.metrics import init_metrics, update_simulation_metrics
    init_metrics(app, simulation_engine)
"""

import time
import logging
import os
from typing import Optional, TYPE_CHECKING

from flask import Flask, Response, request

if TYPE_CHECKING:
    from backend.core import SimulationEngine

logger = logging.getLogger("smartnode.metrics")

# ---------------------------------------------------------------------------
# Prometheus client integration
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        REGISTRY,
    )
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client not installed — /metrics will return 501")

# ---------------------------------------------------------------------------
# OpenTelemetry integration (optional, gracefully degraded)
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False
    logger.warning("opentelemetry packages not installed — tracing disabled")

# ---------------------------------------------------------------------------
# Metric declarations (module-level singletons, created lazily)
# ---------------------------------------------------------------------------
_metrics_initialized = False

# HTTP request metrics
http_requests_total: Optional[object] = None
http_request_duration_seconds: Optional[object] = None
http_requests_in_flight: Optional[object] = None
http_requests_rejected_total: Optional[object] = None

# Simulation business metrics
sim_total_requests_total: Optional[object] = None
sim_accepted_requests_total: Optional[object] = None
sim_rejected_requests_total: Optional[object] = None
sim_completed_requests_total: Optional[object] = None
sim_transmitting_requests: Optional[object] = None
sim_data_transmitted_mb_total: Optional[object] = None

# Resource utilization gauges
sim_satellite_utilization: Optional[object] = None
sim_ground_station_utilization: Optional[object] = None
sim_geo_relay_utilization: Optional[object] = None

# Engine liveness gauge
sim_engine_running: Optional[object] = None

# Decision quality metrics
sim_acceptance_rate: Optional[object] = None
sim_completion_rate: Optional[object] = None
sim_avg_scheduling_time_seconds: Optional[object] = None


def _create_metrics() -> None:
    """Instantiate all Prometheus metric objects once."""
    global _metrics_initialized
    global http_requests_total, http_request_duration_seconds, http_requests_in_flight
    global http_requests_rejected_total
    global sim_total_requests_total, sim_accepted_requests_total
    global sim_rejected_requests_total, sim_completed_requests_total
    global sim_transmitting_requests, sim_data_transmitted_mb_total
    global sim_satellite_utilization, sim_ground_station_utilization
    global sim_geo_relay_utilization, sim_engine_running
    global sim_acceptance_rate, sim_completion_rate, sim_avg_scheduling_time_seconds

    if _metrics_initialized or not _PROM_AVAILABLE:
        return

    http_requests_total = Counter(
        "smartnode_http_requests_total",
        "Total number of HTTP requests received",
        ["method", "endpoint", "status"],
    )
    http_request_duration_seconds = Histogram(
        "smartnode_http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
    )
    http_requests_in_flight = Gauge(
        "smartnode_http_requests_in_flight",
        "Number of HTTP requests currently being processed",
    )
    http_requests_rejected_total = Counter(
        "smartnode_http_requests_rejected_total",
        "Total HTTP requests rejected (rate-limited or auth-failed)",
        ["reason"],
    )

    # Simulation counters
    sim_total_requests_total = Counter(
        "smartnode_sim_requests_total",
        "Total simulation transmission requests submitted",
    )
    sim_accepted_requests_total = Counter(
        "smartnode_sim_accepted_requests_total",
        "Total simulation requests accepted for scheduling",
    )
    sim_rejected_requests_total = Counter(
        "smartnode_sim_rejected_requests_total",
        "Total simulation requests rejected",
        ["reason"],
    )
    sim_completed_requests_total = Counter(
        "smartnode_sim_completed_requests_total",
        "Total simulation requests that completed transmission",
    )
    sim_transmitting_requests = Gauge(
        "smartnode_sim_transmitting_requests",
        "Requests currently in transmitting state",
    )
    sim_data_transmitted_mb_total = Counter(
        "smartnode_sim_data_transmitted_mb_total",
        "Total megabytes transmitted by the simulation",
    )

    # Resource utilization (0.0 – 1.0)
    sim_satellite_utilization = Gauge(
        "smartnode_sim_satellite_utilization_ratio",
        "Fraction of LEO satellites currently occupied (0–1)",
    )
    sim_ground_station_utilization = Gauge(
        "smartnode_sim_ground_station_utilization_ratio",
        "Fraction of ground stations currently occupied (0–1)",
    )
    sim_geo_relay_utilization = Gauge(
        "smartnode_sim_geo_relay_utilization_ratio",
        "Fraction of GEO relay bandwidth in use (0–1)",
    )

    # Engine health
    sim_engine_running = Gauge(
        "smartnode_sim_engine_running",
        "1 if the simulation background thread is alive, 0 otherwise",
    )

    # Decision quality
    sim_acceptance_rate = Gauge(
        "smartnode_sim_acceptance_rate",
        "Rolling acceptance rate (accepted / total)",
    )
    sim_completion_rate = Gauge(
        "smartnode_sim_completion_rate",
        "Rolling completion rate (completed / accepted)",
    )
    sim_avg_scheduling_time_seconds = Gauge(
        "smartnode_sim_avg_scheduling_time_seconds",
        "Average scheduling decision time in seconds",
    )

    _metrics_initialized = True


# ---------------------------------------------------------------------------
# Snapshot state helpers (used to compute deltas for Counters)
# ---------------------------------------------------------------------------
_prev_stats: dict = {}


def update_simulation_metrics(engine: "SimulationEngine") -> None:
    """Pull current stats from the simulation engine and update Prometheus gauges/counters.

    Called on each /metrics scrape to keep values fresh.
    """
    global _prev_stats

    if not _PROM_AVAILABLE or not _metrics_initialized:
        return

    try:
        stats = engine.get_stats()
    except Exception as exc:
        logger.debug("update_simulation_metrics: get_stats failed: %s", exc)
        return

    # --- Counters: increment by delta since last scrape ---
    def _delta(key: str) -> float:
        prev = _prev_stats.get(key, 0)
        curr = stats.get(key, 0)
        d = max(0.0, float(curr) - float(prev))
        return d

    try:
        sim_total_requests_total._value.inc(_delta("total_requests"))  # type: ignore[union-attr]
        sim_accepted_requests_total._value.inc(_delta("accepted_requests"))  # type: ignore[union-attr]
        sim_completed_requests_total._value.inc(_delta("completed_requests"))  # type: ignore[union-attr]
        sim_data_transmitted_mb_total._value.inc(_delta("total_data_transmitted"))  # type: ignore[union-attr]
    except Exception:
        pass

    # Rejected requests by reason
    try:
        prev_dist = _prev_stats.get("rejection_distribution", {})
        curr_dist = stats.get("rejection_distribution", {})
        for reason, count in curr_dist.items():
            prev_count = prev_dist.get(reason, 0)
            delta = max(0, int(count) - int(prev_count))
            if delta > 0:
                sim_rejected_requests_total.labels(reason=reason).inc(delta)  # type: ignore[union-attr]
    except Exception:
        pass

    # --- Gauges ---
    try:
        ru = stats.get("resource_utilization", {})
        sim_satellite_utilization.set(ru.get("satellites", 0.0))  # type: ignore[union-attr]
        sim_ground_station_utilization.set(ru.get("ground_stations", 0.0))  # type: ignore[union-attr]
        sim_geo_relay_utilization.set(ru.get("geo_relays", 0.0))  # type: ignore[union-attr]

        sim_transmitting_requests.set(stats.get("transmitting_requests", 0))  # type: ignore[union-attr]

        dm = stats.get("decision_metrics", {})
        sim_acceptance_rate.set(dm.get("acceptance_rate", 0.0))  # type: ignore[union-attr]
        sim_completion_rate.set(dm.get("completion_rate", 0.0))  # type: ignore[union-attr]
        sim_avg_scheduling_time_seconds.set(dm.get("avg_scheduling_time", 0.0))  # type: ignore[union-attr]

        # Engine liveness
        thread = getattr(engine, "simulation_thread", None)
        alive = int(bool(engine.running and thread and thread.is_alive()))
        sim_engine_running.set(alive)  # type: ignore[union-attr]
    except Exception as exc:
        logger.debug("update_simulation_metrics gauges error: %s", exc)

    # Save snapshot for next delta computation
    _prev_stats = dict(stats)
    _prev_stats["rejection_distribution"] = dict(stats.get("rejection_distribution", {}))


# ---------------------------------------------------------------------------
# Flask integration
# ---------------------------------------------------------------------------

def _normalize_endpoint(path: str) -> str:
    """Collapse dynamic path segments to reduce cardinality."""
    import re
    # Replace UUIDs, numeric IDs, etc.
    path = re.sub(r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "/<id>", path)
    path = re.sub(r"/\d+", "/<id>", path)
    return path


def init_metrics(app: Flask, engine: "SimulationEngine") -> None:
    """Register /metrics endpoint and HTTP instrumentation hooks on *app*.

    Also attempts to configure OpenTelemetry tracing if the SDK is available.

    Args:
        app: The Flask application instance.
        engine: The running SimulationEngine whose stats are exported.
    """
    if not _PROM_AVAILABLE:
        logger.warning("prometheus_client unavailable; skipping metrics init")
        _register_stub_endpoint(app)
        return

    _create_metrics()

    # --- HTTP instrumentation via before/after request hooks ---
    @app.before_request
    def _before() -> None:
        request._metrics_start = time.perf_counter()  # type: ignore[attr-defined]
        if http_requests_in_flight is not None:
            http_requests_in_flight.inc()

    @app.after_request
    def _after(response: Response) -> Response:
        start: float = getattr(request, "_metrics_start", None)  # type: ignore[arg-type]
        if start is not None and http_request_duration_seconds is not None:
            duration = time.perf_counter() - start
            endpoint = _normalize_endpoint(request.path)
            http_request_duration_seconds.labels(
                method=request.method, endpoint=endpoint
            ).observe(duration)
        if http_requests_in_flight is not None:
            http_requests_in_flight.dec()
        if http_requests_total is not None:
            endpoint = _normalize_endpoint(request.path)
            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status=str(response.status_code),
            ).inc()
        return response

    # --- /metrics scrape endpoint ---
    @app.route("/metrics")
    def metrics_endpoint() -> Response:
        """Return Prometheus text exposition format metrics."""
        update_simulation_metrics(engine)
        data = generate_latest(REGISTRY)
        return Response(data, status=200, mimetype=CONTENT_TYPE_LATEST)

    # --- OpenTelemetry tracing (optional) ---
    _init_otel(app)

    logger.info("Prometheus metrics endpoint registered at /metrics")


def _register_stub_endpoint(app: Flask) -> None:
    """Register a /metrics endpoint that returns 501 when prometheus_client is absent."""

    @app.route("/metrics")
    def metrics_stub() -> Response:  # pragma: no cover
        return Response(
            "# prometheus_client not installed\n",
            status=501,
            mimetype="text/plain",
        )


def _init_otel(app: Flask) -> None:
    """Attempt to configure OpenTelemetry Flask instrumentation."""
    if not _OTEL_AVAILABLE:
        return

    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "smartnode")

    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if otel_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )
                exporter = OTLPSpanExporter(endpoint=otel_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OTel OTLP exporter configured: %s", otel_endpoint)
            except ImportError:
                logger.warning("otlp grpc exporter not installed; traces will not be exported")

        trace.set_tracer_provider(provider)
        FlaskInstrumentor().instrument_app(app)
        logger.info("OpenTelemetry Flask instrumentation enabled (service=%s)", service_name)
    except Exception as exc:
        logger.warning("OTel init failed (non-fatal): %s", exc)
