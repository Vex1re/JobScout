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

    # Zero experience
    text_zero1 = "Без опыта работы, ищу стажировку"
    assert ResumeExtractor.extract_experience_years(text_zero1) == 0.0

    text_zero2 = "Опыт работы: 0 лет, начинающий специалист"
    assert ResumeExtractor.extract_experience_years(text_zero2) == 0.0

    # Default fallback
    text_fallback = "Знаю Python и базы данных, готов развиваться"
    assert ResumeExtractor.extract_experience_years(text_fallback) == 0.0

    # Compound periods: 3 года 8 месяцев = 3 + 8/12 ~ 3.7
    text_compound = "Общий коммерческий опыт: 3 года 8 месяцев"
    assert ResumeExtractor.extract_experience_years(text_compound) == 3.7

    # Date intervals
    text_years_interval = "Период работы: 2021 — 2024 в финтех компании"
    assert ResumeExtractor.extract_experience_years(text_years_interval) == 3.0

    # Overlapping intervals (Interval Union: Jan 2021-Dec 2022 and Jun 2022-Jun 2023 -> 2.5 yrs, not 3.0)
    text_overlapping = "Компания A: 01.2021 — 12.2022. Компания B: 06.2022 — 06.2023"
    assert ResumeExtractor.extract_experience_years(text_overlapping) == 2.5


def test_grade_detection():
    assert ResumeExtractor.detect_grade("Senior Backend Developer", 5.0) == "Senior"
    assert ResumeExtractor.detect_grade("Junior Python программист", 1.0) == "Junior"
    assert ResumeExtractor.detect_grade("Тимлид команды разработки", 6.0) == "Lead"
    assert ResumeExtractor.detect_grade("Middle инженер", 2.5) == "Middle"
    assert ResumeExtractor.detect_grade("Разработчик", 0.0) == "Junior"
    assert ResumeExtractor.detect_grade("Стажер Python", 0.0) == "Junior"


def test_salary_expectation_extraction():
    text = "Желаемая зарплата: 200 000 руб. на руки"
    salary = ResumeExtractor.extract_salary_expectation(text)
    assert salary == 200000


@pytest.mark.parametrize(
    "frozen_date, start_text, min_expected, max_expected",
    [
        ("2025-07-01", "01.2024 — по настоящее время", 1.4, 1.6),
        ("2027-01-01", "01.2024 — по настоящее время", 2.9, 3.1),
        ("2030-01-01", "2024 — н.в.", 5.5, 6.2),
    ]
)
def test_dynamic_years_with_freezegun(frozen_date, start_text, min_expected, max_expected):
    from freezegun import freeze_time
    with freeze_time(frozen_date):
        years = ResumeExtractor.extract_experience_years(start_text)
        assert min_expected <= years <= max_expected, (
            f"At {frozen_date}, expected {min_expected}-{max_expected} for '{start_text}', got {years}"
        )

