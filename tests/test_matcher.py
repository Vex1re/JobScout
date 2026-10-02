import pytest
from services.resume_analyzer.matcher import VacancyMatcher


def test_high_match_score():
    candidate_skills = ["Python", "FastAPI", "Docker", "PostgreSQL", "Redis", "Git"]
    candidate_grade = "Middle"
    candidate_role = "Python Backend Developer"
    candidate_experience = 3.0

    vacancy_title = "Middle Python Developer"
    vacancy_desc = "Ищем разработчика со стеком FastAPI, PostgreSQL, Docker и Redis."
    vacancy_reqs = ["Python", "FastAPI", "PostgreSQL", "Docker", "Redis"]

    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade=candidate_grade,
        candidate_role=candidate_role,
        candidate_experience=candidate_experience,
        vacancy_title=vacancy_title,
        vacancy_description=vacancy_desc,
        vacancy_requirements=vacancy_reqs
    )

    assert result["score"] >= 85
    assert "FastAPI" in result["matched_skills"]
    assert "PostgreSQL" in result["matched_skills"]
    assert len(result["missing_skills"]) == 0


def test_missing_skills_highlighted():
    candidate_skills = ["Python", "Django", "PostgreSQL"]
    candidate_grade = "Middle"
    candidate_role = "Python Developer"
    candidate_experience = 2.0

    vacancy_title = "Python Backend Developer"
    vacancy_desc = "Стек: Python, FastAPI, Kafka, Kubernetes, ClickHouse"
    vacancy_reqs = ["Python", "FastAPI", "Apache Kafka", "Kubernetes", "ClickHouse"]

    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade=candidate_grade,
        candidate_role=candidate_role,
        candidate_experience=candidate_experience,
        vacancy_title=vacancy_title,
        vacancy_description=vacancy_desc,
        vacancy_requirements=vacancy_reqs
    )

    assert "Python" in result["matched_skills"]
    assert "Kubernetes" in result["missing_skills"]
    assert result["score"] < 80


def test_blocked_vacancy_zero_score():
    candidate_skills = ["Python", "Django"]
    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=2.0,
        vacancy_title="Легкий заработок",
        vacancy_description="Внесите залог за материалы",
        vacancy_requirements=[],
        risk_level="blocked"
    )

    assert result["score"] == 0
    assert "заблокирована" in result["reason"]


def test_vacancy_experience_extractor():
    from services.resume_analyzer.vacancy_extractor import VacancyExperienceExtractor

    assert VacancyExperienceExtractor.extract_experience_years("Опыт работы от 3 до 5 лет") == (3.0, 5.0)
    assert VacancyExperienceExtractor.extract_experience_years("Требуемый опыт: 1-3 года") == (1.0, 3.0)
    assert VacancyExperienceExtractor.extract_experience_years("Опыт от 2 лет в разработке") == (2.0, None)
    assert VacancyExperienceExtractor.extract_experience_years("Без опыта работы, всему научим") == (0.0, 0.0)
    assert VacancyExperienceExtractor.extract_experience_years("Опыт работы не требуется") == (0.0, 0.0)
    assert VacancyExperienceExtractor.extract_experience_years("5+ years of experience") == (5.0, None)
    assert VacancyExperienceExtractor.extract_experience_years("До 1 года опыта") == (None, 1.0)


def test_vacancy_grade_detector():
    from services.resume_analyzer.vacancy_extractor import VacancyGradeDetector

    assert VacancyGradeDetector.detect_grade("Senior Python Developer", "") == "Senior"
    assert VacancyGradeDetector.detect_grade("Junior Backend Engineer", "") == "Junior"
    assert VacancyGradeDetector.detect_grade("Team Lead Python", "") == "Lead"
    assert VacancyGradeDetector.detect_grade("Архитектор решений", "") == "Lead"
    # By experience fallback
    assert VacancyGradeDetector.detect_grade("Python Developer", "Стек: fastapi", min_experience=0.5) == "Junior"
    assert VacancyGradeDetector.detect_grade("Python Developer", "Стек: fastapi", min_experience=2.0) == "Middle"
    assert VacancyGradeDetector.detect_grade("Python Developer", "Стек: fastapi", min_experience=5.0) == "Senior"


def test_hard_cutoff_junior_to_senior():
    """Junior candidate matching a Senior vacancy must be disqualified (score <= 18)."""
    candidate_skills = ["Python", "FastAPI", "Docker", "PostgreSQL"]
    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade="Junior",
        candidate_role="Python Developer",
        candidate_experience=0.8,
        vacancy_title="Senior Python Backend Developer",
        vacancy_description="Опыт от 5 лет. FastAPI, PostgreSQL, Docker.",
        vacancy_requirements=["Python", "FastAPI", "Docker", "PostgreSQL"],
        vacancy_min_exp=5.0,
        vacancy_grade="Senior"
    )

    assert result["is_disqualified"] is True
    assert result["score"] <= 18
    assert "⛔ Недостаточно опыта/грейда" in result["reason"]


def test_hard_cutoff_experience_deficit():
    """Candidate with 1.0 yr experience against 4.0 yrs required must be disqualified."""
    candidate_skills = ["Python", "Django", "PostgreSQL"]
    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=1.0,
        vacancy_title="Middle/Senior Backend Developer",
        vacancy_description="Требуемый опыт от 4 лет.",
        vacancy_requirements=["Python", "Django", "PostgreSQL"],
        vacancy_min_exp=4.0
    )

    assert result["is_disqualified"] is True
    assert result["score"] <= 18


def test_growth_opportunity_detection():
    """Junior candidate with 1.5 yrs experience matching Middle vacancy with 2.0 yrs required."""
    candidate_skills = ["Python", "FastAPI", "Docker", "PostgreSQL"]
    result = VacancyMatcher.match(
        candidate_skills=candidate_skills,
        candidate_grade="Junior",
        candidate_role="Python Developer",
        candidate_experience=1.5,
        vacancy_title="Middle Python Developer",
        vacancy_description="Ищем разработчика с опытом от 2 лет. FastAPI, Docker.",
        vacancy_requirements=["Python", "FastAPI", "Docker"],
        vacancy_min_exp=2.0,
        vacancy_grade="Middle"
    )

    assert result["is_disqualified"] is False
    assert result["is_growth_opportunity"] is True
    assert result["score"] >= 65
    assert "🌱 Отличная зона роста" in result["reason"]


def test_experience_gap_penalty_tiered():
    """Experience gap penalties: < 1.5 yrs vs >= 1.5 yrs."""
    skills = ["Python", "FastAPI", "Docker"]

    # Deficit = 1.0 yr (< 1.5) -> penalty = 15.0 * 1.0 = 15.0
    res_small_gap = VacancyMatcher.match(
        candidate_skills=skills,
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=2.0,
        vacancy_title="Middle Python Developer",
        vacancy_description="FastAPI, Docker",
        vacancy_requirements=skills,
        vacancy_min_exp=3.0,
        vacancy_grade="Middle"
    )

    # Deficit = 2.0 yrs (>= 1.5) on 3.0 req (req < 3.5, so no hard cutoff) -> penalty = 35 + 20*0.5 = 45.0
    res_large_gap = VacancyMatcher.match(
        candidate_skills=skills,
        candidate_grade="Middle",
        candidate_role="Python Developer",
        candidate_experience=1.0,
        vacancy_title="Middle Python Developer",
        vacancy_description="FastAPI, Docker",
        vacancy_requirements=skills,
        vacancy_min_exp=3.0,
        vacancy_grade="Middle"
    )

    assert res_small_gap["is_disqualified"] is False
    assert res_large_gap["is_disqualified"] is False
    assert res_small_gap["score"] > res_large_gap["score"]
    assert res_large_gap["score"] < 60


def test_card_formatter_experience_block():
    """Card formatter properly displays experience and grade."""
    from bot.formatters.card import format_vacancy_card, format_experience
    from core.database.models import Vacancy

    assert format_experience(1.0, 3.0) == "1–3 г."
    assert format_experience(3.0, None) == "от 3 г."
    assert format_experience(0.0, 0.0) == "Без опыта"

    vac = Vacancy(
        id="test_1",
        source="hh",
        title="Python Dev",
        company="Tech Co",
        url="https://hh.ru/1",
        description="FastAPI dev",
        requirements=["Python", "FastAPI"],
        min_experience=2.0,
        max_experience=4.0,
        target_grade="Middle"
    )
    match_info = {
        "score": 85,
        "matched_skills": ["Python", "FastAPI"],
        "missing_skills": [],
        "vacancy_grade": "Middle",
        "vacancy_min_exp": 2.0,
        "vacancy_max_exp": 4.0,
        "is_growth_opportunity": True,
        "reason": "🌱 Отличная зона роста (Middle)"
    }

    card_text = format_vacancy_card(vac, match_info)
    assert "🎯 <b>Грейд:</b> Middle" in card_text
    assert "⏳ <b>Опыт:</b> 2–4 г." in card_text
    assert "🌱 <b>Зона роста:</b>" in card_text

