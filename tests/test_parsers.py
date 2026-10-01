import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from core.config import settings
from services.parser.hh import HeadHunterParser
from services.parser.habr import HabrCareerParser
from services.parser.kwork import KworkParser
from services.parser.rabota import RabotaRuParser
from services.parser.trudvsem import TrudVsemParser
from services.parser.fl_ru import FLRuParser
from services.parser.habr_freelance import HabrFreelanceParser
from services.parser.remoteok import RemoteOKParser
from services.parser.superjob import SuperJobParser
from services.parser.manager import AggregatorManager


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


def test_config_limits():
    assert settings.MAX_VACANCIES_PER_SOURCE == 50


@pytest.mark.asyncio
async def test_hh_parser_limits():
    parser = HeadHunterParser()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "999",
                "name": "Backend Python Engineer",
                "alternate_url": "https://hh.ru/vacancy/999",
                "employer": {"name": "Yandex"},
                "salary": {"from": 200000, "to": 300000, "currency": "RUR"},
                "snippet": {"requirement": "Python, Django", "responsibility": "Backend dev"},
                "schedule": {"id": "remote"},
                "area": {"name": "Москва"},
                "published_at": "2026-10-01T12:00:00Z"
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="python", limit=50, remote_only=True, page=1)

        assert len(results) == 1
        assert results[0]["id"] == "hh_999"
        assert results[0]["is_remote"] is True
        assert results[0]["salary_min"] == 200000
        # Verify requested per_page and page
        args, kwargs = mock_get.call_args
        assert kwargs["params"]["per_page"] == 50
        assert kwargs["params"]["page"] == 1
        assert kwargs["params"]["schedule"] == "remote"


@pytest.mark.asyncio
async def test_trudvsem_parser():
    parser = TrudVsemParser()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": {
            "vacancies": [
                {
                    "vacancy": {
                        "id": "trud-123",
                        "job-name": "Программист Python",
                        "vac_url": "https://trudvsem.ru/vacancy/card/123",
                        "company": {"name": "НИИ Технологий"},
                        "salary_min": 120000,
                        "salary_max": 0,
                        "currency": "«руб.»",
                        "duty": "Разработка бэкенда на Python и FastApi.",
                        "requirement": {"education": "Высшее", "experience": 3},
                        "schedule": "Дистанционная работа",
                        "region": {"name": "Самарская область"},
                        "addresses": {"address": [{"location": "г. Самара, ул. Мира, 1"}]},
                        "creation-date": "2026-10-01"
                    }
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="python", limit=50, page=0)

        assert len(results) == 1
        vac = results[0]
        assert vac["id"] == "trudvsem_trud-123"
        assert vac["title"] == "Программист Python"
        assert vac["company"] == "НИИ Технологий"
        assert vac["salary_min"] == 120000
        assert vac["salary_max"] is None  # 0 converted to None
        assert vac["currency"] == "RUB"
        assert vac["is_remote"] is True
        assert vac["city"] == "Самара"
        assert "FastAPI" in vac["requirements"]


@pytest.mark.asyncio
async def test_trudvsem_parser_failure_resilience():
    parser = TrudVsemParser()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Timed out")
        results = await parser.fetch_vacancies(query="python")
        assert results == []


def test_fl_ru_budget_parser():
    s_min, s_max, curr = FLRuParser._parse_budget("Требуется доработка (Бюджет: 35 000 руб)")
    assert s_min == 35000
    assert s_max == 35000
    assert curr == "RUB"

    s_min2, s_max2, curr2 = FLRuParser._parse_budget("Разработка сайта (от 50 000 до 100 000 ₽)")
    assert s_min2 == 50000
    assert s_max2 == 100000
    assert curr2 == "RUB"

    s_min3, s_max3, curr3 = FLRuParser._parse_budget("Fix bug (Budget: $200)")
    assert s_min3 == 200
    assert curr3 == "USD"


@pytest.mark.asyncio
async def test_fl_ru_parser():
    parser = FLRuParser()
    xml_content = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
      <channel>
        <title>FL.ru RSS</title>
        <item>
          <title><![CDATA[Python-разработчик: парсер данных (Бюджет: 20 000 &#8381;)]]></title>
          <link>https://www.fl.ru/projects/5524119/python-razrabotchik.html</link>
          <guid>https://www.fl.ru/projects/5524119/python-razrabotchik.html</guid>
          <description><![CDATA[Нужно написать асинхронный парсер на Python с сохранением в PostgreSQL.]]></description>
          <pubDate>Thu, 01 Oct 2026 21:36:13 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_content

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="python", limit=50)

        assert len(results) == 1
        vac = results[0]
        assert vac["id"] == "fl_ru_5524119"
        assert "FL.ru" in vac["title"]
        assert vac["salary_min"] == 20000
        assert vac["salary_max"] == 20000
        assert vac["currency"] == "RUB"
        assert vac["is_freelance"] is True
        assert vac["is_remote"] is True
        assert vac["city"] == "Удаленно"
        assert "PostgreSQL" in vac["requirements"]


@pytest.mark.asyncio
async def test_habr_freelance_parser():
    parser = HabrFreelanceParser()
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Хабр Фриланс Заказы</title>
        <item>
          <title><![CDATA[Telegram-бот на aiogram 3 (Бюджет: 15 000 руб)]]></title>
          <link>https://freelance.habr.com/tasks/12345</link>
          <guid>https://freelance.habr.com/tasks/12345</guid>
          <description><![CDATA[Разработка бота на aiogram и SQLite для рассылки сообщений.]]></description>
          <category><![CDATA[Python]]></category>
          <category><![CDATA[Telegram API]]></category>
          <pubDate>Thu, 01 Oct 2026 20:00:00 GMT</pubDate>
        </item>
      </channel>
    </rss>
    """.encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_content

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="aiogram", limit=10)

        assert len(results) == 1
        vac = results[0]
        assert vac["id"] == "habr_freelance_12345"
        assert vac["is_freelance"] is True
        assert vac["is_remote"] is True
        assert vac["city"] == "Удаленно"
        assert vac["salary_min"] == 15000
        assert "Python" in vac["requirements"]


@pytest.mark.asyncio
async def test_habr_freelance_410_handled():
    parser = HabrFreelanceParser()
    mock_resp = MagicMock()
    mock_resp.status_code = 410  # Service retired
    mock_resp.content = b"Service retired"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="python")
        assert results == []


@pytest.mark.asyncio
async def test_remoteok_parser():
    parser = RemoteOKParser()
    data = [
        {"legal": "Terms of service"},
        {
            "id": "8877",
            "position": "Senior Backend Engineer",
            "company": "Tech Global",
            "salary_min": 120000,
            "salary_max": 160000,
            "tags": ["python", "django", "aws", "docker"],
            "url": "https://remoteok.com/remote-jobs/8877",
            "apply_url": "https://remoteok.com/apply/8877",
            "description": "We are seeking a senior python engineer.",
            "date": "2026-10-01T10:00:00Z"
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = data

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        results = await parser.fetch_vacancies(query="python", limit=10)

        assert len(results) == 1
        vac = results[0]
        assert vac["id"] == "remoteok_8877"
        assert "[RemoteOK] Senior Backend Engineer" == vac["title"]
        assert vac["company"] == "Tech Global"
        assert vac["salary_min"] == 120000
        assert vac["salary_max"] == 160000
        assert vac["currency"] == "USD"
        assert vac["is_remote"] is True
        assert vac["city"] == "Удаленно"
        assert "docker" in vac["requirements"]


@pytest.mark.asyncio
async def test_superjob_parser_api():
    parser = SuperJobParser()
    data = {
        "objects": [
            {
                "id": "54321",
                "profession": "Python Разработчик",
                "link": "https://www.superjob.ru/vakansii/python-54321.html",
                "client": {"title": "СберТех"},
                "payment_from": 180000,
                "payment_to": 250000,
                "currency": "rub",
                "town": {"title": "Москва"},
                "type_of_work": {"id": 6},
                "candidat": "Опыт разработки на Python от 3 лет, FastAPI, asyncpg.",
                "date_published": 1790792682
            }
        ]
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = data

    with patch("core.config.settings.SUPERJOB_API_KEY", "test-secret-key"):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            results = await parser.fetch_vacancies(query="python", limit=50)

            assert len(results) == 1
            vac = results[0]
            assert vac["id"] == "superjob_54321"
            assert vac["title"] == "Python Разработчик"
            assert vac["company"] == "СберТех"
            assert vac["salary_min"] == 180000
            assert vac["salary_max"] == 250000
            assert vac["currency"] == "RUB"
            assert vac["is_remote"] is True
            assert vac["city"] == "Москва"


@pytest.mark.asyncio
async def test_superjob_parser_web():
    parser = SuperJobParser()
    html_page = """
    <html>
      <head><title>Вакансии Python на SuperJob</title></head>
      <body>
        <div class="f-test-vacancy-item">
          <a class="f-test-link-title" href="/vakansii/developer-112233.html">Python Middle Developer</a>
          <span class="company-name">SuperJob Client</span>
          <span class="salary">от 150 000 до 200 000 руб.</span>
          <span class="location">г. Санкт-Петербург (удаленно)</span>
          <div class="description">Разработка высоконагруженных микросервисов на Python.</div>
        </div>
      </body>
    </html>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = html_page

    with patch("core.config.settings.SUPERJOB_API_KEY", None):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            results = await parser.fetch_vacancies(query="python", limit=50)

            assert len(results) == 1
            vac = results[0]
            assert vac["id"] == "superjob_112233"
            assert vac["title"] == "Python Middle Developer"
            assert vac["salary_min"] == 150000
            assert vac["salary_max"] == 200000
            assert vac["is_remote"] is True
            assert vac["city"] == "Санкт-Петербург"


def test_aggregator_manager_registered_parsers():
    manager = AggregatorManager()
    parser_names = [p.name for p in manager.parsers]
    expected = [
        "hh",
        "habr",
        "trudvsem",
        "superjob",
        "remoteok",
        "kwork",
        "fl_ru",
        "habr_freelance",
        "rabota"
    ]
    for exp in expected:
        assert exp in parser_names, f"Parser {exp} not registered in AggregatorManager"


@pytest.mark.asyncio
async def test_aggregator_manager_freelance_filtering():
    manager = AggregatorManager()
    
    # Mock all parsers returning 1 item each
    for p in manager.parsers:
        p.fetch_vacancies = AsyncMock(return_value=[{
            "id": f"{p.name}_1",
            "url": f"https://example.com/{p.name}/1",
            "source": p.name
        }])

    # 1. When include_freelance is False
    res_no_freelance = await manager.fetch_all_for_query(
        query="python",
        include_freelance=False
    )
    sources_no_fl = [r["source"] for r in res_no_freelance]
    assert "kwork" not in sources_no_fl
    assert "fl_ru" not in sources_no_fl
    assert "habr_freelance" not in sources_no_fl
    assert "hh" in sources_no_fl
    assert "trudvsem" in sources_no_fl
    assert "remoteok" in sources_no_fl

    # 2. When include_freelance is True
    res_with_freelance = await manager.fetch_all_for_query(
        query="python",
        include_freelance=True
    )
    sources_with_fl = [r["source"] for r in res_with_freelance]
    assert "kwork" in sources_with_fl
    assert "fl_ru" in sources_with_fl
    assert "habr_freelance" in sources_with_fl
