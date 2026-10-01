import asyncio
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database.models import User, Resume, Vacancy
from core.database.repository import VacancyRepository, InteractionRepository, UserRepository
from services.parser.base import BaseVacanciesParser
from services.parser.hh import HeadHunterParser
from services.parser.habr import HabrCareerParser
from services.parser.kwork import KworkParser
from services.parser.rabota import RabotaRuParser
from services.resume_analyzer.matcher import VacancyMatcher

logger = logging.getLogger(__name__)


class AggregatorManager:
    """
    Coordinates multi-platform parsing across HeadHunter, Habr Career, Kwork, and Rabota.ru,
    aggregates results, applies scam detection and candidate-resume matching.
    Supports dynamic query rotation and pagination offsets.
    """

    def __init__(self):
        self.parsers: List[BaseVacanciesParser] = [
            HeadHunterParser(),
            HabrCareerParser(),
            KworkParser(),
            RabotaRuParser()
        ]

    @staticmethod
    def generate_query_pool(resume: Resume) -> List[str]:
        """
        Builds a prioritized, diverse pool of search queries from candidate profile:
        - Target role title
        - Core tech stack (top 2 skills)
        - Skill pairings & combinations
        - Individual primary technologies
        """
        queries = []
        if resume.title:
            queries.append(resume.title.strip())

        skills = resume.skills or []
        if len(skills) >= 2:
            queries.append(f"{skills[0]} {skills[1]}")
        if len(skills) >= 3:
            queries.append(f"{skills[0]} {skills[2]}")
        if len(skills) >= 4:
            queries.append(f"{skills[1]} {skills[3]}")
        if skills:
            queries.append(skills[0])
        if len(skills) >= 2:
            queries.append(skills[1])

        # Broader role title (e.g. without Senior/Junior/Backend)
        if resume.title:
            clean_role = re.sub(
                r"\b(backend|frontend|fullstack|junior|middle|senior|lead|стажер|разработчик|developer)\b",
                "",
                resume.title,
                flags=re.IGNORECASE
            ).strip()
            if clean_role and len(clean_role) >= 3:
                queries.append(clean_role)

        if not queries:
            queries.append("Python Developer")

        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_clean = q.strip()
            if q_clean and q_clean.lower() not in seen:
                seen.add(q_clean.lower())
                unique_queries.append(q_clean)

        return unique_queries

    async def fetch_all_for_query(
        self,
        query: str,
        limit_per_source: int = 25,
        remote_only: bool = False,
        include_freelance: bool = True,
        page: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Concurrently queries all active aggregators for a given page.
        """
        tasks = []
        for parser in self.parsers:
            if parser.name == "kwork" and not include_freelance:
                continue
            tasks.append(
                parser.fetch_vacancies(
                    query=query,
                    limit=limit_per_source,
                    remote_only=remote_only,
                    page=page
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_vacancies: List[Dict[str, Any]] = []
        seen_urls = set()

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Parser error: {res}")
                continue
            for vac in res:
                url = vac.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_vacancies.append(vac)

        return all_vacancies

    async def search_and_match_for_user(
        self,
        session: AsyncSession,
        user: User,
        resume: Resume,
        custom_query: Optional[str] = None
    ) -> List[Tuple[Vacancy, Dict[str, Any]]]:
        """
        Full dynamic pipeline:
        1. Select query from rotated query pool (or custom query)
        2. Fetch vacancies using user's current search page offset
        3. Advance query index & page offset for next search cycle
        4. Upsert vacancies into database
        5. Fetch unhidden & unviewed vacancies (filtered by city/remote preferences)
        6. Match vacancies with candidate profile
        7. Return ranked list of (Vacancy, match_dict)
        """
        if custom_query:
            query = custom_query
            current_page = user.search_page_offset or 0
        else:
            pool = self.generate_query_pool(resume)
            query_idx = user.last_query_index or 0
            query = pool[query_idx % len(pool)]
            current_page = user.search_page_offset or 0

        logger.info(
            f"Searching vacancies for user {user.telegram_id}: query='{query}', "
            f"page={current_page}, city='{user.city or 'Any'}'"
        )

        # 1. Concurrently fetch fresh vacancies from aggregators
        raw_vacancies = await self.fetch_all_for_query(
            query=query,
            limit_per_source=settings.MAX_VACANCIES_PER_SOURCE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            page=current_page
        )

        # 2. Advance pagination and query rotation offsets for subsequent searches
        await UserRepository.increment_search_offsets(
            session=session,
            telegram_id=user.telegram_id,
            offset_inc=1,
            query_index_inc=1
        )

        # 3. Upsert newly fetched vacancies into database
        await VacancyRepository.upsert_vacancies(session, raw_vacancies)

        # 4. Get unhidden, unviewed vacancies matching user's filters & city
        vacancies = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_blocked=settings.RED_FLAG_STRICT_MODE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            min_salary=user.min_salary,
            exclude_viewed=True,
            user_city=user.city
        )

        # 5. Match candidate resume against vacancies
        matched_results: List[Tuple[Vacancy, Dict[str, Any]]] = []

        for vac in vacancies:
            match_res = VacancyMatcher.match(
                candidate_skills=resume.skills,
                candidate_grade=resume.grade,
                candidate_role=resume.title,
                candidate_experience=resume.years_of_experience,
                vacancy_title=vac.title,
                vacancy_description=vac.description,
                vacancy_requirements=vac.requirements or [],
                risk_level=vac.risk_level
            )

            # Check if match meets user threshold
            if match_res["score"] >= settings.MIN_MATCH_SCORE:
                await InteractionRepository.save_or_update_match(
                    session=session,
                    user_id=user.telegram_id,
                    vacancy_id=vac.id,
                    score=match_res["score"],
                    matched_skills=match_res["matched_skills"],
                    missing_skills=match_res["missing_skills"]
                )
                matched_results.append((vac, match_res))

        # Sort by match score descending
        matched_results.sort(key=lambda x: x[1]["score"], reverse=True)
        return matched_results


aggregator_manager = AggregatorManager()

