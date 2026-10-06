import pytest
import respx
import httpx
from core.resilience import CircuitBreaker, TokenBucket, resilience_manager
from services.parser.trudvsem import TrudVsemParser


@pytest.mark.asyncio
async def test_token_bucket_acquire():
    bucket = TokenBucket(rate=100.0, capacity=10.0)
    # Fast acquire without blocking
    for _ in range(5):
        await bucket.acquire()
    assert bucket.tokens >= 0.0


@pytest.mark.asyncio
async def test_circuit_breaker_transitions():
    cb = CircuitBreaker(max_failures=3, reset_timeout=2)
    source = "test_source"

    assert await cb.can_execute(source) is True

    # Record 2 failures -> status should be degraded but still can_execute
    await cb.record_failure(source, "Error 1")
    await cb.record_failure(source, "Error 2")
    assert await cb.can_execute(source) is True
    health = await cb.get_health(source)
    assert health["status"] == "degraded"
    assert health["consecutive_errors"] == 2

    # 3rd failure -> circuit opens (down)
    await cb.record_failure(source, "Error 3")
    assert await cb.can_execute(source) is False
    health = await cb.get_health(source)
    assert health["status"] == "down"

    # After success -> resets
    await cb.record_success(source)
    assert await cb.can_execute(source) is True
    health = await cb.get_health(source)
    assert health["status"] == "ok"
    assert health["consecutive_errors"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_trudvsem_500_resilience():
    # Mock TrudVsem returning 500 Server Error
    respx.get("http://opendata.trudvsem.ru/api/v1/vacancies").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )
    respx.get("https://opendata.trudvsem.ru/api/v1/vacancies").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    parser = TrudVsemParser()
    vacancies = await parser.fetch_vacancies(query="Docker Java", limit=10)

    # Must return empty list gracefully without throwing an exception or crashing the worker
    assert vacancies == []

    # Source health should register failure
    health = await resilience_manager.circuit_breaker.get_health("trudvsem")
    assert health["error_count"] >= 1
