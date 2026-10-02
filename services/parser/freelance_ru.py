import re
import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class FreelanceRuParser(BaseVacanciesParser):
    """
    Parser for Freelance.ru (freelance.ru) tasks and IT projects.
    Endpoint: https://freelance.ru/task?q={query}
    """

    BASE_URL = "https://freelance.ru"
    SEARCH_URL = "https://freelance.ru/task"

    def __init__(self):
        super().__init__(name="freelance_ru")
        self.is_freelance = True

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches tasks from freelance.ru matching query and page offset.
        """
        vacancies: List[Dict[str, Any]] = []

        params: Dict[str, Any] = {}
        if query and query.strip():
            params["q"] = query.strip()
        if page > 0:
            params["page"] = page + 1

        try:
            async with self.get_client() as client:
                response = await client.get(self.SEARCH_URL, params=params)

                if response.status_code != 200:
                    logger.warning(f"Freelance.ru returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select("article.task-card, .task-card")

                for card in cards[:limit]:
                    title_elem = card.select_one("a.task-card__title-link, .task-card__title a, h2 a, h3 a")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    url = f"{self.BASE_URL}{href}" if href.startswith("/") else href

                    id_match = re.search(r"/task/view/(\d+)", href) or re.search(r"/(\d+)", href)
                    external_id = id_match.group(1) if id_match else href or title

                    # Description
                    desc_elem = card.select_one("p.task-card__desc, .task-card__desc, .task-card__description")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Skills / Chips
                    chips = [c.get_text(strip=True) for c in card.select(".task-card__chips .task-chip") if c.get_text(strip=True)]

                    # Budget / Price
                    budget_elem = card.select_one(".task-card__budget, .task-card__cost")
                    budget_text = budget_elem.get_text(strip=True) if budget_elem else ""
                    salary_min, salary_max, currency = self._parse_budget(budget_text)

                    # Publication date
                    pub_date = self._parse_date(card)

                    vac = self.standardize_vacancy(
                        external_id=str(external_id),
                        title=f"Freelance.ru: {title}",
                        company="Заказчик на Freelance.ru",
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        requirements=chips if chips else None,
                        is_remote=True,
                        is_freelance=True,
                        city="Удаленно",
                        published_at=pub_date
                    )
                    vacancies.append(vac)

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(f"Network error connecting to Freelance.ru: {exc}")
        except Exception as e:
            logger.error(f"Error fetching tasks from Freelance.ru: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_budget(text: str) -> Tuple[Optional[int], Optional[int], str]:
        """
        Parses budget string into (min, max, currency).
        Examples:
        - '2 000 ₽/ заказ' -> (2000, 2000, 'RUB')
        - '10 000 - 25 000 ₽' -> (10000, 25000, 'RUB')
        - '500 $' -> (500, 500, 'USD')
        - 'Обсуждается индивидуально' -> (None, None, 'RUB')
        """
        if not text:
            return None, None, "RUB"

        lower = text.lower()
        if "обсуждается" in lower or "договор" in lower:
            return None, None, "RUB"

        currency = "RUB"
        if "$" in text or "usd" in lower:
            currency = "USD"
        elif "€" in text or "eur" in lower:
            currency = "EUR"

        clean = text.replace("\xa0", " ").replace(" ", "")

        # Check range e.g. 10000-20000
        range_match = re.search(r"(\d+)\s*[-–—..]\s*(\d+)", clean)
        if range_match:
            try:
                return int(range_match.group(1)), int(range_match.group(2)), currency
            except ValueError:
                pass

        numbers = re.findall(r"\d+", clean)
        if not numbers:
            return None, None, currency

        if len(numbers) >= 2 and ("от" in lower and "до" in lower):
            try:
                return int(numbers[0]), int(numbers[1]), currency
            except ValueError:
                pass

        if "от" in lower:
            try:
                return int(numbers[0]), None, currency
            except ValueError:
                pass

        if "до" in lower:
            try:
                return None, int(numbers[0]), currency
            except ValueError:
                pass

        try:
            val = int(numbers[0])
            return val, val, currency
        except ValueError:
            return None, None, currency

    @staticmethod
    def _parse_date(card: BeautifulSoup) -> datetime.datetime:
        """
        Parses publication date from card footer tooltip (title="01.10.2026 16:19").
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        foot_date = card.select_one(".task-card__foot .task-card__foot-item[title]")
        if not foot_date:
            return now

        title_attr = foot_date.get("title", "").strip()
        if not title_attr:
            return now

        try:
            dt = datetime.datetime.strptime(title_attr, "%d.%m.%Y %H:%M")
            return dt.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            return now
