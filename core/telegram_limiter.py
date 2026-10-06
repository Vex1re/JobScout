import asyncio
import logging
import time
from typing import Dict, Optional, Any
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramBadRequest
from core.resilience import TokenBucket

logger = logging.getLogger(__name__)


class TelegramRateLimiter:
    """
    Enforces Telegram API rate limits:
    - Global limit: 25 requests per second
    - Per-chat limit: 1 request per second
    """

    def __init__(self, global_rps: float = 25.0, per_chat_rps: float = 1.0):
        self.global_limiter = TokenBucket(rate=global_rps, capacity=30.0)
        self.per_chat_limiters: Dict[int, TokenBucket] = {}
        self.per_chat_rps = per_chat_rps
        self._lock = asyncio.Lock()

    async def acquire(self, chat_id: int) -> None:
        """Acquires tokens from global bucket and per-chat bucket."""
        # 1. Global limit
        await self.global_limiter.acquire()

        # 2. Per-chat limit
        async with self._lock:
            if chat_id not in self.per_chat_limiters:
                self.per_chat_limiters[chat_id] = TokenBucket(
                    rate=self.per_chat_rps,
                    capacity=1.0
                )
            chat_limiter = self.per_chat_limiters[chat_id]

        await chat_limiter.acquire()


telegram_limiter = TelegramRateLimiter()


async def send_telegram_message_safe(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Any = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True,
    max_retries: int = 3
) -> bool:
    """
    Safely sends a message to Telegram with:
    - Token Bucket rate limiting (global + per-chat)
    - Handling of TelegramRetryAfter with sleep and exponential backoff
    - Handling of TelegramForbiddenError / blocked users
    """
    backoff = 1.0

    for attempt in range(1, max_retries + 1):
        try:
            await telegram_limiter.acquire(chat_id)

            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            return True

        except TelegramRetryAfter as e:
            sleep_duration = max(float(getattr(e, "retry_after", 3.0)), 1.0)
            logger.warning(
                f"Telegram rate limit hit for chat {chat_id}! RetryAfter: {sleep_duration}s "
                f"(attempt {attempt}/{max_retries})"
            )
            await asyncio.sleep(sleep_duration + backoff)
            backoff *= 2.0

        except TelegramForbiddenError as e:
            logger.warning(f"Chat {chat_id} has blocked the bot or is deactivated: {e}")
            return False

        except TelegramBadRequest as e:
            logger.warning(f"Bad request while sending to chat {chat_id}: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error sending message to chat {chat_id}: {e}")
            if attempt == max_retries:
                return False
            await asyncio.sleep(backoff)
            backoff *= 2.0

    return False
