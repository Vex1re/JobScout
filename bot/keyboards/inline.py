from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.database.models import User


def get_onboarding_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📄 Загрузить резюме (PDF / DOCX)",
                    callback_data="upload_resume_file"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Отправить текстом в чат",
                    callback_data="upload_resume_text"
                )
            ]
        ]
    )


def get_resume_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Все верно, сохранить!",
                    callback_data="resume_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить стек навыков",
                    callback_data="resume_edit_skills"
                ),
                InlineKeyboardButton(
                    text="💼 Изменить грейд",
                    callback_data="resume_edit_grade"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Загрузить другое резюме",
                    callback_data="upload_resume_file"
                )
            ]
        ]
    )


def get_grade_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Junior (0-1.5 года)", callback_data="set_grade_Junior"),
                InlineKeyboardButton(text="Middle (1.5-4 года)", callback_data="set_grade_Middle")
            ],
            [
                InlineKeyboardButton(text="Senior (4-7 лет)", callback_data="set_grade_Senior"),
                InlineKeyboardButton(text="Lead / Руководитель (6+ лет)", callback_data="set_grade_Lead")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_resume_confirm")
            ]
        ]
    )


def get_profile_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Заменить резюме", callback_data="upload_resume_file"),
                InlineKeyboardButton(text="✏️ Редактировать стек", callback_data="resume_edit_skills")
            ],
            [
                InlineKeyboardButton(text="🔍 Найти вакансии под резюме", callback_data="action_search_now")
            ]
        ]
    )


def get_vacancy_card_keyboard(
    vacancy_id: str,
    url: str,
    is_favorite: bool,
    current_index: int,
    total_count: int,
    has_ai_tip: bool = True
) -> InlineKeyboardMarkup:
    buttons = []

    # Row 1: Direct link
    buttons.append([
        InlineKeyboardButton(text="🔗 Открыть вакансию", url=url)
    ])

    # Row 2: Favorite & Hide actions
    fav_text = "⭐ В избранном" if is_favorite else "☆ В избранное"
    fav_callback = f"fav_remove:{vacancy_id}:{current_index}" if is_favorite else f"fav_add:{vacancy_id}:{current_index}"
    
    buttons.append([
        InlineKeyboardButton(text=fav_text, callback_data=fav_callback),
        InlineKeyboardButton(text="🚫 Скрыть", callback_data=f"vac_hide:{vacancy_id}:{current_index}")
    ])

    # Row 3: AI Advice button
    if has_ai_tip:
        buttons.append([
            InlineKeyboardButton(text="💡 Совет для отклика", callback_data=f"ai_tip:{vacancy_id}")
        ])

    # Row 4: Navigation (if multiple items)
    if total_count > 1:
        nav_row = []
        if current_index > 0:
            nav_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"vac_page:{current_index - 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noop"))

        nav_row.append(InlineKeyboardButton(text=f"📄 {current_index + 1} / {total_count}", callback_data="noop"))

        if current_index < total_count - 1:
            nav_row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"vac_page:{current_index + 1}"))
        else:
            nav_row.append(InlineKeyboardButton(text="⏹️", callback_data="noop"))

        buttons.append(nav_row)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    remote_status = "Да ✅" if user.remote_only else "Нет ❌"
    freelance_status = "Вкл ✅" if user.include_freelance else "Выкл ❌"
    notify_status = "Вкл 🔔" if user.auto_notify else "Выкл 🔕"
    salary_text = f"{user.min_salary:,} ₽".replace(",", " ") if user.min_salary > 0 else "Не задана (Любая)"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"💰 Мин. зарплата: {salary_text}",
                    callback_data="set_min_salary"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🏠 Только удаленка: {remote_status}",
                    callback_data="toggle_remote"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"💼 Заказы Kwork: {freelance_status}",
                    callback_data="toggle_freelance"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🔔 Автопоиск вакансий: {notify_status}",
                    callback_data="toggle_notify"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Искать с этими фильтрами",
                    callback_data="action_search_now"
                )
            ]
        ]
    )
