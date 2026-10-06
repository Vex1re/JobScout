import pytest
import datetime
from unittest.mock import patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from core.database.models import Base, User
from core.database.repository import InteractionRepository
from services.resume_analyzer.matcher import VacancyMatcher
from services.parser.normalizer import CityNormalizer
from scripts.eval_matcher import evaluate_matcher


def test_soft_grade_penalty_when_low_confidence():
    """
    When grade_confidence >= 0.7, a Junior looking at a Senior vacancy is hard-disqualified.
    When grade_confidence < 0.7, a soft grade penalty is applied instead of hard disqualification.
    """
    # High confidence -> hard disqualification
    res_high = VacancyMatcher.match(
        candidate_skills=["python", "fastapi", "docker"],
        candidate_grade="Junior",
        candidate_role="Python Developer",
        candidate_experience=1.5,
        vacancy_title="Senior Python Architect",
        vacancy_description="Looking for Python architect with deep system knowledge",
        vacancy_requirements=["python", "fastapi", "docker"],
        vacancy_grade="Senior",
        vacancy_min_exp=2.0,
        grade_confidence=0.9,
    )
    assert res_high["is_disqualified"] is True
    assert res_high["grade_compatibility"] == "disqualified"
    assert res_high["score"] <= 18

    # Low confidence (< 0.7) -> soft penalty, no hard disqualification
    res_low = VacancyMatcher.match(
        candidate_skills=["python", "fastapi", "docker"],
        candidate_grade="Junior",
        candidate_role="Python Developer",
        candidate_experience=1.5,
        vacancy_title="Senior Python Architect",
        vacancy_description="Looking for Python architect with deep system knowledge",
        vacancy_requirements=["python", "fastapi", "docker"],
        vacancy_grade="Senior",
        vacancy_min_exp=2.0,
        grade_confidence=0.6,
    )
    assert res_low["is_disqualified"] is False
    assert res_low["score"] > res_high["score"]
    assert res_low["score"] >= 40


def test_configurable_score_weights():
    """
    Tests that VacancyMatcher respects configurable weights in settings.
    """
    # Baseline weights
    res_default = VacancyMatcher.match(
        candidate_skills=["python", "docker"],
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=3.0,
        vacancy_title="Python Developer",
        vacancy_description="Backend developer",
        vacancy_requirements=["python", "docker", "redis", "fastapi"],
        vacancy_grade="Middle",
        vacancy_min_exp=3.0
    )

    # Patch weights to heavily prioritize skills (e.g. 0.90 skills, 0.05 grade, 0.05 exp)
    with patch("core.config.settings.SCORE_WEIGHT_SKILLS", 0.90), \
         patch("core.config.settings.SCORE_WEIGHT_GRADE", 0.05), \
         patch("core.config.settings.SCORE_WEIGHT_EXPERIENCE", 0.05):
        res_skills_heavy = VacancyMatcher.match(
            candidate_skills=["python", "docker"],
            candidate_grade="Middle",
            candidate_role="Python Developer",
            candidate_experience=3.0,
            vacancy_title="Python Developer",
            vacancy_description="Backend developer",
            vacancy_requirements=["python", "docker", "redis", "fastapi"],
            vacancy_grade="Middle",
            vacancy_min_exp=3.0
        )

    # Since candidate only has 50% of the skills, skill_score is lower than perfect grade/exp scores.
    # Increasing skill weight should pull the final score down.
    assert res_skills_heavy["score"] != res_default["score"]


def test_time_decay_freshness():
    """
    Tests that vacancies published in the past receive time decay reductions.
    """
    now = datetime.datetime.now(datetime.timezone.utc)

    fresh_pub = now - datetime.timedelta(days=2)
    two_weeks_pub = now - datetime.timedelta(days=20)
    month_pub = now - datetime.timedelta(days=35)

    res_fresh = VacancyMatcher.match(
        candidate_skills=["python", "fastapi"],
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=3.0,
        vacancy_title="Python Developer",
        vacancy_description="Python dev",
        vacancy_requirements=["python", "fastapi"],
        vacancy_grade="Middle",
        published_at=fresh_pub
    )

    res_two_weeks = VacancyMatcher.match(
        candidate_skills=["python", "fastapi"],
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=3.0,
        vacancy_title="Python Developer",
        vacancy_description="Python dev",
        vacancy_requirements=["python", "fastapi"],
        vacancy_grade="Middle",
        published_at=two_weeks_pub
    )

    res_month = VacancyMatcher.match(
        candidate_skills=["python", "fastapi"],
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=3.0,
        vacancy_title="Python Developer",
        vacancy_description="Python dev",
        vacancy_requirements=["python", "fastapi"],
        vacancy_grade="Middle",
        published_at=month_pub
    )

    assert res_fresh["time_decay_factor"] == 1.0
    assert 0.70 < res_two_weeks["time_decay_factor"] < 0.90
    assert res_month["time_decay_factor"] == 0.70

    assert res_fresh["score"] > res_two_weeks["score"] > res_month["score"]


@pytest.mark.asyncio
async def test_user_interaction_repository():
    """
    Tests logging interactions (favorite, hide, apply_click) and querying hidden / positive canonical IDs.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_factory() as session:
        # Create user
        user = User(telegram_id=987654321, username="test_interactor")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Log interactions
        await InteractionRepository.log_interaction(session, user.telegram_id, "can_id_101", "hide")
        await InteractionRepository.log_interaction(session, user.telegram_id, "can_id_102", "favorite")
        await InteractionRepository.log_interaction(session, user.telegram_id, "can_id_103", "apply_click")
        await InteractionRepository.log_interaction(session, user.telegram_id, "can_id_104", "hide")

        hidden_ids = await InteractionRepository.get_hidden_canonical_ids(session, user.telegram_id)
        assert set(hidden_ids) == {"can_id_101", "can_id_104"}

        pos_fav = await InteractionRepository.get_positive_interactions(session, user.telegram_id, action="favorite")
        assert len(pos_fav) == 1
        assert pos_fav[0].vacancy_canonical_id == "can_id_102"

        pos_all = await InteractionRepository.get_positive_interactions(session, user.telegram_id)
        assert len(pos_all) == 2
        assert {item.vacancy_canonical_id for item in pos_all} == {"can_id_102", "can_id_103"}

    await engine.dispose()


def test_city_normalizer_static_catalog():
    """
    Tests that CityNormalizer successfully leverages the top Russian cities catalog.
    """
    assert CityNormalizer.normalize("Владивосток") == "Владивосток"
    assert CityNormalizer.normalize("Хабаровск") == "Хабаровск"
    assert CityNormalizer.normalize("Красноярск") == "Красноярск"
    assert CityNormalizer.normalize("г. Самара") == "Самара"
    assert CityNormalizer.normalize("Санкт-Петербург") == "Санкт-Петербург"
    assert CityNormalizer.normalize("Питер") == "Санкт-Петербург"


def test_golden_dataset_metrics():
    """
    Evaluates VacancyMatcher on the 20 golden cases and asserts quality thresholds.
    """
    metrics = evaluate_matcher("tests/golden/matcher_golden.json")
    assert metrics["cases_evaluated"] == 20
    assert metrics["mean_recall_at_10"] >= 0.85
    assert metrics["mean_precision_at_10"] >= 0.45
    assert metrics["mean_precision_at_5"] >= 0.90
