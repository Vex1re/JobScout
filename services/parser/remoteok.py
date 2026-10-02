import re
import datetime
import logging
from typing import List, Dict, Any, Optional
import httpx

from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class RemoteOKParser(BaseVacanciesParser):
    """
    Parser for RemoteOK (remoteok.com) public REST API.
    Provides international remote jobs with USD salaries and tech skill tags.
    Endpoint: https://remoteok.com/api (or https://remoteok.com/api?tag={tag})
    """

    BASE_API_URL = "https://remoteok.com/api"

    def __init__(self):
        super().__init__(name="remoteok")
        self.is_freelance = False
        # RemoteOK strictly requires a User-Agent header and json accept
        self.headers = {
            **self.headers,
            "Accept": "application/json"
        }

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 50,
        remote_only: bool = True,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        vacancies: List[Dict[str, Any]] = []

        # Extract primary tag if query contains English tech keywords
        tag_candidate = self._extract_tag_from_query(query)
        url = f"{self.BASE_API_URL}?tag={tag_candidate}" if tag_candidate else self.BASE_API_URL

        raw_data: Optional[List[Dict[str, Any]]] = None

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers, follow_redirects=True) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 1:
                        raw_data = data
                    elif tag_candidate:
                        # Fallback to general API if tag query returned no job items
                        fallback_resp = await client.get(self.BASE_API_URL)
                        if fallback_resp.status_code == 200:
                            raw_data = fallback_resp.json()
                else:
                    logger.warning(f"RemoteOK API returned status {response.status_code}")
                    return []
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning(f"Network error querying RemoteOK API: {exc}")
            return []
        except Exception as e:
            logger.error(f"Error fetching from RemoteOK API: {e}", exc_info=True)
            return []

        if not raw_data:
            return []

        # First element is legal disclaimer / terms
        job_items = [
            it for it in raw_data
            if isinstance(it, dict) and "position" in it and "id" in it
        ]

        # Filter by search keywords if query specified
        filtered_items = self._filter_jobs(job_items, query)

        # Pagination slicing
        start_idx = page * limit
        end_idx = start_idx + limit
        paged_items = filtered_items[start_idx:end_idx]

        for item in paged_items:
            try:
                job_id = str(item.get("id"))
                title = str(item.get("position") or "").strip()
                if not title:
                    continue

                company = str(item.get("company") or "").strip() or "Remote Company"
                apply_url = item.get("apply_url") or item.get("url")
                if not apply_url:
                    apply_url = f"https://remoteok.com/remote-jobs/{job_id}"

                # Salaries (USD)
                s_min_raw = item.get("salary_min")
                s_max_raw = item.get("salary_max")
                salary_min = int(s_min_raw) if s_min_raw and int(s_min_raw) > 0 else None
                salary_max = int(s_max_raw) if s_max_raw and int(s_max_raw) > 0 else None

                # Tags / Requirements
                tags = item.get("tags") or []
                clean_tags = [str(t).strip() for t in tags if str(t).strip()]

                # Description
                raw_desc = item.get("description") or ""
                desc_clean = re.sub(r"<[^>]+>", " ", str(raw_desc)).strip()
                desc_clean = re.sub(r"\s+", " ", desc_clean)

                # Published date
                published_at = None
                date_val = item.get("date")
                epoch_val = item.get("epoch")
                if epoch_val:
                    try:
                        published_at = datetime.datetime.fromtimestamp(int(epoch_val), tz=datetime.timezone.utc)
                    except Exception:
                        pass
                elif date_val:
                    try:
                        clean_date = str(date_val).replace("Z", "+00:00")
                        published_at = datetime.datetime.fromisoformat(clean_date)
                    except Exception:
                        pass

                vac = self.standardize_vacancy(
                    external_id=job_id,
                    title=f"[RemoteOK] {title}",
                    company=company,
                    url=apply_url,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    currency="USD",
                    description=desc_clean,
                    requirements=clean_tags if clean_tags else None,
                    is_remote=True,
                    is_freelance=False,
                    city="Удаленно",
                    published_at=published_at or datetime.datetime.now(datetime.timezone.utc)
                )
                vacancies.append(vac)
            except Exception as exc:
                logger.error(f"Error standardizing RemoteOK job: {exc}", exc_info=True)

        return vacancies

    @staticmethod
    def _extract_tag_from_query(query: str) -> Optional[str]:
        if not query:
            return None

        # Look for english tech keywords in query
        words = re.findall(r"[a-zA-Z0-9]+", query.lower())
        ignore = {"senior", "middle", "junior", "lead", "developer", "engineer", "dev", "tech"}
        for w in words:
            if w not in ignore and len(w) >= 2:
                return w
        return None

    @staticmethod
    def _filter_jobs(jobs: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return jobs

        keywords = [
            w.lower() for w in re.findall(r"[\w+#]+", query)
            if len(w) >= 2 and w.lower() not in {"junior", "middle", "senior", "lead", "стажер", "вакансия", "работа"}
        ]

        if not keywords:
            return jobs

        matched = []
        for job in jobs:
            title = str(job.get("position", "")).lower()
            tags = " ".join([str(t).lower() for t in (job.get("tags") or [])])
            desc = str(job.get("description", "")).lower()
            combined = f"{title} {tags} {desc}"

            if any(k in combined for k in keywords):
                matched.append(job)

        return matched if matched else jobs
