import json
from pathlib import Path
import pytest
import respx
import httpx

from services.parser.hh import HeadHunterParser
from services.parser.habr import HabrCareerParser
from services.parser.trudvsem import TrudVsemParser
from services.parser.superjob import SuperJobParser
from services.parser.remoteok import RemoteOKParser
from services.parser.kwork import KworkParser
from services.parser.fl_ru import FLRuParser
from services.parser.freelance_ru import FreelanceRuParser
from services.parser.rabota import RabotaRuParser

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _verify_vacancy_contract(vac: dict, expected_source: str):
    """Verifies that parsed vacancy satisfies the common aggregator contract."""
    assert "id" in vac and vac["id"], f"Missing id in {expected_source}"
    assert vac.get("source") == expected_source, f"Source mismatch in {expected_source}"
    assert "title" in vac and vac["title"], f"Missing title in {expected_source}"
    assert "company" in vac and vac["company"], f"Missing company in {expected_source}"
    assert "url" in vac and vac["url"].startswith("http"), f"Invalid url in {expected_source}: {vac.get('url')}"
    assert isinstance(vac.get("is_remote"), bool), f"is_remote must be bool in {expected_source}"
    assert isinstance(vac.get("is_freelance"), bool), f"is_freelance must be bool in {expected_source}"
    assert isinstance(vac.get("skills", []), list), f"skills must be list in {expected_source}"


@pytest.mark.asyncio
@respx.mock
async def test_contract_hh():
    content = json.loads((SNAPSHOTS_DIR / "hh.json").read_text(encoding="utf-8"))
    respx.get("https://api.hh.ru/vacancies").respond(status_code=200, json=content)

    parser = HeadHunterParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "hh")
    assert "FastAPI" in results[0]["description"] or "FastAPI" in str(results[0]["skills"])


@pytest.mark.asyncio
@respx.mock
async def test_contract_habr():
    html_content = (SNAPSHOTS_DIR / "habr.html").read_text(encoding="utf-8")
    respx.get("https://career.habr.com/vacancies").respond(status_code=200, text=html_content)

    parser = HabrCareerParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "habr")
    assert "Python Senior Engineer" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_trudvsem():
    content = json.loads((SNAPSHOTS_DIR / "trudvsem.json").read_text(encoding="utf-8"))
    respx.get(url__startswith="http://opendata.trudvsem.ru/api/v1/vacancies").respond(status_code=200, json=content)
    respx.get(url__startswith="https://opendata.trudvsem.ru/api/v1/vacancies").respond(status_code=200, json=content)

    parser = TrudVsemParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "trudvsem")
    assert "Ведущий программист Python" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_superjob():
    html_content = (SNAPSHOTS_DIR / "superjob.html").read_text(encoding="utf-8")
    respx.get(url__startswith="https://www.superjob.ru/vacancy/search/").respond(status_code=200, text=html_content)

    parser = SuperJobParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "superjob")
    assert "Middle Python Developer" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_remoteok():
    content = json.loads((SNAPSHOTS_DIR / "remoteok.json").read_text(encoding="utf-8"))
    respx.get(url__startswith="https://remoteok.com/api").respond(status_code=200, json=content)

    parser = RemoteOKParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "remoteok")
    assert results[0]["is_remote"] is True
    assert "Senior Backend Python Engineer" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_kwork():
    content = json.loads((SNAPSHOTS_DIR / "kwork.json").read_text(encoding="utf-8"))
    respx.post("https://kwork.ru/projects").respond(status_code=200, json=content)

    parser = KworkParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "kwork")
    assert results[0]["is_freelance"] is True
    assert "парсер" in results[0]["title"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_contract_fl_ru():
    xml_content = (SNAPSHOTS_DIR / "fl_ru.xml").read_text(encoding="utf-8")
    respx.get(url__startswith="https://www.fl.ru/rss/all.xml").respond(
        status_code=200,
        content=xml_content.encode("utf-8")
    )

    parser = FLRuParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "fl_ru")
    assert results[0]["is_freelance"] is True
    assert "Telegram" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_freelance_ru():
    html_content = (SNAPSHOTS_DIR / "freelance_ru.html").read_text(encoding="utf-8")
    respx.get(url__startswith="https://freelance.ru/task").respond(status_code=200, text=html_content)

    parser = FreelanceRuParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "freelance_ru")
    assert results[0]["is_freelance"] is True
    assert "Django" in results[0]["title"]


@pytest.mark.asyncio
@respx.mock
async def test_contract_rabota():
    html_content = (SNAPSHOTS_DIR / "rabota.html").read_text(encoding="utf-8")
    respx.get(url__startswith="https://www.rabota.ru/vacancy/").respond(status_code=200, text=html_content)

    parser = RabotaRuParser()
    results = await parser.fetch_vacancies(query="Python", limit=10)
    assert len(results) >= 1
    _verify_vacancy_contract(results[0], "rabota")
    assert "Инженер-программист Python" in results[0]["title"]
