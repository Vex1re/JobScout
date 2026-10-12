import pytest
import datetime
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from aiogram.types import CallbackQuery, Message, User as TgUser

from core.database.models import Base, User, Vacancy, Resume, Subscription, JobApplicationTracker
from core.database.repository import SubscriptionRepository, TrackerRepository, ResumeRepository
from services.payment.stars import TelegramStarsProvider
from services.payment.yookassa import YooKassaProvider
from services.payment.cryptobot import CryptoBotProvider
from bot.handlers.tracker import on_ai_cover_letter, on_ai_gap_analysis, on_track_vacancy, show_tracker
from bot.handlers.premium import cmd_premium


@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        user = User(telegram_id=777888999, username="test_stars_user")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session, user

    await engine.dispose()


@pytest.mark.asyncio
async def test_subscription_and_entitlements(async_db):
    session, user = async_db

    # Initially has no active subscription
    assert await SubscriptionRepository.has_active_subscription(session, user.telegram_id) is False
    assert await SubscriptionRepository.has_entitlement(session, user.telegram_id, "ai_cover_letter") is False

    # Activate Pro subscription
    sub = await SubscriptionRepository.create_or_update_subscription(
        session=session,
        user_id=user.telegram_id,
        plan="pro",
        duration_days=30
    )

    assert sub.plan == "pro"
    assert sub.is_active is True
    assert await SubscriptionRepository.has_active_subscription(session, user.telegram_id) is True
    assert await SubscriptionRepository.has_entitlement(session, user.telegram_id, "ai_cover_letter") is True
    assert await SubscriptionRepository.has_entitlement(session, user.telegram_id, "kanban_tracker") is True
    assert await SubscriptionRepository.has_entitlement(session, user.telegram_id, "team_analytics") is False


@pytest.mark.asyncio
async def test_subscription_expiration(async_db):
    session, user = async_db

    # Create expired subscription
    sub = await SubscriptionRepository.create_or_update_subscription(
        session=session,
        user_id=user.telegram_id,
        plan="pro",
        duration_days=30
    )
    # Manually backdate expiration
    sub.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    await session.commit()

    assert await SubscriptionRepository.has_active_subscription(session, user.telegram_id) is False
    assert await SubscriptionRepository.has_entitlement(session, user.telegram_id, "ai_cover_letter") is False


@pytest.mark.asyncio
async def test_telegram_stars_provider_flow(async_db):
    session, user = async_db
    provider = TelegramStarsProvider()

    # 1. Generate invoice payload
    invoice = await provider.create_invoice_payload(user.telegram_id, "pro")
    assert invoice["currency"] == "XTR"
    assert invoice["provider_token"] == ""
    assert invoice["prices"][0]["amount"] == 150
    assert invoice["payload"].startswith("sub:pro:")

    # 2. Confirm payment
    res = await provider.confirm_payment(
        session=session,
        user_id=user.telegram_id,
        payload=invoice["payload"],
        amount=150
    )
    assert res["success"] is True
    assert res["plan"] == "pro"

    # Verify DB state
    has_active = await SubscriptionRepository.has_active_subscription(session, user.telegram_id)
    assert has_active is True


def test_payment_provider_feature_flags():
    # YooKassa should raise error when disabled
    yk = YooKassaProvider()
    with pytest.raises(RuntimeError) as exc_info:
        yk._ensure_enabled()
    assert "YooKassa provider is currently disabled" in str(exc_info.value)

    # CryptoBot should raise error when disabled
    cb = CryptoBotProvider()
    with pytest.raises(RuntimeError) as exc_info_cb:
        cb._ensure_enabled()
    assert "CryptoBot provider is currently disabled" in str(exc_info_cb.value)


@pytest.mark.asyncio
async def test_job_application_tracker_crud(async_db):
    session, user = async_db

    # 1. Create application
    app = await TrackerRepository.create_or_update_application(
        session=session,
        user_id=user.telegram_id,
        title="Senior Python Engineer",
        company="Global FinTech",
        url="https://hh.ru/vacancy/112233",
        vacancy_id="hh_112233",
        vacancy_canonical_id="can_hh_112233",
        status="applied",
        notes="Sent resume via HH"
    )
    assert app.id is not None
    assert app.status == "applied"

    # 2. Query applications
    apps = await TrackerRepository.get_user_applications(session, user.telegram_id)
    assert len(apps) == 1
    assert apps[0].company == "Global FinTech"

    # 3. Update status (e.g. moved to interview)
    updated = await TrackerRepository.update_status(session, app.id, user.telegram_id, "interview")
    assert updated is not None
    assert updated.status == "interview"

    # Query filtered by status
    interview_apps = await TrackerRepository.get_user_applications(session, user.telegram_id, status="interview")
    assert len(interview_apps) == 1
    assert interview_apps[0].id == app.id

    # 4. Delete application
    deleted = await TrackerRepository.delete_application(session, app.id, user.telegram_id)
    assert deleted is True

    apps_after = await TrackerRepository.get_user_applications(session, user.telegram_id)
    assert len(apps_after) == 0


@pytest.mark.asyncio
async def test_ai_handlers_free_and_pro(async_db):
    session, user = async_db

    # Create dummy vacancy
    vac = Vacancy(
        id="test_vac_123",
        source="hh",
        title="Senior Python Backend Developer",
        company="TechCorp",
        url="https://hh.ru/vacancy/test_vac_123",
        description="Требуется опытный разработчик со знанием Python, FastAPI, Docker, PostgreSQL.",
        skills=["Python", "FastAPI", "Docker", "PostgreSQL", "Kubernetes"]
    )
    session.add(vac)
    await session.commit()

    # Create dummy resume
    await ResumeRepository.save_or_update_resume(
        session=session,
        user_id=user.telegram_id,
        title="Python Backend Engineer",
        grade="Middle",
        years_of_experience=3.0,
        skills=["Python", "FastAPI", "Docker"],
        raw_text="Python Backend Engineer, 3 years experience. Stack: Python, FastAPI, Docker."
    )

    # 1. Test CallbackQuery for Free user (missing PRO entitlement)
    cb_msg = MagicMock(spec=Message)
    cb_msg.answer = AsyncMock()

    cb_letter = MagicMock(spec=CallbackQuery)
    cb_letter.data = "ai_letter:test_vac_123"
    cb_letter.from_user = TgUser(id=user.telegram_id, is_bot=False, first_name="Tester")
    cb_letter.answer = AsyncMock()
    cb_letter.message = cb_msg

    # Call handler WITHOUT 'user' kwarg (simulating aiogram invocation)
    await on_ai_cover_letter(cb_letter, session)
    assert cb_letter.answer.called
    assert "PRO" in cb_letter.answer.call_args[0][0]

    cb_gap = MagicMock(spec=CallbackQuery)
    cb_gap.data = "ai_gap:test_vac_123"
    cb_gap.from_user = TgUser(id=user.telegram_id, is_bot=False, first_name="Tester")
    cb_gap.answer = AsyncMock()
    cb_gap.message = cb_msg

    await on_ai_gap_analysis(cb_gap, session)
    assert cb_gap.answer.called
    assert "PRO" in cb_gap.answer.call_args[0][0]

    # 2. Grant PRO subscription
    await SubscriptionRepository.create_or_update_subscription(
        session=session,
        user_id=user.telegram_id,
        plan="pro",
        duration_days=30
    )

    # Call AI letter again
    cb_letter.answer.reset_mock()
    cb_msg.answer.reset_mock()
    await on_ai_cover_letter(cb_letter, session)
    assert cb_msg.answer.called
    assert "Сопроводительное письмо" in cb_msg.answer.call_args[0][0]

    # Call AI gap analysis again
    cb_gap.answer.reset_mock()
    cb_msg.answer.reset_mock()
    await on_ai_gap_analysis(cb_gap, session)
    assert cb_msg.answer.called
    assert "Gap-анализ" in cb_msg.answer.call_args[0][0]

    # 3. Test on_track_vacancy
    cb_track = MagicMock(spec=CallbackQuery)
    cb_track.data = "track_vac:test_vac_123"
    cb_track.from_user = TgUser(id=user.telegram_id, is_bot=False, first_name="Tester")
    cb_track.answer = AsyncMock()
    await on_track_vacancy(cb_track, session)
    assert cb_track.answer.called
    assert "трекер" in cb_track.answer.call_args[0][0].lower()

    # 4. Test show_tracker and cmd_premium
    msg = MagicMock(spec=Message)
    msg.from_user = TgUser(id=user.telegram_id, is_bot=False, first_name="Tester")
    msg.answer = AsyncMock()

    await show_tracker(msg, session)
    assert msg.answer.called

    await cmd_premium(msg, session)
    assert msg.answer.called
