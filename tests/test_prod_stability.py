import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.types import Message, CallbackQuery, User as TgUser
from aiogram.exceptions import TelegramForbiddenError

from bot.middlewares.throttling import ThrottlingMiddleware
from bot.handlers.vacancies import SearchResultsCache
from core.database.session import async_session_factory, init_db
from core.database.models import User, Resume
from core.database.repository import UserRepository, ResumeRepository
from core.scheduler import run_periodic_alerts


@pytest.mark.asyncio
async def test_throttling_middleware_limits_rapid_calls():
    middleware = ThrottlingMiddleware(rate_limit=0.5)

    handler = AsyncMock(return_value="OK")
    user = TgUser(id=123456, is_bot=False, first_name="Test")

    msg1 = MagicMock(spec=Message)
    msg1.from_user = user

    # First call: should pass
    res1 = await middleware(handler, msg1, {})
    assert res1 == "OK"
    assert handler.call_count == 1

    # Immediate second call (< 0.5s): should be throttled and return None
    res2 = await middleware(handler, msg1, {})
    assert res2 is None
    assert handler.call_count == 1

    # Wait for rate limit window to pass
    await asyncio.sleep(0.55)

    # Third call: should pass again
    res3 = await middleware(handler, msg1, {})
    assert res3 == "OK"
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_throttling_middleware_callback_alert():
    middleware = ThrottlingMiddleware(rate_limit=0.5)
    handler = AsyncMock(return_value="OK")
    user = TgUser(id=999888, is_bot=False, first_name="Test")

    cb = MagicMock(spec=CallbackQuery)
    cb.from_user = user
    cb.answer = AsyncMock()

    # Call 1: passes
    await middleware(handler, cb, {})

    # Call 2: throttled with cb.answer alert
    await middleware(handler, cb, {})
    cb.answer.assert_called_once()
    assert "секунду" in cb.answer.call_args[0][0].lower()


def test_search_results_cache_ttl_and_eviction():
    cache = SearchResultsCache(ttl_seconds=0.2, max_users=2)

    cache[101] = [("vac1", {})]
    cache[102] = [("vac2", {})]
    assert len(cache) == 2

    # Overfill: adding 103 should evict oldest (101)
    cache[103] = [("vac3", {})]
    assert 103 in cache
    assert 102 in cache
    assert 101 not in cache

    # TTL expiration test
    time.sleep(0.25)
    assert cache.get(103) is None
    assert len(cache) == 0


@pytest.mark.asyncio
async def test_delete_user_all_data_gdpr_compliance():
    await init_db()
    test_id = 555444333

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(session, telegram_id=test_id, first_name="DeleteMe")
        await ResumeRepository.save_or_update_resume(
            session=session,
            user_id=test_id,
            title="Тестовый специалист",
            grade="Middle",
            years_of_experience=2.0,
            skills=["Excel", "1С"],
            raw_text="Тестовое резюме"
        )

        # Check exists
        saved_resume = await ResumeRepository.get_resume(session, test_id)
        assert saved_resume is not None

        # Delete all data
        deleted = await UserRepository.delete_user_all_data(session, telegram_id=test_id)
        assert deleted is True

        # Check both user and resume are purged
        purged_resume = await ResumeRepository.get_resume(session, test_id)
        assert purged_resume is None


@pytest.mark.asyncio
async def test_scheduler_deactivates_blocked_users():
    await init_db()
    blocked_id = 999111222

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(session, telegram_id=blocked_id, first_name="BlockedUser")
        user.auto_notify = True
        user.is_active = True
        await ResumeRepository.save_or_update_resume(
            session=session,
            user_id=blocked_id,
            title="Python Developer",
            grade="Middle",
            years_of_experience=2.0,
            skills=["Python"],
            raw_text="Python dev"
        )
        await session.commit()

    # Mock bot that throws TelegramForbiddenError when trying to message blocked_id
    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = TelegramForbiddenError(
        method="sendMessage",
        message="Forbidden: bot was blocked by the user"
    )

    from core.database.models import Vacancy
    fake_vac = Vacancy(
        id="alert_test_vac_1",
        source="hh",
        title="Python Dev",
        company="Co",
        url="https://hh.ru",
        risk_level="safe",
        description="Test Python Vacancy"
    )

    from unittest.mock import patch
    with patch("core.scheduler.aggregator_manager.search_and_match_for_user", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [
            (fake_vac, {"score": 85, "matched_skills": ["Python"], "missing_skills": []})
        ]
        await run_periodic_alerts(mock_bot)

    async with async_session_factory() as session:
        user_after = await UserRepository.get_or_create_user(session, telegram_id=blocked_id)
        assert user_after.is_active is False
