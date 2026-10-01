import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class KworkParser(BaseVacanciesParser):
    """
    Parser for Kwork freelance project exchange (kwork.ru/projects).
    Matches freelance orders matching developer's tech stack.
    """

    BASE_URL = "https://kwork.ru"
    PROJECTS_URL = "https://kwork.ru/projects"

    def __init__(self):
        super().__init__(name="kwork")

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = True,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        params = {
            "keyword": query,
            "page": page + 1
        }

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.PROJECTS_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"Kwork returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select(".wants-card, .project-card")

                for card in cards[:limit]:
                    # Title
                    title_elem = card.select_one(".wants-card__header-title a, .project-card__title a")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    external_id = href.strip("/").split("/")[-1] if href else title

                    # Price / Budget
                    price_elem = card.select_one(".wants-card__header-price, .wants-card__price, .price")
                    price_text = price_elem.get_text(strip=True) if price_elem else ""
                    salary_min, salary_max = self._parse_budget(price_text)

                    # Description
                    desc_elem = card.select_one(".wants-card__description-text, .project-card__desc")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    vac = self.standardize_vacancy(
                        external_id=external_id,
                        title=f"💼 Заказ: {title}",
                        company="Заказчик на Kwork",
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency="RUB",
                        description=desc,
                        is_remote=True,
                        is_freelance=True,
                        city="Удаленно",
                        published_at=datetime.datetime.utcnow()
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error fetching freelance projects from Kwork: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_budget(price_text: str) -> tuple[Optional[int], Optional[int]]:
        if not price_text:
            return None, None

        clean = price_text.replace("\xa0", " ").replace(" ", "")
        numbers = re.findall(r"\d+", clean)
        if not numbers:
            return None, None

        if len(numbers) >= 2 and ("до" in price_text.lower() or "-" in price_text):
            try:
                return int(numbers[0]), int(numbers[1])
            except ValueError:
                pass

        if "до" in price_text.lower():
            try:
                return None, int(numbers[-1])
            except ValueError:
                pass

        if "от" in price_text.lower():
            try:
                return int(numbers[0]), None
            except ValueError:
                pass

        try:
            val = int(numbers[0])
            return val, val
        except ValueError:
            return None, None
