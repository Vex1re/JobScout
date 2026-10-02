import re
import html
import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup

from core.config import settings
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class SuperJobParser(BaseVacanciesParser):
    """
    Parser for SuperJob (superjob.ru) vacancies.
    Supports official SuperJob REST API when SUPERJOB_API_KEY is configured in settings,
    with fallback to web search: https://www.superjob.ru/vacancy/search/?keywords={query}&page={page}.
    """

    BASE_URL = "https://www.superjob.ru"
    WEB_SEARCH_URL = "https://www.superjob.ru/vacancy/search/"
    API_URL = "https://api.superjob.ru/2.0/vacancies/"

    SUPERJOB_TOWN_MAP = {
        "москва": 4,
        "санкт-петербург": 14,
        "петербург": 14,
        "спб": 14,
        "казань": 48,
        "новосибирск": 75,
        "екатеринбург": 33,
        "нижний новгород": 66,
        "самара": 86,
        "краснодар": 53,
        "ростов-на-дону": 83,
        "уфа": 99,
        "воронеж": 25,
        "пермь": 76,
        "волгоград": 22,
        "красноярск": 54,
        "челябинск": 111,
        "омск": 73,
    }

    def __init__(self):
        super().__init__(name="superjob")
        self.is_freelance = False

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        api_key = getattr(settings, "SUPERJOB_API_KEY", None)

        if api_key:
            return await self._fetch_via_api(query=query, limit=limit, remote_only=remote_only, page=page, api_key=api_key, city=city)
        else:
            return await self._fetch_via_web(query=query, limit=limit, remote_only=remote_only, page=page, city=city)

    async def _fetch_via_api(
        self,
        query: str,
        limit: int,
        remote_only: bool,
        page: int,
        api_key: str,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from services.parser.normalizer import CityNormalizer

        headers = {
            **self.headers,
            "X-Api-App-Id": api_key
        }
        params: Dict[str, Any] = {
            "keyword": query,
            "count": min(max(limit, 10), 100),
            "page": page,
            "order_by[date]": "desc"
        }
        if city:
            town_id = self.SUPERJOB_TOWN_MAP.get(city.strip().lower())
            if town_id:
                params["town"] = town_id

        if remote_only:
            params["type_of_work"] = 6  # SuperJob remote work type

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=headers, follow_redirects=True) as client:
                response = await client.get(self.API_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"SuperJob API returned status {response.status_code}")
                    return []

                data = response.json()
                objects = data.get("objects", [])

                for item in objects:
                    v_id = str(item.get("id"))
                    title = item.get("profession") or ""
                    link = item.get("link") or f"{self.BASE_URL}/vakansii/{v_id}.html"

                    client_obj = item.get("client") or {}
                    company = client_obj.get("title") or item.get("firm_name") or "Работодатель на SuperJob"

                    s_min = item.get("payment_from")
                    s_max = item.get("payment_to")
                    salary_min = int(s_min) if s_min and int(s_min) > 0 else None
                    salary_max = int(s_max) if s_max and int(s_max) > 0 else None

                    currency = (item.get("currency") or "rub").upper()
                    if currency in ["RUR", "РУБ", "₽"]:
                        currency = "RUB"

                    town = item.get("town") or {}
                    raw_city = town.get("title")
                    city = CityNormalizer.normalize(raw_city)

                    type_of_work = item.get("type_of_work") or {}
                    is_remote = type_of_work.get("id") == 6 or "удален" in str(raw_city or "").lower()

                    desc = item.get("candidat") or item.get("work") or ""
                    desc = re.sub(r"<[^>]+>", " ", desc).strip()

                    pub_raw = item.get("date_published")
                    published_at = None
                    if pub_raw:
                        try:
                            published_at = datetime.datetime.fromtimestamp(int(pub_raw), tz=datetime.timezone.utc)
                        except Exception:
                            pass

                    vac = self.standardize_vacancy(
                        external_id=v_id,
                        title=title,
                        company=company,
                        url=link,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=city,
                        published_at=published_at or datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error fetching vacancies via SuperJob API: {e}", exc_info=True)

        return vacancies

    async def _fetch_via_web(
        self,
        query: str,
        limit: int,
        remote_only: bool,
        page: int,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from services.parser.normalizer import CityNormalizer

        params: Dict[str, Any] = {
            "keywords": query,
            "page": page + 1
        }
        if city:
            town_id = self.SUPERJOB_TOWN_MAP.get(city.strip().lower())
            if town_id:
                params["town"] = town_id
        if remote_only:
            params["geo[t][0]"] = "4"  # Remote work option in SuperJob

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(self.WEB_SEARCH_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"SuperJob web search returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                page_title = soup.title.get_text() if soup.title else ""

                if "captcha" in page_title.lower():
                    logger.warning("SuperJob web search encountered anti-bot captcha challenge")
                    return []

                # Find vacancy items by common selectors
                cards = soup.select(
                    "article, div[class*='vacancy-item'], div[class*='f-test-vacancy-item'], div[class*='VacancyItem']"
                )

                if not cards:
                    # Fallback: look for /vakansii/ links
                    links = soup.find_all("a", href=lambda h: h and "/vakansii/" in h)
                    seen_links = set()
                    for a in links:
                        href = a.get("href", "")
                        if href in seen_links:
                            continue
                        seen_links.add(href)
                        title_text = a.get_text(strip=True)
                        if len(title_text) >= 5:
                            # Use link as minimalist card
                            id_match = re.search(r"-(\d+)\.html", href)
                            v_id = id_match.group(1) if id_match else href
                            full_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                            vac = self.standardize_vacancy(
                                external_id=str(v_id),
                                title=title_text,
                                company="Работодатель на SuperJob",
                                url=full_url,
                                salary_min=None,
                                salary_max=None,
                                currency="RUB",
                                description="",
                                is_remote=remote_only,
                                is_freelance=False,
                                city="Удаленно" if remote_only else None,
                                published_at=datetime.datetime.now(datetime.timezone.utc)
                            )
                            vacancies.append(vac)
                            if len(vacancies) >= limit:
                                break
                    return vacancies

                for card in cards[:limit]:
                    # Title & link
                    title_elem = card.select_one("a[href*='/vakansii/'], h3 a, h2 a, .f-test-link-title")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    href = title_elem.get("href", "")
                    full_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                    id_match = re.search(r"-(\d+)\.html", href) or re.search(r"/(\d+)\.html", href)
                    v_id = id_match.group(1) if id_match else href or title

                    # Company
                    comp_elem = card.select_one("a[href*='/clients/'], [class*='company-name'], [class*='ClientTitle']")
                    company = comp_elem.get_text(strip=True) if comp_elem else "Работодатель на SuperJob"

                    # Salary
                    salary_elem = card.select_one("[class*='salary'], [class*='Payment'], span:-soup-contains('₽'), span:-soup-contains('руб')")
                    salary_text = salary_elem.get_text(strip=True) if salary_elem else ""
                    s_min, s_max, currency = self._parse_salary(salary_text)

                    # Location / City
                    loc_elem = card.select_one("[class*='location'], [class*='Town'], [class*='metro']")
                    raw_city = loc_elem.get_text(strip=True) if loc_elem else ""
                    city = CityNormalizer.normalize(raw_city)

                    # Remote check
                    full_text = card.get_text(separator=" ", strip=True).lower()
                    is_remote = "удален" in full_text or "дистанцион" in full_text

                    # Description / Snippet
                    desc_elem = card.select_one("[class*='description'], [class*='snippet'], [class*='VacancyInfo']")
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    vac = self.standardize_vacancy(
                        external_id=str(v_id),
                        title=title,
                        company=company,
                        url=full_url,
                        salary_min=s_min,
                        salary_max=s_max,
                        currency=currency,
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=city,
                        published_at=datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)

        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(f"Network error querying SuperJob web search: {exc}")
        except Exception as e:
            logger.error(f"Error scraping SuperJob web search: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_salary(salary_text: str) -> Tuple[Optional[int], Optional[int], str]:
        if not salary_text:
            return None, None, "RUB"

        clean = html.unescape(salary_text).replace("\xa0", " ").strip()
        currency = "RUB"
        if "$" in clean or "usd" in clean.lower():
            currency = "USD"
        elif "€" in clean or "eur" in clean.lower():
            currency = "EUR"

        # Check range: '150 000 — 200 000 руб' or 'от 100 000 до 150 000'
        range_match = re.search(
            r"(?:от\s*)?(\d[\d\s]*\d)\s*(?:до|—|-)\s*(\d[\d\s]*\d)",
            clean,
            flags=re.IGNORECASE
        )
        if range_match:
            try:
                min_v = int(re.sub(r"\s+", "", range_match.group(1)))
                max_v = int(re.sub(r"\s+", "", range_match.group(2)))
                return min_v, max_v, currency
            except ValueError:
                pass

        # Check 'от 100 000'
        from_match = re.search(r"от\s*(\d[\d\s]*\d)", clean, flags=re.IGNORECASE)
        if from_match:
            try:
                min_v = int(re.sub(r"\s+", "", from_match.group(1)))
                return min_v, None, currency
            except ValueError:
                pass

        # Check 'до 200 000'
        to_match = re.search(r"до\s*(\d[\d\s]*\d)", clean, flags=re.IGNORECASE)
        if to_match:
            try:
                max_v = int(re.sub(r"\s+", "", to_match.group(1)))
                return None, max_v, currency
            except ValueError:
                pass

        # Single number
        single_match = re.search(r"(\d[\d\s]*\d)\s*(?:руб|₽|\$|eur|usd)?", clean, flags=re.IGNORECASE)
        if single_match:
            try:
                val = int(re.sub(r"\s+", "", single_match.group(1)))
                if val > 1000:
                    return val, val, currency
            except ValueError:
                pass

        return None, None, currency
