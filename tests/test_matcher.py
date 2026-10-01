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
