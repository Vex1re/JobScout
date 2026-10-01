from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import datetime
from core.config import settings
from services.resume_analyzer.red_flags import RedFlagScanner
from services.resume_analyzer.extractor import ResumeExtractor


class BaseVacanciesParser(ABC):
    """
    Abstract base class for all job and freelance aggregators.
    """

    def __init__(self, name: str):
        self.name = name
        self.headers = {
            "User-Agent": settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        self.timeout = settings.REQUEST_TIMEOUT

    @abstractmethod
    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch vacancies for given search query and page.
        Returns list of standardized vacancy dicts.
        """
        pass

    def standardize_vacancy(
        self,
        external_id: str,
        title: str,
        company: str,
        url: str,
        salary_min: Optional[int],
        salary_max: Optional[int],
        currency: str,
        description: str,
        is_remote: bool = False,
        is_freelance: bool = False,
        city: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        published_at: Optional[datetime.datetime] = None
    ) -> Dict[str, Any]:
        """
        Normalizes vacancy data, extracts tech skills and scans for red flags.
        """
        from services.parser.normalizer import CityNormalizer

        # Red flag & scam detection
        scan_result = RedFlagScanner.scan(title=title, description=description, company=company)

        # Extract requirements/skills if not provided
        if not requirements:
            requirements = ResumeExtractor.extract_skills(f"{title}\n{description}")

        # Standardize currency
        curr = (currency or "RUB").upper()
        if curr in ["RUR", "РУБ", "₽"]:
            curr = "RUB"

        # Normalize city
        norm_city = CityNormalizer.normalize(city)
        if is_remote and not norm_city:
            norm_city = "Удаленно"

        return {
            "id": f"{self.name}_{external_id}",
            "source": self.name,
            "title": title.strip(),
            "company": company.strip() or "Компания не указана",
            "url": url.strip(),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "currency": curr,
            "description": description.strip(),
            "requirements": requirements,
            "is_remote": is_remote,
            "is_freelance": is_freelance,
            "city": norm_city,
            "risk_level": scan_result["risk_level"],
            "red_flags": scan_result["red_flags"],
            "published_at": published_at or datetime.datetime.now(datetime.timezone.utc)
        }
