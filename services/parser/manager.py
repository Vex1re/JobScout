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
from services.parser.trudvsem import TrudVsemParser
from services.parser.fl_ru import FLRuParser
from services.parser.habr_freelance import HabrFreelanceParser
from services.parser.remoteok import RemoteOKParser
from services.parser.superjob import SuperJobParser
from services.parser.kwork import KworkParser
from services.parser.rabota import RabotaRuParser
from services.resume_analyzer.matcher import VacancyMatcher

logger = logging.getLogger(__name__)


class AggregatorManager:
    """
    Coordinates multi-platform parsing across HeadHunter, Habr Career, TrudVsem, SuperJob,
    RemoteOK, Kwork, FL.ru, Habr Freelance, and Rabota.ru.
    Aggregates results, applies scam detection and candidate-resume matching.
    Supports dynamic query rotation and pagination offsets.
    """

    MULTI_PAGE_PARSERS = {"hh", "trudvsem", "superjob", "habr", "rabota"}

    def __init__(self):
        self.parsers: List[BaseVacanciesParser] = [
            HeadHunterParser(),
            HabrCareerParser(),
            TrudVsemParser(),
            SuperJobParser(),
            RemoteOKParser(),
            KworkParser(),
            FLRuParser(),
            HabrFreelanceParser(),
            RabotaRuParser()
        ]

    @staticmethod
    def generate_query_pool(resume: Resume) -> List[str]:
        """
        Builds a comprehensive, prioritized query pool for high-yield search:
        - Target role title (e.g. "Senior Python Backend Developer")
        - English role variations (e.g. "Python Developer", "Backend Developer")
        - Russian role synonyms (e.g. "Разработчик Python", "Программист Python", "Бэкенд разработчик")
        - Primary language / stack (e.g. "Python")
        - Framework pairings (e.g. "Python FastAPI", "Python Django")
        - Infrastructure pairings (e.g. "Python Docker", "FastAPI PostgreSQL")
        - Positional skill pairings & single secondary skills
        """
        queries = []
        raw_title = (resume.title or "").strip()
        if raw_title:
            queries.append(raw_title)

        skills = [s.strip() for s in (resume.skills or []) if s.strip()]
        title_lower = raw_title.lower()

        # 1. Identify primary language / tech
        common_langs = [
            "Python", "Golang", "Go", "Java", "JavaScript", "TypeScript",
            "C++", "C#", "PHP", "Ruby", "Rust", "Kotlin", "Swift"
        ]
        primary_lang = None
        for lang in common_langs:
            if any(s.lower() == lang.lower() for s in skills):
                primary_lang = lang
                break
        if not primary_lang:
            for lang in common_langs:
                if re.search(rf"\b{re.escape(lang.lower())}\b", title_lower):
                    primary_lang = lang
                    break
        if not primary_lang and skills:
            primary_lang = skills[0]
        if not primary_lang:
            primary_lang = "Python"

        # 2. Identify specialization / role direction
        is_backend = any(w in title_lower for w in ["backend", "бэкенд", "бэкэнд", "серверный"]) or (
            primary_lang.lower() in ["python", "go", "golang", "java", "php", "c#", "ruby"]
            and not any(w in title_lower for w in ["data", "ml", "qa", "frontend", "тестировщик"])
        )
        is_frontend = any(w in title_lower for w in ["frontend", "фронтенд", "фронтэнд"])
        is_fullstack = any(w in title_lower for w in ["fullstack", "фулстек", "фуллстек"])
        is_devops = any(w in title_lower for w in ["devops", "девопс", "sre", "инфраструктура", "sysadmin"])
        is_qa = any(w in title_lower for w in ["qa", "тестировщик", "тестирование", "test"])
        is_data = any(w in title_lower for w in ["data", "дата", "ml", "machine learning", "аналитик"])

        # 3. English role variants
        if is_backend:
            queries.append(f"{primary_lang} Developer")
            queries.append("Backend Developer")
            queries.append(f"{primary_lang} Backend Developer")
        elif is_frontend:
            queries.append(f"{primary_lang} Developer")
            queries.append("Frontend Developer")
            queries.append(f"{primary_lang} Frontend Developer")
        elif is_fullstack:
            queries.append(f"{primary_lang} Fullstack Developer")
            queries.append("Fullstack Developer")
            queries.append(f"{primary_lang} Developer")
        elif is_devops:
            queries.append("DevOps Engineer")
            queries.append(f"{primary_lang} DevOps")
        elif is_qa:
            queries.append("QA Engineer")
            queries.append(f"QA Automation {primary_lang}")
        elif is_data:
            queries.append("Data Engineer")
            queries.append(f"{primary_lang} Data Engineer")
        else:
            queries.append(f"{primary_lang} Developer")

        # 4. Russian role synonyms
        queries.append(f"Разработчик {primary_lang}")
        queries.append(f"Программист {primary_lang}")
        queries.append(f"{primary_lang} разработчик")
        if is_backend:
            queries.append("Бэкенд разработчик")
        elif is_frontend:
            queries.append("Фронтенд разработчик")
        elif is_fullstack:
            queries.append("Фулстек разработчик")

        # 5. Positional skill combinations (retains compatibility with test suites)
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

        # 6. Framework pairings
        known_frameworks = [
            "FastAPI", "Django", "Flask", "aiohttp", "React", "Vue", "Angular",
            "Next.js", "NestJS", "Spring", "ASP.NET", "Laravel", "Gin"
        ]
        cand_frameworks = [s for s in skills if any(s.lower() == f.lower() for f in known_frameworks)]
        for fw in cand_frameworks[:2]:
            queries.append(f"{primary_lang} {fw}")
        if len(cand_frameworks) >= 2:
            queries.append(f"{cand_frameworks[0]} {cand_frameworks[1]}")
        # Default framework pairings if primary is Python
        if primary_lang.lower() == "python":
            if "FastAPI" not in [f.capitalize() for f in cand_frameworks]:
                queries.append("Python FastAPI")
            if "Django" not in [f.capitalize() for f in cand_frameworks]:
                queries.append("Python Django")

        # 7. Infrastructure pairings
        known_infra = [
            "Docker", "PostgreSQL", "Redis", "Kafka", "Kubernetes", "RabbitMQ", "ClickHouse", "Linux"
        ]
        cand_infra = [s for s in skills if any(s.lower() == inf.lower() for inf in known_infra)]
        for inf in cand_infra[:2]:
            queries.append(f"{primary_lang} {inf}")
        if cand_frameworks and cand_infra:
            queries.append(f"{cand_frameworks[0]} {cand_infra[0]}")
        elif primary_lang.lower() == "python":
            queries.append("Python Docker")
            queries.append("FastAPI PostgreSQL")

        # 8. Broader role title (without grade/level)
        if raw_title:
            clean_role = re.sub(
                r"\b(backend|frontend|fullstack|junior|middle|senior|lead|стажер|разработчик|developer)\b",
                "",
                raw_title,
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
        page: int = 0,
        scan_pages: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Concurrently queries all active aggregators for a given query,
        scanning multiple pages (e.g. page and page + 1) for primary aggregators
        (HeadHunter, Trudvsem, SuperJob, Habr Career, Rabota.ru).
        """
        tasks = []
        for parser in self.parsers:
            is_freelance = getattr(parser, "is_freelance", False) or parser.name in [
                "kwork", "fl_ru", "habr_freelance"
            ]
            if is_freelance and not include_freelance:
                continue

            if parser.name in self.MULTI_PAGE_PARSERS and scan_pages > 1:
                for p_offset in range(scan_pages):
                    tasks.append(
                        parser.fetch_vacancies(
                            query=query,
                            limit=limit_per_source,
                            remote_only=remote_only,
                            page=page + p_offset
                        )
                    )
            else:
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
        seen_ids = set()

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Parser error: {res}")
                continue
            for vac in res:
                v_id = vac.get("id")
                url = vac.get("url")
                if (v_id and v_id in seen_ids) or (url and url in seen_urls):
                    continue
                if v_id:
                    seen_ids.add(v_id)
                if url:
                    seen_urls.add(url)
                all_vacancies.append(vac)

        return all_vacancies

    async def fetch_all_for_queries(
        self,
        queries: List[str],
        limit_per_source: int = 25,
        remote_only: bool = False,
        include_freelance: bool = True,
        page: int = 0,
        scan_pages: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Concurrently queries all aggregators for multiple search queries in parallel.
        Merges results and deduplicates by both URL and ID.
        """
        tasks = [
            self.fetch_all_for_query(
                query=q,
                limit_per_source=limit_per_source,
                remote_only=remote_only,
                include_freelance=include_freelance,
                page=page,
                scan_pages=scan_pages
            )
            for q in queries
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_vacancies: List[Dict[str, Any]] = []
        seen_urls = set()
        seen_ids = set()

        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Batch query parser error: {res}")
                continue
            for vac in res:
                v_id = vac.get("id")
                url = vac.get("url")
                if (v_id and v_id in seen_ids) or (url and url in seen_urls):
                    continue
                if v_id:
                    seen_ids.add(v_id)
                if url:
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
        Full dynamic high-yield pipeline:
        1. Select batch of 3-5 queries from rotated query pool (or custom query)
        2. Fetch vacancies concurrently across all queries and pages (page & page + 1)
        3. Advance query index & page offset for next search cycle
        4. Upsert vacancies into database
        5. Fetch up to 500 unhidden & unviewed vacancies (filtered by city/remote preferences)
        6. Match vacancies with candidate profile using standard threshold, with adaptive
           fallback to soft threshold (35%) if fewer than 15 matches found
        7. Return ranked list of (Vacancy, match_dict)
        """
        if custom_query:
            batch_queries = [custom_query]
            current_page = user.search_page_offset or 0
        else:
            pool = self.generate_query_pool(resume)
            query_idx = user.last_query_index or 0
            current_page = user.search_page_offset or 0

            # Select a batch of 3-5 diverse queries from the rotated pool
            target_batch_size = min(4, len(pool)) if len(pool) >= 3 else len(pool)
            batch_queries = []
            for i in range(target_batch_size):
                q = pool[(query_idx + i) % len(pool)]
                if q not in batch_queries:
                    batch_queries.append(q)
            if not batch_queries:
                batch_queries = ["Python Developer"]

        logger.info(
            f"Searching vacancies for user {user.telegram_id}: queries={batch_queries}, "
            f"page={current_page}, city='{user.city or 'Any'}'"
        )

        # 1. Concurrently fetch fresh vacancies across batch of queries and pages
        raw_vacancies = await self.fetch_all_for_queries(
            queries=batch_queries,
            limit_per_source=settings.MAX_VACANCIES_PER_SOURCE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            page=current_page,
            scan_pages=2
        )

        # 2. Advance pagination and query rotation offsets for subsequent searches
        await UserRepository.increment_search_offsets(
            session=session,
            telegram_id=user.telegram_id,
            offset_inc=2,
            query_index_inc=len(batch_queries)
        )

        # 3. Upsert newly fetched vacancies into database
        await VacancyRepository.upsert_vacancies(session, raw_vacancies)

        # 4. Get unhidden, unviewed vacancies matching user's filters & city (up to 500 limit)
        vacancies = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_blocked=settings.RED_FLAG_STRICT_MODE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            min_salary=user.min_salary,
            exclude_viewed=True,
            user_city=user.city,
            limit=500
        )

        # 5. Match candidate resume against vacancies
        all_scored: List[Tuple[Vacancy, Dict[str, Any]]] = []
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
            all_scored.append((vac, match_res))

        min_standard_score = getattr(settings, "MIN_MATCH_SCORE", 45)
        soft_threshold = getattr(settings, "SOFT_MATCH_SCORE", 35)
        min_desired_count = getattr(settings, "MIN_DESIRED_MATCHES", 15)

        standard_matches = [
            (vac, res) for vac, res in all_scored
            if res["score"] >= min_standard_score
        ]

        if len(standard_matches) >= min_desired_count:
            chosen_matches = standard_matches
        else:
            logger.info(
                f"Adaptive match fallback activated for user {user.telegram_id}: "
                f"only {len(standard_matches)} met threshold {min_standard_score}%, "
                f"expanding pool with soft threshold {soft_threshold}%"
            )
            chosen_matches = []
            for vac, res in all_scored:
                if res["score"] >= min_standard_score:
                    chosen_matches.append((vac, res))
                elif res["score"] >= soft_threshold:
                    res_copy = dict(res)
                    cur_reason = res_copy.get("reason", "")
                    growth_marker = "🌱 Смежная позиция (зона роста)"
                    if growth_marker not in cur_reason:
                        res_copy["reason"] = f"{growth_marker} | {cur_reason}" if cur_reason else growth_marker
                    res_copy["is_adaptive"] = True
                    chosen_matches.append((vac, res_copy))

        matched_results: List[Tuple[Vacancy, Dict[str, Any]]] = []
        for vac, match_res in chosen_matches:
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

