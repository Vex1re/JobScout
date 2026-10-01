import re
import datetime
import logging
from typing import List, Dict, Any
import httpx
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class HeadHunterParser(BaseVacanciesParser):
    """
    Parser for HeadHunter (hh.ru) using its public REST API.
    """

    API_URL = "https://api.hh.ru/vacancies"

    def __init__(self):
        super().__init__(name="hh")

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        params = {
            "text": query,
            "per_page": min(limit, 50),
            "page": page,
            "order_by": "publication_time",
        }
        if remote_only:
            params["schedule"] = "remote"

        vacancies: List[Dict[str, Any]] = []

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                response = await client.get(self.API_URL, params=params)
                if response.status_code != 200:
                    logger.warning(f"HH API returned status {response.status_code}")
                    return []

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
                    # Strip any HTML tags like <highlighttext>
                    desc = re.sub(r"<[^>]+>", "", desc)

                    # Remote check
                    schedule = item.get("schedule") or {}
                    is_remote = schedule.get("id") == "remote"

                    # City extraction
                    area = item.get("area") or {}
                    raw_city = area.get("name")

                    # Parse published date
                    published_raw = item.get("published_at")
                    published_at = None
                    if published_raw:
                        try:
                            published_at = datetime.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                        except Exception:
                            published_at = datetime.datetime.utcnow()

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
                        published_at=published_at
                    )
                    vacancies.append(vac)

        except Exception as e:
            logger.error(f"Error fetching vacancies from HH: {e}", exc_info=True)

        return vacancies
