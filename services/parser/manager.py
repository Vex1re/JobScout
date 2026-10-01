import asyncio
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database.models import User, Resume, Vacancy
from core.database.repository import VacancyRepository, InteractionRepository
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
    """

    def __init__(self):
        self.parsers: List[BaseVacanciesParser] = [
            HeadHunterParser(),
            HabrCareerParser(),
            KworkParser(),
            RabotaRuParser()
        ]

    async def fetch_all_for_query(
        self,
        query: str,
        limit_per_source: int = 25,
        remote_only: bool = False,
        include_freelance: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Concurrently queries all active aggregators.
        """
        tasks = []
        for parser in self.parsers:
            if parser.name == "kwork" and not include_freelance:
                continue
            tasks.append(
                parser.fetch_vacancies(
                    query=query,
                    limit=limit_per_source,
                    remote_only=remote_only
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
        custom_query: str = None
    ) -> List[Tuple[Vacancy, Dict[str, Any]]]:
        """
        Full pipeline:
        1. Formulate search query from resume (or custom query)
        2. Concurrently fetch vacancies from all aggregators
        3. Save new vacancies to DB
        4. Match each vacancy with candidate's resume
        5. Filter out scams and low scores
        6. Return sorted list of (Vacancy, match_dict)
        """
        # Formulate query from candidate stack
        if custom_query:
            query = custom_query
        elif resume.skills:
            # Take top 1-2 primary skills or target title
            top_skills = resume.skills[:2]
            query = " ".join(top_skills)
        else:
            query = resume.title or "Python"

        logger.info(f"Searching vacancies for user {user.telegram_id} with query '{query}'")

        raw_vacancies = await self.fetch_all_for_query(
            query=query,
            limit_per_source=settings.MAX_VACANCIES_PER_SOURCE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance
        )

        # Upsert vacancies into database
        await VacancyRepository.upsert_vacancies(session, raw_vacancies)

        # Get vacancies for evaluation (including previously stored unhidden ones)
        vacancies = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_blocked=settings.RED_FLAG_STRICT_MODE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            min_salary=user.min_salary
        )

        # Match each vacancy
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
                # Save match record to DB
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
