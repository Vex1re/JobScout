import pytest
from services.resume_analyzer.extractor import ResumeExtractor


def test_skill_extraction():
    text = """
    Обо мне:
    Я бэкенд разработчик с опытом коммерческой разработки 3 года.
    В работе активно использую Python, Django, FastAPI, PostgreSQL, Redis, Docker и Kubernetes.
    Также знаком с Celery, RabbitMQ, Git и Linux. Пишу автотесты на Pytest.
    """
    skills = ResumeExtractor.extract_skills(text)
    
    assert "Python" in skills
    assert "FastAPI" in skills
    assert "PostgreSQL" in skills
    assert "Docker" in skills
    assert "Kubernetes" in skills
    assert "Pytest" in skills
    assert "RabbitMQ" in skills


def test_experience_extraction():
    text1 = "Опыт работы: 4 года в IT компании"
    assert ResumeExtractor.extract_experience_years(text1) == 4.0

    text2 = "Более 5 лет опыта разработки"
    assert ResumeExtractor.extract_experience_years(text2) == 5.0

    text3 = "18 месяцев коммерческого опыта"
    assert ResumeExtractor.extract_experience_years(text3) == 1.5


def test_grade_detection():
    assert ResumeExtractor.detect_grade("Senior Backend Developer", 5.0) == "Senior"
    assert ResumeExtractor.detect_grade("Junior Python программист", 1.0) == "Junior"
    assert ResumeExtractor.detect_grade("Тимлид команды разработки", 6.0) == "Lead"
    assert ResumeExtractor.detect_grade("Middle инженер", 2.5) == "Middle"


def test_salary_expectation_extraction():
    text = "Желаемая зарплата: 200 000 руб. на руки"
    salary = ResumeExtractor.extract_salary_expectation(text)
    assert salary == 200000
