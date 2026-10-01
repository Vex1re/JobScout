from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Main persistent bottom keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Найти вакансии"),
                KeyboardButton(text="👤 Мой профиль и резюме")
            ],
            [
                KeyboardButton(text="⭐ Избранное"),
                KeyboardButton(text="⚙️ Настройки и фильтры")
            ],
            [
                KeyboardButton(text="❓ Помощь / О боте")
            ]
        ],
        resize_keyboard=True
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancel operation keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )
