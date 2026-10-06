import logging
from typing import Optional
import redis.asyncio as aioredis
from core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> Optional[aioredis.Redis]:
    """Returns an async Redis client instance if REDIS_URL is configured and reachable."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.ping()
            return _redis_client
        except Exception:
            _redis_client = None

    if settings.REDIS_URL:
        try:
            client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )
            await client.ping()
            _redis_client = client
            return _redis_client
        except Exception as exc:
            logger.debug(f"Redis not reachable at {settings.REDIS_URL}: {exc}")
            _redis_client = None
            return None

    return None


async def close_redis() -> None:
    """Gracefully closes Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None


class RedisWrapper:
    """Convenience async wrapper around Redis client with graceful no-op fallback."""

    @property
    def is_available(self) -> bool:
        return bool(settings.REDIS_URL)

    async def get(self, key: str) -> Optional[str]:
        client = await get_redis()
        if client:
            try:
                return await client.get(key)
            except Exception:
                return None
        return None

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        client = await get_redis()
        if client:
            try:
                await client.set(key, value, ex=ex)
                return True
            except Exception:
                return False
        return False

    async def delete(self, key: str) -> bool:
        client = await get_redis()
        if client:
            try:
                await client.delete(key)
                return True
            except Exception:
                return False
        return False


redis_client = RedisWrapper()
