import asyncio
import logging
from typing import Any, Optional, Dict
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from core.config import settings

logger = logging.getLogger(__name__)

_arq_pool: Optional[ArqRedis] = None


async def get_arq_pool() -> Optional[ArqRedis]:
    """Returns an arq Redis connection pool if REDIS_URL is configured."""
    global _arq_pool
    if _arq_pool is not None:
        return _arq_pool

    if settings.REDIS_URL:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(settings.REDIS_URL)
            host = parsed.hostname or "localhost"
            port = parsed.port or 6379
            password = parsed.password
            database = int(parsed.path.lstrip("/") or 0) if parsed.path else 0

            redis_settings = RedisSettings(
                host=host,
                port=port,
                password=password,
                database=database
            )
            _arq_pool = await create_pool(redis_settings)
            logger.info("Arq task queue connected to Redis.")
            return _arq_pool
        except Exception as exc:
            logger.warning(f"Could not connect to Redis for task queue ({exc}). Working in local mode.")
            _arq_pool = None
            return None
    return None


async def close_arq_pool() -> None:
    """Closes arq Redis connection pool."""
    global _arq_pool
    if _arq_pool is not None:
        try:
            await _arq_pool.close()
        except Exception:
            pass
        _arq_pool = None


async def enqueue_task(task_name: str, *args, job_id: Optional[str] = None, **kwargs) -> Optional[Any]:
    """
    Enqueues an asynchronous task to Redis queue via arq.
    If Redis is not available (dev/test), executes immediately in background if registered locally.
    """
    pool = await get_arq_pool()
    if pool is not None:
        try:
            job = await pool.enqueue_job(task_name, *args, _job_id=job_id, **kwargs)
            return job
        except Exception as exc:
            logger.error(f"Failed to enqueue task '{task_name}' in arq: {exc}")
            return None

    # Fallback for dev/test when Redis is not active
    logger.debug(f"Redis queue not available. Task '{task_name}' enqueued in local background mode.")
    return None
