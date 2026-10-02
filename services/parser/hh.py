import re
import datetime
import logging
from typing import List, Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class HeadHunterParser(BaseVacanciesParser):
    """
    Parser for HeadHunter (hh.ru).
    Uses public REST API when available, with automatic Web Scraper fallback
    when the REST API returns 403 or encounters errors.
    """

    API_URL = "https://api.hh.ru/vacancies"
    WEB_URL = "https://hh.ru/search/vacancy"

    HH_AREA_MAP = {
        "москва": 1,
        "санкт-петербург": 2,
        "петербург": 2,
        "спб": 2,
        "екатеринбург": 3,
        "новосибирск": 4,
        "нижний новгород": 66,
        "самара": 78,
        "казань": 88,
        "ростов-на-дону": 76,
        "ростов": 76,
        "уфа": 99,
        "красноярск": 54,
        "воронеж": 26,
        "пермь": 72,
        "волгоград": 24,
        "краснодар": 53,
        "челябинск": 104,
        "омск": 68,
        "тюмень": 95,
        "ижевск": 41,
        "барнаул": 14,
        "иркутск": 35,
        "владивосток": 22,
        "ярославль": 112,
        "хабаровск": 102,
        "махачкала": 130,
        "томск": 90,
        "оренбург": 70,
        "кемерово": 47,
        "новокузнецк": 67,
        "рязань": 79,
        "астрахань": 15,
        "пенза": 71,
        "липецк": 57,
        "тула": 92,
        "киров": 49,
        "чебоксары": 105,
        "калининград": 43,
        "сочи": 1261
    }

    def __init__(self):
        super().__init__(name="hh")

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        area_id = None
        if city:
            norm_city = city.strip().lower()
            area_id = self.HH_AREA_MAP.get(norm_city)

        params: Dict[str, Any] = {
            "text": query,
            "per_page": min(max(limit, 50), 100),
            "page": page,
            "order_by": "publication_time",
        }
        if area_id:
            params["area"] = area_id
        if remote_only:
            params["schedule"] = "remote"

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.get(self.API_URL, params=params)
                if response.status_code != 200:
                    logger.warning(
                        f"HH API returned status {response.status_code}, falling back to Web Scraper..."
                    )
                    return await self._fetch_via_web(
                        query=query,
                        limit=limit,
                        remote_only=remote_only,
                        page=page,
                        area_id=area_id,
                        city=city
                    )

                data = response.json()
                items = data.get("items", [])

                for item in items:
                    v_id = str(item.get("id"))
                    title = item.get("name", "")
                    url = item.get("alternate_url", f"https://hh.ru/vacancy/{v_id}")
                    
                    employer = item.get("employer") or {}
                    company = employer.get("name", "Не указана")

                    salary = item.get("salary")
                    salary_min = None
                    salary_max = None
                    currency = "RUB"
                    if salary:
                        salary_min = salary.get("from")
                        salary_max = salary.get("to")
                        currency = salary.get("currency") or "RUB"

                    # Snippets
                    snippet = item.get("snippet") or {}
                    req = snippet.get("requirement") or ""
                    resp = snippet.get("responsibility") or ""
                    desc = f"{req}\n{resp}".strip()
                    desc = re.sub(r"<[^>]+>", "", desc)

                    # Remote check
                    schedule = item.get("schedule") or {}
                    is_remote = schedule.get("id") == "remote"

                    # City extraction
                    area = item.get("area") or {}
                    raw_city = area.get("name") or city

                    # Parse published date
                    published_raw = item.get("published_at")
                    published_at = None
                    if published_raw:
                        try:
                            published_at = datetime.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                        except Exception:
                            published_at = datetime.datetime.now(datetime.timezone.utc)

                    # Experience check
                    exp_obj = item.get("experience") or {}
                    exp_id = exp_obj.get("id")
                    hh_min_exp = None
                    hh_max_exp = None
                    if exp_id == "noExperience":
                        hh_min_exp, hh_max_exp = 0.0, 0.0
                    elif exp_id == "between1And3":
                        hh_min_exp, hh_max_exp = 1.0, 3.0
                    elif exp_id == "between3And6":
                        hh_min_exp, hh_max_exp = 3.0, 6.0
                    elif exp_id == "moreThan6":
                        hh_min_exp, hh_max_exp = 6.0, None

                    vac = self.standardize_vacancy(
                        external_id=v_id,
                        title=title,
                        company=company,
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=raw_city,
                        published_at=published_at,
                        min_experience=hh_min_exp,
                        max_experience=hh_max_exp
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.warning(f"Error fetching from HH API ({e}), falling back to Web Scraper...")
            return await self._fetch_via_web(
                query=query,
                limit=limit,
                remote_only=remote_only,
                page=page,
                area_id=area_id,
                city=city
            )

        return vacancies

    async def _fetch_via_web(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = False,
        page: int = 0,
        area_id: Optional[int] = None,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Web fallback scraper for hh.ru search page when API is unavailable or blocked.
        """
        web_headers = {
            **self.headers,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Referer": "https://hh.ru/",
        }
        params: Dict[str, Any] = {
            "text": query,
            "page": page,
            "order_by": "publication_time",
        }
        if area_id:
            params["area"] = area_id
        elif city and city.strip().lower() in self.HH_AREA_MAP:
            params["area"] = self.HH_AREA_MAP[city.strip().lower()]
        if remote_only:
            params["schedule"] = "remote"

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=web_headers, follow_redirects=True) as client:
                response = await client.get(self.WEB_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"HH Web Search returned status {response.status_code}")
                    return []

                soup = BeautifulSoup(response.text, "html.parser")
                seen_ids = set()

                for a in soup.find_all("a", href=re.compile(r"/vacancy/(\d+)")):
                    m = re.search(r"/vacancy/(\d+)", a.get("href", ""))
                    if not m:
                        continue
                    vac_id = m.group(1)
                    if vac_id in seen_ids:
                        continue

                    title = a.get_text(strip=True)
                    if not title or len(title) < 2:
                        continue
                    seen_ids.add(vac_id)

                    url = f"https://hh.ru/vacancy/{vac_id}"

                    # Ascend to the card container
                    container = a
                    for _ in range(6):
                        if container.parent:
                            container = container.parent
                            if container.find(attrs={"data-qa": re.compile(r"vacancy-serp__vacancy-(employer|compensation|address)")}):
                                break

                    # Salary extraction
                    comp_elem = container.find(attrs={"data-qa": re.compile(r"(compensation|salary)")})
                    salary_min, salary_max, currency = self._parse_salary_text(
                        comp_elem.get_text(" ", strip=True) if comp_elem else ""
                    )

                    # Employer extraction
                    employer_elem = container.find(attrs={"data-qa": re.compile(r"(employer|company)")})
                    company = employer_elem.get_text(strip=True) if employer_elem else "Не указана"

                    # City / address extraction
                    address_elem = container.find(attrs={"data-qa": re.compile(r"(address|city|region)")})
                    vac_city = address_elem.get_text(strip=True) if address_elem else (city or ("Москва" if area_id == 1 else None))
                    if vac_city and "," in vac_city:
                        vac_city = vac_city.split(",")[0].strip()

                    # Snippets / descriptions
                    snippet_req = container.find(attrs={"data-qa": re.compile(r"requirement")})
                    snippet_resp = container.find(attrs={"data-qa": re.compile(r"responsibility")})
                    desc_parts = []
                    if snippet_req:
                        desc_parts.append(snippet_req.get_text(" ", strip=True))
                    if snippet_resp:
                        desc_parts.append(snippet_resp.get_text(" ", strip=True))
                    desc = "\n".join(desc_parts).strip()
                    desc = re.sub(r"<[^>]+>", "", desc)

                    is_remote = remote_only or any(
                        term in desc.lower() or term in title.lower()
                        for term in ["удаленн", "дистанционн", "remote"]
                    )

                    vac = self.standardize_vacancy(
                        external_id=vac_id,
                        title=title,
                        company=company,
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=vac_city,
                        published_at=datetime.datetime.now(datetime.timezone.utc)
                    )
                    vacancies.append(vac)
                    if len(vacancies) >= limit:
                        break

        except Exception as e:
            logger.error(f"Error scraping HH Web search: {e}", exc_info=True)

        return vacancies

    @staticmethod
    def _parse_salary_text(text: str) -> Tuple[Optional[int], Optional[int], str]:
        if not text:
            return None, None, "RUB"
        clean = text.replace("\xa0", " ").replace(" ", "")
        currency = "RUB"
        if "$" in text or "USD" in text:
            currency = "USD"
        elif "€" in text or "EUR" in text:
            currency = "EUR"

        match_range = re.search(r"(?:от)?(\d+)(?:до|-)(\d+)", clean, re.IGNORECASE)
        if match_range:
            return int(match_range.group(1)), int(match_range.group(2)), currency

        match_from = re.search(r"от(\d+)", clean, re.IGNORECASE)
        if match_from:
            return int(match_from.group(1)), None, currency

        match_to = re.search(r"до(\d+)", clean, re.IGNORECASE)
        if match_to:
            return None, int(match_to.group(1)), currency

        digits = re.findall(r"\d+", clean)
        if digits:
            val = int("".join(digits))
            return val, val, currency

        return None, None, currency
