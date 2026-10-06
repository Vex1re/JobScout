import pytest
from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from core.sentry import filter_pii, _before_send, setup_sentry, capture_exception
from core.health import check_health
from core.metrics import (
    record_vacancy_ingested,
    record_parser_error,
    record_search_latency,
    record_notification_sent,
    set_active_users,
    create_monitoring_app
)
from prometheus_client import generate_latest, REGISTRY


def test_pii_filtering_redaction():
    text = "Candidate Ivan ivan@example.com phone +7 (999) 123-45-67 token 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ1234567"
    sanitized = filter_pii(text)
    assert "ivan@example.com" not in sanitized
    assert "[EMAIL_REDACTED]" in sanitized
    assert "+7 (999) 123-45-67" not in sanitized
    assert "[PHONE_REDACTED]" in sanitized
    assert "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ1234567" not in sanitized
    assert "[TOKEN_REDACTED]" in sanitized


def test_sentry_before_send_strips_pii():
    event = {
        "message": "Error processing user with email candidate@test.com",
        "exception": {
            "values": [
                {"value": "Failed for phone 89991234567"}
            ]
        },
        "breadcrumbs": {
            "values": [
                {"message": "Action token 987654321:abcdefghijklmnopqrstuvwxyz123456789"}
            ]
        },
        "extra": {
            "contact": "boss@company.org"
        }
    }
    sanitized_event = _before_send(event, {})
    assert "[EMAIL_REDACTED]" in sanitized_event["message"]
    assert "[PHONE_REDACTED]" in sanitized_event["exception"]["values"][0]["value"]
    assert "[TOKEN_REDACTED]" in sanitized_event["breadcrumbs"]["values"][0]["message"]
    assert "[EMAIL_REDACTED]" in sanitized_event["extra"]["contact"]


def test_sentry_disabled_by_default():
    # In tests without SENTRY_DSN, setup_sentry returns False
    assert setup_sentry() is False
    # capture_exception should safely no-op
    capture_exception(RuntimeError("Test non-fatal error"))


@pytest.mark.asyncio
async def test_health_check_subsystems():
    code, data = await check_health()
    assert code == 200
    assert data["status"] in ["ok", "degraded"]
    assert data["database"] == "connected"
    assert "uptime_seconds" in data
    assert data["version"] == "1.0.0"


def test_prometheus_metrics_registry():
    # Record some metrics
    record_vacancy_ingested("hh", 10)
    record_parser_error("habr", "TimeoutException")
    record_search_latency(0.125)
    record_notification_sent("telegram", 5)
    set_active_users(42)

    raw_metrics = generate_latest(REGISTRY).decode("utf-8")
    assert "jobscout_vacancies_ingested_total" in raw_metrics
    assert 'source="hh"' in raw_metrics
    assert "jobscout_parser_errors_total" in raw_metrics
    assert 'source="habr"' in raw_metrics
    assert "jobscout_search_latency_seconds" in raw_metrics
    assert "jobscout_notifications_sent_total" in raw_metrics
    assert "jobscout_active_users_total 42.0" in raw_metrics


@pytest.mark.asyncio
async def test_monitoring_http_routes():
    app = create_monitoring_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    # Test /healthz
    resp_health = await client.get("/healthz")
    assert resp_health.status == 200
    json_health = await resp_health.json()
    assert json_health["database"] == "connected"

    # Test /metrics
    resp_metrics = await client.get("/metrics")
    assert resp_metrics.status == 200
    text_metrics = await resp_metrics.text()
    assert "jobscout_" in text_metrics

    await client.close()
