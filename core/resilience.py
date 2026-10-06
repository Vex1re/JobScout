import asyncio
import datetime
import json
import logging
import random
import time
from typing import Dict, Any, Optional, List
from core.config import settings
from core.redis import redis_client

logger = logging.getLogger(__name__)

USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"
]

DEFAULT_SOURCE_RPS: Dict[str, float] = {
    "hh": 5.0,
    "trudvsem": 2.0,
    "superjob": 5.0,
    "habr": 3.0,
    "remoteok": 2.0,
    "rabota": 3.0,
    "kwork": 3.0,
    "fl_ru": 2.0,
    "freelance_ru": 3.0,
    "freelancehunt": 2.0
}


class TokenBucket:
    """Asynchronous token bucket rate limiter for external parser requests."""

    def __init__(self, rate: float = 3.0, capacity: float = 5.0):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_updated
            self.last_updated = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens < 1.0:
                sleep_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(sleep_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class CircuitBreaker:
    """
    Circuit breaker per aggregator source.
    Transitions:
    - OK (Closed): normal operation
    - DOWN (Open): 5+ consecutive errors -> blocked for reset timeout (15 min)
    - DEGRADED: sporadic errors, recovering
    Persists source health state to Redis (or in-memory fallback).
    """

    def __init__(
        self,
        max_failures: int = settings.CIRCUIT_BREAKER_MAX_FAILURES,
        reset_timeout: int = settings.CIRCUIT_BREAKER_RESET_TIMEOUT
    ):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self._memory_state: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _get_key(self, source: str) -> str:
        return f"source_health:{source}"

    async def get_health(self, source: str) -> Dict[str, Any]:
        """Returns health record: {status, consecutive_errors, error_count, last_success, open_until}."""
        if redis_client.is_available:
            try:
                data = await redis_client.get(self._get_key(source))
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.warning(f"Failed to read source_health from Redis for {source}: {e}")

        async with self._lock:
            return self._memory_state.get(source, {
                "status": "ok",
                "consecutive_errors": 0,
                "error_count": 0,
                "last_success": time.time(),
                "open_until": 0
            })

    async def can_execute(self, source: str) -> bool:
        """Checks if requests to source are allowed by circuit breaker."""
        health = await self.get_health(source)
        if health.get("status") == "down":
            open_until = health.get("open_until", 0)
            now = time.time()
            if now < open_until:
                remaining = int(open_until - now)
                logger.warning(f"Circuit breaker OPEN for source '{source}': cooling down for {remaining}s")
                return False
            # Timeout expired -> attempt recovery
            health["status"] = "degraded"
            await self._save_health(source, health)
            logger.info(f"Circuit breaker half-open for source '{source}': probing recovery")
        return True

    async def record_success(self, source: str) -> None:
        """Records a successful request, resetting consecutive errors."""
        health = await self.get_health(source)
        health["status"] = "ok"
        health["consecutive_errors"] = 0
        health["last_success"] = time.time()
        health["open_until"] = 0
        await self._save_health(source, health)

    async def record_failure(self, source: str, error_msg: str = "") -> None:
        """Records an error. Opens circuit if threshold reached."""
        health = await self.get_health(source)
        health["consecutive_errors"] = health.get("consecutive_errors", 0) + 1
        health["error_count"] = health.get("error_count", 0) + 1
        health["last_error"] = error_msg
        health["last_error_time"] = time.time()

        if health["consecutive_errors"] >= self.max_failures:
            health["status"] = "down"
            health["open_until"] = time.time() + self.reset_timeout
            logger.warning(
                f"Source '{source}' failed {health['consecutive_errors']} times in a row. "
                f"Circuit breaker OPEN for {self.reset_timeout}s! Error: {error_msg}"
            )
        else:
            health["status"] = "degraded"
            logger.info(
                f"Source '{source}' recorded failure ({health['consecutive_errors']}/{self.max_failures}). "
                f"Error: {error_msg}"
            )

        await self._save_health(source, health)

    async def _save_health(self, source: str, data: Dict[str, Any]) -> None:
        async with self._lock:
            self._memory_state[source] = dict(data)

        if redis_client.is_available:
            try:
                await redis_client.set(
                    self._get_key(source),
                    json.dumps(data),
                    ex=self.reset_timeout * 2
                )
            except Exception as e:
                logger.warning(f"Failed to persist source_health to Redis for {source}: {e}")


class ResilienceManager:
    """Central manager for per-source rate limiters, circuit breakers, and network rotation."""

    def __init__(self):
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiters: Dict[str, TokenBucket] = {
            src: TokenBucket(rate=rps, capacity=rps * 2)
            for src, rps in DEFAULT_SOURCE_RPS.items()
        }

    def get_token_bucket(self, source: str) -> TokenBucket:
        if source not in self.rate_limiters:
            self.rate_limiters[source] = TokenBucket(rate=3.0, capacity=6.0)
        return self.rate_limiters[source]

    def get_user_agent(self) -> str:
        return random.choice(USER_AGENTS)

    def get_proxy(self) -> Optional[str]:
        if settings.PROXIES and len(settings.PROXIES) > 0:
            return random.choice(settings.PROXIES)
        return settings.PROXY_URL


resilience_manager = ResilienceManager()
