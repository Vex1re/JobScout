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


def test_skills_boundary_and_sanitization():
    resume_text = """
    Иванов Матвей
    Java backend разработчик

    Технологический стек: Java Core, ООП, Spring Boot, Spring Data JPA, gRPC, React, PostgreSQL, SQL-transactions, REST, Docker, MySQL, Maven, Railway, Postman, Git, SOLID, Vite, ИИ-агенты, AI Skills, Telegram API, Hibernate, t.tech_investments,
    Я студент 2-го курса, специализируюсь на Backend - разработке на Java и проектировании реляционных баз данных. Есть практический опыт построения REST API, работы с gRPC-потоками, а также разработки автоматизированных систем на базе банковских API и торговых бирж. Умею проектировать структуры БД (MySQL, PostgreSQL), работать с ACID - транзакциями и писать чистый поддерживаемый код.

    Telegram: @vex1re                                                                                                                                              GitHub: Vex1re
    Местоположение: Москва                                                                                                                    Английский язык: A2
    Email: ivanovmatvej4548@gmail.com                                                                                    Телефон: +7 (917) 101-05-80

    Опыт коммерческой разработки – 1 год 9 месяцев
    Август 2026 (1 месяц)
    Java Bot T-Investments - Разработал сервис с подключением к gRPC потоку.

    Июль 2026 (1 месяц)
    Сайты electrochemprogress.ru - Спроектировал клиентскую часть на React + TypeScript + Vite.
    """
    skills = ResumeExtractor.extract_skills(resume_text)

    # Valid skills must be cleanly canonicalized
    assert "Java" in skills
    assert "Spring Boot" in skills
    assert "Spring Data JPA" in skills
    assert "gRPC" in skills
    assert "PostgreSQL" in skills
    assert "MySQL" in skills
    assert "Docker" in skills
    assert "Maven" in skills
    assert "SOLID" in skills
    assert "ООП" in skills
    assert "REST API" in skills
    assert "Vite" in skills
    assert "Telegram API" in skills
    assert "Hibernate" in skills

    # Fluff and garbage MUST NOT be present
    assert "Ai skills" not in skills
    assert "Ии-агенты" not in skills
    assert "T.tech_investments" not in skills
    assert "Август 2026 (1 месяц)" not in skills
    assert "Июль 2026 (1 месяц)" not in skills
    assert "Английский язык" not in skills
    assert "Я студент 2-го курса" not in skills
    assert "Работы с grpc-потоками" not in skills

    # Casing duplicates MUST NOT exist
    assert "Grpc" not in skills
    assert "Mysql" not in skills
    assert "Postgresql" not in skills
    assert "Postgresql)" not in skills
    assert "Rest" not in skills
    assert "Solid" not in skills
    assert "Java core" not in skills
    assert "Spring boot" not in skills
    assert "Spring data jpa" not in skills
    assert "Telegram api" not in skills


