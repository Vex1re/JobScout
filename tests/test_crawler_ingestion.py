import pytest
from unittest.mock import AsyncMock, patch
from core.database.session import init_db, async_session_factory
from core.database.repository import UserRepository, VacancyRepository
from core.database.models import Resume, Vacancy
from services.parser.manager import AggregatorManager
from workers.tasks.crawler import crawl_bucket


@pytest.mark.asyncio
async def test_crawl_bucket_execution():
    await init_db()

    mock_vacs = [
        {
            "id": "hh_crawler_1",
            "source": "hh",
            "title": "Python Crawler Vacancy",
            "company": "Data Corp",
            "url": "https://hh.ru/1",
            "salary_min": 120000,
            "salary_max": 180000,
            "currency": "RUB",
            "description": "Python, Redis, PostgreSQL",
            "requirements": ["Python", "PostgreSQL"],
            "is_remote": True,
            "city": "Москва"
        }
    ]

    with patch("services.parser.manager.AggregatorManager.fetch_all_for_query", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = mock_vacs
        added = await crawl_bucket({}, role="Python Developer", city="Москва", remote_only=True)
        assert added >= 0


@pytest.mark.asyncio
async def test_db_first_search_serves_from_db():
    await init_db()

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=654321987,
            username="db_first_user"
        )
        resume = Resume(
            user_id=user.telegram_id,
            title="Senior Python Architect",
            grade="Senior",
            years_of_experience=6.0,
            skills=["Python", "PostgreSQL", "Docker", "FastAPI"]
        )

        # Populate DB with 20 strong matches
        db_vacs = [
            {
                "id": f"db_warm_vac_{i}",
                "source": "hh",
                "title": f"Senior Python Architect #{i}",
                "company": f"Tech Enterprise {i}",
                "url": f"https://hh.ru/warm_{i}",
                "salary_min": 250000,
                "salary_max": 350000,
                "currency": "RUB",
                "description": "Senior Python Architect. Tech stack: Python, PostgreSQL, Docker, FastAPI.",
                "requirements": ["Python", "PostgreSQL", "Docker", "FastAPI"],
                "is_remote": True,
                "risk_level": "safe",
                "city": "Москва"
            }
            for i in range(20)
        ]
        await VacancyRepository.upsert_vacancies(session, db_vacs)

        manager = AggregatorManager()
        # Spy on fetch_all_for_queries
        with patch.object(manager, "fetch_all_for_queries", new_callable=AsyncMock) as mock_external_fetch:
            results = await manager.search_and_match_for_user(session, user, resume)

            # Assert that external search was NEVER triggered because DB already had >= 15 warm matches
            assert mock_external_fetch.called is False
            assert len(results) >= 15
            assert results[0][1]["score"] >= 80
