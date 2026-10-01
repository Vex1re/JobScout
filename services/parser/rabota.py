import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class RabotaRuParser(BaseVacanciesParser):
    """
    Parser for Rabota.ru (работа.ру).
    """

    BASE_URL = "https://www.rabota.ru"
    SEARCH_URL = "https://www.rabota.ru/vacancy/"

    def __init__(self):
        super().__init__(name="rabota")

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        from services.parser.normalizer import CityNormalizer

        params = {
            "query": query,
            "sort": "date",
            "page": page + 1
        }
        if remote_only:
            params["remote_work"] = "1"

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.SEARCH_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"Rabota.ru returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select(".vacancy-preview-card, article.vacancy-card, .vacancies-list__item")

                for card in cards[:limit]:
                    title_elem = card.select_one("a.vacancy-preview-card__title, .vacancy-card__title a, h3 a")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    external_id = re.search(r"/vacancy/(\d+)", href)
                    v_id = external_id.group(1) if external_id else title

                    # Company
                    company_elem = card.select_one(".vacancy-preview-card__company-name, .vacancy-card__company-title")
                    company = company_elem.get_text(strip=True) if company_elem else "Компания на Работа.ру"

                    # Salary
                    salary_elem = card.select_one(".vacancy-preview-card__salary, .vacancy-card__salary")
                    salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
                    salary_min, salary_max = self._parse_salary(salary_text)

                    # Snippet / Description
                    desc_elem = card.select_one(".vacancy-preview-card__description, .vacancy-card__description")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    # City / Location
                    city_elem = card.select_one(
                        ".vacancy-preview-card__location, .vacancy-card__location, .vacancy-card__town, .vacancy-preview-card__city"
                    )
                    raw_city = city_elem.get_text(strip=True) if city_elem else None
                    city = CityNormalizer.normalize(raw_city)

                    is_remote = "удален" in (title + " " + desc + " " + (raw_city or "")).lower()

                    vac = self.standardize_vacancy(
                        external_id=str(v_id),
                        title=title,
                        company=company,
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency="RUB",
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=city,
                        published_at=datetime.datetime.utcnow()
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error fetching vacancies from Rabota.ru: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_salary(salary_text: str) -> tuple[Optional[int], Optional[int]]:
        if not salary_text:
            return None, None

        clean = salary_text.replace("\xa0", " ").replace(" ", "")
        numbers = re.findall(r"\d+", clean)
        if not numbers:
            return None, None

        if len(numbers) >= 2:
            try:
                return int(numbers[0]), int(numbers[1])
            except ValueError:
                pass

        if "от" in salary_text.lower():
            try:
                return int(numbers[0]), None
            except ValueError:
                pass

        if "до" in salary_text.lower():
            try:
                return None, int(numbers[0])
            except ValueError:
                pass

        try:
            val = int(numbers[0])
            return val, val
        except ValueError:
            return None, None
