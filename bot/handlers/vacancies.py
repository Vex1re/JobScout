import html
from typing import Dict, Any, List, Tuple
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Vacancy
from core.database.repository import (
    UserRepository,
    ResumeRepository,
    VacancyRepository,
    InteractionRepository
)
from services.parser.manager import aggregator_manager
from services.ai.llm_helper import llm_helper
from bot.formatters.card import format_vacancy_card
from bot.keyboards.inline import (
    get_vacancy_card_keyboard,
    get_onboarding_keyboard,
    get_empty_feed_keyboard
)

router = Router(name="vacancies")

import time

class SearchResultsCache(dict):
    """
    Bounded, TTL-aware session store for active user search results.
    Prevents memory leaks in production and provides seamless dict compatibility.
    """
    def __init__(self, ttl_seconds: float = 7200.0, max_users: int = 1000):
        super().__init__()
        self.ttl = ttl_seconds
        self.max_users = max_users
        self.timestamps: Dict[int, float] = {}

    def __setitem__(self, user_id: int, results: Any):
        now = time.time()
        cutoff = now - self.ttl
        expired = [u for u, t in self.timestamps.items() if t < cutoff]
        for u in expired:
            self.pop(u, None)
            self.timestamps.pop(u, None)

        if len(self.timestamps) >= self.max_users and user_id not in self.timestamps:
            oldest_user = min(self.timestamps, key=self.timestamps.get)
            self.pop(oldest_user, None)
            self.timestamps.pop(oldest_user, None)

        self.timestamps[user_id] = now
        super().__setitem__(user_id, results)

    def get(self, user_id: int, default: Any = None) -> Any:
        now = time.time()
        if user_id in self:
            if now - self.timestamps.get(user_id, 0) > self.ttl:
                self.pop(user_id, None)
                self.timestamps.pop(user_id, None)
                return default
            return super().get(user_id, default)
        return default

    def __len__(self) -> int:
        now = time.time()
        cutoff = now - self.ttl
        expired = [u for u, t in self.timestamps.items() if t < cutoff]
        for u in expired:
            self.pop(u, None)
            self.timestamps.pop(u, None)
        return super().__len__()

# Session store for user active search results: user_id -> list of (vac_dict, match_dict)
USER_SEARCH_RESULTS: Dict[int, List[Tuple[Vacancy, Dict[str, Any]]]] = SearchResultsCache()


@router.message(Command("search"))
@router.message(F.text == "🔍 Найти вакансии")
@router.callback_query(F.data == "action_search_now")
async def trigger_search(event: types.Message | types.CallbackQuery, session: AsyncSession):
    is_callback = isinstance(event, types.CallbackQuery)
    user_id = event.from_user.id

    if is_callback:
        await event.answer()
        message = event.message
    else:
        message = event

    user = await UserRepository.get_or_create_user(session=session, telegram_id=user_id)
    resume = await ResumeRepository.get_resume(session=session, user_id=user_id)

    if not resume:
        await message.answer(
            "⚠️ <b>У вас пока нет сохраненного резюме!</b>\n\n"
            "Пожалуйста, загрузите резюме (PDF/DOCX или текстом), "
            "чтобы бот знал ваши навыки и опыт.",
            reply_markup=get_onboarding_keyboard()
        )
        return

    skills_desc = f"Навыки: <code>{', '.join(resume.skills[:5])}</code>\n\n" if resume.skills else ""
    status_msg = await message.answer(
        f"🔎 <b>Ищу вакансии для: {html.escape(resume.title)}...</b>\n"
        f"{skills_desc}"
        f"🌐 Опрашиваю подключенные площадки и биржи...\n"
        f"🛡️ Проверяю на мошенничество и ред-флаги..."
    )

    results = await aggregator_manager.search_and_match_for_user(
        session=session,
        user=user,
        resume=resume
    )

    if not results:
        await status_msg.edit_text(
            "😔 <b>Новых вакансий по вашему запросу сейчас не найдено.</b>\n\n"
            "Возможно, все текущие предложения уже просмотрены или скрыты.\n\n"
            "Попробуйте:\n"
            "• Нажать <b>«🔄 Обновить подборку»</b> (поиск по другим навыкам и страницам)\n"
            "• Нажать <b>«🔄 Сбросить историю просмотров»</b>\n"
            "• Смягчить фильтры поиска в /settings",
            reply_markup=get_empty_feed_keyboard()
        )
        return

    USER_SEARCH_RESULTS[user_id] = results

    # Render first vacancy card
    await _send_vacancy_page(status_msg, user_id, index=0, session=session, edit=True)


async def _send_vacancy_page(
    message: types.Message,
    user_id: int,
    index: int,
    session: AsyncSession,
    edit: bool = False
):
    results = USER_SEARCH_RESULTS.get(user_id, [])
    if not results or index >= len(results) or index < 0:
        await message.edit_text(
            "ℹ️ <b>Все вакансии из текущей подборки просмотрены.</b>\n\n"
            "Вы можете запросить свежие вакансии или сбросить историю просмотров:",
            reply_markup=get_empty_feed_keyboard()
        )
        return

    vac, match_info = results[index]

    # Track as viewed in database
    await InteractionRepository.mark_as_viewed(session=session, user_id=user_id, vacancy_id=vac.id)

    is_fav = await InteractionRepository.is_favorite(session=session, user_id=user_id, vacancy_id=vac.id)

    card_text = format_vacancy_card(vac, match_info)
    keyboard = get_vacancy_card_keyboard(
        vacancy_id=vac.id,
        url=vac.url,
        is_favorite=is_fav,
        current_index=index,
        total_count=len(results),
        has_ai_tip=True
    )

    if edit:
        await message.edit_text(card_text, reply_markup=keyboard)
    else:
        await message.answer(card_text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("vac_page:"))
async def handle_pagination(callback: types.CallbackQuery, session: AsyncSession):
    page_index = int(callback.data.split(":")[1])
    await _send_vacancy_page(callback.message, callback.from_user.id, page_index, session, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("fav_add:"))
async def handle_fav_add(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    vac_id = parts[1]
    curr_index = int(parts[2]) if len(parts) > 2 else 0

    await InteractionRepository.toggle_favorite(session=session, user_id=callback.from_user.id, vacancy_id=vac_id)
    await callback.answer("⭐ Вакансия добавлена в избранное!")

    # Refresh card to update favorite button
    await _send_vacancy_page(callback.message, callback.from_user.id, curr_index, session, edit=True)


@router.callback_query(F.data.startswith("fav_remove:"))
async def handle_fav_remove(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    vac_id = parts[1]
    curr_index = int(parts[2]) if len(parts) > 2 else 0

    await InteractionRepository.toggle_favorite(session=session, user_id=callback.from_user.id, vacancy_id=vac_id)
    await callback.answer("Удалено из избранного.")

    # Refresh card
    await _send_vacancy_page(callback.message, callback.from_user.id, curr_index, session, edit=True)


@router.callback_query(F.data.startswith("vac_hide:"))
async def handle_hide_vacancy(callback: types.CallbackQuery, session: AsyncSession):
    parts = callback.data.split(":")
    vac_id = parts[1]
    curr_index = int(parts[2]) if len(parts) > 2 else 0

    user_id = callback.from_user.id
    await InteractionRepository.hide_vacancy(session=session, user_id=user_id, vacancy_id=vac_id)

    # Remove from active results list
    results = USER_SEARCH_RESULTS.get(user_id, [])
    if results and 0 <= curr_index < len(results):
        results.pop(curr_index)
        USER_SEARCH_RESULTS[user_id] = results

    await callback.answer("🚫 Вакансия скрыта и больше не появится в ленте.")

    if not results:
        await callback.message.edit_text(
            "ℹ️ <b>Все вакансии из этой подборки просмотрены или скрыты.</b>\n\n"
            "Вы можете запросить свежие вакансии или сбросить историю просмотров:",
            reply_markup=get_empty_feed_keyboard()
        )
    else:
        new_index = min(curr_index, len(results) - 1)
        await _send_vacancy_page(callback.message, user_id, new_index, session, edit=True)


@router.callback_query(F.data == "vac_refresh_feed")
async def handle_refresh_feed(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    await callback.answer("🔄 Запрашиваю свежие вакансии...")

    user = await UserRepository.get_or_create_user(session=session, telegram_id=user_id)
    resume = await ResumeRepository.get_resume(session=session, user_id=user_id)

    if not resume:
        await callback.message.answer(
            "⚠️ Резюме не найдено. Пожалуйста, загрузите резюме (/profile).",
            reply_markup=get_onboarding_keyboard()
        )
        return

    status_msg = await callback.message.edit_text(
        "🔎 <b>Ищу новые вакансии на агрегаторах...</b>\n"
        "Ротирую поисковые запросы и опрашиваю следующие страницы выдачи..."
    )

    results = await aggregator_manager.search_and_match_for_user(
        session=session,
        user=user,
        resume=resume
    )

    if not results:
        await status_msg.edit_text(
            "ℹ️ <b>Все найденные вакансии уже просмотрены или скрыты.</b>\n\n"
            "Вы можете сбросить историю просмотров, чтобы пересмотреть подходящие предложения, "
            "или обновить подборку позже.",
            reply_markup=get_empty_feed_keyboard()
        )
        return

    USER_SEARCH_RESULTS[user_id] = results
    await _send_vacancy_page(status_msg, user_id, index=0, session=session, edit=True)


@router.callback_query(F.data == "vac_reset_history")
async def handle_reset_history(callback: types.CallbackQuery, session: AsyncSession):
    user_id = callback.from_user.id
    count = await InteractionRepository.reset_viewed_history(session=session, user_id=user_id)
    await UserRepository.update_preferences(
        session=session,
        telegram_id=user_id,
        search_page_offset=0,
        last_query_index=0
    )

    await callback.answer(f"История просмотров сброшена ({count} вакансий).", show_alert=True)

    user = await UserRepository.get_or_create_user(session=session, telegram_id=user_id)
    resume = await ResumeRepository.get_resume(session=session, user_id=user_id)

    if not resume:
        await callback.message.edit_text(
            "⚠️ Резюме не найдено.",
            reply_markup=get_onboarding_keyboard()
        )
        return

    status_msg = await callback.message.edit_text(
        "🔄 <b>История просмотров сброшена!</b>\n\nФормирую подборку заново..."
    )

    results = await aggregator_manager.search_and_match_for_user(
        session=session,
        user=user,
        resume=resume
    )

    if not results:
        await status_msg.edit_text(
            "😔 Вакансий по текущим критериям не найдено.",
            reply_markup=get_empty_feed_keyboard()
        )
        return

    USER_SEARCH_RESULTS[user_id] = results
    await _send_vacancy_page(status_msg, user_id, index=0, session=session, edit=True)


@router.callback_query(F.data.startswith("ai_tip:"))
async def handle_ai_tip(callback: types.CallbackQuery, session: AsyncSession):
    vac_id = callback.data.split(":")[1]
    vac = await VacancyRepository.get_vacancy(session, vac_id)
    resume = await ResumeRepository.get_resume(session, callback.from_user.id)

    if not vac or not resume:
        await callback.answer("Информация недоступна", show_alert=True)
        return

    await callback.answer("Готовлю рекомендацию...")

    tip = None
    if llm_helper.is_available:
        missing = [s for s in (vac.requirements or []) if s not in resume.skills]
        tip = await llm_helper.generate_application_tip(
            candidate_skills=resume.skills,
            candidate_grade=resume.grade,
            vacancy_title=vac.title,
            vacancy_company=vac.company,
            missing_skills=missing
        )

    if not tip:
        # Fallback intelligent tip
        tip = (
            f"💡 <b>Совет для отклика на «{html.escape(vac.title)}»:</b>\n\n"
            f"В сопроводительном письме сделайте акцент на вашем опыте работы с "
            f"<b>{', '.join(resume.skills[:3])}</b>. "
            f"Упомяните реальные задачи или пет-проекты, в которых вы решали похожие кейсы, "
            f"и выразите интерес к стеку компании."
        )
    else:
        tip = f"💡 <b>Персональный AI-совет для отклика:</b>\n\n{tip}"

    await callback.message.reply(tip)


@router.callback_query(F.data == "noop")
async def handle_noop(callback: types.CallbackQuery):
    await callback.answer()
