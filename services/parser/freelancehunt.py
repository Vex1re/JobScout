import logging
from typing import List, Dict, Any, Optional
import httpx
from core.config import settings
from services.parser.base import BaseVacanciesParser

logger = logging.getLogger(__name__)


class FreelancehuntParser(BaseVacanciesParser):
    """
    Parser for Freelancehunt (freelance orders and projects).
    Requires API Token (https://api.freelancehunt.com/v2/projects).
    Controlled by feature flag `ENABLE_FREELANCEHUNT`.
    """

    API_URL = "https://api.freelancehunt.com/v2/projects"

    def __init__(self):
        super().__init__(name="freelancehunt")
        self.is_freelance = True
        self.api_token = settings.FREELANCEHUNT_API_TOKEN
        self.enabled = settings.ENABLE_FREELANCEHUNT

        if self.enabled and not self.api_token:
            logger.warning(
                "Freelancehunt parser is enabled in settings (ENABLE_FREELANCEHUNT=True), "
                "but FREELANCEHUNT_API_TOKEN is not set. Requests will be skipped."
            )

    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches freelance projects from Freelancehunt API v2."""
        if not self.enabled:
            return []

        if not self.api_token:
            logger.warning("Freelancehunt API token is missing. Skipping search.")
            return []

        from core.resilience import resilience_manager
        if not await resilience_manager.circuit_breaker.can_execute(self.name):
            logger.warning("Freelancehunt circuit breaker is OPEN. Skipping.")
            return []

        await resilience_manager.get_token_bucket(self.name).acquire()

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
            "User-Agent": resilience_manager.get_user_agent()
        }

        # Page in Freelancehunt API is 1-based
        api_page = max(1, page + 1)
        params = {
            "page[number]": api_page,
            "filter[name]": query
        }

        vacancies: List[Dict[str, Any]] = []

        try:
            async with self.get_client(headers=headers) as client:
                response = await client.get(self.API_URL, params=params)

                if response.status_code == 200:
                    await resilience_manager.circuit_breaker.record_success(self.name)
                    data = response.json()
                    projects = data.get("data", [])

                    for p in projects:
                        attributes = p.get("attributes", {})
                        p_id = str(p.get("id") or "")
                        title = attributes.get("name", "").strip()
                        if not title:
                            continue

                        description = attributes.get("description", "")
                        budget = attributes.get("budget") or {}
                        amount = budget.get("amount")
                        curr = budget.get("currency", "RUB")

                        url = attributes.get("url") or f"https://freelancehunt.com/project/{p_id}.html"

                        employer = attributes.get("employer", {})
                        company = employer.get("login") or "Freelancehunt Заказчик"

                        standardized = self.standardize_vacancy(
                            external_id=p_id,
                            title=title,
                            company=company,
                            url=url,
                            salary_min=amount,
                            salary_max=amount,
                            currency=curr,
                            description=description,
                            is_remote=True,
                            is_freelance=True,
                            city="Удаленно"
                        )
                        vacancies.append(standardized)
                        if len(vacancies) >= limit:
                            break

                elif response.status_code == 401 or response.status_code == 403:
                    logger.error("Freelancehunt API authentication failed: invalid API token.")
                    await resilience_manager.circuit_breaker.record_failure(
                        self.name, f"Auth failure {response.status_code}"
                    )
                else:
                    logger.warning(f"Freelancehunt API returned status {response.status_code}")
                    await resilience_manager.circuit_breaker.record_failure(
                        self.name, f"HTTP {response.status_code}"
                    )

        except Exception as e:
            logger.error(f"Error while fetching projects from Freelancehunt: {e}")
            await resilience_manager.circuit_breaker.record_failure(self.name, str(e))

        return vacancies
