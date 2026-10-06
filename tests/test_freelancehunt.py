import pytest
import respx
import httpx
from core.config import settings
from services.parser.freelancehunt import FreelancehuntParser


@pytest.mark.asyncio
async def test_freelancehunt_disabled_by_default():
    parser = FreelancehuntParser()
    # By default ENABLE_FREELANCEHUNT is False
    assert parser.enabled is False
    results = await parser.fetch_vacancies(query="Python")
    assert results == []


@pytest.mark.asyncio
async def test_freelancehunt_warning_on_missing_token(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ENABLE_FREELANCEHUNT", True)
    monkeypatch.setattr(settings, "FREELANCEHUNT_API_TOKEN", None)

    parser = FreelancehuntParser()
    assert parser.enabled is True
    assert parser.api_token is None

    results = await parser.fetch_vacancies(query="Python")
    assert results == []


@pytest.mark.asyncio
@respx.mock
async def test_freelancehunt_parses_projects_with_token(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_FREELANCEHUNT", True)
    monkeypatch.setattr(settings, "FREELANCEHUNT_API_TOKEN", "fake_token_123")

    mock_response = {
        "data": [
            {
                "id": 999111,
                "type": "project",
                "attributes": {
                    "name": "Разработка Telegram бота на Python",
                    "description": "Нужно написать бота с интеграцией PostgreSQL и Aiogram 3.",
                    "url": "https://freelancehunt.com/project/999111.html",
                    "budget": {
                        "amount": 25000,
                        "currency": "RUB"
                    },
                    "employer": {
                        "login": "client_pro"
                    }
                }
            }
        ]
    }

    respx.get("https://api.freelancehunt.com/v2/projects").mock(
        return_value=httpx.Response(200, json=mock_response)
    )

    parser = FreelancehuntParser()
    results = await parser.fetch_vacancies(query="Python", limit=5)

    assert len(results) == 1
    item = results[0]
    assert item["id"] == "freelancehunt_999111"
    assert item["title"] == "Разработка Telegram бота на Python"
    assert item["salary_min"] == 25000
    assert item["currency"] == "RUB"
    assert item["is_freelance"] is True
    assert item["company"] == "client_pro"
