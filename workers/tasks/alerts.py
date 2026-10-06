import logging
from typing import Dict, Any, Optional
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

from core.config import settings
from core.database.session import async_session_factory
from core.database.repository import UserRepository, InteractionRepository
from services.parser.manager import aggregator_manager
from bot.formatters.card import format_vacancy_card
from bot.keyboards.inline import get_vacancy_card_keyboard

logger = logging.getLogger(__name__)


async def process_user_alert(ctx: Dict[str, Any], telegram_id: int) -> int:
    """
    Worker task: checks vacancies for a specific user and delivers fresh top matches.
    Idempotent and isolated per user.
    """
    logger.info(f"Processing alert task for user {telegram_id}...")

    bot: Optional[Bot] = ctx.get("bot")
    close_bot = False
    if bot is None:
        if not settings.BOT_TOKEN:
            logger.warning("No BOT_TOKEN configured. Cannot send alerts.")
            return 0
        bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        close_bot = True

    sent_count = 0
    try:
        async with async_session_factory() as session:
            user = await UserRepository.get_user_by_telegram_id(session, telegram_id)
            if not user or not user.is_active or not user.auto_notify:
                return 0

            resume = user.resume
            if not resume or (not resume.skills and not resume.title):
                return 0

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

            for vac, info in fresh_high_matches[:2]:
                try:
                    await InteractionRepository.save_or_update_match(
                        session=session,
                        user_id=user.telegram_id,
                        vacancy_id=vac.id,
                        score=info["score"],
                        matched_skills=info["matched_skills"],
                        missing_skills=info["missing_skills"],
                        is_sent=True
                    )

                    text = (
                        "🔔 <b>Новая вакансия по вашему профилю!</b>\n\n"
                        + format_vacancy_card(vac, match_info=info, index=1, total=1)
                    )
                    kb = get_vacancy_card_keyboard(
                        vacancy_id=vac.id,
                        url=vac.url,
                        current_index=0,
                        total_count=1,
                        is_favorite=False,
                        is_hidden=False,
                        has_ai_advice=False
                    )

                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=text,
                        reply_markup=kb,
                        disable_web_page_preview=True
                    )
                    sent_count += 1
                except (TelegramForbiddenError, TelegramBadRequest) as e:
                    logger.warning(
                        f"User {user.telegram_id} cannot receive messages ({e}). Deactivating notifications."
                    )
                    await UserRepository.update_settings(
                        session=session,
                        telegram_id=user.telegram_id,
                        auto_notify=False
                    )
                    user.is_active = False
                    await session.commit()
                    break
                except Exception as e:
                    logger.error(f"Error delivering vacancy {vac.id} to {user.telegram_id}: {e}")

    finally:
        if close_bot and bot is not None:
            await bot.session.close()

    return sent_count
