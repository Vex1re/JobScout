import pytest
from services.parser.normalizer import CityNormalizer
from services.resume_analyzer.validator import ResumeValidator
from services.parser.manager import AggregatorManager
from core.database.models import Resume, User, Vacancy
from core.database.repository import (
    UserRepository,
    VacancyRepository,
    InteractionRepository
)
from core.database.session import init_db, async_session_factory


def test_city_normalizer_synonyms():
    assert CityNormalizer.normalize("москва") == "Москва"
    assert CityNormalizer.normalize("МСК") == "Москва"
    assert CityNormalizer.normalize("Moscow") == "Москва"
    assert CityNormalizer.normalize("г. Москва") == "Москва"
    assert CityNormalizer.normalize("г. Санкт-Петербург") == "Санкт-Петербург"
    assert CityNormalizer.normalize("спб") == "Санкт-Петербург"
    assert CityNormalizer.normalize("Питер") == "Санкт-Петербург"
    assert CityNormalizer.normalize("Казань") == "Казань"
    assert CityNormalizer.normalize("Екб") == "Екатеринбург"
    assert CityNormalizer.normalize("Пермь") == "Пермь"
    assert CityNormalizer.normalize("Удаленно") == "Удаленно"
    assert CityNormalizer.normalize("remote") == "Удаленно"


def test_city_normalizer_matching():
    # Remote vacancies match any user city
    assert CityNormalizer.is_match(user_city="Москва", vacancy_city="Казань", is_remote=True) is True
    assert CityNormalizer.is_match(user_city="Пермь", vacancy_city=None, is_remote=True) is True

    # User with no city preference matches any
    assert CityNormalizer.is_match(user_city=None, vacancy_city="Москва", is_remote=False) is True
    assert CityNormalizer.is_match(user_city="Любой", vacancy_city="Казань", is_remote=False) is True

    # Office vacancies match when cities match
    assert CityNormalizer.is_match(user_city="Москва", vacancy_city="г. Москва", is_remote=False) is True
    assert CityNormalizer.is_match(user_city="мск", vacancy_city="Москва", is_remote=False) is True
    assert CityNormalizer.is_match(user_city="Санкт-Петербург", vacancy_city="Питер", is_remote=False) is True

    # Office vacancies don't match different cities
    assert CityNormalizer.is_match(user_city="Москва", vacancy_city="Санкт-Петербург", is_remote=False) is False
    assert CityNormalizer.is_match(user_city="Казань", vacancy_city="Екатеринбург", is_remote=False) is False


def test_resume_validator_valid_resume():
    valid_text = """
    Иван Иванов
    Python Backend Разработчик
    
    Контакты:
    Telegram: @ivan_dev, email: ivan@example.com
    
    Опыт работы:
    Более 3 лет разработки на Python, FastAPI, PostgreSQL, Docker, Redis.
    Проектирование REST API и микросервисов.
    
    Навыки:
    Python, FastAPI, Django, PostgreSQL, Docker, Git, Redis, Linux
    
    Образование:
    МГТУ им. Баумана, Информатика и вычислительная техника
    """
    res = ResumeValidator.validate(valid_text, tech_skills_count=6)
    assert res.is_valid is True
    assert res.score >= 75
    assert res.error_message is None


def test_resume_validator_junior_zero_exp():
    junior_text = """
    Петр Сидоров
    Junior Python Developer
    
    Контакты:
    Telegram: @petr_python
    
    Обо мне и пет-проектах:
    Без коммерческого опыта работы. Реализовал учебный пет-проект интернет-магазина
    на стеке FastAPI, SQLAlchemy и PostgreSQL.
    
    Ключевые навыки:
    Python, FastAPI, Git, SQLite, Docker, Pytest
    
    Образование:
    Курс Python-разработки Яндекс Практикум, 2024
    """
    res = ResumeValidator.validate(junior_text, tech_skills_count=4)
    assert res.is_valid is True


def test_resume_validator_recipe_rejected():
    recipe_text = """
    Вкусный шоколадный торт:
    Ингредиенты: 300 граммов муки, 100 граммов сахара, 2 столовая ложка какао.
    Рецепт: нарезать масло, замесить тесто и выпекать в духовке при 180 градусах.
    Посолить по вкусу.
    """
    res = ResumeValidator.validate(recipe_text, tech_skills_count=0)
    assert res.is_valid is False
    assert res.detected_type == "recipe"
    assert "рецепт" in res.error_message.lower()


def test_resume_validator_contract_rejected():
    contract_text = """
    ДОГОВОР АРЕНДЫ ПОМЕЩЕНИЯ № 42
    Арендодатель в лице генерального директора, действующего на основании устава,
    и Арендатор заключили настоящий договор о нижеследующем.
    Стороны договорились: пункт договора 1.1, ответственность сторон, акт приема-передачи,
    штрафные санкции и банковские реквизиты сторон.
    """
    res = ResumeValidator.validate(contract_text, tech_skills_count=0)
    assert res.is_valid is False
    assert res.detected_type == "contract"
    assert "договор" in res.error_message.lower()


def test_resume_validator_fiction_rejected():
    fiction_text = """
    Глава седьмая.
    — Сказал он с легкой грустью и подошел к окну.
    — Ответила она, затаив дыхание. Ночь опустилась на город, шаги за дверью эхом раздавались по коридору.
    Вдруг он почувствовал, как сердце бешено колотилось.
    """
    res = ResumeValidator.validate(fiction_text, tech_skills_count=0)
    assert res.is_valid is False
    assert res.detected_type == "fiction"


def test_resume_validator_missing_skills_rejected():
    text_no_skills = """
    Иван Иванов
    Менеджер по продажам
    Опыт работы 5 лет в розничной торговле.
    Контакты: телефон +79991234567, email: test@mail.ru.
    Высшее образование: МГУ, экономический факультет.
    """
    res = ResumeValidator.validate(text_no_skills, tech_skills_count=0)
    assert res.is_valid is False
    assert "навык" in res.error_message.lower() or "стек" in res.error_message.lower()


def test_query_pool_generation():
    resume = Resume(
        title="Python Backend Developer",
        grade="Middle",
        years_of_experience=3.0,
        skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"]
    )
    pool = AggregatorManager.generate_query_pool(resume)
    assert len(pool) >= 3
    assert "Python Backend Developer" in pool
    assert "Python FastAPI" in pool
    assert "Python" in pool


@pytest.mark.asyncio
async def test_db_user_viewed_and_city_filtering():
    await init_db()

    async with async_session_factory() as session:
        # Create test user
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=999888777,
            username="test_city_user",
            first_name="Test"
        )
        await UserRepository.update_preferences(
            session=session,
            telegram_id=user.telegram_id,
            city="Казань"
        )

        # Upsert vacancies: one remote, one Kazan office, one Moscow office
        vacs = [
            {
                "id": "test_vac_remote_1",
                "source": "hh",
                "title": "Remote Python",
                "company": "Remote Co",
                "url": "https://test.com/1",
                "is_remote": True,
                "city": "Удаленно"
            },
            {
                "id": "test_vac_kazan_2",
                "source": "hh",
                "title": "Kazan Python",
                "company": "Kazan Co",
                "url": "https://test.com/2",
                "is_remote": False,
                "city": "Казань"
            },
            {
                "id": "test_vac_moscow_3",
                "source": "hh",
                "title": "Moscow Python",
                "company": "Moscow Co",
                "url": "https://test.com/3",
                "is_remote": False,
                "city": "Москва"
            }
        ]
        await VacancyRepository.upsert_vacancies(session, vacs)

        # 1. Test get_unhidden_vacancies with city="Казань":
        # Should include Remote (1) and Kazan (2), but NOT Moscow (3)
        unhidden = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            user_city="Казань",
            remote_only=False,
            exclude_viewed=True
        )
        unhidden_ids = {v.id for v in unhidden}
        assert "test_vac_remote_1" in unhidden_ids
        assert "test_vac_kazan_2" in unhidden_ids
        assert "test_vac_moscow_3" not in unhidden_ids

        # 2. Test mark_as_viewed
        await InteractionRepository.mark_as_viewed(
            session=session,
            user_id=user.telegram_id,
            vacancy_id="test_vac_kazan_2"
        )

        # Now test_vac_kazan_2 should be excluded because it's viewed!
        unhidden_after_view = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            user_city="Казань",
            remote_only=False,
            exclude_viewed=True
        )
        unhidden_after_ids = {v.id for v in unhidden_after_view}
        assert "test_vac_kazan_2" not in unhidden_after_ids
        assert "test_vac_remote_1" in unhidden_after_ids

        # 3. Test reset_viewed_history
        deleted_count = await InteractionRepository.reset_viewed_history(
            session=session,
            user_id=user.telegram_id
        )
        assert deleted_count >= 1

        # After reset, test_vac_kazan_2 should be visible again
        unhidden_after_reset = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            user_city="Казань",
            remote_only=False,
            exclude_viewed=True
        )
        reset_ids = {v.id for v in unhidden_after_reset}
        assert "test_vac_kazan_2" in reset_ids
