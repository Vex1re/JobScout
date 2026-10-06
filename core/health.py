import time
import logging
from typing import Dict, Any, Tuple
from sqlalchemy import text

from core.config import settings
from core.database.session import async_session

logger = logging.getLogger(__name__)

_START_TIME = time.time()


async def check_health() -> Tuple[int, Dict[str, Any]]:
    """
    Checks health of critical subsystems: database and Redis.
    Returns (http_status_code, response_data).
    """
    db_status = "unknown"
    redis_status = "disabled"
    is_healthy = True

    # 1. Database check
    try:
        async with async_session() as session:
            res = await session.execute(text("SELECT 1"))
            val = res.scalar()
            if val == 1:
                db_status = "connected"
            else:
                db_status = "unexpected_result"
                is_healthy = False
    except Exception as exc:
        db_status = f"error: {str(exc)}"
        is_healthy = False
        logger.error("Health check DB failure: %s", exc)

    # 2. Redis check
    if settings.REDIS_URL:
        try:
            from redis.asyncio import from_url
            r = from_url(settings.REDIS_URL, decode_responses=True)
            pong = await r.ping()
            await r.aclose()
            if pong:
                redis_status = "connected"
            else:
                redis_status = "ping_failed"
                is_healthy = False
        except Exception as exc:
            redis_status = f"error: {str(exc)}"
            # If prod, redis failure degrades health
            if settings.ENV == "prod":
                is_healthy = False
            logger.warning("Health check Redis failure: %s", exc)
    else:
        redis_status = "disabled (in-memory mode)"

    uptime = round(time.time() - _START_TIME, 2)
    overall_status = "ok" if is_healthy else ("degraded" if db_status == "connected" else "error")
    http_code = 200 if is_healthy else (200 if overall_status == "degraded" else 503)

    return http_code, {
        "status": overall_status,
        "database": db_status,
        "redis": redis_status,
        "environment": settings.ENV,
        "uptime_seconds": uptime,
        "version": "1.0.0"
    }
