from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import datetime
import httpx
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
        self.proxy = settings.PROXY_URL

    def get_client(self, **kwargs) -> httpx.AsyncClient:
        """
        Creates an httpx.AsyncClient configured with standard headers, timeout, and proxy if configured.
        Rotates User-Agent and proxies via resilience_manager.
        """
        from core.resilience import resilience_manager
        headers = dict(self.headers)
        headers["User-Agent"] = resilience_manager.get_user_agent()

        client_kwargs: Dict[str, Any] = {
            "timeout": kwargs.pop("timeout", self.timeout),
            "headers": kwargs.pop("headers", headers),
            "follow_redirects": kwargs.pop("follow_redirects", True),
        }
        proxy = kwargs.pop("proxy", resilience_manager.get_proxy())
        if proxy:
            client_kwargs["proxy"] = proxy
        client_kwargs.update(kwargs)
        return httpx.AsyncClient(**client_kwargs)

    get_http_client = get_client

    @abstractmethod
    async def fetch_vacancies(
        self,
        query: str,
        limit: int = 30,
        remote_only: bool = False,
        page: int = 0,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch vacancies for given search query, page and optional city.
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
        published_at: Optional[datetime.datetime] = None,
        min_experience: Optional[float] = None,
        max_experience: Optional[float] = None,
        target_grade: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Normalizes vacancy data, extracts tech skills and scans for red flags.
        """
        from services.parser.normalizer import CityNormalizer, CurrencyNormalizer
        from services.deduplication import generate_canonical_id
        from services.resume_analyzer.vacancy_extractor import VacancyExperienceExtractor, VacancyGradeDetector

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

        # Extract experience requirements and target grade if not explicitly given
        combined_text = f"{title}\n{description}"
        if min_experience is None and max_experience is None:
            min_exp, max_exp = VacancyExperienceExtractor.extract_experience_years(combined_text)
        else:
            min_exp, max_exp = min_experience, max_experience

        has_explicit_grade = any(g in title.lower() for g in ["junior", "middle", "senior", "lead", "стажер", "ведущий"])
        if not target_grade:
            target_grade = VacancyGradeDetector.detect_grade(title, description, min_exp)

        # Compute normalized ruble salary
        sal_val = salary_max if salary_max is not None else salary_min
        salary_rub = CurrencyNormalizer.normalize_to_rub(sal_val, curr)

        # Canonical deduplication ID
        canonical_id = generate_canonical_id(
            company=company,
            title=title,
            city=norm_city,
            salary_from=salary_min,
            salary_to=salary_max,
            currency=curr
        )

        clean_desc = description.strip()
        snippet = clean_desc[:300].strip() + ("..." if len(clean_desc) > 300 else "")

        # Remote scope detection
        comb_lower = combined_text.lower()
        if "worldwide" in comb_lower or "любая страна" in comb_lower or "весь мир" in comb_lower:
            remote_scope = "worldwide"
        elif "только рф" in comb_lower or "гражданство рф" in comb_lower or "только россия" in comb_lower:
            remote_scope = "RU"
        elif is_remote:
            remote_scope = "worldwide"
        else:
            remote_scope = "unknown"

        req_exp_str = f"{min_exp or 0}-{max_exp or 'any'} лет" if (min_exp or max_exp) else None
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        return {
            "id": f"{self.name}_{external_id}",
            "external_id": str(external_id),
            "canonical_id": canonical_id,
            "source": self.name,
            "title": title.strip(),
            "company": company.strip() or "Компания не указана",
            "url": url.strip(),
            "salary_min": salary_min,
            "salary_max": salary_max,
            "salary_from": salary_min,
            "salary_to": salary_max,
            "currency": curr,
            "salary_gross_net": "unknown",
            "salary_rub_normalized": salary_rub,
            "description": clean_desc,
            "snippet": snippet,
            "requirements": requirements,
            "skills": requirements,
            "is_remote": is_remote,
            "remote_scope": remote_scope,
            "is_freelance": is_freelance,
            "city": norm_city,
            "city_norm": norm_city,
            "min_experience": min_exp,
            "max_experience": max_exp,
            "required_experience": req_exp_str,
            "target_grade": target_grade,
            "grade": target_grade,
            "grade_confidence": 1.0 if has_explicit_grade else 0.75,
            "risk_level": scan_result["risk_level"],
            "red_flag_level": scan_result["risk_level"],
            "red_flags": scan_result["red_flags"],
            "published_at": published_at or now_dt,
            "first_seen_at": now_dt,
            "last_seen_at": now_dt,
            "is_active": True
        }
