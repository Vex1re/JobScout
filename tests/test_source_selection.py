import pytest
from unittest.mock import AsyncMock, patch

from core.database.models import User, Vacancy
from core.database.repository import UserRepository, VacancyRepository
from core.database.session import init_db, async_session_factory
from services.parser.manager import (
    ALL_SOURCES,
    VACANCY_SOURCES,
    FREELANCE_SOURCES,
    SOURCE_LABELS,
    AggregatorManager
)
from bot.keyboards.inline import get_settings_keyboard, get_sources_settings_keyboard


def test_user_effective_sources_default():
    user = User(telegram_id=12345, enabled_sources=None)
    assert user.get_effective_sources() == ALL_SOURCES

    user_empty = User(telegram_id=12346, enabled_sources=[])
    assert user_empty.get_effective_sources() == ALL_SOURCES


def test_user_effective_sources_custom():
    user = User(telegram_id=12347, enabled_sources=["hh", "habr", "invalid_source"])
    assert user.get_effective_sources() == ["hh", "habr"]


def test_user_effective_sources_habr_freelance_migration():
    user = User(telegram_id=12348, enabled_sources=["hh", "habr_freelance"])
    effective = user.get_effective_sources()
    assert "freelance_ru" in effective
    assert "habr_freelance" not in effective
    assert "hh" in effective


@pytest.mark.asyncio
async def test_user_repository_toggle_source():
    await init_db()

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=777111222,
            username="toggle_tester"
        )
        await UserRepository.set_sources(session, 777111222, ALL_SOURCES)
        await session.refresh(user)

        # Initially all sources are effective (9 sources)
        assert len(user.get_effective_sources()) == 9
        assert "hh" in user.get_effective_sources()

        # Disable 'hh'
        success, current = await UserRepository.toggle_source(
            session=session,
            telegram_id=777111222,
            source_name="hh"
        )
        assert success is True
        assert "hh" not in current
        assert len(current) == 8

        # Toggle 'hh' back on
        success, current = await UserRepository.toggle_source(
            session=session,
            telegram_id=777111222,
            source_name="hh"
        )
        assert success is True
        assert "hh" in current
        assert len(current) == 9

        # Test safety constraint: cannot disable the last remaining source
        await UserRepository.set_sources(
            session=session,
            telegram_id=777111222,
            sources=["kwork"]
        )
        user = await UserRepository.get_or_create_user(session=session, telegram_id=777111222)
        assert user.get_effective_sources() == ["kwork"]

        # Attempt to disable 'kwork' when it's the only one
        success, current = await UserRepository.toggle_source(
            session=session,
            telegram_id=777111222,
            source_name="kwork"
        )
        assert success is False
        assert current == ["kwork"]


@pytest.mark.asyncio
async def test_user_repository_set_sources_presets():
    await init_db()

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=777333444,
            username="preset_tester"
        )

        # Set Vacancies preset
        user = await UserRepository.set_sources(
            session=session,
            telegram_id=777333444,
            sources=VACANCY_SOURCES
        )
        assert user.get_effective_sources() == VACANCY_SOURCES
        assert "kwork" not in user.get_effective_sources()
        assert "hh" in user.get_effective_sources()

        # Set Freelance preset
        user = await UserRepository.set_sources(
            session=session,
            telegram_id=777333444,
            sources=FREELANCE_SOURCES
        )
        assert user.get_effective_sources() == FREELANCE_SOURCES
        assert "hh" not in user.get_effective_sources()
        assert "kwork" in user.get_effective_sources()

        # Set All preset
        user = await UserRepository.set_sources(
            session=session,
            telegram_id=777333444,
            sources=ALL_SOURCES
        )
        assert user.get_effective_sources() == ALL_SOURCES
        assert len(user.get_effective_sources()) == 9


@pytest.mark.asyncio
async def test_vacancy_repository_allowed_sources_filtering():
    await init_db()

    async with async_session_factory() as session:
        test_vacs = [
            {
                "id": "src_test_hh",
                "source": "hh",
                "title": "HH Developer",
                "company": "Company A",
                "url": "https://hh.ru/test1",
                "is_remote": True
            },
            {
                "id": "src_test_kwork",
                "source": "kwork",
                "title": "Kwork Bot Order",
                "company": "Client B",
                "url": "https://kwork.ru/test2",
                "is_remote": True,
                "is_freelance": True
            },
            {
                "id": "src_test_remoteok",
                "source": "remoteok",
                "title": "RemoteOK Engineer",
                "company": "Company C",
                "url": "https://remoteok.com/test3",
                "is_remote": True
            }
        ]
        await VacancyRepository.upsert_vacancies(session, test_vacs)

        # 1. Query with allowed_sources=["kwork"]
        kwork_only = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=888111,
            exclude_viewed=False,
            allowed_sources=["kwork"]
        )
        assert any(v.id == "src_test_kwork" for v in kwork_only)
        assert not any(v.id == "src_test_hh" for v in kwork_only)
        assert not any(v.id == "src_test_remoteok" for v in kwork_only)

        # 2. Query with allowed_sources=["hh", "remoteok"]
        vac_only = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=888111,
            exclude_viewed=False,
            allowed_sources=["hh", "remoteok"]
        )
        assert any(v.id == "src_test_hh" for v in vac_only)
        assert any(v.id == "src_test_remoteok" for v in vac_only)
        assert not any(v.id == "src_test_kwork" for v in vac_only)


@pytest.mark.asyncio
async def test_aggregator_manager_fetch_filtering():
    manager = AggregatorManager()

    # Mock fetch_vacancies on all parsers
    for parser in manager.parsers:
        parser.fetch_vacancies = AsyncMock(return_value=[{"id": f"res_{parser.name}", "url": f"https://{parser.name}.com"}])

    # Fetch with only hh and habr enabled
    results = await manager.fetch_all_for_query(
        query="Python",
        limit_per_source=5,
        scan_pages=1,
        enabled_sources=["hh", "habr"]
    )

    # Verify only hh and habr were called
    hh_parser = next(p for p in manager.parsers if p.name == "hh")
    habr_parser = next(p for p in manager.parsers if p.name == "habr")
    kwork_parser = next(p for p in manager.parsers if p.name == "kwork")

    assert hh_parser.fetch_vacancies.called
    assert habr_parser.fetch_vacancies.called
    assert not kwork_parser.fetch_vacancies.called
    assert len(results) == 2


def test_sources_keyboards_rendering():
    # 1. Test get_settings_keyboard contains sources row
    user = User(telegram_id=999, enabled_sources=["hh", "habr", "kwork"])
    settings_kb = get_settings_keyboard(user)
    buttons = [btn for row in settings_kb.inline_keyboard for btn in row]
    sources_btn = next((b for b in buttons if b.callback_data == "settings_sources"), None)
    assert sources_btn is not None
    assert "3 из 9" in sources_btn.text

    # 2. Test get_sources_settings_keyboard shows checkboxes
    sources_kb = get_sources_settings_keyboard(user)
    all_buttons = [btn for row in sources_kb.inline_keyboard for btn in row]

    hh_btn = next(b for b in all_buttons if b.callback_data == "toggle_src_hh")
    habr_btn = next(b for b in all_buttons if b.callback_data == "toggle_src_habr")
    superjob_btn = next(b for b in all_buttons if b.callback_data == "toggle_src_superjob")

    assert "✅" in hh_btn.text
    assert "✅" in habr_btn.text
    assert "❌" in superjob_btn.text

    # Verify preset buttons exist
    assert any(b.callback_data == "src_preset_all" for b in all_buttons)
    assert any(b.callback_data == "src_preset_vacancies" for b in all_buttons)
    assert any(b.callback_data == "src_preset_freelance" for b in all_buttons)
    assert any(b.callback_data == "back_to_settings" for b in all_buttons)
