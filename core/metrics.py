import logging
from typing import Optional
from aiohttp import web
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    REGISTRY
)

from core.health import check_health

logger = logging.getLogger(__name__)

# Prometheus Metrics Definitions
VACANCIES_INGESTED_TOTAL = Counter(
    "jobscout_vacancies_ingested_total",
    "Total vacancies ingested by crawler/parsers",
    ["source"]
)

PARSER_ERRORS_TOTAL = Counter(
    "jobscout_parser_errors_total",
    "Total aggregator scraping/parsing errors",
    ["source", "error_type"]
)

SEARCH_LATENCY_SECONDS = Histogram(
    "jobscout_search_latency_seconds",
    "Search execution latency in seconds",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

NOTIFICATIONS_SENT_TOTAL = Counter(
    "jobscout_notifications_sent_total",
    "Total notification messages dispatched to users",
    ["channel"]
)

ACTIVE_USERS_TOTAL = Gauge(
    "jobscout_active_users_total",
    "Total active bot users registered"
)


# Helper functions to instrument code
def record_vacancy_ingested(source: str, count: int = 1) -> None:
    VACANCIES_INGESTED_TOTAL.labels(source=source).inc(count)


def record_parser_error(source: str, error_type: str) -> None:
    PARSER_ERRORS_TOTAL.labels(source=source, error_type=error_type).inc()


def record_search_latency(duration_seconds: float) -> None:
    SEARCH_LATENCY_SECONDS.observe(duration_seconds)


def record_notification_sent(channel: str = "telegram", count: int = 1) -> None:
    NOTIFICATIONS_SENT_TOTAL.labels(channel=channel).inc(count)


def set_active_users(count: int) -> None:
    ACTIVE_USERS_TOTAL.set(count)


# aiohttp HTTP Handlers for Prometheus & Healthcheck
async def metrics_handler(request: web.Request) -> web.Response:
    """Returns Prometheus text format metrics."""
    data = generate_latest(REGISTRY)
    return web.Response(body=data, content_type="text/plain", charset="utf-8")


async def healthz_handler(request: web.Request) -> web.Response:
    """Returns system health status for Kubernetes / Docker compose."""
    http_code, health_data = await check_health()
    return web.json_response(health_data, status=http_code)


def create_monitoring_app() -> web.Application:
    """Creates a lightweight aiohttp application with /metrics and /healthz routes."""
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/healthz", healthz_handler)
    return app


async def start_monitoring_server(host: str = "0.0.0.0", port: int = 9090) -> web.AppRunner:
    """Starts standalone monitoring HTTP server in background."""
    app = create_monitoring_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Monitoring server listening on http://%s:%d/metrics and /healthz", host, port)
    return runner
