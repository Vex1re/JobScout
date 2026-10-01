import asyncio
import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.database.session import async_session_factory
from core.database.repository import UserRepository, InteractionRepository
from services.parser.manager import aggregator_manager
from bot.formatters.card import format_vacancy_card
from bot.keyboards.inline import get_vacancy_card_keyboard

logger = logging.getLogger(__name__)


async def run_periodic_alerts(bot: Bot):
    """
    Background job that checks for fresh high-matching vacancies
    and pushes alert notifications to subscribed users.
    """
    logger.info("Starting background vacancy alert cycle...")
    
    async with async_session_factory() as session:
        try:
            users = await UserRepository.get_active_users_with_resumes(session)
            logger.info(f"Found {len(users)} active users with resumes for background checks.")

            for user in users:
                try:
                    resume = user.resume
                    if not resume or not resume.skills:
                        continue

                    # Search and match
                    matches = await aggregator_manager.search_and_match_for_user(
                        session=session,
                        user=user,
                        resume=resume
                    )

                    # Filter top matches with score >= 70%
                    fresh_high_matches = [
                        (vac, info) for vac, info in matches
                        if info.get("score", 0) >= 70
                    ]

                    # Notify for up to 2 top fresh vacancies per cycle to not spam
                    sent_count = 0
                    for vac, info in fresh_high_matches:
                        # Check if user already marked it or if already sent
                        # We save is_sent=True once notified
                        match_rec = await InteractionRepository.save_or_update_match(
                            session=session,
                            user_id=user.telegram_id,
                            vacancy_id=vac.id,
                            score=info["score"],
                            matched_skills=info["matched_skills"],
                            missing_skills=info["missing_skills"],
                            is_sent=True
                        )

                        card_text = format_vacancy_card(vac, info)
                        keyboard = get_vacancy_card_keyboard(
                            vacancy_id=vac.id,
                            url=vac.url,
                            is_favorite=False,
                            current_index=0,
                            total_count=1,
                            has_ai_tip=True
                        )

                        alert_msg = f"🔔 <b>Свежая вакансия под ваш стек!</b>\n\n{card_text}"
                        
                        await bot.send_message(
                            chat_id=user.telegram_id,
                            text=alert_msg,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                        sent_count += 1
                        if sent_count >= 2:
                            break

                        await asyncio.sleep(1.0) # Telegram rate limiting safety

                except Exception as user_err:
                    logger.error(f"Error processing background alerts for user {user.telegram_id}: {user_err}")

        except Exception as e:
            logger.error(f"Error in background alert job: {e}", exc_info=True)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Configures and starts the background task scheduler."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_periodic_alerts,
        "interval",
        minutes=settings.AUTO_SEARCH_INTERVAL_MINUTES,
        args=[bot],
        id="vacancy_alerts_job",
        replace_existing=True
    )
    return scheduler
