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
from bot.keyboards.inline import get_vacancy_card_keyboard, get_onboarding_keyboard

router = Router(name="vacancies")

# In-memory session store for user active search results: user_id -> list of (vac_dict, match_dict)
USER_SEARCH_RESULTS: Dict[int, List[Tuple[Vacancy, Dict[str, Any]]]] = {}


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
            "чтобы бот знал ваши технологии и опыт.",
            reply_markup=get_onboarding_keyboard()
        )
        return

    status_msg = await message.answer(
        f"🔎 <b>Ищу вакансии для {html.escape(resume.title)}...</b>\n"
        f"Стек: <code>{', '.join(resume.skills[:4])}</code>\n\n"
        f"🌐 Опрашиваю <b>HeadHunter</b>, <b>Хабр Карьеру</b>, <b>Kwork</b> и <b>Работа.ру</b>...\n"
        f"🛡️ Проверяю на мошенничество и ред-флаги..."
    )

    results = await aggregator_manager.search_and_match_for_user(
        session=session,
        user=user,
        resume=resume
    )

    if not results:
        await status_msg.edit_text(
            "😔 <b>По вашему запросу сейчас ничего не найдено.</b>\n\n"
            "Попробуйте:\n"
            "• Добавить больше ключевых навыков в резюме (/profile)\n"
            "• Смягчить фильтры поиска в /settings\n\n"
            "Бот продолжит фоновый мониторинг и сразу пришлет уведомление, "
            "когда появятся подходящие вакансии! 🔔"
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
        await message.edit_text("ℹ️ Нет доступных вакансий в текущей подборке.")
        return

    vac, match_info = results[index]
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
        await callback.message.edit_text("ℹ️ Все вакансии из этой подборки просмотрены или скрыты.")
    else:
        new_index = min(curr_index, len(results) - 1)
        await _send_vacancy_page(callback.message, user_id, new_index, session, edit=True)


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
