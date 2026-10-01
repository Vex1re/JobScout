import html
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.repository import UserRepository, ResumeRepository
from bot.keyboards.reply import get_main_menu_keyboard
from bot.keyboards.inline import get_onboarding_keyboard
from bot.states.profile import ProfileStates

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext, session: AsyncSession):
    """Entry point for /start command."""
    user = await UserRepository.get_or_create_user(
        session=session,
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name
    )

    resume = await ResumeRepository.get_resume(session=session, user_id=user.telegram_id)

    name = html.escape(message.from_user.first_name or "Разработчик")

    if not resume:
        welcome_text = (
            f"👋 <b>Привет, {name}!</b>\n\n"
            f"Я — <b>JobScout Bot</b>, умный карьерный ассистент для поиска вакансий и заказов в IT.\n\n"
            f"🔥 <b>Что я умею:</b>\n"
            f"• Парсить вакансии с <b>HeadHunter (hh.ru)</b>, <b>Хабр Карьеры</b>, <b>Работа.ру</b> и заказы с <b>Kwork</b>\n"
            f"• Автоматически анализировать ваше резюме (PDF, DOCX или текст)\n"
            f"• Оценивать процент совпадения по стеку технологий и грейду\n"
            f"• 🛡️ <b>Отсеивать мошенников и вакансии с ред-флагами</b> (залоги, серая зп, сомнительные схемы)\n"
            f"• Присылать свежие подходящие вакансии в фоновом режиме\n\n"
            f"🚀 <b>Для начала создайте профиль:</b> отправьте мне ваше резюме!"
        )
        await message.answer(
            welcome_text,
            reply_markup=get_onboarding_keyboard()
        )
    else:
        welcome_back_text = (
            f"👋 <b>С возвращением, {name}!</b>\n\n"
            f"Ваш профиль активен: <b>{html.escape(resume.title)} ({resume.grade})</b>.\n"
            f"Стек: <code>{', '.join(resume.skills[:6])}...</code>\n\n"
            f"Нажмите <b>«🔍 Найти вакансии»</b> для свежей подборки или перейдите в меню."
        )
        await message.answer(
            welcome_back_text,
            reply_markup=get_main_menu_keyboard()
        )


@router.message(Command("help"))
@router.message(F.text == "❓ Помощь / О боте")
async def handle_help(message: types.Message):
    help_text = (
        "📖 <b>Справка по использованию JobScout Bot</b>\n\n"
        "<b>Команды бота:</b>\n"
        "• /start — Главное меню и перезапуск\n"
        "• /search — Поиск вакансий по вашему резюме\n"
        "• /profile — Просмотр и редактирование резюме\n"
        "• /favorites — Список сохраненных вакансий\n"
        "• /settings — Настройки поиска (удаленка, мин. зп, Kwork, уведомления)\n\n"
        "🛡️ <b>Система защиты от Red-Flags:</b>\n"
        "Бот автоматически фильтрует вакансии с признаками финансовых пирамид, "
        "требованием оплаты залога, неоплачиваемых стажировок и подозрительных условий.\n\n"
        "💡 <b>Поддерживаемые форматы резюме:</b>\n"
        "PDF, DOCX, TXT или обычный текст сообщением."
    )
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())
