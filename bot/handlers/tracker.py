import html
import logging
from typing import Optional, List
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database.models import User, Vacancy, Resume, JobApplicationTracker
from core.database.repository import (
    UserRepository,
    TrackerRepository,
    SubscriptionRepository,
    VacancyRepository,
    ResumeRepository
)
from services.ai.base import get_llm_provider, sanitize_llm_input

logger = logging.getLogger(__name__)

router = Router(name="tracker")

STATUS_EMOJIS = {
    "applied": "📨 Отклик",
    "screening": "📞 Скрининг",
    "interview": "💼 Интервью",
    "offer": "🏆 Оффер",
    "rejected": "❌ Отказ"
}

STATUS_CYCLE = ["applied", "screening", "interview", "offer", "rejected"]


def get_application_keyboard(app: JobApplicationTracker) -> InlineKeyboardMarkup:
    current_idx = STATUS_CYCLE.index(app.status) if app.status in STATUS_CYCLE else 0
    next_status = STATUS_CYCLE[(current_idx + 1) % len(STATUS_CYCLE)]
    next_label = STATUS_EMOJIS[next_status]

    buttons = [
        [
            InlineKeyboardButton(text=f"➔ Перевести в {next_label}", callback_data=f"set_status:{app.id}:{next_status}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"del_app:{app.id}")
        ],
        [
            InlineKeyboardButton(text="📋 К доске", callback_data="open_tracker")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("tracker"))
@router.callback_query(F.data == "open_tracker")
async def show_tracker(event: Message | CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    message = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()

    if user is None:
        from_user = event.from_user
        if from_user:
            user = await UserRepository.get_or_create_user(
                session=session,
                telegram_id=from_user.id,
                username=from_user.username,
                first_name=from_user.first_name
            )

    user_id = user.telegram_id if user else (event.from_user.id if event.from_user else 0)

    # Check entitlement
    has_access = await SubscriptionRepository.has_entitlement(session, user_id, "kanban_tracker")
    has_active_sub = await SubscriptionRepository.has_active_subscription(session, user_id)

    applications = await TrackerRepository.get_user_applications(session, user_id)

    # Status breakdown
    counts = {s: 0 for s in STATUS_CYCLE}
    for app in applications:
        if app.status in counts:
            counts[app.status] += 1

    header = (
        "📊 <b>Канбан-трекер откликов</b>\n\n"
        f"📨 <b>Отклики:</b> {counts['applied']} | "
        f"📞 <b>Скрининг:</b> {counts['screening']} | "
        f"💼 <b>Интервью:</b> {counts['interview']}\n"
        f"🏆 <b>Офферы:</b> {counts['offer']} | "
        f"❌ <b>Отказы:</b> {counts['rejected']}\n"
        "────────────────────────\n"
    )

    if not applications:
        empty_text = (
            f"{header}\n"
            "У вас пока нет отслеживаемых откликов.\n\n"
            "Нажимайте кнопку <b>«📌 В трекер»</b> на карточках вакансий, "
            "чтобы переносить их в воронку и отслеживать прогресс!"
        )
        await message.answer(
            empty_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔍 Найти вакансии", callback_data="search_vacancies"),
                InlineKeyboardButton(text="💎 Подписка PRO", callback_data="open_premium")
            ]])
        )
        return

    text = f"{header}\n<b>Ваши текущие отклики:</b>\n\n"
    buttons = []

    for idx, app in enumerate(applications[:8], start=1):
        status_badge = STATUS_EMOJIS.get(app.status, app.status)
        text += f"{idx}. <b>{html.escape(app.company)}</b> — {html.escape(app.title)}\n   Статус: {status_badge}\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"{idx}. {app.company[:12]} ({status_badge})",
                callback_data=f"view_app:{app.id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(text="💎 Управление подпиской", callback_data="open_premium"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="to_main_menu")
    ])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("view_app:"))
async def on_view_application(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    app_id = int(call.data.split(":")[1])
    stmt = select(JobApplicationTracker).where(
        JobApplicationTracker.id == app_id,
        JobApplicationTracker.user_id == user.telegram_id
    )
    res = await session.execute(stmt)
    app = res.scalar_one_or_none()

    if not app:
        await call.answer("Отклик не найден.", show_alert=True)
        return

    status_badge = STATUS_EMOJIS.get(app.status, app.status)
    created_str = app.created_at.strftime("%d.%m.%Y")
    notes_str = f"\nЗаметка: {html.escape(app.notes)}" if app.notes else ""
    url_str = f"\nСсылка: <a href='{app.url}'>Открыть вакансию</a>" if app.url else ""

    text = (
        f"📋 <b>Карточка отклика</b>\n\n"
        f"<b>Должность:</b> {html.escape(app.title)}\n"
        f"<b>Компания:</b> {html.escape(app.company)}\n"
        f"<b>Статус:</b> {status_badge}\n"
        f"<b>Дата добавления:</b> {created_str}"
        f"{url_str}{notes_str}"
    )

    await call.message.edit_text(text, reply_markup=get_application_keyboard(app))
    await call.answer()


@router.callback_query(F.data.startswith("set_status:"))
async def on_set_status(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    parts = call.data.split(":")
    app_id = int(parts[1])
    new_status = parts[2]

    updated = await TrackerRepository.update_status(session, app_id, user.telegram_id, new_status)
    if not updated:
        await call.answer("Ошибка обновления статуса", show_alert=True)
        return

    await call.answer(f"Статус изменён на: {STATUS_EMOJIS.get(new_status, new_status)}")
    await on_view_application(call, session, user)


@router.callback_query(F.data.startswith("del_app:"))
async def on_delete_application(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    app_id = int(call.data.split(":")[1])
    deleted = await TrackerRepository.delete_application(session, app_id, user.telegram_id)
    if deleted:
        await call.answer("Отклик удалён из трекера.")
        await show_tracker(call, session, user)
    else:
        await call.answer("Не удалось удалить.", show_alert=True)


@router.callback_query(F.data.startswith("track_vac:"))
async def on_track_vacancy(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    vac_id = call.data.split(":", 1)[1]
    stmt = select(Vacancy).where(Vacancy.id == vac_id)
    res = await session.execute(stmt)
    vac = res.scalar_one_or_none()

    if not vac:
        await call.answer("Вакансия не найдена.", show_alert=True)
        return

    app = await TrackerRepository.create_or_update_application(
        session=session,
        user_id=user.telegram_id,
        title=vac.title,
        company=vac.company,
        url=vac.url,
        vacancy_id=vac.id,
        vacancy_canonical_id=vac.canonical_id,
        status="applied"
    )

    await call.answer("📌 Вакансия добавлена в трекер откликов!", show_alert=True)


@router.callback_query(F.data.startswith("ai_letter:"))
async def on_ai_cover_letter(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    # Check entitlement or admin bypass
    is_admin = user and (user.telegram_id in settings.ADMIN_IDS)
    has_ent = await SubscriptionRepository.has_entitlement(session, user.telegram_id, "ai_cover_letter")
    has_sub = await SubscriptionRepository.has_active_subscription(session, user.telegram_id)

    if not (is_admin or has_ent or has_sub):
        await call.answer("Доступно только в подписке PRO!", show_alert=True)
        await call.message.answer(
            "⭐ <b>AI-сопроводительные письма доступны в подписке PRO</b>\n\n"
            "Нейросеть составляет индивидуальное, убедительное сопроводительное письмо под требования конкретного работодателя.\n\n"
            "Оформите подписку через /premium, чтобы разблокировать эту функцию!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⭐ Оформить PRO (150 Stars)", callback_data="buy_sub:pro")
            ]])
        )
        return

    vac_id = call.data.split(":", 1)[1]
    stmt = select(Vacancy).where(Vacancy.id == vac_id)
    res = await session.execute(stmt)
    vac = res.scalar_one_or_none()

    if not vac:
        await call.answer("Вакансия не найдена.", show_alert=True)
        return

    resume = await ResumeRepository.get_resume(session, user.telegram_id)
    await call.answer("Генерирую сопроводительное письмо...")

    cand_skills = ", ".join(resume.skills[:7]) if resume and resume.skills else "Python, Java, SQL"
    cand_role = resume.title if resume else "Разработчик"

    provider = get_llm_provider()
    prompt = (
        f"Напиши профессиональное, краткое и убедительное сопроводительное письмо на русском языке "
        f"для отклика на вакансию '{vac.title}' в компанию '{vac.company}'.\n"
        f"Кандидат: {cand_role}, ключевые навыки: {cand_skills}.\n"
        f"Описание позиции: {vac.description[:400] if vac.description else vac.title}."
    )

    letter = None
    if provider.is_available:
        try:
            resume_text = f"Кандидат: {cand_role}. Ключевые навыки: {cand_skills}."
            vac_text = f"Вакансия: {vac.title} в {vac.company}.\n{vac.description[:1000] if vac.description else vac.title}"
            letter = await provider.generate_cover_letter(resume_text, vac_text)
            if not letter:
                letter = await provider.complete(prompt, max_tokens=350)
        except Exception as e:
            logger.warning(f"Error generating AI cover letter: {e}")

    if not letter:
        letter = (
            f"Здравствуйте!\n\n"
            f"Меня заинтересовала вакансия {vac.title} в {vac.company}. "
            f"Имею практический опыт по профилю ({cand_skills}), быстро погружаюсь в задачи проекта "
            f"и готов внести вклад в разработку ваших сервисов.\n\n"
            f"Буду рад обсудить подробности на интервью!\nС уважением."
        )

    response_text = (
        f"✍️ <b>AI Сопроводительное письмо для {html.escape(vac.company)}:</b>\n\n"
        f"<code>{html.escape(letter)}</code>\n\n"
        f"<i>Скопируйте текст в отклик на сайте!</i>"
    )

    await call.message.answer(
        response_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📌 Добавить в трекер", callback_data=f"track_vac:{vac.id}"),
            InlineKeyboardButton(text="🔍 Gap-анализ", callback_data=f"ai_gap:{vac.id}")
        ]])
    )


@router.callback_query(F.data.startswith("ai_gap:"))
async def on_ai_gap_analysis(call: CallbackQuery, session: AsyncSession, user: Optional[User] = None) -> None:
    if user is None:
        user = await UserRepository.get_or_create_user(
            session=session,
            telegram_id=call.from_user.id,
            username=call.from_user.username,
            first_name=call.from_user.first_name
        )

    # Check entitlement or admin bypass
    is_admin = user and (user.telegram_id in settings.ADMIN_IDS)
    has_ent = await SubscriptionRepository.has_entitlement(session, user.telegram_id, "ai_gap_analysis")
    has_sub = await SubscriptionRepository.has_active_subscription(session, user.telegram_id)

    if not (is_admin or has_ent or has_sub):
        await call.answer("Доступно только в подписке PRO!", show_alert=True)
        await call.message.answer(
            "⭐ <b>AI Gap-анализ доступен в подписке PRO</b>\n\n"
            "Узнайте, каких точных навыков и знаний не хватает вашему резюме, чтобы гарантированно пройти скрининг на эту позицию.\n\n"
            "Оформите подписку через /premium!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⭐ Оформить PRO (150 Stars)", callback_data="buy_sub:pro")
            ]])
        )
        return

    vac_id = call.data.split(":", 1)[1]
    stmt = select(Vacancy).where(Vacancy.id == vac_id)
    res = await session.execute(stmt)
    vac = res.scalar_one_or_none()

    if not vac:
        await call.answer("Вакансия не найдена.", show_alert=True)
        return

    resume = await ResumeRepository.get_resume(session, user.telegram_id)
    await call.answer("Выполняю Gap-анализ требований...")

    user_skills = set(resume.skills) if resume and resume.skills else set()
    req_skills = set(vac.skills or vac.requirements or [])
    missing = list(req_skills - user_skills)

    provider = get_llm_provider()
    cand_skills = ", ".join(resume.skills[:10]) if resume and resume.skills else "Не указаны"
    cand_role = resume.title if resume else "Разработчик"

    ai_explanation = None
    if provider.is_available:
        try:
            cand_info = f"Позиция: {cand_role}. Ключевые навыки: {cand_skills}."
            vac_info = f"Вакансия: {vac.title} в {vac.company}.\nТребования: {vac.description[:1000] if vac.description else vac.title}"
            ai_explanation = await provider.explain_match(cand_info, vac_info)
        except Exception as e:
            logger.warning(f"Error calling explain_match in gap analysis: {e}")

    if ai_explanation:
        report = (
            f"🔍 <b>AI Gap-анализ для «{html.escape(vac.title)}»:</b>\n\n"
            f"{html.escape(ai_explanation)}\n\n"
            f"<i>Готовьтесь к техническому интервью сфокусированно!</i>"
        )
    else:
        analysis_points = []
        if missing:
            analysis_points.append(f"• <b>Недостающие требования стека:</b> {', '.join(missing[:5])}")
        else:
            analysis_points.append("• <b>Стек полностью соответствует</b> заявленным требованиям!")

        if vac.required_experience:
            analysis_points.append(f"• <b>Требуемый опыт:</b> {vac.required_experience}")

        analysis_points.append("• <b>Рекомендация:</b> Сделайте акцент в резюме на релевантных кейсах и архитектурных решениях.")

        report = (
            f"🔍 <b>AI Gap-анализ для «{html.escape(vac.title)}»:</b>\n\n"
            + "\n".join(analysis_points) +
            "\n\n<i>Готовьтесь к техническому интервью сфокусированно!</i>"
        )

    await call.message.answer(
        report,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✍️ Сопроводительное письмо", callback_data=f"ai_letter:{vac.id}"),
            InlineKeyboardButton(text="📌 Добавить в трекер", callback_data=f"track_vac:{vac.id}")
        ]])
    )

