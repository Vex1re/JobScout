import re
import datetime
import logging
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import httpx
from bs4 import BeautifulSoup
from services.parser.base import BaseVacanciesParser
from services.resume_analyzer.extractor import ResumeExtractor, TECH_SKILLS_MAP

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
        self._api_disabled: bool = False
        self._details_cache: Dict[str, Tuple[float, str, List[str], Optional[float], Optional[float]]] = {}

    async def _fetch_vacancy_details(
        self,
        client: httpx.AsyncClient,
        vac_id: str
    ) -> Tuple[str, List[str], Optional[float], Optional[float], Optional[str]]:
        """
        Fetches full vacancy description, key skills tags, required experience and employer from hh.ru/vacancy/{id}.
        Uses internal TTL cache (2h) to avoid redundant requests.
        """
        now = time.time()
        cached = self._details_cache.get(vac_id)
        if cached:
            ts, desc, skills, min_exp, max_exp, comp = cached
            if now - ts < 7200:
                return desc, skills, min_exp, max_exp, comp

        url = f"https://hh.ru/vacancy/{vac_id}"
        desc = ""
        skills: List[str] = []
        min_exp: Optional[float] = None
        max_exp: Optional[float] = None
        comp: Optional[str] = None

        try:
            res = await client.get(url, timeout=self.timeout)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")

                # 1. Full description
                desc_el = (
                    soup.find(attrs={"data-qa": "vacancy-description"})
                    or soup.find(class_=lambda c: c and "vacancy-description" in c)
                )
                if desc_el:
                    desc = desc_el.get_text("\n", strip=True)
                    desc = re.sub(r"<[^>]+>", "", desc)

                # 2. Key skills tags
                skill_tags = soup.find_all(
                    attrs={"data-qa": re.compile(r"(skills-element|bloko-tag__text)")}
                )
                for st in skill_tags:
                    raw_tag = st.get_text(strip=True)
                    if not raw_tag:
                        continue
                    clean_tag = ResumeExtractor._normalize_token(raw_tag)
                    if clean_tag and not ResumeExtractor._is_garbage_token(clean_tag.lower()):
                        low_tag = clean_tag.lower()
                        if low_tag in TECH_SKILLS_MAP:
                            clean_tag = TECH_SKILLS_MAP[low_tag]
                        if clean_tag not in skills:
                            skills.append(clean_tag)

                # 3. Required experience if present on page
                exp_el = soup.find(attrs={"data-qa": "vacancy-experience"})
                if exp_el:
                    exp_text = exp_el.get_text(strip=True).lower()
                    if "не требуется" in exp_text or "без опыта" in exp_text:
                        min_exp, max_exp = 0.0, 0.0
                    elif "1–3" in exp_text or "1-3" in exp_text or "1 года" in exp_text:
                        min_exp, max_exp = 1.0, 3.0
                    elif "3–6" in exp_text or "3-6" in exp_text:
                        min_exp, max_exp = 3.0, 6.0
                    elif "более 6" in exp_text or "> 6" in exp_text:
                        min_exp, max_exp = 6.0, None

                # 4. Employer name from page if available
                comp_el = soup.find(attrs={"data-qa": "vacancy-company-name"})
                if comp_el:
                    comp = comp_el.get_text(strip=True)

        except Exception as e:
            logger.debug(f"Failed to fetch details for HH vacancy {vac_id}: {e}")

        self._details_cache[vac_id] = (now, desc, skills, min_exp, max_exp, comp)
        return desc, skills, min_exp, max_exp, comp

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

        if self._api_disabled:
            return await self._fetch_via_web(
                query=query,
                limit=limit,
                remote_only=remote_only,
                page=page,
                area_id=area_id,
                city=city
            )

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
                    self._api_disabled = True
                    logger.info(
                        f"HH API returned status {response.status_code}, switching to Web Scraper..."
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

                    # Requirements extraction
                    requirements = ResumeExtractor.extract_skills(f"{title}\n{desc}")

                    vac = self.standardize_vacancy(
                        external_id=v_id,
                        title=title,
                        company=company,
                        url=url,
                        salary_min=salary_min,
                        salary_max=salary_max,
                        currency=currency,
                        description=desc,
                        requirements=requirements,
                        is_remote=is_remote,
                        is_freelance=False,
                        city=raw_city,
                        published_at=published_at,
                        min_experience=hh_min_exp,
                        max_experience=hh_max_exp
                    )
                    vacancies.append(vac)

        except Exception as e:
            self._api_disabled = True
            logger.info(f"HH API unavailable ({e}), switching to Web Scraper...")
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
                raw_items = []

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
                    container = (
                        a.find_parent("article")
                        or a.find_parent(attrs={"data-qa": re.compile(r"vacancy-serp__vacancy")})
                    )
                    if not container:
                        container = a
                        for _ in range(6):
                            if container.parent:
                                container = container.parent
                                if container.find(attrs={"data-qa": re.compile(r"vacancy-serp__vacancy-(employer|compensation|address)")}):
                                    break

                    # Salary extraction
                    comp_elem = container.find(attrs={"data-qa": re.compile(r"(compensation|salary)")}) if container else None
                    salary_min, salary_max, currency = self._parse_salary_text(
                        comp_elem.get_text(" ", strip=True) if comp_elem else ""
                    )

                    # Employer extraction
                    employer_elem = (
                        container.find(attrs={"data-qa": "vacancy-serp__vacancy-employer-text"})
                        or container.find(attrs={"data-qa": "vacancy-serp__vacancy-employer"})
                    ) if container else None
                    company = employer_elem.get_text(strip=True) if employer_elem else "Не указана"

                    # City / address extraction
                    address_elem = container.find(attrs={"data-qa": re.compile(r"(address|city|region)")}) if container else None
                    vac_city = address_elem.get_text(strip=True) if address_elem else (city or ("Москва" if area_id == 1 else None))
                    if vac_city and "," in vac_city:
                        vac_city = vac_city.split(",")[0].strip()

                    # Work experience tag from card if present
                    card_exp = None
                    if container:
                        exp_elem = container.find(attrs={"data-qa": re.compile(r"vacancy-serp__vacancy-work-experience-")})
                        if exp_elem:
                            qa_val = exp_elem.get("data-qa", "")
                            if "noExperience" in qa_val:
                                card_exp = (0.0, 0.0)
                            elif "between1And3" in qa_val:
                                card_exp = (1.0, 3.0)
                            elif "between3And6" in qa_val:
                                card_exp = (3.0, 6.0)
                            elif "moreThan6" in qa_val:
                                card_exp = (6.0, None)

                    # Snippet text from card if present (e.g. in older layouts or test fixtures)
                    snippet_req = (
                        container.find(attrs={"data-qa": re.compile(r"(requirement|snippet_requirement)")})
                    ) if container else None
                    snippet_resp = (
                        container.find(attrs={"data-qa": re.compile(r"(responsibility|snippet_responsibility)")})
                    ) if container else None
                    card_desc_parts = []
                    if snippet_req:
                        card_desc_parts.append(snippet_req.get_text(" ", strip=True))
                    if snippet_resp:
                        card_desc_parts.append(snippet_resp.get_text(" ", strip=True))
                    card_desc = "\n".join(card_desc_parts).strip()
                    card_desc = re.sub(r"<[^>]+>", "", card_desc)

                    is_remote = remote_only or any(
                        term in title.lower() or term in card_desc.lower()
                        for term in ["удаленн", "дистанционн", "remote"]
                    )

                    raw_items.append({
                        "id": vac_id,
                        "title": title,
                        "company": company,
                        "url": url,
                        "salary_min": salary_min,
                        "salary_max": salary_max,
                        "currency": currency,
                        "city": vac_city,
                        "is_remote": is_remote,
                        "card_exp": card_exp,
                        "card_desc": card_desc,
                    })
                    if len(raw_items) >= limit:
                        break

                # Concurrently enrich vacancies with full description and key skills
                semaphore = asyncio.Semaphore(8)

                async def _enrich_item(item: Dict[str, Any]) -> Dict[str, Any]:
                    async with semaphore:
                        desc, explicit_skills, min_exp, max_exp, detail_company = await self._fetch_vacancy_details(
                            client, item["id"]
                        )
                        final_desc = desc if desc else item.get("card_desc", "")

                        final_company = item["company"]
                        if (not final_company or final_company == "Не указана") and detail_company:
                            final_company = detail_company

                        extracted_skills = ResumeExtractor.extract_skills(f"{item['title']}\n{final_desc}")
                        all_skills = sorted(list(set(explicit_skills + extracted_skills)))

                        min_e = item["card_exp"][0] if item["card_exp"] else min_exp
                        max_e = item["card_exp"][1] if item["card_exp"] else max_exp

                        is_rem = item["is_remote"] or any(
                            term in final_desc.lower()
                            for term in ["удаленн", "дистанционн", "remote"]
                        )

                        return self.standardize_vacancy(
                            external_id=item["id"],
                            title=item["title"],
                            company=final_company,
                            url=item["url"],
                            salary_min=item["salary_min"],
                            salary_max=item["salary_max"],
                            currency=item["currency"],
                            description=final_desc,
                            requirements=all_skills,
                            is_remote=is_rem,
                            is_freelance=False,
                            city=item["city"],
                            published_at=datetime.datetime.now(datetime.timezone.utc),
                            min_experience=min_e,
                            max_experience=max_e,
                        )

                enriched = await asyncio.gather(*[_enrich_item(it) for it in raw_items], return_exceptions=True)
                for vac in enriched:
                    if isinstance(vac, dict):
                        vacancies.append(vac)

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
