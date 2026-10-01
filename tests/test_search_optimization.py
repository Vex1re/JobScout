import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.database.session import async_session_factory, init_db
from core.database.models import User, Resume, Vacancy
from core.database.repository import VacancyRepository, UserRepository
from services.parser.manager import AggregatorManager
from bot.formatters.card import format_vacancy_card, format_source_badge, get_score_badge


def test_generate_query_pool_all_required_categories():
    """
    Verifies that generate_query_pool includes:
    1. English role title ("Python Developer", "Backend Developer")
    2. Russian role synonyms ("Разработчик Python", "Программист Python", "Бэкенд разработчик")
    3. Single key tech/stack ("Python")
    4. Framework pairings ("Python FastAPI", "Python Django")
    5. Infrastructure pairings ("Python Docker", "FastAPI PostgreSQL")
    """
    resume = Resume(
        title="Python Backend Developer",
        grade="Middle",
        years_of_experience=3.0,
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"]
    )
    pool = AggregatorManager.generate_query_pool(resume)

    # 1. English role titles
    assert "Python Developer" in pool
    assert "Backend Developer" in pool

    # 2. Russian role synonyms
    assert "Разработчик Python" in pool
    assert "Программист Python" in pool
    assert "Бэкенд разработчик" in pool

    # 3. Single key tech/stack
    assert "Python" in pool

    # 4. Framework pairings
    assert "Python FastAPI" in pool
    assert "Python Django" in pool

    # 5. Infrastructure pairings
    assert "Python Docker" in pool
    assert "FastAPI PostgreSQL" in pool

    # Deduplicated and non-empty
    assert len(pool) == len(set(q.lower() for q in pool))
    assert all(len(q.strip()) > 0 for q in pool)


def test_generate_query_pool_diverse_profile():
    """Tests query pool generation for a Frontend / React profile."""
    resume = Resume(
        title="Frontend Developer",
        grade="Senior",
        years_of_experience=5.0,
        skills=["TypeScript", "React", "Next.js", "Docker"]
    )
    pool = AggregatorManager.generate_query_pool(resume)

    assert "Frontend Developer" in pool
    assert "Фронтенд разработчик" in pool
    assert any("TypeScript" in q for q in pool)
    assert any("React" in q for q in pool)


@pytest.mark.asyncio
async def test_multi_page_scanning():
    """
    Verifies that multi-page scanning queries both page and page + 1
    for primary aggregators (HH, Trudvsem, SuperJob, Habr, Rabota).
    """
    manager = AggregatorManager()
    called_pages = {}

    for parser in manager.parsers:
        called_pages[parser.name] = []

        async def make_mock_fetch(p_name):
            async def _mock_fetch(query, limit=50, remote_only=False, page=0):
                called_pages[p_name].append(page)
                return [{
                    "id": f"{p_name}_page_{page}",
                    "url": f"https://example.com/{p_name}/{page}",
                    "source": p_name,
                    "title": f"Dev {p_name} {page}"
                }]
            return _mock_fetch

        parser.fetch_vacancies = await make_mock_fetch(parser.name)

    results = await manager.fetch_all_for_query(
        query="python",
        page=0,
        scan_pages=2
    )

    # Primary multi-page aggregators must be called for page 0 and page 1
    for name in manager.MULTI_PAGE_PARSERS:
        assert 0 in called_pages[name], f"{name} was not called for page 0"
        assert 1 in called_pages[name], f"{name} was not called for page 1"
        assert len(called_pages[name]) == 2

    # Single-feed / RSS parsers should be called once for page 0
    assert len(called_pages["fl_ru"]) == 1
    assert len(called_pages["remoteok"]) == 1

    # Total vacancies returned should include page 0 and page 1 items
    assert len(results) > 10


@pytest.mark.asyncio
async def test_multi_query_parallel_fetching_and_deduplication():
    """
    Verifies that fetch_all_for_queries executes multiple search queries concurrently,
    merges the result sets, and deduplicates by both ID and URL.
    """
    manager = AggregatorManager()

    # Setup parser that returns items based on query
    for parser in manager.parsers:
        async def mock_fetch(query, limit=50, remote_only=False, page=0):
            return [
                {
                    "id": f"unique_item_{page}",
                    "url": f"https://example.com/unique_{page}",
                    "source": "hh",
                    "title": f"Dev {query} {page}"
                },
                # Duplicate item across queries
                {
                    "id": "shared_duplicate_id",
                    "url": "https://example.com/shared_duplicate_url",
                    "source": "hh",
                    "title": "Shared Vacancy"
                }
            ]
        parser.fetch_vacancies = AsyncMock(side_effect=mock_fetch)

    queries = ["Python Developer", "Backend Developer", "Python FastAPI", "Python Docker"]
    results = await manager.fetch_all_for_queries(
        queries=queries,
        page=0,
        scan_pages=1
    )

    # Ensure duplicate items are deduplicated to exactly 1 instance
    dup_ids = [r for r in results if r["id"] == "shared_duplicate_id"]
    assert len(dup_ids) == 1

    dup_urls = [r for r in results if r["url"] == "https://example.com/shared_duplicate_url"]
    assert len(dup_urls) == 1


@pytest.mark.asyncio
async def test_vacancy_repository_limit_expanded_to_500():
    """
    Verifies that VacancyRepository.get_unhidden_vacancies default limit is 500,
    and returns more than 100 vacancies (e.g. 150) without artificial truncation.
    """
    await init_db()

    async with async_session_factory() as session:
        # Create user
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=888777666,
            username="high_capacity_user"
        )

        # Insert 150 vacancies
        vacancies_data = [
            {
                "id": f"bulk_vac_{i}",
                "source": "hh",
                "title": f"Python Engineer #{i}",
                "company": f"Corp {i}",
                "url": f"https://hh.ru/vacancy/bulk_{i}",
                "salary_min": 100000,
                "salary_max": 200000,
                "currency": "RUB",
                "description": "Python, FastAPI",
                "requirements": ["Python", "FastAPI"],
                "is_remote": True,
                "risk_level": "safe",
                "city": "Москва"
            }
            for i in range(150)
        ]
        await VacancyRepository.upsert_vacancies(session, vacancies_data)

        # Retrieve with default limit (should be 500, not 100)
        retrieved = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_viewed=False
        )

        bulk_items = [v for v in retrieved if v.id.startswith("bulk_vac_")]
        assert len(bulk_items) == 150, f"Expected 150 vacancies, but got {len(bulk_items)} (was truncated?)"

        # Retrieve with explicit custom limit
        custom_retrieved = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_viewed=False,
            limit=50
        )
        assert len(custom_retrieved) == 50


@pytest.mark.asyncio
async def test_adaptive_match_scoring_fallback():
    """
    Verifies that when fewer than 15 vacancies meet standard threshold (45%),
    the adaptive match fallback engages, lowering the threshold to 35% and
    marking adjacent positions with '🌱 Смежная позиция (зона роста)'.
    """
    await init_db()

    async with async_session_factory() as session:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=777666555,
            username="adaptive_user"
        )
        resume = Resume(
            user_id=user.telegram_id,
            title="Junior Python Developer",
            grade="Junior",
            years_of_experience=1.0,
            skills=["Python", "SQLite"]
        )

        # Create 5 strong matches (>=45%) and 10 soft matches (35-44%)
        test_vacs = []
        # Strong: Junior Python Developer with SQLite
        for i in range(5):
            test_vacs.append(
                Vacancy(
                    id=f"strong_vac_{i}",
                    source="hh",
                    title="Junior Python Developer",
                    company="Tech Dev",
                    url=f"https://hh.ru/strong_{i}",
                    salary_min=70000,
                    salary_max=90000,
                    currency="RUB",
                    description="Python, SQLite",
                    requirements=["Python", "SQLite"],
                    is_remote=True,
                    risk_level="safe"
                )
            )

        # Soft: Middle Python Backend Developer with advanced requirements
        for i in range(10):
            test_vacs.append(
                Vacancy(
                    id=f"soft_vac_{i}",
                    source="hh",
                    title="Middle Python Backend Developer",
                    company="Fintech Corp",
                    url=f"https://hh.ru/soft_{i}",
                    salary_min=180000,
                    salary_max=250000,
                    currency="RUB",
                    description="Python, FastAPI, Kafka, Kubernetes, Docker, PostgreSQL",
                    requirements=["Python", "FastAPI", "Kafka", "Kubernetes", "Docker", "PostgreSQL"],
                    is_remote=True,
                    risk_level="safe"
                )
            )

        # Mock VacancyRepository.get_unhidden_vacancies to return test_vacs
        manager = AggregatorManager()
        manager.fetch_all_for_queries = AsyncMock(return_value=[])

        def mock_matcher(*args, **kwargs):
            vac_title = kwargs.get("vacancy_title", "")
            if "Junior" in vac_title:
                return {
                    "score": 85,
                    "matched_skills": ["Python", "SQLite"],
                    "missing_skills": [],
                    "grade_compatibility": "exact",
                    "vacancy_grade": "Junior",
                    "reason": "✅ Совпало: Python, SQLite"
                }
            else:
                return {
                    "score": 38,
                    "matched_skills": ["Python"],
                    "missing_skills": ["Kafka", "Kubernetes"],
                    "grade_compatibility": "growth_opportunity",
                    "vacancy_grade": "Middle",
                    "reason": "⚡ Требуется подтянуть: Kafka, Kubernetes"
                }

        with patch("core.database.repository.VacancyRepository.get_unhidden_vacancies", new_callable=AsyncMock) as mock_get_vacs:
            with patch("services.resume_analyzer.matcher.VacancyMatcher.match", side_effect=mock_matcher):
                mock_get_vacs.return_value = test_vacs

                results = await manager.search_and_match_for_user(
                    session=session,
                    user=user,
                    resume=resume
                )

                # Total results should be 15 because adaptive mode caught the 10 soft vacancies
                assert len(results) == 15

                # The strong vacancies have score >= 45%
                strong_results = [r for r in results if r[0].id.startswith("strong_vac_")]
                assert len(strong_results) == 5
                for vac, match in strong_results:
                    assert match["score"] >= 45
                    assert not match.get("is_adaptive")

                # The soft vacancies have score in [35, 45) and is_adaptive=True
                soft_results = [r for r in results if r[0].id.startswith("soft_vac_")]
                assert len(soft_results) == 10
                for vac, match in soft_results:
                    assert 35 <= match["score"] < 45
                    assert match.get("is_adaptive") is True
                    assert "🌱 Смежная позиция (зона роста)" in match.get("reason", "")


def test_card_formatter_source_badges_and_adaptive_notes():
    """Verifies that all 9 aggregators have badges and adaptive recommendations render."""
    sources = ["hh", "habr", "trudvsem", "superjob", "remoteok", "kwork", "fl_ru", "habr_freelance", "rabota"]
    for s in sources:
        badge = format_source_badge(s)
        assert badge != s.capitalize(), f"Source badge for {s} is not customized"

    # Score badge for soft adaptive match (35-44%)
    assert "🌱" in get_score_badge(38)
    assert "Зона роста" in get_score_badge(38)

    # Card rendering with adaptive info
    vac = Vacancy(
        id="hh_adaptive_test",
        source="hh",
        title="Middle Python Developer",
        company="Startup Co",
        url="https://hh.ru/adaptive",
        salary_min=150000,
        salary_max=200000,
        currency="RUB",
        description="Разработка на Python и FastAPI",
        requirements=["Python", "FastAPI"],
        is_remote=True,
        city="Москва",
        risk_level="safe",
        red_flags=[]
    )
    match_info = {
        "score": 38,
        "matched_skills": ["Python"],
        "missing_skills": ["FastAPI"],
        "reason": "🌱 Смежная позиция (зона роста) | ✅ Совпало: Python",
        "is_adaptive": True
    }
    card = format_vacancy_card(vac, match_info)
    assert "🌱" in card
    assert "Смежная позиция (зона роста)" in card
