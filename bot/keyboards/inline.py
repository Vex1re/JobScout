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

    # Row 3: Tracker & AI Tools
    buttons.append([
        InlineKeyboardButton(text="📌 В трекер", callback_data=f"track_vac:{vacancy_id}"),
        InlineKeyboardButton(text="✍️ AI письмо", callback_data=f"ai_letter:{vacancy_id}"),
        InlineKeyboardButton(text="🔍 Gap", callback_data=f"ai_gap:{vacancy_id}")
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

    # Row 5: Dynamic feed refresh
    buttons.append([
        InlineKeyboardButton(text="🔄 Обновить подборку (новые вакансии)", callback_data="vac_refresh_feed")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_empty_feed_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Обновить подборку (новые вакансии)", callback_data="vac_refresh_feed")
            ],
            [
                InlineKeyboardButton(text="🔄 Сбросить историю просмотров", callback_data="vac_reset_history")
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки и фильтры", callback_data="back_to_settings")
            ]
        ]
    )


def get_city_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Москва", callback_data="quick_city:Москва"),
                InlineKeyboardButton(text="Санкт-Петербург", callback_data="quick_city:Санкт-Петербург")
            ],
            [
                InlineKeyboardButton(text="Казань", callback_data="quick_city:Казань"),
                InlineKeyboardButton(text="Екатеринбург", callback_data="quick_city:Екатеринбург")
            ],
            [
                InlineKeyboardButton(text="🌐 Любой город", callback_data="quick_city:any"),
                InlineKeyboardButton(text="✍️ Ввести вручную", callback_data="enter_city_manual")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="back_to_settings")
            ]
        ]
    )


def get_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    remote_status = "Да ✅" if user.remote_only else "Нет ❌"
    freelance_status = "Вкл ✅" if user.include_freelance else "Выкл ❌"
    notify_status = "Вкл 🔔" if user.auto_notify else "Выкл 🔕"
    salary_val = user.min_salary or 0
    salary_text = f"{salary_val:,} ₽".replace(",", " ") if salary_val > 0 else "Не задана (Любая)"
    city_text = user.city if user.city else "Любой"
    sources_count = len(user.get_effective_sources())

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📍 Город: {city_text}",
                    callback_data="set_city"
                )
            ],
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
                    text=f"💼 Фриланс-биржи: {freelance_status}",
                    callback_data="toggle_freelance"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🌐 Сайты и биржи: {sources_count} из 9 ⚙️",
                    callback_data="settings_sources"
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
            ],
            [
                InlineKeyboardButton(
                    text="🗑️ Удалить мои данные",
                    callback_data="request_delete_account"
                )
            ]
        ]
    )


def get_sources_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    from services.parser.manager import ALL_SOURCES, SOURCE_LABELS
    effective_sources = set(user.get_effective_sources())

    buttons = []
    # Source rows
    for src in ALL_SOURCES:
        label = SOURCE_LABELS.get(src, src)
        status = "✅" if src in effective_sources else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {label}",
                callback_data=f"toggle_src_{src}"
            )
        ])

    # Presets row
    buttons.append([
        InlineKeyboardButton(text="⚡ Включить все", callback_data="src_preset_all"),
    ])
    buttons.append([
        InlineKeyboardButton(text="💼 Только вакансии", callback_data="src_preset_vacancies"),
        InlineKeyboardButton(text="💻 Только фриланс", callback_data="src_preset_freelance"),
    ])

    # Back button
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад в настройки", callback_data="back_to_settings")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

