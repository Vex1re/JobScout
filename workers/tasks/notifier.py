import html
import logging
from typing import List, Tuple, Dict, Any, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.database.models import Vacancy, User
from bot.formatters.card import format_salary

logger = logging.getLogger(__name__)


def format_digest_message(
    matches: List[Tuple[Vacancy, Dict[str, Any]]],
    max_items: int = 5
) -> str:
    """
    Consolidates multiple newly found vacancies into a single structured digest message.
    Significantly reduces message traffic and avoids chat flooding.
    """
    total = len(matches)
    displayed = matches[:max_items]

    lines = [
        f"🔥 <b>Дайджест новых вакансий (найдено: {total})</b>\n"
        "Мы подобрали наиболее релевантные предложения по вашему стеку:\n"
    ]

    for idx, (vac, info) in enumerate(displayed, start=1):
        safe_title = html.escape(vac.title or "Вакансия")
        safe_company = html.escape(vac.company or "Компания не указана")
        safe_city = html.escape(vac.city or ("Удаленно" if vac.is_remote else "Не указан"))
        score = info.get("score", 0)

        salary_str = format_salary(vac.salary_min, vac.salary_max, vac.currency)

        skills = info.get("matched_skills", [])
        skills_str = ", ".join(skills[:4]) if skills else "По описанию"

        item_text = (
            f"<b>{idx}. <a href=\"{vac.url}\">{safe_title}</a></b>\n"
            f"🏢 {safe_company} | 📍 {safe_city}\n"
            f"💰 {salary_str} | 🎯 Совпадение: <b>{score}%</b>\n"
            f"⚡ Стек: {skills_str}\n"
        )
        lines.append(item_text)

    if total > max_items:
        lines.append(f"<i>...и еще {total - max_items} подходящих предложений в базе бота.</i>\n")

    lines.append("Используйте команду /search для перехода в режим подробного просмотра.")
    return "\n".join(lines)


def get_digest_keyboard(matches: List[Tuple[Vacancy, Dict[str, Any]]]) -> InlineKeyboardMarkup:
    """Creates keyboard with direct vacancy links and search shortcut."""
    buttons = []
    # Up to 3 direct links as quick buttons
    for idx, (vac, _) in enumerate(matches[:3], start=1):
        short_title = (vac.title[:20] + "..") if len(vac.title) > 20 else vac.title
        buttons.append([
            InlineKeyboardButton(text=f"🔗 #{idx} {short_title}", url=vac.url)
        ])

    buttons.append([
        InlineKeyboardButton(text="🔍 Найти вакансии в боте", callback_data="action_search_now")
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)
