import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class HabrCareerParser(BaseVacanciesParser):
    """
    Parser for Habr Career (career.habr.com).
    """

    BASE_URL = "https://career.habr.com"
    SEARCH_URL = "https://career.habr.com/vacancies"

    HABR_CITY_MAP = {
        "москва": 678,
        "санкт-петербург": 679,
        "петербург": 679,
        "спб": 679,
        "казань": 693,
        "новосибирск": 682,
        "екатеринбург": 680,
        "нижний новгород": 681,
        "самара": 699,
        "краснодар": 703,
        "ростов-на-дону": 686,
        "ростов": 686,
        "воронеж": 687,
        "уфа": 695,
        "пермь": 689,
        "красноярск": 684,
        "челябинск": 683,
        "омск": 685,
        "волгоград": 688,
        "тюмень": 698,
        "томск": 691,
        "иркутск": 696,
        "ярославль": 701,
        "владивосток": 692,
        "сочи": 757,
        "калининград": 702
    }

    def __init__(self):
        super().__init__(name="habr")

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from services.parser.normalizer import CityNormalizer

        params: Dict[str, Any] = {
            "q": query,
            "sort": "date",
            "type": "all",
            "page": page + 1
        }
        if city:
            norm_city = city.strip().lower()
            city_id = self.HABR_CITY_MAP.get(norm_city)
            if city_id:
                params["city_id"] = city_id

        if remote_only:
            params["remote"] = "1"

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.SEARCH_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"Habr Career returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                cards = soup.select(".vacancy-card")

                for card in cards[:limit]:
                    # Extract title and link
                    title_elem = card.select_one(".vacancy-card__title a")
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    external_id = href.split("/")[-1] if href else title

                    # Extract company
                    company_elem = card.select_one(".vacancy-card__company-title a")
                    company = company_elem.get_text(strip=True) if company_elem else "Компания на Хабр Карьере"

                    # Extract salary
                    salary_elem = card.select_one(".vacancy-card__salary")
                    salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
                    salary_min, salary_max, currency = self._parse_salary(salary_text)

                    # Extract skills badges
                    skills_elems = card.select(".vacancy-card__skills a, .preserve-line")
                    skills = [s.get_text(strip=True) for s in skills_elems if s.get_text(strip=True)]

                    # Meta info (remote, city, etc.)
                    meta_elem = card.select_one(".vacancy-card__meta")
                    unique_meta = []
                    if meta_elem:
                        meta_items = [
                            s.get_text(strip=True)
                            for s in meta_elem.find_all(True)
                            if s.get_text(strip=True) and not s.find_all(True)
                        ]
                        if not meta_items:
                            meta_items = [
                                part.strip()
                                for part in meta_elem.get_text(separator=" • ", strip=True).split("•")
                                if part.strip()
                            ]
                        seen_meta = set()
                        for item in meta_items:
                            item_fixed = re.sub(r"(удаленно|удалённо)([А-ЯA-Z])", r"\1 • \2", item, flags=re.IGNORECASE)
                            for subpart in item_fixed.split("•"):
                                subpart = subpart.strip()
                                if subpart and subpart.lower() not in seen_meta:
                                    seen_meta.add(subpart.lower())
                                    unique_meta.append(subpart)
                        meta_text = " • ".join(unique_meta)
                    else:
                        meta_text = ""

                    is_remote = "удален" in meta_text.lower() or "remote" in meta_text.lower()

                    # Extract city from meta tokens
                    city = None
                    for token in unique_meta:
                        norm = CityNormalizer.normalize(token)
                        if norm and norm != "Удаленно":
                            city = norm
                            break

                    desc = f"Навыки: {', '.join(skills)}\nУсловия: {meta_text}" if meta_text else f"Навыки: {', '.join(skills)}"

                    vac = self.standardize_vacancy(
                        external_id=external_id,
                        title=title,
                        company=company,
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=city,
                        requirements=skills,
                        published_at=datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error fetching vacancies from Habr Career: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_salary(salary_text: str) -> tuple[Optional[int], Optional[int], str]:
        if not salary_text:
            return None, None, "RUB"

        clean = salary_text.replace("\xa0", " ").replace(" ", "")
        salary_min = None
        salary_max = None
        currency = "RUB"

        if "$" in clean or "usd" in clean.lower():
            currency = "USD"
        elif "€" in clean or "eur" in clean.lower():
            currency = "EUR"

        min_match = re.search(r"от(\d+)", clean)
        max_match = re.search(r"до(\d+)", clean)

        if min_match:
            try:
                salary_min = int(min_match.group(1))
            except ValueError:
                pass

        if max_match:
            try:
                salary_max = int(max_match.group(1))
            except ValueError:
                pass

        return salary_min, salary_max, currency
