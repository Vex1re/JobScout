import logging
from urllib.parse import urlparse
from arq.connections import RedisSettings
from core.config import settings
from workers.tasks.alerts import process_user_alert

logger = logging.getLogger(__name__)


async def startup(ctx):
    logger.info("JobScout Arq worker started.")


async def shutdown(ctx):
    logger.info("JobScout Arq worker shutting down.")


def get_redis_settings() -> RedisSettings:
    if settings.REDIS_URL:
        try:
            parsed = urlparse(settings.REDIS_URL)
            return RedisSettings(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                password=parsed.password,
                database=int(parsed.path.lstrip("/") or 0) if parsed.path else 0
            )
        except Exception:
            pass
    return RedisSettings(host="localhost", port=6379)


class WorkerSettings:
    """arq worker configuration settings."""
    functions = [process_user_alert]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 300
    max_tries = 3


if __name__ == "__main__":
    import asyncio
    from arq import run_worker
    asyncio.run(run_worker(WorkerSettings))
