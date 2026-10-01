import pytest
from services.parser.hh import HeadHunterParser
from services.parser.habr import HabrCareerParser
from services.parser.kwork import KworkParser
from services.parser.rabota import RabotaRuParser


def test_standardize_vacancy():
    parser = HeadHunterParser()
    vac = parser.standardize_vacancy(
        external_id="12345",
        title="Python Developer",
        company="Tech Corp",
        url="https://hh.ru/vacancy/12345",
        salary_min=150000,
        salary_max=220000,
        currency="RUR",
        description="Разработка на Python, FastAPI и PostgreSQL.",
        is_remote=True
    )

    assert vac["id"] == "hh_12345"
    assert vac["currency"] == "RUB"
    assert vac["is_remote"] is True
    assert vac["city"] == "Удаленно"
    assert "FastAPI" in vac["requirements"]
    assert vac["risk_level"] == "safe"

    vac_office = parser.standardize_vacancy(
        external_id="12346",
        title="Office Developer",
        company="Tech Corp",
        url="https://hh.ru/vacancy/12346",
        salary_min=100000,
        salary_max=150000,
        currency="RUB",
        description="Python",
        is_remote=False,
        city="г. Москва"
    )
    assert vac_office["city"] == "Москва"


def test_kwork_budget_parser():
    min_val, max_val = KworkParser._parse_budget("до 25 000 руб.")
    assert max_val == 25000

    min_val2, max_val2 = KworkParser._parse_budget("от 10 000 до 30 000 руб.")
    assert min_val2 == 10000
    assert max_val2 == 30000


def test_habr_salary_parser():
    s_min, s_max, curr = HabrCareerParser._parse_salary("от 200 000 до 350 000 ₽")
    assert s_min == 200000
    assert s_max == 350000
    assert curr == "RUB"
