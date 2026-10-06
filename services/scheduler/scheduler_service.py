import asyncio
import logging
import sys
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.database.session import async_session_factory, init_db
from core.database.repository import UserRepository
from core.queue import enqueue_task, get_arq_pool
from workers.tasks.alerts import process_user_alert

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [Scheduler]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("JobScoutScheduler")


async def trigger_periodic_alerts():
    """
    Lightweight scheduler trigger: queries active users and enqueues alert jobs to the task queue.
    Does NOT perform heavy network scraping in this process.
    """
    logger.info("Executing periodic alert scheduler trigger...")
    arq_pool = await get_arq_pool()

    async with async_session_factory() as session:
        try:
            users = await UserRepository.get_active_users_with_resumes(session)
            logger.info(f"Enqueuing alert jobs for {len(users)} active subscribed users.")

            timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M")
            for user in users:
                job_id = f"alert_{user.telegram_id}_{timestamp_str}"
                if arq_pool is not None:
                    await enqueue_task("process_user_alert", user.telegram_id, job_id=job_id)
                else:
                    # In local dev without Redis, process in background task
                    asyncio.create_task(process_user_alert({}, user.telegram_id))

        except Exception as e:
            logger.error(f"Error enqueuing user alert jobs: {e}", exc_info=True)


async def main():
    logger.info("Starting JobScout standalone scheduler service...")
    await init_db()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        trigger_periodic_alerts,
        trigger="interval",
        minutes=settings.AUTO_SEARCH_INTERVAL_MINUTES,
        id="periodic_alerts_job",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler running (interval: {settings.AUTO_SEARCH_INTERVAL_MINUTES}m). Press Ctrl+C to exit.")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping scheduler...")
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
