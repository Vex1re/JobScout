import logging
import asyncio
from typing import Optional, List, Dict, Any
from core.database.session import async_session_factory
from core.database.repository import VacancyRepository
from services.deduplication import deduplicate_vacancies

logger = logging.getLogger(__name__)

DEFAULT_ROLES: List[str] = [
    "Python Developer",
    "Java Developer",
    "Frontend Developer",
    "Backend Developer",
    "QA Engineer",
    "DevOps Engineer",
    "Data Scientist",
    "Project Manager",
    "Системный администратор",
    "Дизайнер",
    "Бухгалтер",
    "Менеджер по продажам",
    "Маркетолог"
]

DEFAULT_CITIES: List[Optional[str]] = [
    None,  # Все города / Удаленно
    "Москва",
    "Санкт-Петербург",
    "Казань",
    "Екатеринбург",
    "Новосибирск"
]


async def crawl_bucket(
    ctx: Dict[str, Any],
    role: str,
    city: Optional[str] = None,
    remote_only: bool = False,
    scan_pages: int = 2
) -> int:
    """
    Crawls aggregators for a specific (role × city × remote) bucket,
    pre-computes all vacancy metadata (grade, experience, skills, red-flags, canonical_id),
    deduplicates cross-source postings, and upserts into database.
    """
    from services.parser.manager import aggregator_manager

    logger.info(f"Crawler started for bucket: role='{role}', city='{city or 'Any'}', remote={remote_only}")
    try:
        raw_vacancies = await aggregator_manager.fetch_all_for_query(
            query=role,
            limit_per_source=30,
            remote_only=remote_only,
            include_freelance=True,
            page=0,
            scan_pages=scan_pages,
            city=city
        )

        if not raw_vacancies:
            logger.info(f"Crawler found 0 vacancies for bucket: role='{role}', city='{city}'")
            return 0

        # Cross-source deduplication
        deduped = deduplicate_vacancies(raw_vacancies)

        # Upsert into DB
        async with async_session_factory() as session:
            added = await VacancyRepository.upsert_vacancies(session, deduped)

        logger.info(
            f"Crawler finished bucket: role='{role}', city='{city}': "
            f"fetched {len(raw_vacancies)}, deduped {len(deduped)}, new saved {added}"
        )
        return added

    except Exception as e:
        logger.error(f"Error in crawl_bucket for '{role}' ({city}): {e}", exc_info=True)
        return 0


async def crawl_all_buckets(ctx: Dict[str, Any]) -> int:
    """
    Orchestrates ingestion across high-demand buckets.
    Enqueues tasks into queue or executes sequential batch.
    """
    from core.queue import enqueue_task

    total_enqueued = 0
    logger.info("Starting crawl_all_buckets ingestion sweep...")

    for role in DEFAULT_ROLES:
        for city in DEFAULT_CITIES:
            # Crawl remote and office buckets
            for remote_only in ([True, False] if city is None else [False]):
                # Enqueue to background queue if available, else run directly
                try:
                    await enqueue_task(
                        "crawl_bucket",
                        role=role,
                        city=city,
                        remote_only=remote_only,
                        scan_pages=1
                    )
                    total_enqueued += 1
                except Exception:
                    # In dev / no queue fallback
                    await crawl_bucket(ctx, role=role, city=city, remote_only=remote_only, scan_pages=1)
                    total_enqueued += 1

    logger.info(f"Crawl all buckets completed. Enqueued/ran {total_enqueued} bucket crawl jobs.")
    return total_enqueued
