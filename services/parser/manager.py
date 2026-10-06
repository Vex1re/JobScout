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
from services.parser.freelance_ru import FreelanceRuParser
from services.parser.habr_freelance import HabrFreelanceParser
from services.parser.remoteok import RemoteOKParser
from services.parser.superjob import SuperJobParser
from services.parser.kwork import KworkParser
from services.parser.rabota import RabotaRuParser
from services.parser.freelancehunt import FreelancehuntParser
from services.resume_analyzer.matcher import VacancyMatcher
from services.deduplication import deduplicate_vacancies
from core.redis import redis_client
from core.sentry import capture_exception
from core.metrics import record_vacancy_ingested, record_parser_error, record_search_latency
import json
import time

logger = logging.getLogger(__name__)

ALL_SOURCES: List[str] = [
    "hh",
    "habr",
    "trudvsem",
    "superjob",
    "remoteok",
    "kwork",
    "fl_ru",
    "freelance_ru",
    "rabota",
]

VACANCY_SOURCES: List[str] = [
    "hh",
    "habr",
    "trudvsem",
    "superjob",
    "remoteok",
    "rabota",
]

FREELANCE_SOURCES: List[str] = [
    "kwork",
    "fl_ru",
    "freelance_ru",
]

SOURCE_LABELS: Dict[str, str] = {
    "hh": "HeadHunter (hh.ru)",
    "habr": "Хабр Карьера",
    "trudvsem": "Работа России",
    "superjob": "SuperJob",
    "remoteok": "RemoteOK (Global)",
    "kwork": "Kwork (Фриланс)",
    "fl_ru": "FL.ru (Фриланс)",
    "freelance_ru": "Freelance.ru (Фриланс)",
    "habr_freelance": "Хабр Фриланс",
    "rabota": "Работа.ру",
    "freelancehunt": "Freelancehunt (Фриланс)",
}

if settings.ENABLE_FREELANCEHUNT:
    if "freelancehunt" not in ALL_SOURCES:
        ALL_SOURCES.append("freelancehunt")
    if "freelancehunt" not in FREELANCE_SOURCES:
        FREELANCE_SOURCES.append("freelancehunt")


class OnDemandSearchCache:
    """Caches raw parsed results by (source, query, city, page) to prevent duplicate crawling."""
    def __init__(self, ttl_seconds: int = 1200):
        self.ttl = ttl_seconds
        self._memory_cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

    def _make_key(self, source: str, query: str, city: Optional[str], page: int) -> str:
        q_norm = (query or "").strip().lower()
        c_norm = (city or "").strip().lower()
        return f"ondemand_cache:{source}:{q_norm}:{c_norm}:{page}"

    async def get(self, source: str, query: str, city: Optional[str], page: int) -> Optional[List[Dict[str, Any]]]:
        key = self._make_key(source, query, city, page)
        if redis_client.is_available:
            try:
                raw = await redis_client.get(key)
                if raw:
                    return json.loads(raw)
            except Exception:
                pass

        if key in self._memory_cache:
            ts, items = self._memory_cache[key]
            if time.time() - ts < self.ttl:
                return items
            self._memory_cache.pop(key, None)
        return None

    async def set(self, source: str, query: str, city: Optional[str], page: int, items: List[Dict[str, Any]]) -> None:
        key = self._make_key(source, query, city, page)
        # Store up to 50 items per key to preserve memory
        to_store = items[:50]
        if redis_client.is_available:
            try:
                await redis_client.set(key, json.dumps(to_store, default=str), ex=self.ttl)
            except Exception:
                pass
        self._memory_cache[key] = (time.time(), to_store)


class AggregatorManager:
    """
    Coordinates multi-platform parsing across HeadHunter, Habr Career, TrudVsem, SuperJob,
    RemoteOK, Kwork, FL.ru, Freelance.ru, and Rabota.ru.
    Aggregates results, applies scam detection and candidate-resume matching.
    Supports dynamic query rotation and pagination offsets.
    """

    MULTI_PAGE_PARSERS = {"hh", "trudvsem", "superjob", "habr", "rabota", "freelance_ru"}

    def __init__(self):
        self.cache = OnDemandSearchCache(ttl_seconds=settings.SEARCH_CACHE_TTL_MINUTES * 60)
        self.parsers: List[BaseVacanciesParser] = [
            HeadHunterParser(),
            HabrCareerParser(),
            TrudVsemParser(),
            SuperJobParser(),
            RemoteOKParser(),
            KworkParser(),
            FLRuParser(),
            FreelanceRuParser(),
            RabotaRuParser()
        ]
        if settings.ENABLE_FREELANCEHUNT:
            self.parsers.append(FreelancehuntParser())

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
        # Check if candidate is in IT / Software Development
        tech_indicators = [
            "developer", "разработчик", "программист", "backend", "бэкенд", "frontend",
            "фронтенд", "fullstack", "фулстек", "devops", "девопс", "qa", "тестировщик",
            "data scientist", "data engineer", "инженер данных", "ml", "software",
            "сисадмин", "sysadmin"
        ]
        is_it_role = any(re.search(rf"\b{re.escape(ti)}\b", title_lower) for ti in tech_indicators) or any(
            any(s.lower() == l.lower() for l in common_langs) or s.lower() in ["docker", "kubernetes", "fastapi", "django", "react", "vue"]
            for s in skills
        )

        if not is_it_role and (raw_title or skills):
            # Non-IT / Universal profession query generation
            clean_title = re.sub(
                r"\b(junior|middle|senior|lead|ведущий|главный|старший|младший|помощник|стажер)\b",
                "",
                raw_title,
                flags=re.IGNORECASE
            ).strip()

            base_role = clean_title if clean_title else raw_title

            # Clean role variants
            if base_role and base_role not in queries:
                queries.append(base_role)

            # Role + top skill pairings
            for s in skills[:3]:
                if s.lower() not in base_role.lower():
                    queries.append(f"{base_role} {s}".strip())

            # Top skills
            for s in skills[:3]:
                queries.append(s)

            if len(skills) >= 2:
                queries.append(f"{skills[0]} {skills[1]}")

            # Universal domain synonyms
            if any(w in title_lower for w in ["маркетолог", "маркетинг", "smm", "seo", "таргет"]):
                for syn in ["Маркетолог", "Интернет-маркетолог", "Специалист по маркетингу"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["бухгалтер", "бухгалтерия", "финанс", "экономист"]):
                for syn in ["Бухгалтер", "Бухгалтер 1С", "Помощник бухгалтера"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["продаж", "sales", "b2b", "клиент"]):
                for syn in ["Менеджер по продажам", "Специалист по продажам", "Менеджер по работе с клиентами"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["дизайн", "дизайнер", "ui/ux", "графическ"]):
                for syn in ["Дизайнер", "Графический дизайнер", "Веб-дизайнер"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["hr", "рекрутер", "кадр", "персонал"]):
                for syn in ["HR-менеджер", "Рекрутер", "Менеджер по персоналу"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["юрист", "юрисконсульт", "право"]):
                for syn in ["Юрист", "Юрисконсульт"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["логист", "логистик", "склад", "закупк"]):
                for syn in ["Логист", "Менеджер по логистике"]:
                    if syn not in queries:
                        queries.append(syn)
            elif any(w in title_lower for w in ["project", "проект", "управлен"]):
                for syn in ["Project Manager", "Менеджер проектов"]:
                    if syn not in queries:
                        queries.append(syn)

        else:
            # IT Developer query generation pipeline
            # 1. Identify primary language / tech
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
            queries.append(raw_title if raw_title else "Специалист")

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
        scan_pages: int = 2,
        enabled_sources: Optional[List[str]] = None,
        city: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Concurrently queries all active aggregators for a given query and city,
        scanning multiple pages (e.g. page and page + 1) for primary aggregators.
        Uses on-demand query cache to prevent redundant crawler hits.
        Filters aggregators if enabled_sources is specified.
        """
        async def _fetch_with_cache(p: BaseVacanciesParser, p_num: int):
            cached = await self.cache.get(p.name, query, city, p_num)
            if cached is not None:
                return cached
            try:
                res = await p.fetch_vacancies(
                    query=query,
                    limit=limit_per_source,
                    remote_only=remote_only,
                    page=p_num,
                    city=city
                )
                if res and isinstance(res, list):
                    record_vacancy_ingested(p.name, len(res))
                    await self.cache.set(p.name, query, city, p_num, res)
                return res
            except Exception as exc:
                record_parser_error(p.name, type(exc).__name__)
                capture_exception(exc, source=p.name)
                raise exc

        tasks = []
        for parser in self.parsers:
            if enabled_sources is not None and parser.name not in enabled_sources:
                continue

            is_freelance = getattr(parser, "is_freelance", False) or parser.name in FREELANCE_SOURCES
            if is_freelance and not include_freelance:
                continue

            if parser.name in self.MULTI_PAGE_PARSERS and scan_pages > 1:
                for p_offset in range(scan_pages):
                    tasks.append(_fetch_with_cache(parser, page + p_offset))
            else:
                tasks.append(_fetch_with_cache(parser, page))

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
        scan_pages: int = 2,
        enabled_sources: Optional[List[str]] = None,
        city: Optional[str] = None
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
                scan_pages=scan_pages,
                enabled_sources=enabled_sources,
                city=city
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
        Decoupled search pipeline:
        1. Checks database first for matching vacancies matching candidate preferences & city.
        2. If database already has enough fresh matches (>= MIN_DESIRED_MATCHES), serve directly.
        3. If DB matches < MIN_DESIRED_MATCHES, triggers on-demand fetch with query TTL-cache.
        4. Deduplicates cross-source postings and upserts into database.
        5. Matches vacancies with candidate profile using standard threshold, with adaptive
           fallback to soft threshold (35%) if fewer than 15 matches found.
        6. Returns ranked list of (Vacancy, match_dict).
        """
        t_start = time.perf_counter()
        if custom_query:
            batch_queries = [custom_query]
            current_page = (user.search_page_offset or 0) % 5
        else:
            pool = self.generate_query_pool(resume)
            query_idx = user.last_query_index or 0
            current_page = (user.search_page_offset or 0) % 5

            target_batch_size = min(4, len(pool)) if len(pool) >= 3 else len(pool)
            batch_queries = []
            for i in range(target_batch_size):
                q = pool[(query_idx + i) % len(pool)]
                if q not in batch_queries:
                    batch_queries.append(q)
            if not batch_queries:
                batch_queries = ["Python Developer"]

        user_sources = user.get_effective_sources()
        logger.info(
            f"Searching vacancies for user {user.telegram_id}: queries={batch_queries}, "
            f"page={current_page}, city='{user.city or 'Any'}', sources={user_sources}"
        )

        min_standard_score = getattr(settings, "MIN_MATCH_SCORE", 45)
        soft_threshold = getattr(settings, "SOFT_MATCH_SCORE", 35)
        min_desired_count = getattr(settings, "MIN_DESIRED_MATCHES", 15)

        # Step 1: Query local database first
        vacancies = await VacancyRepository.get_unhidden_vacancies(
            session=session,
            user_id=user.telegram_id,
            exclude_blocked=settings.RED_FLAG_STRICT_MODE,
            remote_only=user.remote_only,
            include_freelance=user.include_freelance,
            min_salary=user.min_salary,
            exclude_viewed=True,
            user_city=user.city,
            allowed_sources=user_sources,
            limit=500
        )

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

        matching_count = sum(1 for _, res in all_scored if res["score"] >= min_standard_score)

        # Step 2: Trigger on-demand external crawl ONLY if DB bucket has fewer than desired matches
        if matching_count < min_desired_count:
            logger.info(
                f"DB matches ({matching_count}) < {min_desired_count} for user {user.telegram_id}. "
                f"Triggering on-demand external search across aggregators..."
            )
            raw_vacancies = await self.fetch_all_for_queries(
                queries=batch_queries,
                limit_per_source=settings.MAX_VACANCIES_PER_SOURCE,
                remote_only=user.remote_only,
                include_freelance=user.include_freelance,
                page=current_page,
                scan_pages=2,
                enabled_sources=user_sources,
                city=user.city
            )

            # Deduplicate and upsert
            deduped = deduplicate_vacancies(raw_vacancies)
            await VacancyRepository.upsert_vacancies(session, deduped)

            # Re-fetch from DB
            vacancies = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=user.telegram_id,
                exclude_blocked=settings.RED_FLAG_STRICT_MODE,
                remote_only=user.remote_only,
                include_freelance=user.include_freelance,
                min_salary=user.min_salary,
                exclude_viewed=True,
                user_city=user.city,
                allowed_sources=user_sources,
                limit=500
            )

            all_scored = []
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
        else:
            logger.info(
                f"Found {matching_count} warm matches in DB for user {user.telegram_id}. "
                f"Serving directly from database without external scraping."
            )

        # Advance pagination and query rotation offsets
        await UserRepository.increment_search_offsets(
            session=session,
            telegram_id=user.telegram_id,
            offset_inc=2,
            query_index_inc=len(batch_queries)
        )

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
        record_search_latency(time.perf_counter() - t_start)
        return matched_results


aggregator_manager = AggregatorManager()

