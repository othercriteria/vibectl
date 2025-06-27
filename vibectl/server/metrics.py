"""Prometheus metrics helpers for vibectl-server.

This module lazily starts a Prometheus HTTP endpoint (``/metrics``) using
``prometheus_client.start_http_server`` and exposes counters / gauges that
other server components can import and update without worrying about whether
metrics are enabled.

If the metrics endpoint is not started (``init_metrics_server`` never called)
the metrics objects are still valid - they just won't be externally scraped.
"""

from threading import Lock
from typing import Final

from prometheus_client import Counter, Gauge, start_http_server

# ---------------------------------------------------------------------------
# Metric definitions (keep labels minimal to avoid cardinality explosions)
# ---------------------------------------------------------------------------

REQUESTS_TOTAL: Final = Counter(
    "vibectl_requests_total",
    "Total number of requests processed by vibectl-server",
    ["sub"],
)

RATE_LIMITED_TOTAL: Final = Counter(
    "vibectl_rate_limited_total",
    "Total number of requests rejected due to rate limiting",
    ["sub", "limit_type"],
)

CONCURRENT_IN_FLIGHT: Final = Gauge(
    "vibectl_concurrent_in_flight",
    "Current number of in-flight requests handled by vibectl-server",
    ["sub"],
)

# ---------------------------------------------------------------------------
# HTTP exporter management
# ---------------------------------------------------------------------------

_METRICS_STARTED = False
_METRICS_LOCK = Lock()


def init_metrics_server(port: int = 9095) -> None:
    """Start the Prometheus HTTP endpoint on *port* (idempotent).

    Re-invocations are ignored so callers do not need to coordinate.
    """

    global _METRICS_STARTED

    if _METRICS_STARTED:
        return

    with _METRICS_LOCK:
        if _METRICS_STARTED:
            return

        # ``addr`` defaults to 0.0.0.0 so we don't bind to localhost only.
        start_http_server(port)
        _METRICS_STARTED = True
