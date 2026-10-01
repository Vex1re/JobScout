import html
from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.repository import InteractionRepository
from bot.formatters.card import format_salary, format_source_badge
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router(name="favorites")


@router.message(Command("favorites"))
@router.message(F.text == "⭐ Избранное")
async def show_favorites(message: types.Message, session: AsyncSession):
    favs = await InteractionRepository.get_favorites(session=session, user_id=message.from_user.id)

    if not favs:
        await message.answer(
            "⭐ <b>У вас пока нет сохраненных вакансий.</b>\n\n"
            "При просмотре вакансий нажимайте кнопку <b>«☆ В избранное»</b>, "
            "чтобы сохранить их сюда для быстрого отклика."
        )
        return

    text = f"⭐ <b>Ваши сохраненные вакансии ({len(favs)}):</b>\n\n"
    buttons = []

    for idx, vac in enumerate(favs[:10], start=1):
        salary_text = format_salary(vac.salary_min, vac.salary_max, vac.currency)
        source = format_source_badge(vac.source)
        text += (
            f"<b>{idx}.</b> <a href=\"{vac.url}\">{html.escape(vac.title)}</a>\n"
            f"🏢 {html.escape(vac.company)} | {source}\n"
            f"💰 <code>{salary_text}</code>\n\n"
        )
        buttons.append([
            InlineKeyboardButton(text=f"🔗 #{idx} Открыть {vac.title[:25]}...", url=vac.url),
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"fav_del_list:{vac.id}")
        ])

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("fav_del_list:"))
async def remove_fav_from_list(callback: types.CallbackQuery, session: AsyncSession):
    vac_id = callback.data.split(":")[1]
    await InteractionRepository.toggle_favorite(session=session, user_id=callback.from_user.id, vacancy_id=vac_id)
    await callback.answer("Удалено из избранного.")
    await show_favorites(callback.message, session)
