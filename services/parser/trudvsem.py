import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx

from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class TrudVsemParser(BaseVacanciesParser):
    """
    Parser for 'Работа России' (trudvsem.ru) using its public OpenData REST API.
    Does not require API keys or captcha.
    Endpoint: https://opendata.trudvsem.ru/api/v1/vacancies
    """

    API_URL = "https://opendata.trudvsem.ru/api/v1/vacancies"
    FALLBACK_URL = "http://opendata.trudvsem.ru/api/v1/vacancies"

    def __init__(self):
        super().__init__(name="trudvsem")
        self.is_freelance = False
        # TrudVsem OpenData API can occasionally be slow to respond
        self.api_timeout = max(self.timeout, 20.0)

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = False,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        from services.parser.normalizer import CityNormalizer

        effective_limit = min(max(limit, 10), 100)
        offset = page * 50

        params = {
            "text": query,
            "limit": effective_limit,
            "offset": offset,
        }

        vacancies: List[Dict[str, Any]] = []

        # Try HTTPS first, fallback to HTTP if SSL error occurs
        urls_to_try = [self.API_URL, self.FALLBACK_URL]
        response_data: Optional[Dict[str, Any]] = None

        async with httpx.AsyncClient(timeout=self.api_timeout, headers=self.headers, follow_redirects=True) as client:
            for url in urls_to_try:
                try:
                    response = await client.get(url, params=params)
                    if response.status_code == 200:
                        response_data = response.json()
                        break
                    else:
                        logger.warning(f"TrudVsem returned status {response.status_code} for URL {url}")
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    logger.warning(f"TrudVsem connection issue with {url}: {exc}")
                    continue
                except Exception as exc:
                    logger.warning(f"TrudVsem request failed for {url}: {exc}")
                    continue

        if not response_data:
            return []

        try:
            results_obj = response_data.get("results", {})
            raw_items = results_obj.get("vacancies", []) if isinstance(results_obj, dict) else []

            for item_wrap in raw_items:
                v = item_wrap.get("vacancy") if isinstance(item_wrap, dict) else None
                if not v or not isinstance(v, dict):
                    continue

                v_id = str(v.get("id") or "")
                title = str(v.get("job-name") or "").strip()
                if not title:
                    continue

                # Direct link
                vac_url = str(v.get("vac_url") or "").strip()
                if not vac_url and v_id:
                    vac_url = f"https://trudvsem.ru/vacancy/card/{v_id}"

                # Employer info
                company_obj = v.get("company")
                if isinstance(company_obj, dict):
                    company = company_obj.get("name") or "Работодатель на Работа России"
                elif company_obj:
                    company = str(company_obj)
                else:
                    company = "Работодатель на Работа России"

                # Salary range
                s_min_raw = v.get("salary_min")
                s_max_raw = v.get("salary_max")
                salary_min = None
                salary_max = None
                if s_min_raw is not None:
                    try:
                        val = int(s_min_raw)
                        if val > 0:
                            salary_min = val
                    except (ValueError, TypeError):
                        pass

                if s_max_raw is not None:
                    try:
                        val = int(s_max_raw)
                        if val > 0:
                            salary_max = val
                    except (ValueError, TypeError):
                        pass

                # Currency normalization
                curr_raw = str(v.get("currency") or "").lower()
                if any(sym in curr_raw for sym in ["руб", "₽", "rur", "rub"]):
                    currency = "RUB"
                elif "$" in curr_raw or "usd" in curr_raw:
                    currency = "USD"
                elif "€" in curr_raw or "eur" in curr_raw:
                    currency = "EUR"
                else:
                    currency = "RUB"

                # Description / Duties & Requirements
                duty = str(v.get("duty") or "").strip()
                req_obj = v.get("requirement")
                req_text = ""
                if isinstance(req_obj, dict):
                    education = req_obj.get("education") or ""
                    experience = req_obj.get("experience")
                    exp_str = f"Опыт: {experience} г." if experience else ""
                    qual = req_obj.get("qualification") or ""
                    req_text = " ".join(filter(None, [education, exp_str, qual]))
                elif req_obj:
                    req_text = str(req_obj).strip()

                desc_parts = [duty, req_text]
                desc = "\n".join([p for p in desc_parts if p]).strip()
                desc = re.sub(r"<[^>]+>", "", desc)

                # Remote flag
                schedule = str(v.get("schedule") or "").lower()
                work_place_type = str(v.get("workPlaceType") or "").lower()
                is_remote = (
                    "дистанц" in schedule
                    or "удален" in schedule
                    or "дистанц" in work_place_type
                    or "удален" in work_place_type
                    or "дистанц" in duty.lower()
                    or "удален" in duty.lower()
                    or "дистанц" in title.lower()
                    or "удален" in title.lower()
                )

                if remote_only and not is_remote:
                    continue

                # City extraction
                raw_city = None
                addresses = v.get("addresses", {})
                if isinstance(addresses, dict):
                    addr_list = addresses.get("address", [])
                    if isinstance(addr_list, list) and addr_list:
                        raw_city = addr_list[0].get("location")

                if not raw_city:
                    region_obj = v.get("region")
                    if isinstance(region_obj, dict):
                        raw_city = region_obj.get("name")
                    elif region_obj:
                        raw_city = str(region_obj)

                city = CityNormalizer.normalize(raw_city)

                # Published date
                pub_raw = v.get("creation-date") or v.get("date_modify")
                published_at = None
                if pub_raw:
                    try:
                        # e.g. '2026-09-30' or ISO format
                        pub_clean = str(pub_raw).split("T")[0]
                        published_at = datetime.datetime.strptime(pub_clean, "%Y-%m-%d").replace(
                            tzinfo=datetime.timezone.utc
                        )
                    except Exception:
                        published_at = datetime.datetime.now(datetime.timezone.utc)

                vac = self.standardize_vacancy(
                    external_id=v_id,
                    title=title,
                    company=company,
                    url=vac_url,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    currency=currency,
                    description=desc,
                    is_remote=is_remote,
                    is_freelance=False,
                    city=city,
                    published_at=published_at
                )
                vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error parsing TrudVsem vacancies: {e}", exc_info=True)

        return vacancies
