import pytest
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError
from core.telegram_limiter import TelegramRateLimiter, send_telegram_message_safe
from workers.tasks.notifier import format_digest_message, get_digest_keyboard
from core.database.models import Vacancy


@pytest.mark.asyncio
async def test_telegram_rate_limiter():
    limiter = TelegramRateLimiter(global_rps=50.0, per_chat_rps=20.0)
    # Ensure acquire works without hanging
    for _ in range(5):
        await limiter.acquire(chat_id=123456)


@pytest.mark.asyncio
async def test_send_telegram_message_safe_retry_after():
    bot = AsyncMock()
    # First call raises TelegramRetryAfter(method=..., message=..., retry_after=1)
    retry_exc = TelegramRetryAfter(
        method=AsyncMock(),
        message="Flood control exceeded",
        retry_after=0.05
    )

    bot.send_message.side_effect = [retry_exc, AsyncMock()]

    success = await send_telegram_message_safe(
        bot=bot,
        chat_id=999888,
        text="Test Alert",
        max_retries=2
    )

    assert success is True
    assert bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_send_telegram_message_safe_forbidden():
    bot = AsyncMock()
    bot.send_message.side_effect = TelegramForbiddenError(
        method=AsyncMock(),
        message="Bot was blocked by user"
    )

    success = await send_telegram_message_safe(
        bot=bot,
        chat_id=999888,
        text="Test Alert"
    )

    assert success is False
    assert bot.send_message.call_count == 1


def test_format_digest_message():
    vac1 = Vacancy(
        id="hh_1",
        source="hh",
        title="Backend Developer",
        company="Tech Alpha",
        url="https://hh.ru/1",
        salary_min=150000,
        salary_max=200000,
        currency="RUB",
        is_remote=True
    )
    vac2 = Vacancy(
        id="habr_2",
        source="habr",
        title="Frontend Developer",
        company="Design Beta",
        url="https://habr.com/2",
        salary_min=120000,
        currency="RUB",
        is_remote=False,
        city="Москва"
    )

    matches = [
        (vac1, {"score": 85, "matched_skills": ["Python", "FastAPI"]}),
        (vac2, {"score": 75, "matched_skills": ["Vue", "TypeScript"]}),
    ]

    text = format_digest_message(matches)
    assert "Дайджест новых вакансий (найдено: 2)" in text
    assert "Backend Developer" in text
    assert "Frontend Developer" in text
    assert "Tech Alpha" in text
    assert "Design Beta" in text
    assert "85%" in text
    assert "75%" in text

    kb = get_digest_keyboard(matches)
    assert len(kb.inline_keyboard) == 3  # 2 vacancy link rows + 1 search button row
