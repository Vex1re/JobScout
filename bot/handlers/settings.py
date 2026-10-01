import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.repository import UserRepository
from bot.keyboards.inline import get_settings_keyboard
from bot.keyboards.reply import get_cancel_keyboard, get_main_menu_keyboard
from bot.states.profile import ProfileStates

router = Router(name="settings")


@router.message(Command("settings"))
@router.message(F.text == "⚙️ Настройки и фильтры")
async def show_settings(message: types.Message, session: AsyncSession):
    user = await UserRepository.get_or_create_user(session=session, telegram_id=message.from_user.id)
    text = (
        "⚙️ <b>Настройки поиска и фильтрации вакансий</b>\n\n"
        "Здесь вы можете настроить параметры подбора:\n"
        "• <b>Мин. зарплата</b> — отсеивать вакансии ниже этой планки\n"
        "• <b>Удаленка</b> — показывать только предложения с удаленным форматом\n"
        "• <b>Kwork</b> — включать ли freelance заказы с биржи\n"
        "• <b>Автопоиск</b> — периодический фоновый поиск с пуш-уведомлениями"
    )
    await message.answer(text, reply_markup=get_settings_keyboard(user))


@router.callback_query(F.data == "toggle_remote")
async def toggle_remote(callback: types.CallbackQuery, session: AsyncSession):
    user = await UserRepository.get_or_create_user(session=session, telegram_id=callback.from_user.id)
    new_val = not user.remote_only
    user = await UserRepository.update_preferences(session=session, telegram_id=user.telegram_id, remote_only=new_val)
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user))
    status = "включен (только удаленка)" if new_val else "выключен (все форматы)"
    await callback.answer(f"Фильтр удаленки: {status}")


@router.callback_query(F.data == "toggle_freelance")
async def toggle_freelance(callback: types.CallbackQuery, session: AsyncSession):
    user = await UserRepository.get_or_create_user(session=session, telegram_id=callback.from_user.id)
    new_val = not user.include_freelance
    user = await UserRepository.update_preferences(session=session, telegram_id=user.telegram_id, include_freelance=new_val)
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user))
    status = "включены" if new_val else "отключены"
    await callback.answer(f"Заказы Kwork: {status}")


@router.callback_query(F.data == "toggle_notify")
async def toggle_notify(callback: types.CallbackQuery, session: AsyncSession):
    user = await UserRepository.get_or_create_user(session=session, telegram_id=callback.from_user.id)
    new_val = not user.auto_notify
    user = await UserRepository.update_preferences(session=session, telegram_id=user.telegram_id, auto_notify=new_val)
    await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(user))
    status = "включен 🔔" if new_val else "выключен 🔕"
    await callback.answer(f"Автопоиск вакансий: {status}")


@router.callback_query(F.data == "set_min_salary")
async def prompt_min_salary(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.waiting_min_salary)
    await callback.message.answer(
        "💰 <b>Введите минимальную желаемую зарплату в рублях:</b>\n"
        "Например: <code>150000</code> или <code>0</code> чтобы снять ограничение.",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()


@router.message(ProfileStates.waiting_min_salary, F.text)
async def process_min_salary(message: types.Message, state: FSMContext, session: AsyncSession):
    clean = re.sub(r"\D", "", message.text)
    if not clean:
        await message.answer("⚠️ Введите числовое значение (например, 150000).")
        return

    val = int(clean)
    await UserRepository.update_preferences(session=session, telegram_id=message.from_user.id, min_salary=val)
    await state.clear()

    user = await UserRepository.get_or_create_user(session=session, telegram_id=message.from_user.id)
    salary_str = f"{val:,} ₽".replace(",", " ") if val > 0 else "Снято (Любая ЗП)"

    await message.answer(
        f"✅ <b>Минимальная планка зарплаты установлена: {salary_str}</b>",
        reply_markup=get_main_menu_keyboard()
    )
    await message.answer("⚙️ Текущие настройки:", reply_markup=get_settings_keyboard(user))
