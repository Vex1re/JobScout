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

    name = html.escape(message.from_user.first_name or "Соискатель")

    if not resume:
        welcome_text = (
            f"👋 <b>Привет, {name}!</b>\n\n"
            f"Я — <b>JobScout Bot</b>, умный карьерный ассистент для поиска вакансий и фриланс-заказов "
            f"для любых профессий (IT, маркетинг, дизайн, продажи, финансы, менеджмент и др.).\n\n"
            f"🔥 <b>Что я умею:</b>\n"
            f"• Агрегировать предложения с <b>9 площадок</b> (HeadHunter, Работа.ру, SuperJob, Kwork, FL.ru, Хабр и др.)\n"
            f"• Автоматически анализировать ваше резюме (PDF, DOCX или текст)\n"
            f"• Оценивать процент совпадения по вашим ключевым навыкам и опыту\n"
            f"• 🛡️ <b>Отсеивать мошенников и вакансии с ред-флагами</b> (залоги, серая зп, сомнительные схемы)\n"
            f"• Присылать свежие подходящие вакансии в фоновом режиме\n\n"
            f"🔒 <i>Используя бота, вы соглашаетесь с обработкой данных для подбора вакансий. "
            f"Вы можете удалить все свои данные в любой момент командой /delete_me.</i>\n\n"
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
            f"Навыки: <code>{', '.join(resume.skills[:6])}...</code>\n\n"
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
        "• /settings — Настройки поиска (город, удаленка, мин. зп, источники, уведомления)\n"
        "• /delete_me — Полное удаление профиля и данных (152-ФЗ / GDPR)\n\n"
        "🛡️ <b>Система защиты от Red-Flags:</b>\n"
        "Бот автоматически фильтрует вакансии с признаками финансовых пирамид, "
        "требованием оплаты залога, неоплачиваемых стажировок и подозрительных условий.\n\n"
        "💡 <b>Поддерживаемые форматы резюме:</b>\n"
        "PDF, DOCX, TXT или обычный текст сообщением."
    )
    await message.answer(help_text, reply_markup=get_main_menu_keyboard())
