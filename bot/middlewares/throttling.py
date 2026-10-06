import time
import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from core.config import settings
from core.redis import get_redis

logger = logging.getLogger(__name__)

LUA_THROTTLE = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class ThrottlingMiddleware(BaseMiddleware):
    """
    Rate-limiter middleware preventing Telegram API 429 flood errors
    and user button/command spamming.
    Uses Redis atomically in production and falls back to in-memory dictionary in dev.
    """

    def __init__(self, rate_limit: float = None):
        self.rate_limit = rate_limit if rate_limit is not None else settings.THROTTLE_RATE_LIMIT
        self.last_actions: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id

        if user_id:
            is_throttled = False
            used_redis = False

            try:
                redis_conn = await get_redis()
                if redis_conn is not None:
                    used_redis = True
                    key = f"throttle:{user_id}"
                    count = await redis_conn.eval(LUA_THROTTLE, 1, key, int(self.rate_limit * 1000))
                    if count > 1:
                        is_throttled = True
            except Exception as e:
                logger.debug(f"Redis throttling check failed ({e}), using in-memory fallback.")
                used_redis = False

            if not used_redis:
                now = time.time()
                last_time = self.last_actions.get(user_id, 0.0)

                # Evict stale entries when the cache grows
                if len(self.last_actions) > 3000:
                    cutoff = now - 30.0
                    self.last_actions = {u: t for u, t in self.last_actions.items() if t > cutoff}

                if (now - last_time) < self.rate_limit:
                    is_throttled = True
                else:
                    self.last_actions[user_id] = now

            if is_throttled:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("⏳ Секунду, обрабатываю предыдущий запрос...", show_alert=False)
                    except Exception:
                        pass
                return None

        return await handler(event, data)
