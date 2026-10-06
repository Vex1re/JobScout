import pytest
from services.deduplication import (
    generate_canonical_id,
    compute_simhash,
    simhash_distance,
    deduplicate_vacancies,
    normalize_company_name,
    normalize_title
)


def test_normalize_company_and_title():
    assert normalize_company_name("ООО 'Яндекс Технологии'") == "яндекс технологии"
    assert normalize_company_name("ПАО Сбербанк, г. Москва") == "сбербанк г москва"
    assert normalize_company_name("Google LLC") == "google"
    assert normalize_company_name(None) == "unknown"

    assert normalize_title("Senior Python Developer (FastAPI / Docker)") == "senior python developer fastapi docker"
    assert normalize_title(None) == "unknown"


def test_canonical_id_stability():
    cid1 = generate_canonical_id(
        company="ООО Яндекс",
        title="Python Developer",
        city="Москва",
        salary_from=150000,
        salary_to=200000
    )
    cid2 = generate_canonical_id(
        company="Яндекс LLC",
        title="python developer",
        city="г. Москва",
        salary_from=160000,
        salary_to=190000
    )
    assert cid1 == cid2, f"Expected identical canonical IDs, got {cid1} vs {cid2}"


def test_simhash_near_duplicates():
    text1 = "Ищем опытного Python разработчика со знанием FastAPI, PostgreSQL и Docker. Удаленная работа."
    text2 = "Ищем опытного Python разработчика со знанием FastAPI, PostgreSQL и Docker. Полностью удаленная работа."
    different_text = "Требуется шеф-повар итальянской кухни в ресторан в центре города. Опыт от 3 лет."

    h1 = compute_simhash(text1)
    h2 = compute_simhash(text2)
    h3 = compute_simhash(different_text)

    dist_near = simhash_distance(h1, h2)
    dist_far = simhash_distance(h1, h3)

    assert dist_near <= 8, f"Near duplicates should have small distance, got {dist_near}"
    assert dist_far >= 15, f"Different texts should have large distance, got {dist_far}"


def test_collapse_cross_source_duplicates():
    vacancies = [
        {
            "id": "hh_12345",
            "source": "hh",
            "title": "Senior Python Developer",
            "company": "ООО Финтех Софт",
            "city": "Москва",
            "url": "https://hh.ru/vacancy/12345",
            "salary_min": 200000,
            "salary_max": 250000,
            "description": "Short description"
        },
        {
            "id": "superjob_98765",
            "source": "superjob",
            "title": "Senior Python Developer",
            "company": "Финтех Софт",
            "city": "Москва",
            "url": "https://superjob.ru/vacancy/98765",
            "salary_min": 200000,
            "salary_max": 270000,
            "description": "Detailed and longer description with stack: Python, Django, PostgreSQL, Docker."
        }
    ]

    deduped = deduplicate_vacancies(vacancies)
    assert len(deduped) == 1
    collapsed = deduped[0]

    assert set(collapsed["sources"]) == {"hh", "superjob"}
    assert collapsed["source_urls"]["hh"] == "https://hh.ru/vacancy/12345"
    assert collapsed["source_urls"]["superjob"] == "https://superjob.ru/vacancy/98765"
    assert "Django" in collapsed["description"]
    assert collapsed["salary_max"] == 270000
